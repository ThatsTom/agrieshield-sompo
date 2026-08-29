"""Features meteorológicas diárias neutras e compartilhadas.

As precipitações são expressas em milímetros, as temperaturas em graus
Celsius, a umidade relativa em percentual e a velocidade média do vento em
m/s. Ausência é sempre ``None``; zero permanece uma observação válida.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from pydantic import Field, model_validator

from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
)
from backend.risco.modelos import FonteDado, ModeloDominio, NaturezaDado


FEATURES_DIARIAS_VERSION = "exposicao-features-diarias-v2"


class FeatureDiariaCompartilhada(ModeloDominio):
    data: date

    precipitacao_d0: float | None = Field(default=None, ge=0)
    precipitacao_d1_d3: float | None = Field(default=None, ge=0)
    precipitacao_d4_d7: float | None = Field(default=None, ge=0)
    acumulado_3d: float | None = Field(default=None, ge=0)
    acumulado_7d: float | None = Field(default=None, ge=0)
    dias_consecutivos_com_chuva: int | None = Field(default=None, ge=0)
    dias_desde_ultima_chuva_relevante: int | None = Field(default=None, ge=0)

    temperatura_media: float | None = None
    temperatura_maxima: float | None = None
    temperatura_minima: float | None = None
    umidade_relativa: float | None = Field(default=None, ge=0, le=100)
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)


class FeaturesDiariasCompartilhadas(ModeloDominio):
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    periodo: JanelaHistorica
    referencia_temporal: ReferenciaTemporalHistorica
    metadados_vento: dict[str, Any] = Field(default_factory=dict)
    dias: tuple[FeatureDiariaCompartilhada, ...]
    versao: str = FEATURES_DIARIAS_VERSION

    @model_validator(mode="after")
    def validar_calendario(self) -> "FeaturesDiariasCompartilhadas":
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("features diárias exigem natureza HISTORICO")
        if len(self.dias) != self.periodo.dias_esperados:
            raise ValueError("coleção diária deve representar toda a janela solicitada")
        datas_esperadas = tuple(
            self.periodo.inicio + timedelta(days=indice)
            for indice in range(self.periodo.dias_esperados)
        )
        if tuple(feature.data for feature in self.dias) != datas_esperadas:
            raise ValueError("features diárias devem seguir o calendário solicitado")
        return self

    def por_data(self, data_consulta: date) -> FeatureDiariaCompartilhada:
        if not self.periodo.inicio <= data_consulta <= self.periodo.fim:
            raise KeyError(data_consulta)
        indice = (data_consulta - self.periodo.inicio).days
        return self.dias[indice]


def _somar_precipitacao_calendario(
    por_data: dict[date, RegistroMeteorologicoDiario],
    data_referencia: date,
    deslocamentos: range,
) -> float | None:
    valores: list[float] = []
    for deslocamento in deslocamentos:
        registro = por_data.get(data_referencia - timedelta(days=deslocamento))
        if registro is None or registro.precipitacao_mm is None:
            return None
        valores.append(registro.precipitacao_mm)
    return sum(valores)


def calcular_features_diarias_compartilhadas(
    serie: SerieHistoricaFonte,
) -> FeaturesDiariasCompartilhadas:
    """Deriva evidências para cada data da janela, sem imputação ou interpretação."""

    if not isinstance(serie, SerieHistoricaFonte):
        raise TypeError("serie deve ser uma SerieHistoricaFonte")

    por_data = {registro.data: registro for registro in serie.registros}
    dias: list[FeatureDiariaCompartilhada] = []
    sequencia_chuva = 0
    dias_desde_chuva: int | None = None

    data_atual = serie.periodo_solicitado.inicio
    while data_atual <= serie.periodo_solicitado.fim:
        registro = por_data.get(data_atual)
        precipitacao_d0 = registro.precipitacao_mm if registro is not None else None

        if precipitacao_d0 is None:
            sequencia_no_dia = None
            sequencia_chuva = 0
            dias_desde_no_dia = None
            dias_desde_chuva = None
        elif precipitacao_d0 > 0:
            sequencia_chuva += 1
            sequencia_no_dia = sequencia_chuva
            dias_desde_chuva = 0
            dias_desde_no_dia = 0
        else:
            sequencia_chuva = 0
            sequencia_no_dia = 0
            if dias_desde_chuva is None:
                dias_desde_no_dia = None
            else:
                dias_desde_chuva += 1
                dias_desde_no_dia = dias_desde_chuva

        dias.append(
            FeatureDiariaCompartilhada(
                data=data_atual,
                precipitacao_d0=precipitacao_d0,
                precipitacao_d1_d3=_somar_precipitacao_calendario(
                    por_data, data_atual, range(1, 4)
                ),
                precipitacao_d4_d7=_somar_precipitacao_calendario(
                    por_data, data_atual, range(4, 8)
                ),
                acumulado_3d=_somar_precipitacao_calendario(
                    por_data, data_atual, range(0, 3)
                ),
                acumulado_7d=_somar_precipitacao_calendario(
                    por_data, data_atual, range(0, 7)
                ),
                dias_consecutivos_com_chuva=sequencia_no_dia,
                dias_desde_ultima_chuva_relevante=dias_desde_no_dia,
                temperatura_media=(
                    registro.temperatura_media_c if registro is not None else None
                ),
                temperatura_maxima=(
                    registro.temperatura_maxima_c if registro is not None else None
                ),
                temperatura_minima=(
                    registro.temperatura_minima_c if registro is not None else None
                ),
                umidade_relativa=(
                    registro.umidade_media_pct if registro is not None else None
                ),
                velocidade_vento_media_m_s=(
                    registro.velocidade_vento_media_m_s
                    if registro is not None
                    else None
                ),
            )
        )
        data_atual += timedelta(days=1)

    return FeaturesDiariasCompartilhadas(
        id_fazenda=serie.id_fazenda,
        fonte=serie.fonte,
        natureza=serie.natureza,
        tipo_produto=serie.tipo_produto,
        dataset=serie.dataset,
        periodo=serie.periodo_solicitado,
        referencia_temporal=serie.referencia_temporal,
        metadados_vento=dict(serie.metadados_origem.get("vento") or {}),
        dias=tuple(dias),
    )


__all__ = [
    "FEATURES_DIARIAS_VERSION",
    "FeatureDiariaCompartilhada",
    "FeaturesDiariasCompartilhadas",
    "calcular_features_diarias_compartilhadas",
]
