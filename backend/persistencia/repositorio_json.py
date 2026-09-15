"""Repositorio generico para resultados ricos armazenados como JSONB."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional

from .supabase_rest import cliente_supabase


class RepositorioSupabaseJson:
    def __init__(self, tabela: str) -> None:
        self._tabela = tabela

    def salvar(self, id_fazenda: str, resultado: Dict[str, Any]) -> Dict[str, Any]:
        linha = {
            "id_fazenda": int(id_fazenda),
            "resultado": deepcopy(resultado),
        }
        salvos = cliente_supabase().upsert(
            self._tabela, linha, conflito="id_fazenda"
        )
        if not salvos:
            return deepcopy(resultado)
        return deepcopy(salvos[0].get("resultado") or resultado)

    def buscar(self, id_fazenda: str) -> Optional[Dict[str, Any]]:
        linhas = cliente_supabase().selecionar(
            self._tabela,
            colunas="resultado",
            filtros={"id_fazenda": f"eq.{int(id_fazenda)}"},
            limite=1,
        )
        if not linhas:
            return None
        resultado = linhas[0].get("resultado")
        return deepcopy(resultado) if isinstance(resultado, dict) else None


__all__ = ["RepositorioSupabaseJson"]
