"""Comparacao pura entre scores de duas janelas consecutivas de 90 dias."""

from __future__ import annotations

import math
from datetime import timedelta
from enum import Enum

from pydantic import Field, model_validator

from backend.exposicao.modelos import FinalidadeJanela, JanelaHistorica
from backend.exposicao.politica import ClassificacaoIndice, PerigoExposicao
from backend.exposicao.score_exposicao import (
    MotivoIndisponibilidadeScore,
    ResultadoScoreExposicaoMaquinario,
)
from backend.risco.modelos import ModeloDominio


COMPARACAO_SCORE_VERSION = "exposicao-comparacao-score-90d-v1"
METODOLOGIA_COMPARACAO_SCORE = "COMPARACAO_SCORE_EXPOSICAO_90D_V1"
DISCLAIMER_COMPARACAO_SCORE = (
    "Comparacao demonstrativa do Score de Exposicao ambiental e territorial "
    "de maquinas e equipamentos agricolas entre duas janelas consecutivas. "
    "Nao representa variacao de probabilidade atuarial de sinistro nem "
    "calibracao oficial da Sompo."
)


class DirecaoVariacaoScore(str, Enum):
    AUMENTO = "AUMENTO"
    REDUCAO = "REDUCAO"
    ESTAVEL = "ESTAVEL"


class MotivoIndisponibilidadeComparacao(str, Enum):
    SCORE_ANTERIOR_NAO_PUBLICAVEL = "SCORE_ANTERIOR_NAO_PUBLICAVEL"
    SCORE_ATUAL_NAO_PUBLICAVEL = "SCORE_ATUAL_NAO_PUBLICAVEL"
    AMBOS_SCORES_NAO_PUBLICAVEIS = "AMBOS_SCORES_NAO_PUBLICAVEIS"


class MotivoPercentualIndisponivel(str, Enum):
    BASE_ANTERIOR_ZERO = "BASE_ANTERIOR_ZERO"
    COMPARACAO_NAO_PUBLICAVEL = "COMPARACAO_NAO_PUBLICAVEL"


class IndisponibilidadePerigoComparacao(ModeloDominio):
    perigo: PerigoExposicao
    motivos: tuple[MotivoIndisponibilidadeScore, ...] = Field(min_length=1)


class ResultadoComparacaoScoreExposicao90d(ModeloDominio):
    id_fazenda: str | None = None
    politica_id: str = Field(min_length=1)
    politica_versao: str = Field(min_length=1)
    metodologia: str = Field(default=METODOLOGIA_COMPARACAO_SCORE, min_length=1)
    metodologia_score: str = Field(min_length=1)
    janela_anterior: JanelaHistorica
    janela_atual: JanelaHistorica
    score_anterior: float | None = Field(default=None, ge=0, le=100)
    classificacao_anterior: ClassificacaoIndice | None = None
    score_atual: float | None = Field(default=None, ge=0, le=100)
    classificacao_atual: ClassificacaoIndice | None = None
    variacao_pontos: float | None = Field(default=None, ge=-100, le=100)
    variacao_percentual: float | None = None
    direcao: DirecaoVariacaoScore | None = None
    classificacao_mudou: bool | None = None
    comparacao_publicavel: bool
    qualidade_suficiente_anterior: bool
    qualidade_suficiente_atual: bool
    perigos_indisponiveis_anterior: tuple[PerigoExposicao, ...] = ()
    perigos_indisponiveis_atual: tuple[PerigoExposicao, ...] = ()
    detalhes_indisponibilidade_anterior: tuple[
        IndisponibilidadePerigoComparacao, ...
    ] = ()
    detalhes_indisponibilidade_atual: tuple[IndisponibilidadePerigoComparacao, ...] = ()
    motivo_indisponibilidade: MotivoIndisponibilidadeComparacao | None = None
    motivo_percentual_indisponivel: MotivoPercentualIndisponivel | None = None
    disclaimer: str = Field(default=DISCLAIMER_COMPARACAO_SCORE, min_length=1)
    versao: str = Field(default=COMPARACAO_SCORE_VERSION, min_length=1)

    @model_validator(mode="after")
    def validar_resultado(self) -> "ResultadoComparacaoScoreExposicao90d":
        _validar_janelas(self.janela_anterior, self.janela_atual)
        if (
            tuple(item.perigo for item in self.detalhes_indisponibilidade_anterior)
            != self.perigos_indisponiveis_anterior
        ):
            raise ValueError("detalhes de indisponibilidade anterior incoerentes")
        if (
            tuple(item.perigo for item in self.detalhes_indisponibilidade_atual)
            != self.perigos_indisponiveis_atual
        ):
            raise ValueError("detalhes de indisponibilidade atual incoerentes")
        if self.comparacao_publicavel:
            if self.score_anterior is None or self.score_atual is None:
                raise ValueError("comparacao publicavel exige os dois scores")
            if self.classificacao_anterior is None or self.classificacao_atual is None:
                raise ValueError("comparacao publicavel exige classificacoes")
            if not (
                self.qualidade_suficiente_anterior and self.qualidade_suficiente_atual
            ):
                raise ValueError("comparacao publicavel exige qualidade suficiente")
            if self.motivo_indisponibilidade is not None:
                raise ValueError("comparacao publicavel nao possui indisponibilidade")
            if self.perigos_indisponiveis_anterior or self.perigos_indisponiveis_atual:
                raise ValueError(
                    "comparacao publicavel nao possui perigos indisponiveis"
                )

            variacao = self.score_atual - self.score_anterior
            if self.variacao_pontos is None or not math.isclose(
                self.variacao_pontos,
                variacao,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("variacao em pontos incoerente")
            if self.direcao != _direcao(variacao):
                raise ValueError("direcao incoerente com a variacao em pontos")
            if self.classificacao_mudou != (
                self.classificacao_anterior != self.classificacao_atual
            ):
                raise ValueError("mudanca de classificacao incoerente")

            if self.score_anterior == 0:
                if self.score_atual == 0:
                    if self.variacao_percentual != 0:
                        raise ValueError(
                            "variacao percentual de zero para zero deve ser zero"
                        )
                    if self.motivo_percentual_indisponivel is not None:
                        raise ValueError("zero para zero possui percentual disponivel")
                else:
                    if self.variacao_percentual is not None:
                        raise ValueError("base zero nao possui variacao percentual")
                    if (
                        self.motivo_percentual_indisponivel
                        != MotivoPercentualIndisponivel.BASE_ANTERIOR_ZERO
                    ):
                        raise ValueError("base zero exige motivo explicito")
            else:
                percentual = variacao / self.score_anterior * 100
                if self.variacao_percentual is None or not math.isclose(
                    self.variacao_percentual,
                    percentual,
                    rel_tol=0.0,
                    abs_tol=1e-12,
                ):
                    raise ValueError("variacao percentual incoerente")
                if self.motivo_percentual_indisponivel is not None:
                    raise ValueError(
                        "percentual calculado nao possui indisponibilidade"
                    )
        else:
            if any(
                valor is not None
                for valor in (
                    self.variacao_pontos,
                    self.variacao_percentual,
                    self.direcao,
                    self.classificacao_mudou,
                )
            ):
                raise ValueError("comparacao indisponivel nao publica variacao parcial")
            if self.motivo_indisponibilidade is None:
                raise ValueError("comparacao indisponivel exige motivo explicito")
            motivo_esperado = _motivo_indisponibilidade(
                self.qualidade_suficiente_anterior,
                self.qualidade_suficiente_atual,
            )
            if self.motivo_indisponibilidade != motivo_esperado:
                raise ValueError("motivo de indisponibilidade incoerente")
            if (
                self.motivo_percentual_indisponivel
                != MotivoPercentualIndisponivel.COMPARACAO_NAO_PUBLICAVEL
            ):
                raise ValueError("percentual indisponivel exige motivo explicito")
        return self


def _validar_janelas(
    anterior: JanelaHistorica,
    atual: JanelaHistorica,
) -> None:
    if anterior.dias_esperados != 90 or atual.dias_esperados != 90:
        raise ValueError("comparacao exige duas janelas de 90 dias")
    if anterior.finalidade != FinalidadeJanela.COMPARACAO_ANTERIOR:
        raise ValueError("janela anterior exige finalidade de comparacao")
    if atual.finalidade != FinalidadeJanela.ATUAL:
        raise ValueError("janela atual exige finalidade atual")
    if anterior.data_referencia != atual.data_referencia:
        raise ValueError("janelas devem compartilhar a data de referencia")
    if anterior.inicio >= atual.inicio:
        raise ValueError("janela anterior deve preceder cronologicamente a atual")
    inicio_esperado = anterior.fim + timedelta(days=1)
    if inicio_esperado < atual.inicio:
        raise ValueError("janelas nao podem possuir gap")
    if inicio_esperado > atual.inicio:
        raise ValueError("janelas nao podem se sobrepor")


def _direcao(variacao_pontos: float) -> DirecaoVariacaoScore:
    if variacao_pontos > 0:
        return DirecaoVariacaoScore.AUMENTO
    if variacao_pontos < 0:
        return DirecaoVariacaoScore.REDUCAO
    return DirecaoVariacaoScore.ESTAVEL


def _motivo_indisponibilidade(
    anterior_publicavel: bool,
    atual_publicavel: bool,
) -> MotivoIndisponibilidadeComparacao | None:
    if not anterior_publicavel and not atual_publicavel:
        return MotivoIndisponibilidadeComparacao.AMBOS_SCORES_NAO_PUBLICAVEIS
    if not anterior_publicavel:
        return MotivoIndisponibilidadeComparacao.SCORE_ANTERIOR_NAO_PUBLICAVEL
    if not atual_publicavel:
        return MotivoIndisponibilidadeComparacao.SCORE_ATUAL_NAO_PUBLICAVEL
    return None


def _detalhes_indisponibilidade(
    score: ResultadoScoreExposicaoMaquinario,
) -> tuple[IndisponibilidadePerigoComparacao, ...]:
    return tuple(
        IndisponibilidadePerigoComparacao(
            perigo=item.perigo,
            motivos=item.motivos_indisponibilidade,
        )
        for item in score.contribuicoes
        if item.participa_score and not item.elegivel
    )


def _validar_mesma_composicao(
    anterior: ResultadoScoreExposicaoMaquinario,
    atual: ResultadoScoreExposicaoMaquinario,
) -> None:
    campos_estruturais = ("perigos_participantes", "perigos_excluidos")
    if any(
        getattr(anterior, campo) != getattr(atual, campo)
        for campo in campos_estruturais
    ):
        raise ValueError("scores usam politicas de composicao diferentes")
    if not math.isclose(
        anterior.soma_pesos,
        atual.soma_pesos,
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError("scores usam politicas de composicao diferentes")
    for contribuicao_anterior, contribuicao_atual in zip(
        anterior.contribuicoes,
        atual.contribuicoes,
    ):
        if (
            contribuicao_anterior.perigo != contribuicao_atual.perigo
            or contribuicao_anterior.participa_score
            != contribuicao_atual.participa_score
            or not math.isclose(
                contribuicao_anterior.peso,
                contribuicao_atual.peso,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("scores usam politicas de composicao diferentes")


def comparar_scores_exposicao_90d(
    score_anterior: ResultadoScoreExposicaoMaquinario,
    score_atual: ResultadoScoreExposicaoMaquinario,
) -> ResultadoComparacaoScoreExposicao90d:
    """Compara dois scores prontos sem recalcular score, perigo ou classificacao."""

    if not isinstance(score_anterior, ResultadoScoreExposicaoMaquinario):
        raise TypeError("score_anterior deve ser ResultadoScoreExposicaoMaquinario")
    if not isinstance(score_atual, ResultadoScoreExposicaoMaquinario):
        raise TypeError("score_atual deve ser ResultadoScoreExposicaoMaquinario")
    score_anterior = ResultadoScoreExposicaoMaquinario.model_validate(
        score_anterior.model_dump()
    )
    score_atual = ResultadoScoreExposicaoMaquinario.model_validate(
        score_atual.model_dump()
    )

    if score_anterior.id_fazenda != score_atual.id_fazenda:
        raise ValueError("scores devem pertencer a mesma fazenda")
    if score_anterior.politica_id != score_atual.politica_id:
        raise ValueError("politica_id diverge entre os scores")
    if score_anterior.politica_versao != score_atual.politica_versao:
        raise ValueError("versao da politica diverge entre os scores")
    if (
        score_anterior.metodologia != score_atual.metodologia
        or score_anterior.versao != score_atual.versao
    ):
        raise ValueError("metodologia do score diverge entre as janelas")
    _validar_mesma_composicao(score_anterior, score_atual)
    _validar_janelas(score_anterior.janela, score_atual.janela)

    publicavel = score_anterior.score_publicavel and score_atual.score_publicavel
    motivo = _motivo_indisponibilidade(
        score_anterior.score_publicavel,
        score_atual.score_publicavel,
    )

    variacao = None
    percentual = None
    motivo_percentual = None
    direcao = None
    classificacao_mudou = None
    if publicavel:
        variacao = score_atual.score - score_anterior.score
        direcao = _direcao(variacao)
        classificacao_mudou = score_anterior.classificacao != score_atual.classificacao
        if score_anterior.score == 0:
            if score_atual.score == 0:
                percentual = 0.0
            else:
                motivo_percentual = MotivoPercentualIndisponivel.BASE_ANTERIOR_ZERO
        else:
            percentual = variacao / score_anterior.score * 100
    else:
        motivo_percentual = MotivoPercentualIndisponivel.COMPARACAO_NAO_PUBLICAVEL

    return ResultadoComparacaoScoreExposicao90d(
        id_fazenda=score_atual.id_fazenda,
        politica_id=score_atual.politica_id,
        politica_versao=score_atual.politica_versao,
        metodologia_score=score_atual.metodologia,
        janela_anterior=score_anterior.janela,
        janela_atual=score_atual.janela,
        score_anterior=score_anterior.score,
        classificacao_anterior=score_anterior.classificacao,
        score_atual=score_atual.score,
        classificacao_atual=score_atual.classificacao,
        variacao_pontos=variacao,
        variacao_percentual=percentual,
        direcao=direcao,
        classificacao_mudou=classificacao_mudou,
        comparacao_publicavel=publicavel,
        qualidade_suficiente_anterior=score_anterior.qualidade_suficiente,
        qualidade_suficiente_atual=score_atual.qualidade_suficiente,
        perigos_indisponiveis_anterior=score_anterior.perigos_indisponiveis,
        perigos_indisponiveis_atual=score_atual.perigos_indisponiveis,
        detalhes_indisponibilidade_anterior=_detalhes_indisponibilidade(score_anterior),
        detalhes_indisponibilidade_atual=_detalhes_indisponibilidade(score_atual),
        motivo_indisponibilidade=motivo,
        motivo_percentual_indisponivel=motivo_percentual,
    )


__all__ = [
    "COMPARACAO_SCORE_VERSION",
    "DISCLAIMER_COMPARACAO_SCORE",
    "METODOLOGIA_COMPARACAO_SCORE",
    "DirecaoVariacaoScore",
    "IndisponibilidadePerigoComparacao",
    "MotivoIndisponibilidadeComparacao",
    "MotivoPercentualIndisponivel",
    "ResultadoComparacaoScoreExposicao90d",
    "comparar_scores_exposicao_90d",
]
