"""Persistencia serverless de clima, dashboard e jobs no Supabase."""

from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Mapping

import pandas as pd

from .supabase_rest import cliente_supabase


TABELA_CLIMA = "agrishield_clima_observacoes"
TABELA_DASHBOARD = "agrishield_dashboard"
TABELA_JOBS = "agrishield_jobs_climaticos"

COLUNAS_CLIMA = (
    "data",
    "ano",
    "mes",
    "dia",
    "temp_media_c",
    "temp_maxima_c",
    "temp_minima_c",
    "precipitacao_mm",
    "umidade_relativa_pct",
    "radiacao_solar_mj",
    "vento_ms",
    "dias_sem_chuva_consecutivos",
    "faixa_dias_sem_chuva",
    "nivel_risco_agroclimatico",
    "chuva_acumulada_7d",
    "chuva_acumulada_3d",
    "umidade_media_3d",
    "solo_encharcado",
    "condicao_operacional",
)


def _valor_json(valor: Any) -> Any:
    if valor is None:
        return None
    if isinstance(valor, (datetime, date, pd.Timestamp)):
        return valor.isoformat()
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(valor, "item"):
        valor = valor.item()
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    return valor


def _estrutura_json(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {str(chave): _estrutura_json(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_estrutura_json(item) for item in valor]
    return _valor_json(valor)


def salvar_observacoes_climaticas(
    id_fazenda: str, df: pd.DataFrame, origem: str
) -> None:
    linhas = []
    for registro in df.to_dict(orient="records"):
        linha = {
            "id_fazenda": int(id_fazenda),
            "origem_dados": origem,
        }
        for coluna in COLUNAS_CLIMA:
            if coluna in registro:
                linha[coluna] = _valor_json(registro[coluna])
        if linha.get("data"):
            linha["data"] = str(linha["data"])[:10]
        linhas.append(linha)

    cliente = cliente_supabase()
    for inicio in range(0, len(linhas), 500):
        cliente.upsert(
            TABELA_CLIMA,
            linhas[inicio : inicio + 500],
            conflito="id_fazenda,data",
            retornar=False,
        )


def salvar_dashboard(
    id_fazenda: str, resumo: Mapping[str, Any], origem_dados: str
) -> dict[str, Any]:
    payload_resumo = _estrutura_json(dict(resumo))
    linha = {
        "id_fazenda": int(id_fazenda),
        "data_referencia": resumo.get("data_referencia"),
        "score": resumo.get("score"),
        "condicao_atual": resumo.get("condicao_atual"),
        "origem_dados": origem_dados,
        "distribuicao_30d": _estrutura_json(resumo.get("distribuicao_30d", {})),
        "metricas_dia": _estrutura_json(resumo.get("metricas_dia", {})),
        "fatores_risco": _estrutura_json(resumo.get("fatores_risco", [])),
        "resumo": payload_resumo,
    }
    resultado = cliente_supabase().upsert(
        TABELA_DASHBOARD, linha, conflito="id_fazenda"
    )
    return resultado[0] if resultado else linha


def buscar_dashboard(id_fazenda: str) -> dict[str, Any] | None:
    linhas = cliente_supabase().selecionar(
        TABELA_DASHBOARD,
        filtros={"id_fazenda": f"eq.{int(id_fazenda)}"},
        limite=1,
    )
    if not linhas:
        return None
    linha = linhas[0]
    resumo = dict(linha.get("resumo") or {})
    if not resumo:
        resumo = {
            "data_referencia": linha.get("data_referencia"),
            "score": linha.get("score"),
            "condicao_atual": linha.get("condicao_atual"),
            "distribuicao_30d": linha.get("distribuicao_30d") or {},
            "metricas_dia": linha.get("metricas_dia") or {},
            "fatores_risco": linha.get("fatores_risco") or [],
        }
    resumo["origem_dados"] = linha.get("origem_dados")
    return resumo


def salvar_job(id_fazenda: str, job: Mapping[str, Any]) -> dict[str, Any]:
    linha = {
        "id_fazenda": int(id_fazenda),
        "job_id": job.get("job_id"),
        "status": job.get("status"),
        "progresso": int(job.get("progresso") or 0),
        "mensagem": job.get("mensagem") or "",
        "score_preview": _estrutura_json(job.get("score_preview")),
        "dados": _estrutura_json(dict(job)),
    }
    resultado = cliente_supabase().upsert(
        TABELA_JOBS, linha, conflito="id_fazenda"
    )
    return resultado[0] if resultado else linha


def buscar_job(id_fazenda: str) -> dict[str, Any] | None:
    linhas = cliente_supabase().selecionar(
        TABELA_JOBS,
        filtros={"id_fazenda": f"eq.{int(id_fazenda)}"},
        limite=1,
    )
    if not linhas:
        return None
    linha = linhas[0]
    dados = dict(linha.get("dados") or {})
    dados.update(
        {
            "id_fazenda": str(id_fazenda),
            "job_id": linha.get("job_id"),
            "status": linha.get("status"),
            "progresso": linha.get("progresso"),
            "mensagem": linha.get("mensagem"),
            "score_preview": linha.get("score_preview"),
            "atualizado_em": linha.get("updated_at"),
        }
    )
    return dados


__all__ = [
    "buscar_dashboard",
    "buscar_job",
    "salvar_dashboard",
    "salvar_job",
    "salvar_observacoes_climaticas",
]
