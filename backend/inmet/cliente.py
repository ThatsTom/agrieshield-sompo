"""Clientes HTTP das superfícies oficiais adotadas do INMET."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .normalizacao import ErroDadosInmet, normalizar_catalogo


URL_CATALOGO = "https://apitempo.inmet.gov.br/estacoes/T"
URL_HISTORICO_ANUAL = "https://portal.inmet.gov.br/uploads/dadoshistoricos/{ano}.zip"


class ErroClienteInmet(RuntimeError):
    """Falha de transporte ou resposta inválida de uma fonte oficial."""


class ClienteCatalogoInmet:
    def __init__(
        self, *, sessao: Optional[requests.Session] = None, timeout_s: int = 30
    ):
        self._sessao = sessao or requests.Session()
        self._timeout_s = timeout_s

    def obter_estacoes(self) -> List[Dict[str, Any]]:
        try:
            resposta = self._sessao.get(URL_CATALOGO, timeout=self._timeout_s)
            resposta.raise_for_status()
            payload = resposta.json()
            estacoes = normalizar_catalogo(payload)
        except (requests.Timeout, requests.RequestException) as exc:
            raise ErroClienteInmet(
                "Falha ao consultar o catálogo oficial do INMET"
            ) from exc
        except (ValueError, ErroDadosInmet) as exc:
            raise ErroClienteInmet(
                "Resposta inválida do catálogo oficial do INMET"
            ) from exc
        if not estacoes:
            raise ErroClienteInmet(
                "Catálogo INMET sem estações automáticas operantes válidas"
            )
        return estacoes


class ClienteHistoricoInmet:
    def __init__(
        self, *, sessao: Optional[requests.Session] = None, timeout_s: int = 180
    ):
        self._sessao = sessao or requests.Session()
        self._timeout_s = timeout_s

    def baixar_ano(self, ano: int) -> bytes:
        if ano < 2000:
            raise ValueError(
                "O histórico automático oficial está disponível a partir de 2000"
            )
        url = URL_HISTORICO_ANUAL.format(ano=ano)
        try:
            resposta = self._sessao.get(url, timeout=self._timeout_s)
            resposta.raise_for_status()
        except (requests.Timeout, requests.RequestException) as exc:
            raise ErroClienteInmet(
                f"Falha ao baixar o histórico oficial INMET de {ano}"
            ) from exc
        if not resposta.content:
            raise ErroClienteInmet(
                f"Histórico oficial INMET de {ano} retornou conteúdo vazio"
            )
        return resposta.content


__all__ = [
    "ClienteCatalogoInmet",
    "ClienteHistoricoInmet",
    "ErroClienteInmet",
    "URL_CATALOGO",
    "URL_HISTORICO_ANUAL",
]
