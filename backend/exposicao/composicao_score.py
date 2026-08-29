"""Politica estrutural de composicao dos perigos, sem calcular Score Geral.

Cada perigo participa do score com um unico peso, configurado pelo Analista
Sompo e persistido fora do codigo. Nao ha distincao entre peso nominal e
peso efetivo, nem redistribuicao automatica de peso entre os perigos quando
um deles esta inativo: o peso de um perigo inativo e simplesmente zero na
composicao, sem afetar os demais.
"""

from __future__ import annotations

import math

from pydantic import Field, model_validator

from backend.exposicao.politica import (
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import ModeloDominio


COMPOSICAO_SCORE_VERSION = "exposicao-composicao-score-v2"
METODOLOGIA_COMPOSICAO_SCORE = "PESO_UNICO_CONFIGURAVEL_POR_INDICADOR_V1"
DESCRICAO_COMPOSICAO_SCORE = (
    "Cada um dos cinco indicadores participa do score com um unico peso "
    "configuravel pelo Analista Sompo, sem distincao entre peso nominal e "
    "peso efetivo e sem redistribuicao automatica entre indicadores."
)


class ConfiguracaoComposicaoPerigo(ModeloDominio):
    perigo: PerigoExposicao
    peso: float = Field(ge=0, le=1)
    participa_score: bool

    @model_validator(mode="after")
    def validar_participacao(self) -> "ConfiguracaoComposicaoPerigo":
        if not self.participa_score and self.peso != 0:
            raise ValueError("perigo inativo na configuracao exige peso zero")
        return self


class PoliticaComposicaoScore(ModeloDominio):
    politica_id: str = Field(min_length=1)
    configuracoes: tuple[ConfiguracaoComposicaoPerigo, ...] = Field(
        min_length=5,
        max_length=5,
    )
    soma_pesos: float = Field(ge=0, le=1)
    metodologia: str = Field(default=METODOLOGIA_COMPOSICAO_SCORE, min_length=1)
    descricao: str = Field(default=DESCRICAO_COMPOSICAO_SCORE, min_length=1)
    versao: str = Field(default=COMPOSICAO_SCORE_VERSION, min_length=1)

    @model_validator(mode="after")
    def validar_politica(self) -> "PoliticaComposicaoScore":
        if not self.politica_id.strip():
            raise ValueError("politica_id nao pode ser vazio")
        if not self.metodologia.strip() or not self.descricao.strip():
            raise ValueError("metodologia e descricao devem ser explicitas")

        perigos = tuple(configuracao.perigo for configuracao in self.configuracoes)
        if perigos != tuple(PerigoExposicao):
            raise ValueError("configuracoes devem conter os cinco perigos em ordem")
        if len(set(perigos)) != 5:
            raise ValueError("perigos nao podem se repetir")

        participantes = tuple(
            configuracao
            for configuracao in self.configuracoes
            if configuracao.participa_score
        )
        if not participantes:
            raise ValueError("politica exige ao menos um participante ativo")
        soma = math.fsum(configuracao.peso for configuracao in participantes)
        if not math.isclose(soma, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("soma dos pesos dos indicadores ativos deve ser 1.0")
        if not math.isclose(self.soma_pesos, soma, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("soma de pesos declarada diverge das configuracoes")
        return self

    def configuracao_de(
        self,
        perigo: PerigoExposicao,
    ) -> ConfiguracaoComposicaoPerigo:
        for configuracao in self.configuracoes:
            if configuracao.perigo == perigo:
                return configuracao
        raise KeyError(perigo)


def criar_politica_composicao_score(
    politica: PoliticaExposicaoEquipamentos,
) -> PoliticaComposicaoScore:
    """Deriva a composicao efetiva diretamente dos pesos configurados."""

    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    configuracoes = tuple(
        ConfiguracaoComposicaoPerigo(
            perigo=perigo,
            peso=politica.pesos_perigos.peso(perigo),
            participa_score=True,
        )
        for perigo in PerigoExposicao
    )
    return PoliticaComposicaoScore(
        politica_id=politica.id_politica,
        configuracoes=configuracoes,
        soma_pesos=math.fsum(configuracao.peso for configuracao in configuracoes),
    )


__all__ = [
    "COMPOSICAO_SCORE_VERSION",
    "DESCRICAO_COMPOSICAO_SCORE",
    "METODOLOGIA_COMPOSICAO_SCORE",
    "ConfiguracaoComposicaoPerigo",
    "PoliticaComposicaoScore",
    "criar_politica_composicao_score",
]
