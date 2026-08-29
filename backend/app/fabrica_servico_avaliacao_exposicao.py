"""Composicao das dependencias concretas do servico AGRISHIELD-EQUIP."""

from __future__ import annotations

from backend.app.provedor_contexto_territorial_persistido import (
    ProvedorContextoTerritorialPersistido,
)
from backend.app.provedor_pesos_perigos_persistido import (
    ProvedorPesosPerigosPersistido,
)
from backend.app.servico_avaliacao_exposicao import (
    RepositorioFazendasPorFuncao,
    ServicoAvaliacaoExposicao,
)
from backend.etl.etapa1_cadastro_fazendas import buscar_fazenda
from backend.exposicao.clientes import (
    ClienteNasaPowerHistorico,
    ClienteOpenMeteoHistorico,
)
from backend.risco.modelos import FonteDado


def criar_servico_avaliacao_exposicao() -> ServicoAvaliacaoExposicao:
    """Cria o servico sem executar consultas externas ou avaliar uma fazenda."""

    return ServicoAvaliacaoExposicao(
        repositorio_fazendas=RepositorioFazendasPorFuncao(buscar_fazenda),
        clientes_meteorologicos={
            FonteDado.NASA_POWER: ClienteNasaPowerHistorico(),
            FonteDado.OPEN_METEO: ClienteOpenMeteoHistorico(),
        },
        provedor_contexto_territorial=ProvedorContextoTerritorialPersistido(),
        provedor_pesos_perigos=ProvedorPesosPerigosPersistido(),
    )


__all__ = ["criar_servico_avaliacao_exposicao"]
