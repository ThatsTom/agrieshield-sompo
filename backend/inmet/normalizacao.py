"""Normalização determinística de estações e observações oficiais do INMET."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timezone
import io
import math
from pathlib import PurePosixPath
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional
import zipfile


FONTE_INMET = "INMET"
VARIAVEIS_QUALIDADE = (
    "temperatura_c",
    "precipitacao_mm",
    "umidade_pct",
    "vento_m_s",
    "rajada_m_s",
    "direcao_vento_graus",
    "pressao_hpa",
    "radiacao_kj_m2",
)
SENTINELAS_AUSENCIA = {-999.0, -9999.0}


class ErroDadosInmet(RuntimeError):
    """Indica conteúdo oficial ausente, inválido ou incompatível."""


def _numero(valor: Any) -> Optional[float]:
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        numero = float(
            texto.replace(".", "").replace(",", ".") if "," in texto else texto
        )
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numero) or numero in SENTINELAS_AUSENCIA:
        return None
    return numero


def _coordenada(valor: Any, minimo: float, maximo: float) -> Optional[float]:
    numero = _numero(valor)
    if numero is None or not minimo <= numero <= maximo:
        return None
    return numero


def normalizar_catalogo(payload: Any) -> List[Dict[str, Any]]:
    """Filtra e normaliza estações automáticas, operantes e pertencentes ao INMET."""
    if not isinstance(payload, list):
        raise ErroDadosInmet("O catálogo INMET não retornou uma lista JSON")

    estacoes: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("TP_ESTACAO") or "").strip() != "Automatica":
            continue
        if str(item.get("SG_ENTIDADE") or "").strip() != "INMET":
            continue
        if str(item.get("CD_SITUACAO") or "").strip() != "Operante":
            continue

        codigo = str(item.get("CD_ESTACAO") or "").strip().upper()
        latitude = _coordenada(item.get("VL_LATITUDE"), -90.0, 90.0)
        longitude = _coordenada(item.get("VL_LONGITUDE"), -180.0, 180.0)
        if not codigo or latitude is None or longitude is None:
            continue

        estacoes.append(
            {
                "codigo": codigo,
                "nome": str(item.get("DC_NOME") or "").strip(),
                "uf": str(item.get("SG_ESTADO") or "").strip().upper(),
                "latitude": latitude,
                "longitude": longitude,
                "altitude_m": _numero(item.get("VL_ALTITUDE")),
                "situacao": "Operante",
                "tipo": "Automatica",
                "entidade": "INMET",
                "inicio_operacao": item.get("DT_INICIO_OPERACAO"),
                "fim_operacao": item.get("DT_FIM_OPERACAO"),
            }
        )
    return estacoes


def distancia_haversine_km(
    latitude_origem: float,
    longitude_origem: float,
    latitude_destino: float,
    longitude_destino: float,
) -> float:
    """Calcula a distância geodésica aproximada entre dois pontos."""
    lat1 = _coordenada(latitude_origem, -90.0, 90.0)
    lon1 = _coordenada(longitude_origem, -180.0, 180.0)
    lat2 = _coordenada(latitude_destino, -90.0, 90.0)
    lon2 = _coordenada(longitude_destino, -180.0, 180.0)
    if None in (lat1, lon1, lat2, lon2):
        raise ValueError("Coordenadas inválidas para cálculo Haversine")

    raio_terra_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    return raio_terra_km * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def rankear_estacoes(
    latitude: float,
    longitude: float,
    estacoes: Iterable[Dict[str, Any]],
    *,
    limite: Optional[int] = 5,
) -> List[Dict[str, Any]]:
    """Ordena por distância e usa o código como desempate determinístico."""
    candidatos = []
    for estacao in estacoes:
        candidato = dict(estacao)
        candidato["distancia_km"] = distancia_haversine_km(
            latitude,
            longitude,
            candidato["latitude"],
            candidato["longitude"],
        )
        candidatos.append(candidato)
    candidatos.sort(key=lambda item: (item["distancia_km"], item["codigo"]))
    if limite is None:
        return candidatos
    if limite <= 0:
        raise ValueError("limite deve ser positivo")
    return candidatos[:limite]


def _sem_acentos(texto: str) -> str:
    return (
        "".join(
            caractere
            for caractere in unicodedata.normalize("NFKD", texto)
            if not unicodedata.combining(caractere)
        )
        .upper()
        .strip()
    )


def _buscar_coluna(colunas: Iterable[str], prefixo: str) -> str:
    esperado = _sem_acentos(prefixo)
    for coluna in colunas:
        if _sem_acentos(coluna).startswith(esperado):
            return coluna
    raise ErroDadosInmet(f"Coluna obrigatória ausente no arquivo INMET: {prefixo}")


def _timestamp_utc(data_bruta: str, hora_bruta: str) -> datetime:
    data_texto = str(data_bruta or "").strip()
    data_objeto = None
    for formato in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            data_objeto = datetime.strptime(data_texto, formato).date()
            break
        except ValueError:
            continue
    digitos_hora = "".join(re.findall(r"\d", str(hora_bruta or "")))[:4]
    if data_objeto is None or len(digitos_hora) != 4:
        raise ValueError("Data ou hora inválida no arquivo INMET")
    hora = int(digitos_hora[:2])
    minuto = int(digitos_hora[2:])
    return datetime.combine(data_objeto, time(hora, minuto), tzinfo=timezone.utc)


def _localizar_arquivo(zf: zipfile.ZipFile, codigo_estacao: str) -> str:
    codigo = str(codigo_estacao or "").strip().upper()
    padrao = re.compile(rf"(?:^|_){re.escape(codigo)}(?:_|\.)", re.IGNORECASE)
    candidatos = sorted(
        nome
        for nome in zf.namelist()
        if PurePosixPath(nome).suffix.upper() == ".CSV"
        and padrao.search(PurePosixPath(nome).name)
    )
    if not candidatos:
        raise ErroDadosInmet(f"Estação {codigo} não encontrada no ZIP anual do INMET")
    return candidatos[0]


def parsear_zip_historico(
    conteudo_zip: bytes,
    codigo_estacao: str,
    *,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    ingerido_em_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Extrai uma única estação do ZIP anual sem interpolar ou misturar séries."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(conteudo_zip))
    except (zipfile.BadZipFile, TypeError) as exc:
        raise ErroDadosInmet("Resposta do histórico INMET não é um ZIP válido") from exc

    with zf:
        nome_arquivo = _localizar_arquivo(zf, codigo_estacao)
        bruto = zf.read(nome_arquivo)
    try:
        texto = bruto.decode("latin-1")
    except UnicodeDecodeError as exc:
        raise ErroDadosInmet(
            "Arquivo INMET não pôde ser decodificado como Latin-1"
        ) from exc

    linhas = texto.splitlines()
    try:
        indice_cabecalho = next(
            indice
            for indice, linha in enumerate(linhas)
            if _sem_acentos(linha).startswith("DATA;")
        )
    except StopIteration as exc:
        raise ErroDadosInmet(
            "Cabeçalho horário não encontrado no arquivo INMET"
        ) from exc

    metadados = {}
    for linha in linhas[:indice_cabecalho]:
        chave, separador, valor = linha.partition(";")
        if separador:
            metadados[_sem_acentos(chave).lower().replace(" ", "_")] = valor.strip()

    leitor = csv.DictReader(linhas[indice_cabecalho:], delimiter=";")
    colunas = [coluna for coluna in (leitor.fieldnames or []) if coluna]
    if not colunas:
        raise ErroDadosInmet("Arquivo horário INMET sem colunas")

    mapa = {
        "data": _buscar_coluna(colunas, "DATA"),
        "hora": _buscar_coluna(colunas, "HORA UTC"),
        "precipitacao_mm": _buscar_coluna(colunas, "PRECIPITACAO TOTAL"),
        "pressao_hpa": _buscar_coluna(
            colunas, "PRESSAO ATMOSFERICA AO NIVEL DA ESTACAO, HORARIA"
        ),
        "radiacao_kj_m2": _buscar_coluna(colunas, "RADIACAO GLOBAL"),
        "temperatura_c": _buscar_coluna(
            colunas, "TEMPERATURA DO AR - BULBO SECO, HORARIA"
        ),
        "umidade_pct": _buscar_coluna(colunas, "UMIDADE RELATIVA DO AR, HORARIA"),
        "direcao_vento_graus": _buscar_coluna(colunas, "VENTO, DIRECAO HORARIA"),
        "rajada_m_s": _buscar_coluna(colunas, "VENTO, RAJADA MAXIMA"),
        "vento_m_s": _buscar_coluna(colunas, "VENTO, VELOCIDADE HORARIA"),
    }

    instante_ingestao = (ingerido_em_utc or datetime.now(timezone.utc)).astimezone(
        timezone.utc
    )
    observacoes: List[Dict[str, Any]] = []
    linhas_descartadas = 0
    for linha in leitor:
        linha.pop("", None)
        linha.pop(None, None)
        try:
            observado = _timestamp_utc(linha.get(mapa["data"]), linha.get(mapa["hora"]))
        except (TypeError, ValueError):
            linhas_descartadas += 1
            continue
        if data_inicio and observado.date() < data_inicio:
            continue
        if data_fim and observado.date() > data_fim:
            continue
        observacoes.append(
            {
                "codigo_estacao": str(codigo_estacao).strip().upper(),
                "observado_em_utc": observado.isoformat(),
                "temperatura_c": _numero(linha.get(mapa["temperatura_c"])),
                "precipitacao_mm": _numero(linha.get(mapa["precipitacao_mm"])),
                "umidade_pct": _numero(linha.get(mapa["umidade_pct"])),
                "vento_m_s": _numero(linha.get(mapa["vento_m_s"])),
                "rajada_m_s": _numero(linha.get(mapa["rajada_m_s"])),
                "direcao_vento_graus": _numero(linha.get(mapa["direcao_vento_graus"])),
                "pressao_hpa": _numero(linha.get(mapa["pressao_hpa"])),
                "radiacao_kj_m2": _numero(linha.get(mapa["radiacao_kj_m2"])),
                "fonte": FONTE_INMET,
                "ingerido_em_utc": instante_ingestao.isoformat(),
            }
        )
    observacoes.sort(key=lambda item: item["observado_em_utc"])
    return {
        "arquivo": nome_arquivo,
        "metadados": metadados,
        "observacoes": observacoes,
        "linhas_descartadas": linhas_descartadas,
    }


def calcular_qualidade(
    observacoes: Iterable[Dict[str, Any]],
    data_inicio: date,
    data_fim: date,
) -> Dict[str, Any]:
    """Calcula disponibilidade objetiva, sem classificar a qualidade."""
    if data_fim < data_inicio:
        raise ValueError("data_fim deve ser igual ou posterior a data_inicio")
    lista = list(observacoes)
    horas_esperadas = ((data_fim - data_inicio).days + 1) * 24
    timestamps = {
        item.get("observado_em_utc") for item in lista if item.get("observado_em_utc")
    }
    variaveis = {}
    for variavel in VARIAVEIS_QUALIDADE:
        disponiveis = {
            item.get("observado_em_utc")
            for item in lista
            if item.get("observado_em_utc") and item.get(variavel) is not None
        }
        variaveis[variavel] = {
            "horas_esperadas": horas_esperadas,
            "horas_disponiveis": len(disponiveis),
            "disponibilidade_pct": round(len(disponiveis) * 100.0 / horas_esperadas, 2),
        }
    return {
        "horas_esperadas": horas_esperadas,
        "horas_observadas": len(timestamps),
        "variaveis": variaveis,
    }


__all__ = [
    "ErroDadosInmet",
    "FONTE_INMET",
    "calcular_qualidade",
    "distancia_haversine_km",
    "normalizar_catalogo",
    "parsear_zip_historico",
    "rankear_estacoes",
]
