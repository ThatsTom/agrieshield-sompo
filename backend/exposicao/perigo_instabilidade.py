"""Exposicao territorial e ambiental a instabilidade operacional.

A suscetibilidade estrutural e derivada da declividade media SRTM e permanece
como evidencia mesmo em dias secos. Somente sua combinacao com a ativacao
hidrica temporal alimenta eventos. Os parametros sao demonstrativos e nao
constituem limites operacionais universais.
"""

from __future__ import annotations

import math
from datetime import date

from pydantic import Field, model_validator

from backend.exposicao.agregacao_perigos import (
    ResultadoAgregacaoPerigo,
    SerieIndicesDiariosPerigo,
    ValorIndiceDiario,
    agregar_indice_historico,
    criar_indices_diarios,
)
from backend.exposicao.features_diarias import FeaturesDiariasCompartilhadas
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.perigos_hidricos import (
    DIAS_CONTEXTO_HIDRICO,
    CondicaoHidricaDiaria,
    calcular_condicoes_hidricas,
)
from backend.exposicao.politica import (
    ParametrosInstabilidade,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import (
    AnaliseGeoespacialNormalizada,
    AtributoGeoespacial,
    ModeloDominio,
)


PERIGO_INSTABILIDADE_VERSION = "exposicao-instabilidade-v1"
METODOLOGIA_SUSCETIBILIDADE = (
    "INTERPOLACAO_LINEAR_DA_CURVA_DE_DECLIVIDADE_DEMONSTRATIVA_V1"
)
METODOLOGIA_INSTABILIDADE = "SUSCETIBILIDADE_TOPOGRAFICA_X_ATIVACAO_HIDRICA_TEMPORAL_V1"
MOTIVO_ATIVACAO_APLICADA = "ATIVACAO_HIDRICA_APLICADA"
MOTIVO_DADO_HIDRICO_INDISPONIVEL = "DADO_HIDRICO_INDISPONIVEL"
MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL = "DADO_DECLIVIDADE_INDISPONIVEL"


class SuscetibilidadeTopografica(ModeloDominio):
    declividade_media: AtributoGeoespacial
    posicao_topografica_relativa: AtributoGeoespacial
    indice_suscetibilidade_topografica: float | None = Field(default=None, ge=0, le=100)
    posicao_topografica_aplicada_no_calculo: bool = False
    metodologia: str = METODOLOGIA_SUSCETIBILIDADE
    politica_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_contexto(self) -> "SuscetibilidadeTopografica":
        if self.declividade_media.unidade != "graus":
            raise ValueError("curva de declividade exige unidade em graus")
        if self.posicao_topografica_aplicada_no_calculo:
            raise ValueError(
                "posicao topografica relativa e somente evidencia nesta versao"
            )
        if (
            self.declividade_media.valor is None
            and self.indice_suscetibilidade_topografica is not None
        ):
            raise ValueError("declividade ausente nao pode fabricar suscetibilidade")
        if (
            self.declividade_media.valor is not None
            and self.indice_suscetibilidade_topografica is None
        ):
            raise ValueError("declividade disponivel exige suscetibilidade")
        return self


class InstabilidadeDiaria(ModeloDominio):
    data: date
    declividade_media_graus: float | None = Field(default=None, ge=0)
    posicao_topografica_relativa_m: float | None = None
    indice_suscetibilidade_topografica: float | None = Field(default=None, ge=0, le=100)
    indice_condicao_hidrica: float | None = Field(default=None, ge=0, le=100)
    fator_ativacao_hidrica: float | None = Field(default=None, ge=0, le=1)
    ativacao_hidrica_aplicada: bool
    motivo: str = Field(min_length=1)
    indice_exposicao_instabilidade: float | None = Field(default=None, ge=0, le=100)
    metodologia: str = METODOLOGIA_INSTABILIDADE
    politica_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_disponibilidade(self) -> "InstabilidadeDiaria":
        if self.indice_suscetibilidade_topografica is None:
            if self.indice_exposicao_instabilidade is not None:
                raise ValueError("suscetibilidade ausente torna o indice indisponivel")
            if self.ativacao_hidrica_aplicada:
                raise ValueError("nao ha base topografica para aplicar ativacao")
            if self.motivo != MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL:
                raise ValueError("ausencia de declividade deve permanecer explicita")
            return self

        if self.indice_condicao_hidrica is None:
            if self.fator_ativacao_hidrica is not None:
                raise ValueError("dado hidrico ausente nao possui fator de ativacao")
            if self.ativacao_hidrica_aplicada:
                raise ValueError("dado hidrico ausente nao pode aplicar ativacao")
            if self.motivo != MOTIVO_DADO_HIDRICO_INDISPONIVEL:
                raise ValueError("ausencia hidrica deve permanecer explicita")
            if self.indice_exposicao_instabilidade is not None:
                raise ValueError("sem dado hidrico a exposicao temporal e indisponivel")
        elif self.indice_exposicao_instabilidade is None:
            raise ValueError("condicao hidrica disponivel exige indice temporal")
        elif self.fator_ativacao_hidrica is None:
            raise ValueError("condicao hidrica disponivel exige fator de ativacao")
        else:
            if not self.ativacao_hidrica_aplicada:
                raise ValueError("condicao hidrica disponivel deve aplicar ativacao")
            if self.motivo != MOTIVO_ATIVACAO_APLICADA:
                raise ValueError("ativacao aplicada deve possuir motivo coerente")
            esperado = min(
                self.indice_suscetibilidade_topografica * self.fator_ativacao_hidrica,
                100.0,
            )
            if not math.isclose(
                self.indice_exposicao_instabilidade,
                esperado,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError("indice diario diverge da formula configurada")
        return self


class ResultadoExposicaoInstabilidade(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.INSTABILIDADE
    periodo_features: JanelaHistorica
    janela_analisada: JanelaHistorica
    dias_contexto_calendario: int = Field(ge=0, le=DIAS_CONTEXTO_HIDRICO)
    evidencia_geoespacial: AnaliseGeoespacialNormalizada
    suscetibilidade_topografica: SuscetibilidadeTopografica
    instabilidades_diarias: tuple[InstabilidadeDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_instabilidade: ParametrosInstabilidade
    metodologia: str = METODOLOGIA_INSTABILIDADE
    versao: str = PERIGO_INSTABILIDADE_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoExposicaoInstabilidade":
        if self.perigo != PerigoExposicao.INSTABILIDADE:
            raise ValueError("resultado aceita somente exposicao a instabilidade")
        if not (
            self.periodo_features.inicio <= self.janela_analisada.inicio
            and self.janela_analisada.fim <= self.periodo_features.fim
        ):
            raise ValueError("janela analisada deve estar contida nas features")
        contexto_esperado = min(
            DIAS_CONTEXTO_HIDRICO,
            (self.janela_analisada.inicio - self.periodo_features.inicio).days,
        )
        if self.dias_contexto_calendario != contexto_esperado:
            raise ValueError("quantidade de dias de contexto incoerente")
        if self.indices_diarios.periodo != self.janela_analisada:
            raise ValueError("indices devem representar a janela analisada")
        if (
            self.agregacao_90d.inicio != self.janela_analisada.inicio
            or self.agregacao_90d.fim != self.janela_analisada.fim
        ):
            raise ValueError("agregacao deve representar a janela analisada")
        if (
            self.suscetibilidade_topografica.declividade_media
            != self.evidencia_geoespacial.declividade_media_graus
            or self.suscetibilidade_topografica.posicao_topografica_relativa
            != self.evidencia_geoespacial.posicao_topografica_relativa_m
        ):
            raise ValueError("suscetibilidade diverge da evidencia geoespacial")
        if any(
            id_resultado != self.politica_id
            for id_resultado in (
                self.indices_diarios.politica_id,
                self.agregacao_90d.politica_id,
                self.suscetibilidade_topografica.politica_id,
            )
        ) or not all(
            item.politica_id == self.politica_id for item in self.instabilidades_diarias
        ):
            raise ValueError("politica incoerente no resultado")
        if tuple(item.data for item in self.instabilidades_diarias) != tuple(
            item.data for item in self.indices_diarios.indices
        ):
            raise ValueError("detalhes e indices devem compartilhar o calendario")
        for item in self.instabilidades_diarias:
            if (
                item.declividade_media_graus
                != self.suscetibilidade_topografica.declividade_media.valor
                or item.posicao_topografica_relativa_m
                != self.suscetibilidade_topografica.posicao_topografica_relativa.valor
                or item.indice_suscetibilidade_topografica
                != self.suscetibilidade_topografica.indice_suscetibilidade_topografica
            ):
                raise ValueError("detalhe diario diverge da suscetibilidade estrutural")
        return self


def normalizar_declividade(
    declividade_graus: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    """Interpola a curva demonstrativa configurada, sem inferir terreno ausente."""

    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    if declividade_graus is None:
        return None
    if isinstance(declividade_graus, bool) or not isinstance(
        declividade_graus, (int, float)
    ):
        raise TypeError("declividade deve ser numerica")
    if not math.isfinite(declividade_graus) or declividade_graus < 0:
        raise ValueError("declividade deve ser finita e nao negativa")

    pontos = politica.parametros_instabilidade.curva_declividade
    if declividade_graus <= pontos[0].declividade_graus:
        return pontos[0].indice
    for inferior, superior in zip(pontos, pontos[1:]):
        if declividade_graus <= superior.declividade_graus:
            proporcao = (declividade_graus - inferior.declividade_graus) / (
                superior.declividade_graus - inferior.declividade_graus
            )
            return inferior.indice + proporcao * (superior.indice - inferior.indice)
    return pontos[-1].indice


def obter_fator_ativacao_hidrica(
    indice_condicao_hidrica: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    if indice_condicao_hidrica is None:
        return None
    if isinstance(indice_condicao_hidrica, bool) or not isinstance(
        indice_condicao_hidrica, (int, float)
    ):
        raise TypeError("indice hidrico deve ser numerico")
    if (
        not math.isfinite(indice_condicao_hidrica)
        or not 0 <= indice_condicao_hidrica <= 100
    ):
        raise ValueError("indice hidrico deve estar entre zero e cem")

    selecionada = politica.parametros_instabilidade.faixas_ativacao_hidrica[0]
    for faixa in politica.parametros_instabilidade.faixas_ativacao_hidrica:
        if indice_condicao_hidrica < faixa.inicio_indice_hidrico:
            break
        selecionada = faixa
    return selecionada.fator_ativacao


def calcular_suscetibilidade_topografica(
    analise: AnaliseGeoespacialNormalizada,
    politica: PoliticaExposicaoEquipamentos,
) -> SuscetibilidadeTopografica:
    if not isinstance(analise, AnaliseGeoespacialNormalizada):
        raise TypeError("analise deve ser AnaliseGeoespacialNormalizada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    if analise.declividade_media_graus.unidade != "graus":
        raise ValueError("curva demonstrativa aceita somente declividade em graus")
    return SuscetibilidadeTopografica(
        declividade_media=analise.declividade_media_graus,
        posicao_topografica_relativa=analise.posicao_topografica_relativa_m,
        indice_suscetibilidade_topografica=normalizar_declividade(
            analise.declividade_media_graus.valor,
            politica,
        ),
        politica_id=politica.id_politica,
    )


def calcular_instabilidade_diaria(
    suscetibilidade: SuscetibilidadeTopografica,
    condicao_hidrica: CondicaoHidricaDiaria,
    politica: PoliticaExposicaoEquipamentos,
) -> InstabilidadeDiaria:
    if not isinstance(suscetibilidade, SuscetibilidadeTopografica):
        raise TypeError("suscetibilidade deve ser SuscetibilidadeTopografica")
    if not isinstance(condicao_hidrica, CondicaoHidricaDiaria):
        raise TypeError("condicao_hidrica deve ser CondicaoHidricaDiaria")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")

    indice_base = suscetibilidade.indice_suscetibilidade_topografica
    indice_hidrico = condicao_hidrica.indice_hidrico_meteorologico
    fator_ativacao = obter_fator_ativacao_hidrica(indice_hidrico, politica)

    if indice_base is None:
        indice_final = None
        aplicado = False
        motivo = MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL
    elif indice_hidrico is None:
        indice_final = None
        aplicado = False
        motivo = MOTIVO_DADO_HIDRICO_INDISPONIVEL
    else:
        indice_final = min(indice_base * fator_ativacao, 100.0)
        aplicado = True
        motivo = MOTIVO_ATIVACAO_APLICADA

    return InstabilidadeDiaria(
        data=condicao_hidrica.data,
        declividade_media_graus=suscetibilidade.declividade_media.valor,
        posicao_topografica_relativa_m=(
            suscetibilidade.posicao_topografica_relativa.valor
        ),
        indice_suscetibilidade_topografica=indice_base,
        indice_condicao_hidrica=indice_hidrico,
        fator_ativacao_hidrica=fator_ativacao,
        ativacao_hidrica_aplicada=aplicado,
        motivo=motivo,
        indice_exposicao_instabilidade=indice_final,
        politica_id=politica.id_politica,
    )


def calcular_exposicao_instabilidade(
    features: FeaturesDiariasCompartilhadas,
    analise_geoespacial: AnaliseGeoespacialNormalizada,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoExposicaoInstabilidade:
    """Combina relevo estrutural e o nucleo hidrico ja calculado na Fase 4."""

    if not isinstance(features, FeaturesDiariasCompartilhadas):
        raise TypeError("features deve ser FeaturesDiariasCompartilhadas")
    alvo = janela_alvo or features.periodo
    suscetibilidade = calcular_suscetibilidade_topografica(
        analise_geoespacial,
        politica,
    )
    condicoes = calcular_condicoes_hidricas(features, politica, alvo)
    detalhes = tuple(
        calcular_instabilidade_diaria(suscetibilidade, condicao, politica)
        for condicao in condicoes
    )
    indices = criar_indices_diarios(
        alvo,
        (
            ValorIndiceDiario(
                data=item.data,
                indice=item.indice_exposicao_instabilidade,
            )
            for item in detalhes
        ),
        politica,
    )
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoExposicaoInstabilidade(
        periodo_features=features.periodo,
        janela_analisada=alvo,
        dias_contexto_calendario=min(
            DIAS_CONTEXTO_HIDRICO,
            (alvo.inicio - features.periodo.inicio).days,
        ),
        evidencia_geoespacial=analise_geoespacial,
        suscetibilidade_topografica=suscetibilidade,
        instabilidades_diarias=detalhes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_instabilidade=politica.parametros_instabilidade,
    )


__all__ = [
    "METODOLOGIA_INSTABILIDADE",
    "METODOLOGIA_SUSCETIBILIDADE",
    "MOTIVO_ATIVACAO_APLICADA",
    "MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL",
    "MOTIVO_DADO_HIDRICO_INDISPONIVEL",
    "PERIGO_INSTABILIDADE_VERSION",
    "InstabilidadeDiaria",
    "ResultadoExposicaoInstabilidade",
    "SuscetibilidadeTopografica",
    "calcular_exposicao_instabilidade",
    "calcular_instabilidade_diaria",
    "calcular_suscetibilidade_topografica",
    "normalizar_declividade",
    "obter_fator_ativacao_hidrica",
]
