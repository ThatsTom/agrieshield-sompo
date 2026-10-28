# =============================================================================
# AgriShield — Serviços externos e fallbacks
#
# - geocoding_por_cep(): consulta o ViaCEP e complementa coordenadas conhecidas.
# - geocoding_por_endereco(): sugere coordenadas a partir do endereço completo.
# - previsao_open_meteo(): consulta previsão pública Open-Meteo e gera alertas.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Dict, List
import sys
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "etl"))
from etapa1_cadastro_fazendas import resolver_cep_base_estatica, normalizar_cep


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI_CEP_V2_URL = "https://brasilapi.com.br/api/cep/v2/{cep}"
NOMINATIM_SEARCH_URL = os.getenv(
    "AGRISHIELD_GEOCODING_URL", "https://nominatim.openstreetmap.org/search"
).strip()
NOMINATIM_USER_AGENT = os.getenv(
    "AGRISHIELD_GEOCODING_USER_AGENT",
    "AgriShield/1.0",
).strip()
NOMINATIM_CACHE_TTL_SEGUNDOS = 24 * 60 * 60
OPEN_METEO_SCHEMA_VERSION = "1"
OPEN_METEO_FORECAST_DAYS = 5
OPEN_METEO_INSIGHTS_FORECAST_DAYS = 7
OPEN_METEO_TIMEZONE = "America/Cuiaba"
OPEN_METEO_DAILY = "precipitation_sum,precipitation_probability_max,temperature_2m_max"
OPEN_METEO_UNIDADES = {
    "time": "iso8601",
    "precipitation_sum": "mm",
    "precipitation_probability_max": "%",
    "temperature_2m_max": "°C",
}


class ErroContratoOpenMeteo(ValueError):
    """Resposta recebida, mas incompatível com o contrato solicitado."""


class CepInvalido(ValueError):
    """O CEP informado não possui exatamente oito dígitos."""


class CepNaoEncontrado(LookupError):
    """O ViaCEP respondeu corretamente, mas não conhece o CEP."""


class ErroConsultaCep(RuntimeError):
    """O serviço de CEP não pôde ser consultado e não há fallback local."""


class ErroConsultaEndereco(RuntimeError):
    """O provedor de geocodificação de endereço não pôde ser consultado."""


_CACHE_GEOCODIFICACAO: dict[
    tuple[str, str, str, str, str, str], tuple[float, Dict[str, Any]]
] = {}
_LOCK_GEOCODIFICACAO = threading.Lock()
_ULTIMA_CONSULTA_GEOCODIFICACAO = 0.0

_NOMES_UF = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins",
}


def _agora_utc(relogio: Callable[[], datetime] | None = None) -> datetime:
    instante = (relogio or (lambda: datetime.now(timezone.utc)))()
    if instante.tzinfo is None:
        raise ValueError("O relógio Open-Meteo deve retornar datetime com timezone")
    return instante.astimezone(timezone.utc)


def _sanitizar_erro(exc: Exception) -> Dict[str, str]:
    texto = " ".join(str(exc).split())
    texto = re.sub(
        r"(?i)\bauthorization\b\s*[:=]\s*(?:bearer\s+)?\S+",
        "authorization=[redacted]",
        texto,
    )
    texto = re.sub(
        r"(?i)\b(token|authorization|credential|api[_ -]?key)\b(\s*[:=]\s*)\S+",
        r"\1\2[redacted]",
        texto,
    )[:300]
    if isinstance(exc, requests.Timeout | requests.ConnectionError):
        categoria = "transporte"
    elif isinstance(exc, requests.HTTPError):
        categoria = "http"
    elif isinstance(exc, ErroContratoOpenMeteo):
        categoria = "contrato_invalido"
    elif isinstance(exc, (ValueError, TypeError)):
        categoria = "parsing"
    else:
        categoria = "falha_inesperada"
    return {
        "categoria": categoria,
        "tipo": type(exc).__name__,
        "detalhe": texto or type(exc).__name__,
    }


def _numero_opcional(
    valor: Any, campo: str, *, inteiro: bool = False
) -> float | int | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ErroContratoOpenMeteo(f"{campo} deve ser numérico ou nulo")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ErroContratoOpenMeteo(f"{campo} deve ser numérico ou nulo") from exc
    if not math.isfinite(numero):
        raise ErroContratoOpenMeteo(f"{campo} deve ser finito ou nulo")
    if inteiro:
        if not numero.is_integer():
            raise ErroContratoOpenMeteo(f"{campo} deve ser inteiro ou nulo")
        return int(numero)
    return numero


def _numero_metadata(valor: Any, campo: str) -> float | None:
    if valor is None:
        return None
    numero = _numero_opcional(valor, campo)
    return float(numero) if numero is not None else None


def _validar_e_materializar_dias(
    payload: Mapping[str, Any],
    *,
    dias_esperados: int,
) -> tuple[List[Dict[str, Any]], Dict[str, str], List[str]]:
    daily = payload.get("daily")
    if not isinstance(daily, Mapping):
        raise ErroContratoOpenMeteo("daily ausente ou inválido")

    campos = {
        "time": daily.get("time"),
        "precipitation_sum": daily.get("precipitation_sum"),
        "precipitation_probability_max": daily.get("precipitation_probability_max"),
        "temperature_2m_max": daily.get("temperature_2m_max"),
    }
    for nome, valores in campos.items():
        if not isinstance(valores, list):
            raise ErroContratoOpenMeteo(f"daily.{nome} ausente ou inválido")
        if len(valores) != dias_esperados:
            raise ErroContratoOpenMeteo(
                f"daily.{nome} deve conter {dias_esperados} valores"
            )

    unidades_brutas = payload.get("daily_units")
    if unidades_brutas is None:
        unidades: Dict[str, str] = {}
        flags = ["UNIDADES_AUSENTES"]
    elif not isinstance(unidades_brutas, Mapping):
        raise ErroContratoOpenMeteo("daily_units inválido")
    else:
        unidades = {
            str(chave): str(valor)
            for chave, valor in unidades_brutas.items()
            if valor is not None
        }
        flags = []
        for campo, esperada in OPEN_METEO_UNIDADES.items():
            recebida = unidades.get(campo)
            if recebida is not None and recebida != esperada:
                raise ErroContratoOpenMeteo(f"unidade incompatível para {campo}")

    # Estrutura, unidades e valores são validados antes de criar qualquer dia.
    datas: List[str] = []
    valores: Dict[str, List[float | int | None]] = {
        "precipitation_sum": [],
        "precipitation_probability_max": [],
        "temperature_2m_max": [],
    }
    for indice in range(dias_esperados):
        data_bruta = campos["time"][indice]
        if not isinstance(data_bruta, str):
            raise ErroContratoOpenMeteo("daily.time deve conter datas ISO")
        try:
            date.fromisoformat(data_bruta)
        except ValueError as exc:
            raise ErroContratoOpenMeteo("daily.time deve conter datas ISO") from exc
        datas.append(data_bruta)
        valores["precipitation_sum"].append(
            _numero_opcional(campos["precipitation_sum"][indice], "precipitation_sum")
        )
        valores["precipitation_probability_max"].append(
            _numero_opcional(
                campos["precipitation_probability_max"][indice],
                "precipitation_probability_max",
                inteiro=True,
            )
        )
        valores["temperature_2m_max"].append(
            _numero_opcional(campos["temperature_2m_max"][indice], "temperature_2m_max")
        )

    dias = [
        {
            "data_local": datas[indice],
            "precipitacao_mm": valores["precipitation_sum"][indice],
            "prob_precip_pct": valores["precipitation_probability_max"][indice],
            "temp_max_c": valores["temperature_2m_max"][indice],
        }
        for indice in range(dias_esperados)
    ]
    return dias, unidades, flags


def _resultado_sintetico(
    *,
    latitude: float,
    longitude: float,
    dias_esperados: int,
    timezone_solicitado: str,
    coletado_em_utc: datetime,
    erro: Dict[str, str],
) -> Dict[str, Any]:
    try:
        fuso = ZoneInfo(timezone_solicitado)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone Open-Meteo inválido") from exc
    data_base = coletado_em_utc.astimezone(fuso).date()
    chuva = [4.0, 18.5, 34.0, 22.0, 6.0, 1.5, 9.0]
    prob = [35, 68, 86, 74, 40, 20, 55]
    dias = [
        {
            "data_local": (data_base + timedelta(days=i)).isoformat(),
            "precipitacao_mm": chuva[i],
            "prob_precip_pct": prob[i],
            "temp_max_c": 33.0 - i * 0.4,
        }
        for i in range(dias_esperados)
    ]
    return {
        "schema_version": OPEN_METEO_SCHEMA_VERSION,
        "fonte": "SIMULADOR_INTERNO",
        "natureza": "PREVISTO",
        "simulado": True,
        "coletado_em_utc": coletado_em_utc.isoformat(),
        "requisicao": {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "forecast_days": dias_esperados,
            "timezone_solicitado": timezone_solicitado,
        },
        "resposta": {
            "latitude_grade": None,
            "longitude_grade": None,
            "elevacao_m": None,
            "timezone": timezone_solicitado,
            "timezone_abbreviation": None,
            "utc_offset_seconds": None,
            "generationtime_ms": None,
            "unidades": dict(OPEN_METEO_UNIDADES),
        },
        "dias": dias,
        "qualidade": {
            "status": "PARCIAL",
            "dias_esperados": dias_esperados,
            "dias_recebidos": dias_esperados,
            "variaveis_ausentes": [],
            "flags": ["DADO_SINTETICO", "FONTE_PRIMARIA_INDISPONIVEL"],
        },
        "erro_origem": erro,
    }


def consultar_open_meteo(
    lat: float,
    lon: float,
    *,
    relogio: Callable[[], datetime] | None = None,
    http_get: Callable[..., Any] | None = None,
    timezone_solicitado: str = OPEN_METEO_TIMEZONE,
    forecast_days: int = OPEN_METEO_FORECAST_DAYS,
) -> Dict[str, Any]:
    """Consulta uma vez e retorna o contrato rico real ou integralmente sintético."""
    if forecast_days not in (
        OPEN_METEO_FORECAST_DAYS,
        OPEN_METEO_INSIGHTS_FORECAST_DAYS,
    ):
        raise ValueError("A previsão Open-Meteo deve solicitar 5 ou 7 dias")
    getter = http_get or requests.get
    coletado_em: datetime | None = None
    try:
        resposta_http = getter(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": OPEN_METEO_DAILY,
                "forecast_days": forecast_days,
                "timezone": timezone_solicitado,
            },
            timeout=(5, 20),
        )
        resposta_http.raise_for_status()
        try:
            payload = resposta_http.json()
        except Exception as exc:
            raise ValueError("resposta Open-Meteo não contém JSON válido") from exc
        coletado_em = _agora_utc(relogio)
        if not isinstance(payload, Mapping):
            raise ErroContratoOpenMeteo("resposta Open-Meteo deve ser um objeto")
        dias, unidades, flags = _validar_e_materializar_dias(
            payload, dias_esperados=forecast_days
        )
        ausentes = sorted(
            {
                campo
                for dia in dias
                for campo in ("precipitacao_mm", "prob_precip_pct", "temp_max_c")
                if dia[campo] is None
            }
        )
        if ausentes:
            flags.append("VALORES_AUSENTES")
        status = "PARCIAL" if flags else "DISPONIVEL"
        return {
            "schema_version": OPEN_METEO_SCHEMA_VERSION,
            "fonte": "OPEN_METEO",
            "natureza": "PREVISTO",
            "simulado": False,
            "coletado_em_utc": coletado_em.isoformat(),
            "requisicao": {
                "latitude": float(lat),
                "longitude": float(lon),
                "forecast_days": forecast_days,
                "timezone_solicitado": timezone_solicitado,
            },
            "resposta": {
                "latitude_grade": _numero_metadata(payload.get("latitude"), "latitude"),
                "longitude_grade": _numero_metadata(
                    payload.get("longitude"), "longitude"
                ),
                "elevacao_m": _numero_metadata(payload.get("elevation"), "elevation"),
                "timezone": payload.get("timezone"),
                "timezone_abbreviation": payload.get("timezone_abbreviation"),
                "utc_offset_seconds": (
                    int(
                        _numero_opcional(
                            payload.get("utc_offset_seconds"),
                            "utc_offset_seconds",
                            inteiro=True,
                        )
                    )
                    if payload.get("utc_offset_seconds") is not None
                    else None
                ),
                "generationtime_ms": _numero_metadata(
                    payload.get("generationtime_ms"), "generationtime_ms"
                ),
                "unidades": unidades,
            },
            "dias": dias,
            "qualidade": {
                "status": status,
                "dias_esperados": forecast_days,
                "dias_recebidos": len(dias),
                "variaveis_ausentes": ausentes,
                "flags": flags,
            },
            "erro_origem": None,
        }
    except Exception as exc:
        coletado_em = coletado_em or _agora_utc(relogio)
        return _resultado_sintetico(
            latitude=lat,
            longitude=lon,
            dias_esperados=forecast_days,
            timezone_solicitado=timezone_solicitado,
            coletado_em_utc=coletado_em,
            erro=_sanitizar_erro(exc),
        )


def geocoding_por_cep(
    cep: str, *, http_get: Callable[..., Any] = requests.get
) -> Dict[str, Any]:
    """Consulta o ViaCEP e anexa coordenadas apenas quando a base local é exata.

    O ViaCEP fornece endereço, mas não latitude/longitude. Por isso as
    coordenadas continuam opcionais e só são retornadas quando o CEP existe
    exatamente na base geográfica local do projeto.
    """
    cep_limpo = normalizar_cep(cep)
    if len(cep_limpo) != 8:
        raise CepInvalido("CEP deve conter exatamente 8 dígitos")

    try:
        base = resolver_cep_base_estatica(cep_limpo)
    except Exception:
        # A base local é apenas um enriquecimento opcional. Falhas de banco ou
        # arquivo não podem impedir a consulta principal ao ViaCEP.
        base = None
    # O repositório legado também procura por prefixo. Coordenadas aproximadas
    # de outro CEP não devem ser gravadas como se fossem a fazenda do usuário.
    base_exata = base if base and base.get("origem") == "base_estatica" else None

    try:
        resposta = http_get(VIACEP_URL.format(cep=cep_limpo), timeout=(5, 10))
        resposta.raise_for_status()
        payload = resposta.json()
        if not isinstance(payload, Mapping):
            raise ValueError("resposta JSON do ViaCEP não é um objeto")
        if payload.get("erro") is True or str(payload.get("erro", "")).lower() == "true":
            raise CepNaoEncontrado("CEP não encontrado no ViaCEP")

        return {
            "cep": payload.get("cep") or cep_limpo,
            "logradouro": payload.get("logradouro") or "",
            "complemento": payload.get("complemento") or "",
            "bairro": payload.get("bairro") or "",
            "cidade": payload.get("localidade") or "",
            "uf": payload.get("uf") or "",
            "ibge": payload.get("ibge") or "",
            "latitude": float(base_exata["latitude"]) if base_exata else None,
            "longitude": float(base_exata["longitude"]) if base_exata else None,
            "origem": "viacep+base_estatica" if base_exata else "viacep",
        }
    except CepNaoEncontrado:
        raise
    except (requests.RequestException, ValueError, TypeError) as exc:
        if base_exata:
            return {
                "cep": cep_limpo,
                "logradouro": base_exata.get("logradouro", ""),
                "complemento": "",
                "bairro": base_exata.get("bairro", ""),
                "cidade": base_exata.get("cidade", ""),
                "uf": base_exata.get("uf", ""),
                "ibge": "",
                "latitude": float(base_exata["latitude"]),
                "longitude": float(base_exata["longitude"]),
                "origem": "base_estatica_fallback",
            }
        raise ErroConsultaCep("ViaCEP temporariamente indisponível") from exc


def _texto_endereco(valor: Any, limite: int) -> str:
    return " ".join(str(valor or "").strip().split())[:limite]


def _numero_endereco_normalizado(valor: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(valor or "").upper())


def _texto_comparavel(valor: Any) -> str:
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", str(valor or ""))
        if not unicodedata.combining(caractere)
    )
    texto = re.sub(r"[^0-9A-Z]+", " ", sem_acentos.upper()).strip()
    abreviacoes = {
        "AV": "AVENIDA",
        "AV.": "AVENIDA",
        "R": "RUA",
        "R.": "RUA",
        "ROD": "RODOVIA",
        "ROD.": "RODOVIA",
        "ESTR": "ESTRADA",
        "ESTR.": "ESTRADA",
        "PC": "PRACA",
        "PCA": "PRACA",
    }
    partes = texto.split()
    if partes:
        partes[0] = abreviacoes.get(partes[0], partes[0])
    return " ".join(partes)


def _texto_compativel(esperado: Any, recebido: Any) -> bool:
    esperado_normalizado = _texto_comparavel(esperado)
    recebido_normalizado = _texto_comparavel(recebido)
    if not esperado_normalizado or not recebido_normalizado:
        return False
    if esperado_normalizado == recebido_normalizado:
        return True

    esperado_tokens = esperado_normalizado.split()
    recebido_tokens = recebido_normalizado.split()
    menor, maior = (
        (esperado_tokens, recebido_tokens)
        if len(esperado_tokens) <= len(recebido_tokens)
        else (recebido_tokens, esperado_tokens)
    )
    if len(menor) == 1:
        return len(menor[0]) >= 4 and menor[0] in maior
    return any(
        maior[indice : indice + len(menor)] == menor
        for indice in range(len(maior) - len(menor) + 1)
    )


def _avaliar_candidato_nominatim(
    candidato: Mapping[str, Any],
    *,
    cep: str,
    logradouro: str,
    numero: str,
    bairro: str,
    cidade: str,
    uf: str,
    inclui_numero: bool,
) -> tuple[int, bool] | None:
    """Valida o contexto e pontua candidatos sem confundir homônimos."""
    try:
        latitude = float(candidato.get("lat"))
        longitude = float(candidato.get("lon"))
    except (TypeError, ValueError):
        return None
    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    ):
        return None

    endereco = candidato.get("address")
    if not isinstance(endereco, Mapping):
        return None
    if str(endereco.get("country_code") or "").lower() != "br":
        return None

    cep_candidato = normalizar_cep(endereco.get("postcode"))
    cep_confirmado = bool(cep_candidato) and cep_candidato == cep
    cep_divergente = bool(cep_candidato) and not cep_confirmado

    cidades = [
        endereco.get(chave)
        for chave in ("city", "town", "village", "municipality", "county")
        if endereco.get(chave)
    ]
    cidade_compativel = any(_texto_compativel(cidade, item) for item in cidades)
    if cidades and not cidade_compativel:
        return None

    iso_uf = str(
        endereco.get("ISO3166-2-lvl4")
        or endereco.get("ISO3166-2-lvl3")
        or ""
    ).upper()
    estados = [
        endereco.get(chave)
        for chave in ("state", "state_district")
        if endereco.get(chave)
    ]
    if iso_uf:
        uf_compativel = iso_uf == f"BR-{uf}"
    else:
        valores_uf_esperados = {
            _texto_comparavel(uf),
            _texto_comparavel(_NOMES_UF.get(uf, uf)),
        }
        uf_compativel = any(
            _texto_comparavel(item) in valores_uf_esperados for item in estados
        )
    if (iso_uf or estados) and not uf_compativel:
        return None

    # CEPs institucionais, rurais e de grandes logradouros frequentemente
    # divergem do CEP do ponto mapeado no OpenStreetMap. A divergência reduz a
    # confiança, mas não invalida rua + cidade + UF confirmadas.
    if cep_divergente and not (cidade_compativel and uf_compativel):
        return None

    logradouros = [
        endereco.get(chave)
        for chave in (
            "road",
            "pedestrian",
            "residential",
            "footway",
            "path",
            "highway",
            "square",
        )
        if endereco.get(chave)
    ]
    logradouro_compativel = any(
        _texto_compativel(logradouro, item) for item in logradouros
    ) or _texto_compativel(logradouro, candidato.get("display_name"))
    if not logradouro_compativel:
        return None

    # Sem CEP no retorno, cidade e UF precisam confirmar o contexto. Isso evita
    # aceitar uma rua homônima apenas porque o número coincide.
    if not cep_candidato and not (cidade_compativel and uf_compativel):
        return None

    bairros = [
        endereco.get(chave)
        for chave in ("suburb", "neighbourhood", "city_district", "quarter")
        if endereco.get(chave)
    ]
    bairro_compativel = bool(bairro) and any(
        _texto_compativel(bairro, item) for item in bairros
    )
    numero_esperado = _numero_endereco_normalizado(numero)
    numero_confirmado = inclui_numero and bool(numero_esperado) and (
        _numero_endereco_normalizado(endereco.get("house_number")) == numero_esperado
    )
    pontuacao = (
        (100 if numero_confirmado else 0)
        + (30 if cep_confirmado else 0)
        + (15 if cidade_compativel else 0)
        + (15 if uf_compativel else 0)
        + (10 if bairro_compativel else 0)
        - (10 if cep_divergente else 0)
    )
    return pontuacao, numero_confirmado


def _consultar_nominatim(
    parametros: Dict[str, Any], *, http_get: Callable[..., Any]
) -> list[Mapping[str, Any]]:
    global _ULTIMA_CONSULTA_GEOCODIFICACAO

    # O serviço público exige no máximo uma consulta por segundo por aplicação.
    # Chamadas de teste injetam outro cliente e não passam por espera real.
    if http_get is requests.get:
        with _LOCK_GEOCODIFICACAO:
            agora = time.monotonic()
            espera = 1.0 - (agora - _ULTIMA_CONSULTA_GEOCODIFICACAO)
            if espera > 0:
                time.sleep(espera)
            _ULTIMA_CONSULTA_GEOCODIFICACAO = time.monotonic()

    resposta = http_get(
        NOMINATIM_SEARCH_URL,
        params=parametros,
        headers={
            "User-Agent": NOMINATIM_USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
        timeout=(2, 4),
    )
    resposta.raise_for_status()
    payload = resposta.json()
    if not isinstance(payload, list):
        raise ValueError("resposta JSON do geocodificador não é uma lista")
    return [item for item in payload if isinstance(item, Mapping)]


def _consultar_brasilapi_cep(
    cep: str,
    *,
    cidade: str,
    uf: str,
    http_get: Callable[..., Any],
) -> Dict[str, Any] | None:
    """Retorna o centro aproximado do CEP quando a BrasilAPI o disponibiliza."""
    resposta = http_get(
        BRASILAPI_CEP_V2_URL.format(cep=cep),
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=(2, 4),
    )
    resposta.raise_for_status()
    payload = resposta.json()
    if not isinstance(payload, Mapping):
        raise ValueError("resposta JSON da BrasilAPI não é um objeto")

    cep_retornado = normalizar_cep(payload.get("cep"))
    cidade_retornada = _texto_endereco(payload.get("city"), 120)
    uf_retornada = _texto_endereco(payload.get("state"), 2).upper()
    if (
        cep_retornado != cep
        or not cidade_retornada
        or not _texto_compativel(cidade, cidade_retornada)
        or uf_retornada != uf
    ):
        return None

    localizacao = payload.get("location")
    coordenadas = (
        localizacao.get("coordinates")
        if isinstance(localizacao, Mapping)
        else None
    )
    if not isinstance(coordenadas, Mapping):
        return None
    try:
        latitude = float(coordenadas.get("latitude"))
        longitude = float(coordenadas.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (
        math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
        and (latitude != 0 or longitude != 0)
        and -35 <= latitude <= 6
        and -75 <= longitude <= -32
    ):
        return None

    descricao = ", ".join(
        parte
        for parte in (
            _texto_endereco(payload.get("street"), 180),
            _texto_endereco(payload.get("neighborhood"), 120),
            _texto_endereco(payload.get("city"), 120),
            _texto_endereco(payload.get("state"), 2).upper(),
        )
        if parte
    )
    return {
        "latitude": round(latitude, 7),
        "longitude": round(longitude, 7),
        "descricao": descricao,
    }


def geocoding_por_endereco(
    *,
    cep: str,
    logradouro: str,
    numero_km: str,
    bairro: str = "",
    cidade: str,
    uf: str,
    http_get: Callable[..., Any] = requests.get,
) -> Dict[str, Any]:
    """Sugere coordenadas sem apresentá-las como localização exata garantida.

    Primeiro tenta o endereço com número/Km. Se não houver resultado, faz uma
    segunda consulta pelo logradouro. O retorno sempre informa o nível de
    precisão para que a interface peça confirmação no mapa.
    """
    cep_limpo = normalizar_cep(cep)
    if len(cep_limpo) != 8:
        raise CepInvalido("CEP deve conter exatamente 8 dígitos")

    logradouro_limpo = _texto_endereco(logradouro, 180)
    numero_limpo = _texto_endereco(numero_km, 50)
    bairro_limpo = _texto_endereco(bairro, 120)
    cidade_limpa = _texto_endereco(cidade, 120)
    uf_limpa = _texto_endereco(uf, 2).upper()
    if not logradouro_limpo or not numero_limpo or not cidade_limpa or len(uf_limpa) != 2:
        raise ValueError(
            "Preencha CEP, logradouro, Número/Km, cidade e UF antes de localizar."
        )

    chave_cache = (
        cep_limpo,
        logradouro_limpo.casefold(),
        numero_limpo.casefold(),
        bairro_limpo.casefold(),
        cidade_limpa.casefold(),
        uf_limpa,
    )
    if http_get is requests.get:
        with _LOCK_GEOCODIFICACAO:
            cache = _CACHE_GEOCODIFICACAO.get(chave_cache)
            if cache and time.monotonic() - cache[0] < NOMINATIM_CACHE_TTL_SEGUNDOS:
                return dict(cache[1])

    contexto_parametros: Dict[str, Any] = {
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 5,
        "countrycodes": "br",
        "layer": "address",
        "city": cidade_limpa,
        "state": _NOMES_UF.get(uf_limpa, uf_limpa),
        "country": "Brasil",
        "accept-language": "pt-BR",
    }
    parametros_com_cep = {**contexto_parametros, "postalcode": cep_limpo}
    consultas = [
        (
            {**parametros_com_cep, "street": f"{numero_limpo} {logradouro_limpo}"},
            True,
        ),
        (
            {**contexto_parametros, "street": f"{numero_limpo} {logradouro_limpo}"},
            True,
        ),
        ({**contexto_parametros, "street": logradouro_limpo}, False),
    ]
    selecionado: Mapping[str, Any] | None = None
    consulta_com_numero = False
    melhor_pontuacao_global = -1
    melhor_numero_confirmado = False
    erro_nominatim: Exception | None = None
    try:
        for parametros, inclui_numero in consultas:
            resultados = _consultar_nominatim(parametros, http_get=http_get)
            for candidato in resultados:
                avaliacao = _avaliar_candidato_nominatim(
                    candidato,
                    cep=cep_limpo,
                    logradouro=logradouro_limpo,
                    numero=numero_limpo,
                    bairro=bairro_limpo,
                    cidade=cidade_limpa,
                    uf=uf_limpa,
                    inclui_numero=inclui_numero,
                )
                if avaliacao is None:
                    continue
                pontuacao, numero_confirmado_candidato = avaliacao
                if pontuacao > melhor_pontuacao_global:
                    selecionado = candidato
                    consulta_com_numero = inclui_numero
                    melhor_pontuacao_global = pontuacao
                    melhor_numero_confirmado = numero_confirmado_candidato
            if melhor_numero_confirmado:
                break
    except (requests.RequestException, ValueError, TypeError) as exc:
        erro_nominatim = exc

    ponto_cep: Dict[str, Any] | None = None
    erro_brasilapi: Exception | None = None
    if selecionado is None:
        try:
            ponto_cep = _consultar_brasilapi_cep(
                cep_limpo,
                cidade=cidade_limpa,
                uf=uf_limpa,
                http_get=http_get,
            )
        except (requests.RequestException, ValueError, TypeError) as exc:
            erro_brasilapi = exc

    if selecionado is None and ponto_cep is None and erro_nominatim and erro_brasilapi:
        raise ErroConsultaEndereco(
            "Não foi possível consultar a localização automática agora."
        ) from erro_nominatim

    if selecionado is None and ponto_cep is None:
        resultado: Dict[str, Any] = {
            "encontrado": False,
            "latitude": None,
            "longitude": None,
            "origem": "nominatim_openstreetmap+brasilapi_cep_v2",
            "precisao": "indisponivel",
            "descricao": "",
            "motivo": "sem_coordenadas_compativeis",
            "requer_confirmacao": False,
            "aviso": (
                "Não encontramos coordenadas compatíveis com este endereço. "
                "Posicione o pino no mapa ou informe latitude e longitude."
            ),
            "atribuicao": "© OpenStreetMap contributors",
        }
    elif selecionado is None:
        resultado = {
            "encontrado": True,
            "latitude": ponto_cep["latitude"],
            "longitude": ponto_cep["longitude"],
            "origem": "brasilapi_cep_v2",
            "precisao": "cep",
            "descricao": ponto_cep["descricao"],
            "motivo": "centro_aproximado_cep",
            "requer_confirmacao": True,
            "aviso": (
                "Ponto aproximado pelo CEP; confirme a sede ou ajuste o pino no mapa."
            ),
            "atribuicao": "BrasilAPI CEP v2; geolocalização © OpenStreetMap contributors",
        }
    else:
        endereco = selecionado.get("address")
        endereco = endereco if isinstance(endereco, Mapping) else {}
        numero_retornado = _numero_endereco_normalizado(endereco.get("house_number"))
        numero_esperado = _numero_endereco_normalizado(numero_limpo)
        numero_confirmado = bool(numero_esperado) and numero_retornado == numero_esperado
        cep_retornado = normalizar_cep(endereco.get("postcode"))
        cep_divergente = bool(cep_retornado) and cep_retornado != cep_limpo
        precisao = "numero" if consulta_com_numero and numero_confirmado else "logradouro"
        resultado = {
            "encontrado": True,
            "latitude": round(float(selecionado["lat"]), 7),
            "longitude": round(float(selecionado["lon"]), 7),
            "origem": "nominatim_openstreetmap",
            "precisao": precisao,
            "descricao": _texto_endereco(selecionado.get("display_name"), 500),
            "motivo": (
                "numero_confirmado_cep_divergente"
                if precisao == "numero" and cep_divergente
                else "numero_confirmado"
                if precisao == "numero"
                else "logradouro_aproximado_cep_divergente"
                if cep_divergente
                else "logradouro_aproximado"
            ),
            "requer_confirmacao": precisao != "numero",
            "aviso": (
                "Número localizado; o CEP do ponto no mapa difere do CEP informado. Revise o pino."
                if precisao == "numero" and cep_divergente
                else "Número confirmado pelo geocodificador; revise o ponto no mapa."
                if precisao == "numero"
                else "Logradouro localizado com CEP divergente; confirme ou ajuste o pino no mapa."
                if cep_divergente
                else "Ponto aproximado pelo logradouro; confirme ou ajuste manualmente no mapa."
            ),
            "atribuicao": "© OpenStreetMap contributors",
        }

    if http_get is requests.get and resultado["encontrado"]:
        with _LOCK_GEOCODIFICACAO:
            if len(_CACHE_GEOCODIFICACAO) >= 512:
                mais_antiga = min(
                    _CACHE_GEOCODIFICACAO,
                    key=lambda chave: _CACHE_GEOCODIFICACAO[chave][0],
                )
                _CACHE_GEOCODIFICACAO.pop(mais_antiga, None)
            _CACHE_GEOCODIFICACAO[chave_cache] = (time.monotonic(), dict(resultado))
    return resultado


def previsao_open_meteo(
    lat: float,
    lon: float,
    *,
    forecast_days: int = OPEN_METEO_FORECAST_DAYS,
    alert_days: int | None = None,
) -> Dict[str, Any]:
    """Fachada legada; dados sintéticos nunca são expostos para decisão."""
    rico = consultar_open_meteo(lat, lon, forecast_days=forecast_days)
    if rico["simulado"]:
        return {
            "origem": "fallback_simulado",
            "dias": [],
            "alertas": [],
            "erro": (rico.get("erro_origem") or {}).get("tipo"),
        }

    dias = [
        {
            "data": dia["data_local"],
            "precipitacao_mm": dia["precipitacao_mm"],
            "prob_precip_pct": dia["prob_precip_pct"],
            "temp_max_c": dia["temp_max_c"],
        }
        for dia in rico["dias"]
    ]
    return {
        "origem": "api_open_meteo",
        "dias": dias,
        "alertas": gerar_alertas_chuva(
            dias[:alert_days] if alert_days is not None else dias
        ),
        "coletado_em_utc": rico.get("coletado_em_utc"),
    }


def gerar_alertas_chuva(dias: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    alertas = []
    for d in dias:
        mm = _numero_opcional(d.get("precipitacao_mm"), "precipitacao_mm")
        if mm is None:
            continue
        prob = _numero_opcional(d.get("prob_precip_pct"), "prob_precip_pct")
        if mm >= 30 or (mm >= 18 and prob is not None and prob >= 70):
            alertas.append(
                {
                    "tipo": "Chuvas intensas previstas",
                    "severidade": "Alta" if mm >= 35 else "Média",
                    "detalhe": (
                        f"{mm:.0f} mm previstos; probabilidade {prob:.0f}%"
                        if prob is not None
                        else f"{mm:.0f} mm previstos; probabilidade indisponível"
                    ),
                    "data": str(d.get("data")),
                }
            )
    ordem = {"Alta": 0, "Média": 1, "Baixa": 2}
    alertas.sort(key=lambda a: ordem.get(a.get("severidade"), 9))
    return alertas[:3]
