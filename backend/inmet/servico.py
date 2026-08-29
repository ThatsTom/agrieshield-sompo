"""Orquestração INMET por fazenda, isolada dos fluxos de risco."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Optional

from .cliente import (
    ClienteCatalogoInmet,
    ClienteHistoricoInmet,
    URL_CATALOGO,
    URL_HISTORICO_ANUAL,
)
from .normalizacao import calcular_qualidade, parsear_zip_historico, rankear_estacoes
from .repositorio import RepositorioInmet


class FazendaInmetNaoEncontrada(LookupError):
    pass


class ResultadoInmetNaoEncontrado(LookupError):
    pass


class ServicoInmet:
    def __init__(
        self,
        *,
        cliente_catalogo: ClienteCatalogoInmet,
        cliente_historico: ClienteHistoricoInmet,
        repositorio: RepositorioInmet,
        buscar_fazenda: Callable[[str], Optional[Dict[str, Any]]],
    ) -> None:
        self._cliente_catalogo = cliente_catalogo
        self._cliente_historico = cliente_historico
        self._repositorio = repositorio
        self._buscar_fazenda = buscar_fazenda

    def _fazenda(self, id_fazenda: str) -> Dict[str, Any]:
        fazenda = self._buscar_fazenda(str(id_fazenda))
        if not fazenda:
            raise FazendaInmetNaoEncontrada("Fazenda não encontrada")
        return fazenda

    def listar_candidatos(self, id_fazenda: str, *, limite: int = 5) -> Dict[str, Any]:
        fazenda = self._fazenda(id_fazenda)
        estacoes = self._cliente_catalogo.obter_estacoes()
        candidatos = rankear_estacoes(
            float(fazenda["latitude"]),
            float(fazenda["longitude"]),
            estacoes,
            limite=max(5, limite),
        )
        return {
            "id_fazenda": str(id_fazenda),
            "localizacao_fazenda": {
                "latitude": float(fazenda["latitude"]),
                "longitude": float(fazenda["longitude"]),
            },
            "fonte_catalogo": URL_CATALOGO,
            "candidatos": candidatos,
        }

    def coletar(
        self,
        id_fazenda: str,
        *,
        data_inicio: date,
        data_fim: date,
        codigo_estacao: Optional[str] = None,
    ) -> Dict[str, Any]:
        if data_fim < data_inicio:
            raise ValueError("data_fim deve ser igual ou posterior a data_inicio")
        if data_inicio.year != data_fim.year:
            raise ValueError(
                "A coleta deve permanecer dentro de um único arquivo anual"
            )

        fazenda = self._fazenda(id_fazenda)
        estacoes = self._cliente_catalogo.obter_estacoes()
        ranking = rankear_estacoes(
            float(fazenda["latitude"]),
            float(fazenda["longitude"]),
            estacoes,
            limite=None,
        )
        if not ranking:
            raise ValueError("Nenhuma estação INMET elegível foi encontrada")

        selecionada = ranking[0]
        if codigo_estacao:
            codigo = codigo_estacao.strip().upper()
            selecionada = next(
                (estacao for estacao in ranking if estacao["codigo"] == codigo),
                None,
            )
            if selecionada is None:
                raise ValueError(
                    "Estação solicitada não pertence ao catálogo elegível atual"
                )

        conteudo = self._cliente_historico.baixar_ano(data_inicio.year)
        ingerido_em = datetime.now(timezone.utc)
        extraido = parsear_zip_historico(
            conteudo,
            selecionada["codigo"],
            data_inicio=data_inicio,
            data_fim=data_fim,
            ingerido_em_utc=ingerido_em,
        )
        observacoes = extraido["observacoes"]
        resultado = {
            "id_fazenda": str(id_fazenda),
            "estacao": selecionada,
            "periodo": {
                "data_inicio": data_inicio.isoformat(),
                "data_fim": data_fim.isoformat(),
                "timezone": "UTC",
            },
            "observacoes": observacoes,
            "qualidade": calcular_qualidade(observacoes, data_inicio, data_fim),
            "origem": {
                "fonte": "INMET",
                "catalogo_url": URL_CATALOGO,
                "historico_url": URL_HISTORICO_ANUAL.format(ano=data_inicio.year),
                "arquivo": extraido["arquivo"],
            },
            "diagnostico": {
                "linhas_descartadas": extraido["linhas_descartadas"],
                "estacoes_misturadas": False,
            },
            "ingerido_em_utc": ingerido_em.isoformat(),
        }
        return self._repositorio.salvar(str(id_fazenda), resultado)

    def obter(self, id_fazenda: str) -> Dict[str, Any]:
        self._fazenda(id_fazenda)
        resultado = self._repositorio.buscar(str(id_fazenda))
        if resultado is None:
            raise ResultadoInmetNaoEncontrado(
                "Dados INMET não encontrados para a fazenda"
            )
        return resultado


__all__ = [
    "FazendaInmetNaoEncontrada",
    "ResultadoInmetNaoEncontrado",
    "ServicoInmet",
]
