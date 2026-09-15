"""Contrato substituível e repositório transitório do MapBiomas."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Dict, Optional, Protocol

from backend.persistencia.repositorio_json import RepositorioSupabaseJson


class RepositorioMapBiomas(Protocol):
    """Contrato mínimo para futura implementação em Supabase."""

    def salvar(self, id_fazenda: str, resultado: Dict[str, Any]) -> Dict[str, Any]: ...

    def buscar(self, id_fazenda: str) -> Optional[Dict[str, Any]]: ...


class RepositorioMapBiomasMemoria:
    """Upsert por fazenda durante a vida do processo, sem persistência local."""

    def __init__(self) -> None:
        self._registros: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()

    def salvar(self, id_fazenda: str, resultado: Dict[str, Any]) -> Dict[str, Any]:
        chave = str(id_fazenda)
        with self._lock:
            self._registros[chave] = deepcopy(resultado)
            return deepcopy(self._registros[chave])

    def buscar(self, id_fazenda: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            resultado = self._registros.get(str(id_fazenda))
            return deepcopy(resultado) if resultado is not None else None


class RepositorioMapBiomasSupabase(RepositorioSupabaseJson):
    """Persistencia duravel da ultima analise MapBiomas por fazenda."""

    def __init__(self) -> None:
        super().__init__("agrishield_mapbiomas")


__all__ = [
    "RepositorioMapBiomas",
    "RepositorioMapBiomasMemoria",
    "RepositorioMapBiomasSupabase",
]
