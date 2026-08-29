"""Harness observacional de testes de mesa multi-regionais."""

from .executor import DependenciasValidacao, ExecutorValidacaoMultiregional
from .modelos import CenarioValidacao, ModoCenario, StatusFonte, carregar_cenarios
from .relatorio import comparar_resultados, salvar_relatorios

__all__ = [
    "CenarioValidacao",
    "DependenciasValidacao",
    "ExecutorValidacaoMultiregional",
    "ModoCenario",
    "StatusFonte",
    "carregar_cenarios",
    "comparar_resultados",
    "salvar_relatorios",
]
