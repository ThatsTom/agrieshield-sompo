"""Orquestracao deterministica da avaliacao AGRISHIELD-EQUIP em duas janelas."""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import Field, model_validator

from backend.exposicao.comparacao_score import (
    ResultadoComparacaoScoreExposicao90d,
    comparar_scores_exposicao_90d,
)
from backend.exposicao.composicao_score import (
    PoliticaComposicaoScore,
    criar_politica_composicao_score,
)
from backend.exposicao.features_diarias import (
    FeaturesDiariasCompartilhadas,
    calcular_features_diarias_compartilhadas,
)
from backend.exposicao.modelos import (
    IntervaloTemporalHistorico,
    JanelaHistorica,
    QualidadeHistorica,
    ReferenciaTemporalHistorica,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
)
from backend.exposicao.perigos_hidricos import (
    DIAS_AQUISICAO_DUAS_JANELAS_90D,
)
from backend.exposicao.politica import PoliticaExposicaoEquipamentos
from backend.exposicao.score_exposicao import (
    ResultadoScoreExposicaoMaquinario,
    calcular_score_exposicao_maquinario,
)
from backend.exposicao.validacao_integrada import (
    ResultadoValidacaoIntegradaPerigos,
    validar_cinco_perigos,
)
from backend.risco.modelos import (
    AnaliseGeoespacialNormalizada,
    FonteDado,
    ModeloDominio,
)


AVALIACAO_EXPOSICAO_VERSION = "exposicao-avaliacao-duas-janelas-v1"
METODOLOGIA_AVALIACAO_EXPOSICAO = "ORQUESTRACAO_EXPOSICAO_MAQUINARIO_90D_V1"
DIAS_ANALISE_DUAS_JANELAS = 180
DIAS_CONTEXTO_ESPERADOS = DIAS_AQUISICAO_DUAS_JANELAS_90D - DIAS_ANALISE_DUAS_JANELAS
AVISO_WARMUP_INCOMPLETO = "WARMUP_ANTECEDENTE_INCOMPLETO"


class ResultadoAvaliacaoExposicaoMaquinario(ModeloDominio):
    id_fazenda: str | None = None
    politica_id: str = Field(min_length=1)
    fonte_meteorologica: FonteDado
    tipo_produto: TipoProdutoHistorico
    dataset: str = Field(min_length=1)
    referencia_temporal: ReferenciaTemporalHistorica
    data_referencia: date
    periodo_aquisicao: JanelaHistorica
    periodo_efetivo: IntervaloTemporalHistorico | None = None
    qualidade_aquisicao: QualidadeHistorica
    periodo_features: JanelaHistorica
    janela_anterior: JanelaHistorica
    janela_atual: JanelaHistorica
    dias_contexto_esperados: int = Field(ge=0)
    dias_contexto_disponiveis: int = Field(ge=0)
    warmup_completo: bool
    features_compartilhadas: FeaturesDiariasCompartilhadas
    politica_composicao: PoliticaComposicaoScore
    validacao_anterior: ResultadoValidacaoIntegradaPerigos
    score_anterior: ResultadoScoreExposicaoMaquinario
    validacao_atual: ResultadoValidacaoIntegradaPerigos
    score_atual: ResultadoScoreExposicaoMaquinario
    comparacao: ResultadoComparacaoScoreExposicao90d
    avaliacao_publicavel: bool
    avisos_metodologicos: tuple[str, ...]
    metodologia: str = Field(default=METODOLOGIA_AVALIACAO_EXPOSICAO, min_length=1)
    versao: str = Field(default=AVALIACAO_EXPOSICAO_VERSION, min_length=1)

    @model_validator(mode="after")
    def validar_resultado(self) -> "ResultadoAvaliacaoExposicaoMaquinario":
        if self.data_referencia != self.periodo_aquisicao.data_referencia:
            raise ValueError("data de referencia diverge do periodo de aquisicao")
        if self.periodo_features != self.features_compartilhadas.periodo:
            raise ValueError("periodo de features diverge das features compartilhadas")
        if self.periodo_aquisicao != self.periodo_features:
            raise ValueError("aquisicao e features devem compartilhar o periodo")
        if (
            self.qualidade_aquisicao.dias_esperados
            != self.periodo_aquisicao.dias_esperados
        ):
            raise ValueError("qualidade diverge do periodo de aquisicao")
        if self.dias_contexto_esperados != DIAS_CONTEXTO_ESPERADOS:
            raise ValueError("orquestracao v1 exige sete dias de contexto")
        if self.dias_contexto_disponiveis > self.dias_contexto_esperados:
            raise ValueError("contexto disponivel nao pode exceder o esperado")
        if self.warmup_completo != (
            self.dias_contexto_disponiveis == self.dias_contexto_esperados
        ):
            raise ValueError("estado do warm-up diverge da disponibilidade")
        if (
            not self.warmup_completo
            and AVISO_WARMUP_INCOMPLETO not in self.avisos_metodologicos
        ):
            raise ValueError("warm-up incompleto exige aviso explicito")

        if self.features_compartilhadas.fonte != self.fonte_meteorologica:
            raise ValueError("fonte das features diverge da avaliacao")
        if self.features_compartilhadas.tipo_produto != self.tipo_produto:
            raise ValueError("produto das features diverge da avaliacao")
        if self.features_compartilhadas.dataset != self.dataset:
            raise ValueError("dataset das features diverge da avaliacao")
        if self.features_compartilhadas.referencia_temporal != self.referencia_temporal:
            raise ValueError("referencia temporal das features diverge da avaliacao")
        if self.features_compartilhadas.id_fazenda != self.id_fazenda:
            raise ValueError("identidade da fazenda diverge das features")

        for validacao, score, janela in (
            (self.validacao_anterior, self.score_anterior, self.janela_anterior),
            (self.validacao_atual, self.score_atual, self.janela_atual),
        ):
            if validacao.janela != janela or score.janela != janela:
                raise ValueError("subresultado diverge da janela da avaliacao")
            if (
                validacao.politica_id != self.politica_id
                or score.politica_id != self.politica_id
            ):
                raise ValueError("politica diverge entre os subresultados")
            if validacao.fonte_meteorologica != self.fonte_meteorologica:
                raise ValueError("fonte meteorologica diverge entre as janelas")
            if (
                validacao.id_fazenda != self.id_fazenda
                or score.id_fazenda != self.id_fazenda
            ):
                raise ValueError("fazenda diverge entre os subresultados")
        if self.politica_composicao.politica_id != self.politica_id:
            raise ValueError("politica de composicao diverge da avaliacao")
        for score in (self.score_anterior, self.score_atual):
            for configuracao, contribuicao in zip(
                self.politica_composicao.configuracoes,
                score.contribuicoes,
            ):
                if (
                    configuracao.perigo != contribuicao.perigo
                    or configuracao.peso != contribuicao.peso
                    or configuracao.participa_score != contribuicao.participa_score
                ):
                    raise ValueError("score diverge da politica de composicao unica")

        if (
            self.comparacao.janela_anterior != self.janela_anterior
            or self.comparacao.janela_atual != self.janela_atual
            or self.comparacao.score_anterior != self.score_anterior.score
            or self.comparacao.classificacao_anterior
            != self.score_anterior.classificacao
            or self.comparacao.score_atual != self.score_atual.score
            or self.comparacao.classificacao_atual != self.score_atual.classificacao
        ):
            raise ValueError("comparacao diverge dos scores da avaliacao")
        publicavel = (
            self.score_anterior.score_publicavel
            and self.score_atual.score_publicavel
            and self.comparacao.comparacao_publicavel
        )
        if self.avaliacao_publicavel != publicavel:
            raise ValueError("publicabilidade final incoerente")
        return self


def _contar_contexto_disponivel(
    serie: SerieHistoricaFonte,
    janela_anterior: JanelaHistorica,
) -> int:
    inicio_contexto = janela_anterior.inicio - timedelta(days=DIAS_CONTEXTO_ESPERADOS)
    fim_contexto = janela_anterior.inicio - timedelta(days=1)
    precipitacao_por_data = {
        registro.data: registro.precipitacao_mm for registro in serie.registros
    }
    return sum(
        precipitacao_por_data.get(inicio_contexto + timedelta(days=indice)) is not None
        for indice in range((fim_contexto - inicio_contexto).days + 1)
    )


def executar_avaliacao_exposicao_maquinario(
    serie: SerieHistoricaFonte,
    contexto_territorial: AnaliseGeoespacialNormalizada,
    politica: PoliticaExposicaoEquipamentos,
) -> ResultadoAvaliacaoExposicaoMaquinario:
    """Encadeia componentes existentes para duas janelas, sem adquirir dados."""

    if not isinstance(serie, SerieHistoricaFonte):
        raise TypeError("serie deve ser SerieHistoricaFonte")
    if not isinstance(contexto_territorial, AnaliseGeoespacialNormalizada):
        raise TypeError("contexto_territorial deve ser AnaliseGeoespacialNormalizada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    serie = SerieHistoricaFonte.model_validate(serie.model_dump())
    contexto_territorial = AnaliseGeoespacialNormalizada.model_validate(
        contexto_territorial.model_dump()
    )
    politica = PoliticaExposicaoEquipamentos.model_validate(politica.model_dump())

    if politica.janela_historica_dias != 90 or politica.comparacao_anterior_dias != 90:
        raise ValueError("orquestracao v1 exige duas janelas de 90 dias")
    periodo_analise = JanelaHistorica.criar_atual(
        serie.periodo_solicitado.data_referencia,
        dias=DIAS_ANALISE_DUAS_JANELAS,
    )
    janela_anterior, janela_atual = periodo_analise.dividir_em_periodos_90()
    if (
        serie.periodo_solicitado.inicio > janela_anterior.inicio
        or serie.periodo_solicitado.fim < janela_atual.fim
    ):
        raise ValueError("periodo fornecido nao cobre as duas janelas de 90 dias")

    features = calcular_features_diarias_compartilhadas(serie)
    validacao_anterior = validar_cinco_perigos(
        features,
        contexto_territorial,
        politica,
        janela_alvo=janela_anterior,
    )
    validacao_atual = validar_cinco_perigos(
        features,
        contexto_territorial,
        politica,
        janela_alvo=janela_atual,
    )
    composicao = criar_politica_composicao_score(politica)
    score_anterior = calcular_score_exposicao_maquinario(
        validacao_anterior,
        composicao,
        politica,
    )
    score_atual = calcular_score_exposicao_maquinario(
        validacao_atual,
        composicao,
        politica,
    )
    comparacao = comparar_scores_exposicao_90d(score_anterior, score_atual)

    dias_contexto_disponiveis = _contar_contexto_disponivel(
        serie,
        janela_anterior,
    )
    warmup_completo = dias_contexto_disponiveis == DIAS_CONTEXTO_ESPERADOS
    avisos = tuple(
        dict.fromkeys(
            (
                *validacao_anterior.avisos,
                *validacao_atual.avisos,
                composicao.descricao,
                *((AVISO_WARMUP_INCOMPLETO,) if not warmup_completo else ()),
            )
        )
    )
    return ResultadoAvaliacaoExposicaoMaquinario(
        id_fazenda=serie.id_fazenda,
        politica_id=politica.id_politica,
        fonte_meteorologica=serie.fonte,
        tipo_produto=serie.tipo_produto,
        dataset=serie.dataset,
        referencia_temporal=serie.referencia_temporal,
        data_referencia=serie.periodo_solicitado.data_referencia,
        periodo_aquisicao=serie.periodo_solicitado,
        periodo_efetivo=serie.periodo_efetivo,
        qualidade_aquisicao=serie.qualidade,
        periodo_features=features.periodo,
        janela_anterior=janela_anterior,
        janela_atual=janela_atual,
        dias_contexto_esperados=DIAS_CONTEXTO_ESPERADOS,
        dias_contexto_disponiveis=dias_contexto_disponiveis,
        warmup_completo=warmup_completo,
        features_compartilhadas=features,
        politica_composicao=composicao,
        validacao_anterior=validacao_anterior,
        score_anterior=score_anterior,
        validacao_atual=validacao_atual,
        score_atual=score_atual,
        comparacao=comparacao,
        avaliacao_publicavel=(
            score_anterior.score_publicavel
            and score_atual.score_publicavel
            and comparacao.comparacao_publicavel
        ),
        avisos_metodologicos=avisos,
    )


__all__ = [
    "AVALIACAO_EXPOSICAO_VERSION",
    "AVISO_WARMUP_INCOMPLETO",
    "DIAS_ANALISE_DUAS_JANELAS",
    "DIAS_CONTEXTO_ESPERADOS",
    "METODOLOGIA_AVALIACAO_EXPOSICAO",
    "ResultadoAvaliacaoExposicaoMaquinario",
    "executar_avaliacao_exposicao_maquinario",
]
