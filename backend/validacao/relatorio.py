"""Serialização estrita e relatórios sem interpretação de risco novo."""

from __future__ import annotations

import csv
from datetime import date, datetime
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
from pydantic import BaseModel


COLUNAS_RESUMO = (
    "id_cenario",
    "uf",
    "modo",
    "latitude",
    "longitude",
    "area_ha",
    "nasa_origem",
    "chuva_7d_mm",
    "umidade_3d_pct",
    "temp_max_c",
    "nasa_data_efetiva_chuva",
    "nasa_defasagem_chuva_dias",
    "nasa_freshness_chuva",
    "nasa_data_efetiva_umidade",
    "nasa_defasagem_umidade_dias",
    "nasa_freshness_umidade",
    "nasa_data_efetiva_temperatura",
    "nasa_defasagem_temperatura_dias",
    "nasa_freshness_temperatura",
    "openmeteo_fonte",
    "openmeteo_simulado",
    "previsao_status",
    "inmet_estacao",
    "inmet_distancia_km",
    "inmet_disponibilidade_chuva_periodo_pct",
    "inmet_disponibilidade_chuva_lookback_pct",
    "declividade_graus",
    "inmet_ultima_observacao",
    "inmet_defasagem_dias",
    "inmet_freshness",
    "posicao_topografica_m",
    "distancia_drenagem_m",
    "area_drenagem_km2",
    "mapbiomas_classe",
    "agricultura_pct",
    "pastagem_pct",
    "vegetacao_nativa_pct",
    "agua_pct",
    "mapbiomas_cobertura_pct",
    "score_legado",
    "estado_legado",
    "status_execucao",
)


def para_json_compativel(valor: Any) -> Any:
    """Converte contratos e escalares sem emitir NaN ou Infinity."""
    if isinstance(valor, BaseModel):
        return para_json_compativel(valor.model_dump(mode="json"))
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Path):
        return str(valor)
    if isinstance(valor, Mapping):
        return {str(chave): para_json_compativel(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple, set)):
        return [para_json_compativel(item) for item in valor]
    if valor is pd.NA or valor is pd.NaT:
        return None
    if hasattr(valor, "item") and callable(valor.item):
        try:
            return para_json_compativel(valor.item())
        except (TypeError, ValueError):
            return None
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _obter(objeto: Any, *caminho: str) -> Any:
    atual = objeto
    for chave in caminho:
        if not isinstance(atual, Mapping):
            return None
        atual = atual.get(chave)
    return atual


def _feature(resultado: Mapping[str, Any], nome: str) -> Any:
    features = _obter(resultado, "camada_canonica", "climaticas", "features") or []
    for item in features:
        if isinstance(item, Mapping) and item.get("nome") == nome:
            return item.get("valor")
    return None


def _contexto_feature(resultado: Mapping[str, Any], nome: str) -> Mapping[str, Any]:
    features = _obter(resultado, "camada_canonica", "climaticas", "features") or []
    for item in features:
        if isinstance(item, Mapping) and item.get("nome") == nome:
            contexto = item.get("contexto_temporal")
            return contexto if isinstance(contexto, Mapping) else {}
    return {}


def resumir_cenario(resultado: Mapping[str, Any]) -> dict[str, Any]:
    referencia = resultado.get("referencia") or {}
    fontes = resultado.get("fontes") or {}
    nasa = fontes.get("NASA_POWER") or {}
    openmeteo = fontes.get("OPEN_METEO") or {}
    inmet = fontes.get("INMET") or {}
    srtm = fontes.get("SRTM") or {}
    merit = fontes.get("MERIT_HYDRO") or {}
    mapa = fontes.get("MAPBIOMAS") or {}
    score = resultado.get("score_legado") or {}
    temporal_chuva = _contexto_feature(resultado, "chuva_acumulada_7_dias_mm")
    temporal_umidade = _contexto_feature(resultado, "umidade_relativa_media_3_dias_pct")
    temporal_temperatura = _contexto_feature(
        resultado, "temperatura_maxima_dia_referencia_c"
    )
    temporal_inmet = _obter(inmet, "dados", "diagnostico_temporal") or {}
    return {
        "id_cenario": resultado.get("id_cenario"),
        "uf": resultado.get("parametros", {}).get("uf"),
        "modo": resultado.get("parametros", {}).get("modo"),
        "latitude": referencia.get("latitude"),
        "longitude": referencia.get("longitude"),
        "area_ha": referencia.get("area_ha"),
        "nasa_origem": _obter(nasa, "dados", "origem"),
        "chuva_7d_mm": _feature(resultado, "chuva_acumulada_7_dias_mm"),
        "umidade_3d_pct": _feature(resultado, "umidade_relativa_media_3_dias_pct"),
        "temp_max_c": _feature(resultado, "temperatura_maxima_dia_referencia_c"),
        "nasa_data_efetiva_chuva": temporal_chuva.get("data_referencia_efetiva"),
        "nasa_defasagem_chuva_dias": temporal_chuva.get("defasagem_dias"),
        "nasa_freshness_chuva": temporal_chuva.get("freshness_status"),
        "nasa_data_efetiva_umidade": temporal_umidade.get("data_referencia_efetiva"),
        "nasa_defasagem_umidade_dias": temporal_umidade.get("defasagem_dias"),
        "nasa_freshness_umidade": temporal_umidade.get("freshness_status"),
        "nasa_data_efetiva_temperatura": temporal_temperatura.get(
            "data_referencia_efetiva"
        ),
        "nasa_defasagem_temperatura_dias": temporal_temperatura.get("defasagem_dias"),
        "nasa_freshness_temperatura": temporal_temperatura.get("freshness_status"),
        "openmeteo_fonte": _obter(openmeteo, "dados", "bruto", "fonte"),
        "openmeteo_simulado": _obter(openmeteo, "dados", "bruto", "simulado"),
        "previsao_status": openmeteo.get("status"),
        "inmet_estacao": _obter(inmet, "dados", "bruto", "estacao", "codigo"),
        "inmet_distancia_km": _obter(
            inmet, "dados", "bruto", "estacao", "distancia_km"
        ),
        "inmet_disponibilidade_chuva_periodo_pct": _obter(
            temporal_inmet, "janela_operacional", "disponibilidade_precipitacao_pct"
        ),
        "inmet_disponibilidade_chuva_lookback_pct": _obter(
            temporal_inmet, "janela_lookback", "disponibilidade_precipitacao_pct"
        ),
        "inmet_ultima_observacao": temporal_inmet.get("ultima_observacao_disponivel"),
        "inmet_defasagem_dias": temporal_inmet.get("defasagem_dias"),
        "inmet_freshness": temporal_inmet.get("freshness_status"),
        "declividade_graus": _obter(
            srtm, "dados", "atributos", "declividade_media", "valor"
        ),
        "posicao_topografica_m": _obter(
            srtm, "dados", "atributos", "posicao_topografica_relativa", "valor"
        ),
        "distancia_drenagem_m": _obter(
            merit, "dados", "atributos", "distancia_drenagem", "valor"
        ),
        "area_drenagem_km2": _obter(
            merit, "dados", "atributos", "area_drenagem_montante", "valor"
        ),
        "mapbiomas_classe": _obter(
            mapa, "dados", "bruto", "cobertura", "classe_predominante_nome"
        ),
        "agricultura_pct": _obter(
            mapa, "dados", "bruto", "cobertura", "agricultura_pct"
        ),
        "pastagem_pct": _obter(mapa, "dados", "bruto", "cobertura", "pastagem_pct"),
        "vegetacao_nativa_pct": _obter(
            mapa, "dados", "bruto", "cobertura", "vegetacao_nativa_pct"
        ),
        "agua_pct": _obter(mapa, "dados", "bruto", "cobertura", "agua_pct"),
        "mapbiomas_cobertura_pct": _obter(
            mapa, "dados", "bruto", "qualidade", "cobertura_valida_pct"
        ),
        "score_legado": score.get("score"),
        "estado_legado": score.get("estado"),
        "status_execucao": resultado.get("status_execucao"),
    }


def comparar_resultados(resultados: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Aponta extremos e ausências objetivas, sem criar ranking ou risco."""
    linhas = [resumir_cenario(resultado) for resultado in resultados]
    metricas = (
        "chuva_7d_mm",
        "umidade_3d_pct",
        "temp_max_c",
        "nasa_defasagem_chuva_dias",
        "nasa_defasagem_umidade_dias",
        "nasa_defasagem_temperatura_dias",
        "inmet_defasagem_dias",
        "inmet_distancia_km",
        "declividade_graus",
        "distancia_drenagem_m",
        "agricultura_pct",
        "pastagem_pct",
        "vegetacao_nativa_pct",
        "agua_pct",
    )
    comparativo: dict[str, Any] = {}
    for metrica in metricas:
        validos = [
            (linha["id_cenario"], linha[metrica])
            for linha in linhas
            if isinstance(linha.get(metrica), (int, float))
            and not isinstance(linha.get(metrica), bool)
            and math.isfinite(float(linha[metrica]))
        ]
        comparativo[metrica] = {
            "menor": (
                {
                    "id_cenario": min(validos, key=lambda item: item[1])[0],
                    "valor": min(validos, key=lambda item: item[1])[1],
                }
                if validos
                else None
            ),
            "maior": (
                {
                    "id_cenario": max(validos, key=lambda item: item[1])[0],
                    "valor": max(validos, key=lambda item: item[1])[1],
                }
                if validos
                else None
            ),
            "ausentes": [
                linha["id_cenario"] for linha in linhas if linha.get(metrica) is None
            ],
        }
    comparativo["freshness_por_cenario"] = {
        linha["id_cenario"]: {
            "nasa_chuva": linha["nasa_freshness_chuva"],
            "nasa_umidade": linha["nasa_freshness_umidade"],
            "nasa_temperatura": linha["nasa_freshness_temperatura"],
            "inmet": linha["inmet_freshness"],
        }
        for linha in linhas
    }
    return comparativo


def salvar_relatorios(
    execucao: Mapping[str, Any],
    pasta_saida: str | Path,
) -> tuple[Path, Path]:
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    timestamp = str(execucao["executado_em_utc"]).replace(":", "").replace("-", "")
    timestamp = timestamp.replace("+0000", "Z").replace("+00:00", "Z")
    json_path = pasta / f"resultado_multiregional_{timestamp}.json"
    csv_path = pasta / f"resumo_multiregional_{timestamp}.csv"
    serializavel = para_json_compativel(execucao)
    json_path.write_text(
        json.dumps(serializavel, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_RESUMO, delimiter=";")
        escritor.writeheader()
        for resultado in serializavel.get("resultados", []):
            linha = para_json_compativel(resumir_cenario(resultado))
            escritor.writerow(
                {
                    chave: "" if linha.get(chave) is None else linha.get(chave)
                    for chave in COLUNAS_RESUMO
                }
            )
    return json_path, csv_path


__all__ = [
    "COLUNAS_RESUMO",
    "comparar_resultados",
    "para_json_compativel",
    "resumir_cenario",
    "salvar_relatorios",
]
