"""Adapta os parametros persistidos do modelo ao contrato do motor.

Mantido com o nome historico (o mecanismo nasceu so para os pesos do score);
hoje devolve o pacote completo de overrides (pesos + coeficientes internos de
Exposicao Hidrica, Instabilidade, Incendio, Tempestades e Trafegabilidade).
"""

from __future__ import annotations

from backend.app.servico_parametros_score import (
    OverridesParametrosModelo,
    carregar_overrides_parametros_modelo,
)


class ProvedorPesosPerigosPersistido:
    """Le a configuracao de parametros vigente uma vez por avaliacao."""

    def obter(self) -> OverridesParametrosModelo:
        return carregar_overrides_parametros_modelo()


__all__ = ["ProvedorPesosPerigosPersistido"]
