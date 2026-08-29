"""Camada canônica e isolada de dados de risco do AgriShield.

O pacote apenas normaliza objetos já coletados, calcula features neutras e
compõe contratos. Ele não consulta fontes, persiste dados ou calcula risco.
"""

from .agregador import agregar_features
from .features import calcular_features_climaticas
from .modelos import (
    AgregacaoTemporal,
    ConjuntoFeatures,
    ContextoTemporalFeature,
    FonteDado,
    FreshnessStatus,
    NaturezaDado,
    NivelProcessamento,
    QualidadeDado,
    StatusQualidade,
)
from .normalizacao import (
    normalizar_cadastro,
    normalizar_geoespacial,
    normalizar_inmet,
    normalizar_mapbiomas,
    normalizar_nasa,
    normalizar_open_meteo,
)

__all__ = [
    "AgregacaoTemporal",
    "ConjuntoFeatures",
    "ContextoTemporalFeature",
    "FonteDado",
    "FreshnessStatus",
    "NaturezaDado",
    "NivelProcessamento",
    "QualidadeDado",
    "StatusQualidade",
    "agregar_features",
    "calcular_features_climaticas",
    "normalizar_cadastro",
    "normalizar_geoespacial",
    "normalizar_inmet",
    "normalizar_mapbiomas",
    "normalizar_nasa",
    "normalizar_open_meteo",
]
