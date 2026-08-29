"""Núcleo meteorológico interno da Exposição Hídrica.

Os parâmetros são demonstrativos da política AgriShield. Nesta versão não há
modificador territorial: valores SRTM/MERIT permanecem evidências brutas sem
uma suscetibilidade normalizada aprovada. Trafegabilidade não reutiliza mais
este núcleo; tem metodologia própria em `perigo_trafegabilidade.py`.
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
from backend.exposicao.features_diarias import (
    FeatureDiariaCompartilhada,
    FeaturesDiariasCompartilhadas,
)
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.politica import (
    ParametrosCondicaoHidrica,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import ModeloDominio


PERIGOS_HIDRICOS_VERSION = "exposicao-perigos-hidricos-v1"
DIAS_CONTEXTO_HIDRICO = 7
# Aquisição futura para duas janelas: 7 dias de warm-up + 180 dias analisados.
DIAS_AQUISICAO_DUAS_JANELAS_90D = 187
METODOLOGIA_METEOROLOGICA = "CONDICAO_HIDRICA_METEOROLOGICA_SEM_CONTEXTO_TERRITORIAL"
LIMITACAO_TERRITORIAL = (
    "Índice meteorológico: declividade, posição topográfica, distância à drenagem "
    "e área a montante ainda não possuem suscetibilidade normalizada aprovada."
)
GRUPO_DEPENDENCIA_HIDRICA = "NUCLEO_HIDRICO_METEOROLOGICO_COMPARTILHADO_V1"
AVISO_DEPENDENCIA_HIDRICA = (
    "Exposição hídrica e trafegabilidade compartilham o mesmo núcleo meteorológico "
    "nesta versão, ainda sem diferenciação por território ou solo; não devem ser "
    "combinadas como evidências independentes e uma composição futura deve impedir "
    "dupla contagem enquanto permanecerem equivalentes por construção."
)


class CondicaoHidricaDiaria(ModeloDominio):
    data: date
    indice_chuva_atual: float | None = Field(default=None, ge=0, le=100)
    indice_d1_d3: float | None = Field(default=None, ge=0, le=100)
    indice_d4_d7: float | None = Field(default=None, ge=0, le=100)
    multiplicador_persistencia: float | None = Field(default=None, gt=0)
    indice_antecedente: float | None = Field(default=None, ge=0, le=100)
    indice_hidrico_meteorologico: float | None = Field(default=None, ge=0, le=100)


class ResultadoPerigoHidricoOperacional(ModeloDominio):
    perigo: PerigoExposicao
    periodo_features: JanelaHistorica
    janela_analisada: JanelaHistorica
    dias_contexto_calendario: int = Field(ge=0, le=DIAS_CONTEXTO_HIDRICO)
    condicoes_hidricas: tuple[CondicaoHidricaDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_condicao_hidrica: ParametrosCondicaoHidrica
    metodologia: str = METODOLOGIA_METEOROLOGICA
    contexto_territorial_aplicado: bool = False
    limitacao_territorial: str = LIMITACAO_TERRITORIAL
    grupo_dependencia: str = GRUPO_DEPENDENCIA_HIDRICA
    nucleo_meteorologico_compartilhado: bool = True
    evidencia_independente: bool = False
    aviso_dependencia: str = AVISO_DEPENDENCIA_HIDRICA
    versao: str = PERIGOS_HIDRICOS_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoPerigoHidricoOperacional":
        if self.perigo not in {
            PerigoExposicao.EXPOSICAO_HIDRICA,
            PerigoExposicao.TRAFEGABILIDADE,
        }:
            raise ValueError(
                "resultado aceita somente os dois perigos hídricos da fase"
            )
        if self.contexto_territorial_aplicado:
            raise ValueError("esta versão não aplica contexto territorial")
        if not self.limitacao_territorial.strip():
            raise ValueError("limitação territorial deve permanecer explícita")
        if self.grupo_dependencia != GRUPO_DEPENDENCIA_HIDRICA:
            raise ValueError("grupo de dependência hídrica deve permanecer explícito")
        if not self.nucleo_meteorologico_compartilhado or self.evidencia_independente:
            raise ValueError("resultados hídricos desta versão não são independentes")
        if not self.aviso_dependencia.strip():
            raise ValueError("dependência entre os perigos deve permanecer documentada")
        if not (
            self.periodo_features.inicio <= self.janela_analisada.inicio
            and self.janela_analisada.fim <= self.periodo_features.fim
        ):
            raise ValueError(
                "janela analisada deve estar contida no período das features"
            )
        contexto_esperado = min(
            DIAS_CONTEXTO_HIDRICO,
            (self.janela_analisada.inicio - self.periodo_features.inicio).days,
        )
        if self.dias_contexto_calendario != contexto_esperado:
            raise ValueError("quantidade de dias de contexto calendário incoerente")
        if self.indices_diarios.periodo != self.janela_analisada:
            raise ValueError("índices devem representar somente a janela analisada")
        if self.politica_id != self.indices_diarios.politica_id:
            raise ValueError("política dos índices diários é incoerente")
        if self.politica_id != self.agregacao_90d.politica_id:
            raise ValueError("política da agregação é incoerente")
        if (
            self.agregacao_90d.inicio != self.indices_diarios.periodo.inicio
            or self.agregacao_90d.fim != self.indices_diarios.periodo.fim
        ):
            raise ValueError("agregação e índices devem compartilhar o período")
        if tuple(item.data for item in self.condicoes_hidricas) != tuple(
            item.data for item in self.indices_diarios.indices
        ):
            raise ValueError("condições e índices devem compartilhar o calendário")
        return self


def normalizar_precipitacao(
    precipitacao_mm: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    """Aplica interpolação linear na curva demonstrativa configurada."""

    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    if precipitacao_mm is None:
        return None
    if isinstance(precipitacao_mm, bool) or not isinstance(
        precipitacao_mm, (int, float)
    ):
        raise TypeError("precipitação deve ser numérica")
    if not math.isfinite(precipitacao_mm) or precipitacao_mm < 0:
        raise ValueError("precipitação deve ser finita e não negativa")
    pontos = politica.parametros_condicao_hidrica.curva_precipitacao
    if precipitacao_mm <= pontos[0].precipitacao_mm:
        return pontos[0].indice
    for inferior, superior in zip(pontos, pontos[1:]):
        if precipitacao_mm <= superior.precipitacao_mm:
            proporcao = (precipitacao_mm - inferior.precipitacao_mm) / (
                superior.precipitacao_mm - inferior.precipitacao_mm
            )
            return inferior.indice + proporcao * (superior.indice - inferior.indice)
    return pontos[-1].indice


def _multiplicador_persistencia(
    dias_consecutivos: int | None,
    parametros: ParametrosCondicaoHidrica,
) -> float | None:
    if dias_consecutivos is None:
        return None
    if dias_consecutivos <= 1:
        return parametros.multiplicador_persistencia_0_1_dia
    if dias_consecutivos <= 3:
        return parametros.multiplicador_persistencia_2_3_dias
    return parametros.multiplicador_persistencia_4_mais_dias


def calcular_condicao_hidrica_diaria(
    feature: FeatureDiariaCompartilhada,
    politica: PoliticaExposicaoEquipamentos,
) -> CondicaoHidricaDiaria:
    """Combina somente os blocos não sobrepostos produzidos na Fase 2."""

    if not isinstance(feature, FeatureDiariaCompartilhada):
        raise TypeError("feature deve ser uma FeatureDiariaCompartilhada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")

    parametros = politica.parametros_condicao_hidrica
    indice_atual = normalizar_precipitacao(feature.precipitacao_d0, politica)
    indice_d1_d3 = normalizar_precipitacao(feature.precipitacao_d1_d3, politica)
    indice_d4_d7 = normalizar_precipitacao(feature.precipitacao_d4_d7, politica)
    multiplicador = _multiplicador_persistencia(
        feature.dias_consecutivos_com_chuva,
        parametros,
    )

    antecedente: float | None = None
    if (
        indice_d1_d3 is not None
        and indice_d4_d7 is not None
        and multiplicador is not None
    ):
        antecedente_base = (
            indice_d1_d3 * parametros.peso_antecedente_d1_d3
            + indice_d4_d7 * parametros.peso_antecedente_d4_d7
        )
        antecedente = min(antecedente_base * multiplicador, 100.0)

    indice_hidrico: float | None = None
    if indice_atual is not None and antecedente is not None:
        indice_hidrico = min(
            indice_atual * parametros.peso_chuva_atual
            + antecedente * parametros.peso_chuva_antecedente,
            100.0,
        )

    return CondicaoHidricaDiaria(
        data=feature.data,
        indice_chuva_atual=indice_atual,
        indice_d1_d3=indice_d1_d3,
        indice_d4_d7=indice_d4_d7,
        multiplicador_persistencia=multiplicador,
        indice_antecedente=antecedente,
        indice_hidrico_meteorologico=indice_hidrico,
    )


def calcular_condicoes_hidricas(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    janela_alvo: JanelaHistorica | None = None,
) -> tuple[CondicaoHidricaDiaria, ...]:
    if not isinstance(features, FeaturesDiariasCompartilhadas):
        raise TypeError("features deve ser FeaturesDiariasCompartilhadas")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    alvo = janela_alvo or features.periodo
    if not isinstance(alvo, JanelaHistorica):
        raise TypeError("janela_alvo deve ser uma JanelaHistorica")
    if alvo.dias_esperados != politica.janela_historica_dias:
        raise ValueError("janela deve possuir a duração definida pela política")
    if not (
        features.periodo.inicio <= alvo.inicio and alvo.fim <= features.periodo.fim
    ):
        raise ValueError("janela alvo deve estar contida no período das features")
    return tuple(
        calcular_condicao_hidrica_diaria(feature, politica)
        for feature in features.dias
        if alvo.inicio <= feature.data <= alvo.fim
    )


def _calcular_perigo_hidrico(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    perigo: PerigoExposicao,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoPerigoHidricoOperacional:
    alvo = janela_alvo or features.periodo
    condicoes = calcular_condicoes_hidricas(features, politica, alvo)
    valores = tuple(
        ValorIndiceDiario(
            data=condicao.data,
            indice=condicao.indice_hidrico_meteorologico,
        )
        for condicao in condicoes
    )
    indices = criar_indices_diarios(alvo, valores, politica)
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoPerigoHidricoOperacional(
        perigo=perigo,
        periodo_features=features.periodo,
        janela_analisada=alvo,
        dias_contexto_calendario=min(
            DIAS_CONTEXTO_HIDRICO,
            (alvo.inicio - features.periodo.inicio).days,
        ),
        condicoes_hidricas=condicoes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_condicao_hidrica=politica.parametros_condicao_hidrica,
    )


def calcular_condicao_hidrica_meteorologica(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoPerigoHidricoOperacional:
    """Agrega o núcleo meteorológico interno, sem promovê-lo a perigo oficial."""

    return _calcular_perigo_hidrico(
        features,
        politica,
        PerigoExposicao.EXPOSICAO_HIDRICA,
        janela_alvo,
    )


__all__ = [
    "AVISO_DEPENDENCIA_HIDRICA",
    "DIAS_AQUISICAO_DUAS_JANELAS_90D",
    "DIAS_CONTEXTO_HIDRICO",
    "GRUPO_DEPENDENCIA_HIDRICA",
    "PERIGOS_HIDRICOS_VERSION",
    "CondicaoHidricaDiaria",
    "ResultadoPerigoHidricoOperacional",
    "calcular_condicao_hidrica_diaria",
    "calcular_condicoes_hidricas",
    "calcular_condicao_hidrica_meteorologica",
    "normalizar_precipitacao",
]
