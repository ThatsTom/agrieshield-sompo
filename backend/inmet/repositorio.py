"""Contrato substituível e implementação local mínima do repositório INMET."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Dict, Optional, Protocol


class RepositorioInmet(Protocol):
    def salvar(self, id_fazenda: str, resultado: Dict[str, Any]) -> Dict[str, Any]: ...

    def buscar(self, id_fazenda: str) -> Optional[Dict[str, Any]]: ...


class RepositorioInmetMemoria:
    """Upsert por fazenda durante a vida do processo; não cria arquivos locais."""

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
            registro = self._registros.get(str(id_fazenda))
            return deepcopy(registro) if registro is not None else None


__all__ = ["RepositorioInmet", "RepositorioInmetMemoria"]
