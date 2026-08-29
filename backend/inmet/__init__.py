"""Subsistema independente de dados meteorológicos observados do INMET."""

from .cliente import ClienteCatalogoInmet, ClienteHistoricoInmet, ErroClienteInmet
from .normalizacao import (
    ErroDadosInmet,
    calcular_qualidade,
    distancia_haversine_km,
    normalizar_catalogo,
    parsear_zip_historico,
    rankear_estacoes,
)
from .repositorio import RepositorioInmet, RepositorioInmetMemoria
from .servico import (
    FazendaInmetNaoEncontrada,
    ResultadoInmetNaoEncontrado,
    ServicoInmet,
)

__all__ = [
    "ClienteCatalogoInmet",
    "ClienteHistoricoInmet",
    "ErroClienteInmet",
    "ErroDadosInmet",
    "FazendaInmetNaoEncontrada",
    "RepositorioInmet",
    "RepositorioInmetMemoria",
    "ResultadoInmetNaoEncontrado",
    "ServicoInmet",
    "calcular_qualidade",
    "distancia_haversine_km",
    "normalizar_catalogo",
    "parsear_zip_historico",
    "rankear_estacoes",
]
