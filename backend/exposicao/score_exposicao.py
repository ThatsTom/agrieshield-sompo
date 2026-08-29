"""Score consolidado de exposicao do maquinario para uma janela validada.

Esta camada combina exclusivamente resultados dos perigos ja calculados e
validados. Ela nao acessa fontes, nao recalcula eventos e nao redistribui peso
quando um perigo participante esta indisponivel: se faltar dado suficiente em
qualquer perigo ativo, nenhum score parcial e publicado. Essa e a decisao
deliberada e mais segura para o MVP; nenhuma regra de redistribuicao foi
inventada para compensar a ausencia.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import Field, model_validator

from backend.exposicao.composicao_score import PoliticaComposicaoScore
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.politica import (
    ClassificacaoIndice,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.exposicao.validacao_integrada import (
    ResultadoValidacaoIntegradaPerigos,
)
from backend.risco.modelos import ModeloDominio


SCORE_EXPOSICAO_VERSION = "exposicao-score-maquinario-90d-v2"
METODOLOGIA_SCORE_EXPOSICAO = "SCORE_EXPOSICAO_MAQUINARIO_90D_V1"
DISCLAIMER_SCORE_EXPOSICAO = (
    "Score demonstrativo de exposicao ambiental e territorial de maquinas e "
    "equipamentos agricolas. Nao representa probabilidade atuarial de sinistro "
    "nem calibracao oficial da Sompo."
)


class TipoNaoContribuicaoScore(str, Enum):
    INATIVO_NA_CONFIGURACAO = "INATIVO_NA_CONFIGURACAO"
    DADO_INSUFICIENTE = "DADO_INSUFICIENTE"


class MotivoIndisponibilidadeScore(str, Enum):
    INDICE_AGREGADO_AUSENTE = "INDICE_AGREGADO_AUSENTE"
    CLASSIFICACAO_AGREGADA_AUSENTE = "CLASSIFICACAO_AGREGADA_AUSENTE"
    QUALIDADE_INSUFICIENTE = "QUALIDADE_INSUFICIENTE"
    COBERTURA_ABAIXO_DA_POLITICA = "COBERTURA_ABAIXO_DA_POLITICA"


class ContribuicaoPerigoScore(ModeloDominio):
    perigo: PerigoExposicao
    indice_perigo: float | None = Field(default=None, ge=0, le=100)
    classificacao_perigo: ClassificacaoIndice | None = None
    peso: float = Field(ge=0, le=1)
    participa_score: bool
    elegivel: bool
    contribuicao: float | None = Field(default=None, ge=0, le=100)
    cobertura_percentual: float = Field(ge=0, le=100)
    cobertura_minima_percentual: float = Field(ge=0, le=100)
    qualidade_suficiente: bool
    tipo_nao_contribuicao: TipoNaoContribuicaoScore | None = None
    motivos_indisponibilidade: tuple[MotivoIndisponibilidadeScore, ...] = ()

    @model_validator(mode="after")
    def validar_contribuicao(self) -> "ContribuicaoPerigoScore":
        cobertura_atende = self.cobertura_percentual >= self.cobertura_minima_percentual
        if self.qualidade_suficiente != cobertura_atende:
            raise ValueError("qualidade diverge da cobertura minima da politica")

        if not self.participa_score:
            if self.elegivel:
                raise ValueError("perigo excluido nao pode ser elegivel")
            if self.peso != 0 or self.contribuicao != 0:
                raise ValueError("perigo excluido exige peso e contribuicao zero")
            if (
                self.tipo_nao_contribuicao
                != TipoNaoContribuicaoScore.INATIVO_NA_CONFIGURACAO
            ):
                raise ValueError("perigo excluido exige estado explicito")
            if self.motivos_indisponibilidade:
                raise ValueError("exclusao por configuracao nao e indisponibilidade")
            return self

        if self.peso <= 0:
            raise ValueError("participante exige peso positivo")
        if self.elegivel:
            if self.indice_perigo is None or self.classificacao_perigo is None:
                raise ValueError("participante elegivel exige indice e classificacao")
            if not self.qualidade_suficiente:
                raise ValueError("participante elegivel exige qualidade suficiente")
            esperado = self.indice_perigo * self.peso
            if self.contribuicao is None or not math.isclose(
                self.contribuicao,
                esperado,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("contribuicao diverge do indice e peso")
            if self.tipo_nao_contribuicao is not None:
                raise ValueError("participante elegivel nao possui nao contribuicao")
            if self.motivos_indisponibilidade:
                raise ValueError("participante elegivel nao possui indisponibilidade")
        else:
            if self.contribuicao is not None:
                raise ValueError("participante indisponivel nao fabrica contribuicao")
            if self.tipo_nao_contribuicao != TipoNaoContribuicaoScore.DADO_INSUFICIENTE:
                raise ValueError("participante indisponivel exige estado explicito")
            if not self.motivos_indisponibilidade:
                raise ValueError("participante indisponivel exige motivo explicito")
        return self


class ResultadoScoreExposicaoMaquinario(ModeloDominio):
    id_fazenda: str | None = None
    politica_id: str = Field(min_length=1)
    politica_versao: str = Field(min_length=1)
    janela: JanelaHistorica
    score: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None
    qualidade_suficiente: bool
    score_publicavel: bool
    contribuicoes: tuple[ContribuicaoPerigoScore, ...] = Field(
        min_length=5,
        max_length=5,
    )
    soma_pesos: float = Field(ge=0, le=1)
    perigos_participantes: tuple[PerigoExposicao, ...]
    perigos_excluidos: tuple[PerigoExposicao, ...]
    perigos_indisponiveis: tuple[PerigoExposicao, ...]
    avisos_metodologicos: tuple[str, ...]
    metodologia: str = Field(default=METODOLOGIA_SCORE_EXPOSICAO, min_length=1)
    disclaimer: str = Field(default=DISCLAIMER_SCORE_EXPOSICAO, min_length=1)
    versao: str = Field(default=SCORE_EXPOSICAO_VERSION, min_length=1)

    @model_validator(mode="after")
    def validar_resultado(self) -> "ResultadoScoreExposicaoMaquinario":
        perigos = tuple(item.perigo for item in self.contribuicoes)
        if perigos != tuple(PerigoExposicao):
            raise ValueError("contribuicoes devem conter os cinco perigos em ordem")

        participantes = tuple(
            item.perigo for item in self.contribuicoes if item.participa_score
        )
        excluidos = tuple(
            item.perigo for item in self.contribuicoes if not item.participa_score
        )
        indisponiveis = tuple(
            item.perigo
            for item in self.contribuicoes
            if item.participa_score and not item.elegivel
        )
        if self.perigos_participantes != participantes:
            raise ValueError("lista de perigos participantes incoerente")
        if self.perigos_excluidos != excluidos:
            raise ValueError("lista de perigos excluidos incoerente")
        if self.perigos_indisponiveis != indisponiveis:
            raise ValueError("lista de perigos indisponiveis incoerente")

        soma = math.fsum(
            item.peso for item in self.contribuicoes if item.participa_score
        )
        if not math.isclose(soma, self.soma_pesos, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("soma de pesos diverge das contribuicoes")
        if not math.isclose(soma, 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("pesos dos participantes devem somar 1.0")

        if indisponiveis:
            if self.score is not None or self.classificacao is not None:
                raise ValueError("score parcial nao pode ser publicado")
            if self.qualidade_suficiente or self.score_publicavel:
                raise ValueError("indisponibilidade exige qualidade insuficiente")
        else:
            contribuicoes = tuple(
                item.contribuicao for item in self.contribuicoes if item.participa_score
            )
            if any(valor is None for valor in contribuicoes):
                raise ValueError("participantes elegiveis exigem contribuicoes")
            esperado = math.fsum(valor for valor in contribuicoes if valor is not None)
            if self.score is None or not math.isclose(
                self.score,
                esperado,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("score diverge da soma das contribuicoes")
            if self.classificacao is None:
                raise ValueError("score disponivel exige classificacao")
            if not self.qualidade_suficiente or not self.score_publicavel:
                raise ValueError("score completo deve ser publicavel")
        return self

    def contribuicao_de(self, perigo: PerigoExposicao) -> ContribuicaoPerigoScore:
        for contribuicao in self.contribuicoes:
            if contribuicao.perigo == perigo:
                return contribuicao
        raise KeyError(perigo)


def _resultados_por_perigo(
    validacao: ResultadoValidacaoIntegradaPerigos,
) -> dict[PerigoExposicao, object]:
    return {
        PerigoExposicao.EXPOSICAO_HIDRICA: validacao.exposicao_hidrica,
        PerigoExposicao.TRAFEGABILIDADE: validacao.trafegabilidade,
        PerigoExposicao.INSTABILIDADE: validacao.instabilidade,
        PerigoExposicao.INCENDIO: validacao.propagacao_fogo,
        PerigoExposicao.TEMPESTADES: validacao.tempestade,
    }


def _motivos_indisponibilidade(
    agregacao: object,
) -> tuple[MotivoIndisponibilidadeScore, ...]:
    motivos: list[MotivoIndisponibilidadeScore] = []
    if agregacao.indice_agregado is None:
        motivos.append(MotivoIndisponibilidadeScore.INDICE_AGREGADO_AUSENTE)
    if agregacao.classificacao_agregada is None:
        motivos.append(MotivoIndisponibilidadeScore.CLASSIFICACAO_AGREGADA_AUSENTE)
    if not agregacao.qualidade_suficiente:
        motivos.append(MotivoIndisponibilidadeScore.QUALIDADE_INSUFICIENTE)
    if agregacao.cobertura_percentual < agregacao.cobertura_minima_percentual:
        motivos.append(MotivoIndisponibilidadeScore.COBERTURA_ABAIXO_DA_POLITICA)
    return tuple(motivos)


def calcular_score_exposicao_maquinario(
    validacao: ResultadoValidacaoIntegradaPerigos,
    composicao: PoliticaComposicaoScore,
    politica: PoliticaExposicaoEquipamentos,
) -> ResultadoScoreExposicaoMaquinario:
    """Calcula um score completo, ou nenhum score quando faltar participante."""

    if not isinstance(validacao, ResultadoValidacaoIntegradaPerigos):
        raise TypeError("validacao deve ser ResultadoValidacaoIntegradaPerigos")
    if not isinstance(composicao, PoliticaComposicaoScore):
        raise TypeError("composicao deve ser PoliticaComposicaoScore")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")

    # Revalida inclusive objetos produzidos por model_copy/model_construct antes
    # de usar os resultados no score.
    validacao = ResultadoValidacaoIntegradaPerigos.model_validate(
        validacao.model_dump()
    )
    composicao = PoliticaComposicaoScore.model_validate(composicao.model_dump())
    politica = PoliticaExposicaoEquipamentos.model_validate(politica.model_dump())

    if politica.id_politica != validacao.politica_id:
        raise ValueError("politica base diverge da validacao integrada")
    if politica.id_politica != composicao.politica_id:
        raise ValueError("politica base diverge da composicao")
    if validacao.janela.dias_esperados != politica.janela_historica_dias:
        raise ValueError("janela diverge da duracao definida pela politica")

    resultados = _resultados_por_perigo(validacao)
    contribuicoes: list[ContribuicaoPerigoScore] = []
    for configuracao in composicao.configuracoes:
        resultado = resultados[configuracao.perigo]
        agregacao = resultado.agregacao_90d
        if resultado.janela_analisada != validacao.janela:
            raise ValueError("janela do perigo diverge da validacao integrada")
        if resultado.politica_id != politica.id_politica:
            raise ValueError("politica do perigo diverge da politica base")
        if not math.isclose(
            agregacao.cobertura_minima_percentual,
            politica.parametros_normalizacao_90d.cobertura_minima_percentual,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("cobertura minima do perigo diverge da politica base")
        if (
            agregacao.indice_agregado is not None
            and agregacao.classificacao_agregada
            != politica.classificar_indice(agregacao.indice_agregado)
        ):
            raise ValueError("classificacao do perigo diverge da politica base")
        if not math.isclose(
            configuracao.peso,
            politica.pesos_perigos.peso(configuracao.perigo),
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("peso diverge da politica base")

        if not configuracao.participa_score:
            contribuicoes.append(
                ContribuicaoPerigoScore(
                    perigo=configuracao.perigo,
                    indice_perigo=agregacao.indice_agregado,
                    classificacao_perigo=agregacao.classificacao_agregada,
                    peso=configuracao.peso,
                    participa_score=False,
                    elegivel=False,
                    contribuicao=0.0,
                    cobertura_percentual=agregacao.cobertura_percentual,
                    cobertura_minima_percentual=agregacao.cobertura_minima_percentual,
                    qualidade_suficiente=agregacao.qualidade_suficiente,
                    tipo_nao_contribuicao=TipoNaoContribuicaoScore.INATIVO_NA_CONFIGURACAO,
                )
            )
            continue

        motivos = _motivos_indisponibilidade(agregacao)
        elegivel = not motivos
        contribuicoes.append(
            ContribuicaoPerigoScore(
                perigo=configuracao.perigo,
                indice_perigo=agregacao.indice_agregado,
                classificacao_perigo=agregacao.classificacao_agregada,
                peso=configuracao.peso,
                participa_score=True,
                elegivel=elegivel,
                contribuicao=(
                    agregacao.indice_agregado * configuracao.peso if elegivel else None
                ),
                cobertura_percentual=agregacao.cobertura_percentual,
                cobertura_minima_percentual=agregacao.cobertura_minima_percentual,
                qualidade_suficiente=agregacao.qualidade_suficiente,
                tipo_nao_contribuicao=(
                    None if elegivel else TipoNaoContribuicaoScore.DADO_INSUFICIENTE
                ),
                motivos_indisponibilidade=motivos,
            )
        )

    indisponiveis = tuple(
        item.perigo
        for item in contribuicoes
        if item.participa_score and not item.elegivel
    )
    score = (
        None
        if indisponiveis
        else math.fsum(
            item.contribuicao
            for item in contribuicoes
            if item.participa_score and item.contribuicao is not None
        )
    )
    if score is not None and not 0 <= score <= 100:
        raise ValueError("score calculado fora do dominio 0..100")

    return ResultadoScoreExposicaoMaquinario(
        id_fazenda=validacao.id_fazenda,
        politica_id=politica.id_politica,
        politica_versao=politica.versao,
        janela=validacao.janela,
        score=score,
        classificacao=(
            politica.classificar_indice(score) if score is not None else None
        ),
        qualidade_suficiente=not indisponiveis,
        score_publicavel=not indisponiveis,
        contribuicoes=tuple(contribuicoes),
        soma_pesos=composicao.soma_pesos,
        perigos_participantes=tuple(
            item.perigo for item in contribuicoes if item.participa_score
        ),
        perigos_excluidos=tuple(
            item.perigo for item in contribuicoes if not item.participa_score
        ),
        perigos_indisponiveis=indisponiveis,
        avisos_metodologicos=tuple(
            dict.fromkeys((*validacao.avisos, composicao.descricao))
        ),
    )


__all__ = [
    "DISCLAIMER_SCORE_EXPOSICAO",
    "METODOLOGIA_SCORE_EXPOSICAO",
    "SCORE_EXPOSICAO_VERSION",
    "ContribuicaoPerigoScore",
    "MotivoIndisponibilidadeScore",
    "ResultadoScoreExposicaoMaquinario",
    "TipoNaoContribuicaoScore",
    "calcular_score_exposicao_maquinario",
]
