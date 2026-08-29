# =============================================================================
# AgriShield — Serviços externos e fallbacks
#
# - geocoding_por_cep(): consulta o ViaCEP e complementa coordenadas conhecidas.
# - previsao_open_meteo(): consulta previsão pública Open-Meteo e gera alertas.
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
import math
from pathlib import Path
import re
from typing import Any, Dict, List
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "etl"))
from etapa1_cadastro_fazendas import resolver_cep_base_estatica, normalizar_cep


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
OPEN_METEO_SCHEMA_VERSION = "1"
OPEN_METEO_FORECAST_DAYS = 5
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
    chuva = [4.0, 18.5, 34.0, 22.0, 6.0]
    prob = [35, 68, 86, 74, 40]
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
) -> Dict[str, Any]:
    """Consulta uma vez e retorna o contrato rico real ou integralmente sintético."""
    getter = http_get or requests.get
    coletado_em: datetime | None = None
    try:
        resposta_http = getter(
            OPEN_METEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": OPEN_METEO_DAILY,
                "forecast_days": OPEN_METEO_FORECAST_DAYS,
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
            payload, dias_esperados=OPEN_METEO_FORECAST_DAYS
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
                "forecast_days": OPEN_METEO_FORECAST_DAYS,
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
                "dias_esperados": OPEN_METEO_FORECAST_DAYS,
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
            dias_esperados=OPEN_METEO_FORECAST_DAYS,
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

    base = resolver_cep_base_estatica(cep_limpo)
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


def previsao_open_meteo(lat: float, lon: float) -> Dict[str, Any]:
    """Fachada legada; dados sintéticos nunca são expostos para decisão."""
    rico = consultar_open_meteo(lat, lon)
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
        "alertas": gerar_alertas_chuva(dias),
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
