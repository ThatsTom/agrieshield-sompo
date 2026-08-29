"""Metodologia meteorológica própria de Trafegabilidade.

Não reutiliza o núcleo hídrico (`perigos_hidricos.py`): usa somente a
precipitação do próprio dia, o acumulado dos últimos 3 dias e uma
recuperação/secagem baseada em dias desde a última chuva relevante. Não usa
SRTM, MERIT Hydro, MapBiomas, declividade, posição topográfica, proximidade
de drenagem ou área montante.

EXPERIMENTAL — metodologia ainda não calibrada contra sinistros ou dados
reais de operação de máquinas.
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
    ParametrosTrafegabilidade,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import ModeloDominio


PERIGO_TRAFEGABILIDADE_VERSION = "exposicao-perigo-trafegabilidade-v1"
DIAS_CONTEXTO_TRAFEGABILIDADE = 7
METODOLOGIA_TRAFEGABILIDADE = (
    "COMPOSICAO_METEOROLOGICA_PROPRIA_DIA_ACUMULADO_RECUPERACAO_V1"
)
AVISO_METODOLOGIA_TRAFEGABILIDADE = (
    "Metodologia experimental, ainda não calibrada contra sinistros ou dados "
    "reais de operação de máquinas."
)

# Metodologia fixa no código, não configurável: expoente e normalizador da
# curva de precipitação, e horizonte da recuperação/secagem em dias.
EXPOENTE_CURVA_PRECIPITACAO = 1.4
NORMALIZADOR_PRECIPITACAO_MM = 80.0
DIAS_HORIZONTE_RECUPERACAO = 4.0


class TrafegabilidadeDiaria(ModeloDominio):
    data: date
    precipitacao_d0: float | None = Field(default=None, ge=0)
    acumulado_3d: float | None = Field(default=None, ge=0)
    dias_desde_ultima_chuva_relevante: int | None = Field(default=None, ge=0)
    componente_dia: float | None = Field(default=None, ge=0, le=100)
    componente_acumulado: float | None = Field(default=None, ge=0, le=100)
    componente_recuperacao: float | None = Field(default=None, ge=0, le=100)
    indice_trafegabilidade: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validar_disponibilidade(self) -> "TrafegabilidadeDiaria":
        componentes_disponiveis = (
            self.componente_dia is not None
            and self.componente_acumulado is not None
            and self.componente_recuperacao is not None
        )
        if componentes_disponiveis != (self.indice_trafegabilidade is not None):
            raise ValueError(
                "índice de trafegabilidade exige os três componentes disponíveis"
            )
        return self


class ResultadoTrafegabilidade(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.TRAFEGABILIDADE
    periodo_features: JanelaHistorica
    janela_analisada: JanelaHistorica
    dias_contexto_calendario: int = Field(ge=0, le=DIAS_CONTEXTO_TRAFEGABILIDADE)
    trafegabilidade_diaria: tuple[TrafegabilidadeDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_trafegabilidade: ParametrosTrafegabilidade
    metodologia: str = METODOLOGIA_TRAFEGABILIDADE
    aviso_metodologia: str = AVISO_METODOLOGIA_TRAFEGABILIDADE
    versao: str = PERIGO_TRAFEGABILIDADE_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoTrafegabilidade":
        if self.perigo != PerigoExposicao.TRAFEGABILIDADE:
            raise ValueError("resultado aceita somente Trafegabilidade")
        if not self.aviso_metodologia.strip():
            raise ValueError(
                "aviso de metodologia experimental deve permanecer explícito"
            )
        if not (
            self.periodo_features.inicio <= self.janela_analisada.inicio
            and self.janela_analisada.fim <= self.periodo_features.fim
        ):
            raise ValueError(
                "janela analisada deve estar contida no período das features"
            )
        contexto_esperado = min(
            DIAS_CONTEXTO_TRAFEGABILIDADE,
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
        if tuple(item.data for item in self.trafegabilidade_diaria) != tuple(
            item.data for item in self.indices_diarios.indices
        ):
            raise ValueError(
                "detalhes diários e índices devem compartilhar o calendário"
            )
        for detalhe, indice in zip(
            self.trafegabilidade_diaria, self.indices_diarios.indices
        ):
            if detalhe.indice_trafegabilidade != indice.indice:
                raise ValueError("detalhe diário diverge do índice publicado")
        return self


def curva_precipitacao_trafegabilidade(precipitacao_mm: float | None) -> float | None:
    """Curva própria de Trafegabilidade: ``min(100 × (P/80)^1,4, 100)``.

    Não reaproveita a curva de precipitação do núcleo hídrico.
    """

    if precipitacao_mm is None:
        return None
    if isinstance(precipitacao_mm, bool) or not isinstance(
        precipitacao_mm, (int, float)
    ):
        raise TypeError("precipitação deve ser numérica")
    if not math.isfinite(precipitacao_mm) or precipitacao_mm < 0:
        raise ValueError("precipitação deve ser finita e não negativa")
    return min(
        100.0
        * (precipitacao_mm / NORMALIZADOR_PRECIPITACAO_MM)
        ** EXPOENTE_CURVA_PRECIPITACAO,
        100.0,
    )


def calcular_recuperacao_trafegabilidade(
    componente_acumulado: float | None,
    dias_desde_ultima_chuva_relevante: int | None,
) -> float | None:
    """Recuperação/secagem: componente de acumulado decaindo linearmente em 4 dias."""

    if componente_acumulado is None or dias_desde_ultima_chuva_relevante is None:
        return None
    if isinstance(componente_acumulado, bool) or not isinstance(
        componente_acumulado, (int, float)
    ):
        raise TypeError("componente_acumulado deve ser numérico")
    if not math.isfinite(componente_acumulado) or not 0 <= componente_acumulado <= 100:
        raise ValueError("componente_acumulado deve estar entre 0 e 100")
    if isinstance(dias_desde_ultima_chuva_relevante, bool) or not isinstance(
        dias_desde_ultima_chuva_relevante, int
    ):
        raise TypeError("dias_desde_ultima_chuva_relevante deve ser inteiro")
    if dias_desde_ultima_chuva_relevante < 0:
        raise ValueError("dias_desde_ultima_chuva_relevante deve ser não negativo")
    fator_secagem = max(
        0.0, 1 - dias_desde_ultima_chuva_relevante / DIAS_HORIZONTE_RECUPERACAO
    )
    return componente_acumulado * fator_secagem


def calcular_trafegabilidade_diaria(
    feature: FeatureDiariaCompartilhada,
    politica: PoliticaExposicaoEquipamentos,
) -> TrafegabilidadeDiaria:
    if not isinstance(feature, FeatureDiariaCompartilhada):
        raise TypeError("feature deve ser uma FeatureDiariaCompartilhada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")

    parametros = politica.parametros_trafegabilidade
    componente_dia = curva_precipitacao_trafegabilidade(feature.precipitacao_d0)
    componente_acumulado = curva_precipitacao_trafegabilidade(feature.acumulado_3d)
    componente_recuperacao = calcular_recuperacao_trafegabilidade(
        componente_acumulado, feature.dias_desde_ultima_chuva_relevante
    )

    indice_final: float | None = None
    if (
        componente_dia is not None
        and componente_acumulado is not None
        and componente_recuperacao is not None
    ):
        indice_final = min(
            componente_dia * parametros.peso_dia
            + componente_acumulado * parametros.peso_acumulado
            + componente_recuperacao * parametros.peso_recuperacao,
            100.0,
        )

    return TrafegabilidadeDiaria(
        data=feature.data,
        precipitacao_d0=feature.precipitacao_d0,
        acumulado_3d=feature.acumulado_3d,
        dias_desde_ultima_chuva_relevante=feature.dias_desde_ultima_chuva_relevante,
        componente_dia=componente_dia,
        componente_acumulado=componente_acumulado,
        componente_recuperacao=componente_recuperacao,
        indice_trafegabilidade=indice_final,
    )


def calcular_trafegabilidade_desfavoravel(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoTrafegabilidade:
    """Calcula a Trafegabilidade com metodologia meteorológica própria."""

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

    detalhes = tuple(
        calcular_trafegabilidade_diaria(feature, politica)
        for feature in features.dias
        if alvo.inicio <= feature.data <= alvo.fim
    )
    valores = tuple(
        ValorIndiceDiario(data=detalhe.data, indice=detalhe.indice_trafegabilidade)
        for detalhe in detalhes
    )
    indices = criar_indices_diarios(
        alvo,
        valores,
        politica,
        limiar_relevancia=politica.parametros_trafegabilidade.limiar_relevancia,
    )
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoTrafegabilidade(
        periodo_features=features.periodo,
        janela_analisada=alvo,
        dias_contexto_calendario=min(
            DIAS_CONTEXTO_TRAFEGABILIDADE,
            (alvo.inicio - features.periodo.inicio).days,
        ),
        trafegabilidade_diaria=detalhes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_trafegabilidade=politica.parametros_trafegabilidade,
    )


__all__ = [
    "AVISO_METODOLOGIA_TRAFEGABILIDADE",
    "DIAS_CONTEXTO_TRAFEGABILIDADE",
    "DIAS_HORIZONTE_RECUPERACAO",
    "EXPOENTE_CURVA_PRECIPITACAO",
    "METODOLOGIA_TRAFEGABILIDADE",
    "NORMALIZADOR_PRECIPITACAO_MM",
    "PERIGO_TRAFEGABILIDADE_VERSION",
    "ResultadoTrafegabilidade",
    "TrafegabilidadeDiaria",
    "calcular_recuperacao_trafegabilidade",
    "calcular_trafegabilidade_desfavoravel",
    "calcular_trafegabilidade_diaria",
    "curva_precipitacao_trafegabilidade",
]
