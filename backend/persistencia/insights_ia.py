"""Cache persistente dos briefings de IA no Supabase."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.persistencia.supabase_rest import cliente_supabase


TABELA_INSIGHTS_IA = "agrishield_insights_ia"


def buscar_insight_ia(
    id_fazenda: str, contexto_hash: str
) -> dict[str, Any] | None:
    registros = cliente_supabase().selecionar(
        TABELA_INSIGHTS_IA,
        filtros={
            "id_fazenda": f"eq.{int(id_fazenda)}",
            "contexto_hash": f"eq.{contexto_hash}",
        },
        limite=1,
    )
    return registros[0] if registros else None


def salvar_insight_ia(
    id_fazenda: str,
    *,
    contexto_hash: str,
    modelo: str,
    insight: Mapping[str, Any],
    uso: Mapping[str, Any] | None = None,
    gerado_em: str | None = None,
) -> dict[str, Any]:
    instante = gerado_em or datetime.now(timezone.utc).isoformat()
    registros = cliente_supabase().upsert(
        TABELA_INSIGHTS_IA,
        {
            "id_fazenda": int(id_fazenda),
            "contexto_hash": contexto_hash,
            "modelo": modelo,
            "insight": dict(insight),
            "uso": dict(uso or {}),
            "gerado_em": instante,
        },
        conflito="id_fazenda",
    )
    return registros[0] if registros else {
        "id_fazenda": int(id_fazenda),
        "contexto_hash": contexto_hash,
        "modelo": modelo,
        "insight": dict(insight),
        "uso": dict(uso or {}),
        "gerado_em": instante,
    }


__all__ = ["buscar_insight_ia", "salvar_insight_ia"]
