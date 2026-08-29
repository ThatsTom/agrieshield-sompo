"""Protótipo paralelo do Hídrico V2 T3_g3.

EXPERIMENTAL — NÃO CALIBRADO CONTRA SINISTROS REAIS. Este módulo não altera
o Hídrico v1, a política AGRISHIELD-EQUIP-v1.0 ou qualquer endpoint oficial.
As constantes territoriais reproduzem o baseline da simulação e não devem ser
recalculadas a partir da carteira corrente.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Iterable

from pydantic import Field, model_validator

from backend.exposicao.agregacao_perigos import (
    ResultadoAgregacaoPerigo,
    ValorIndiceDiario,
    agregar_indice_historico,
    criar_indices_diarios,
)
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.perigos_hidricos import normalizar_precipitacao
from backend.exposicao.politica import (
    ClassificacaoIndice,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import ModeloDominio


HIDRICO_V2_EXPERIMENTAL_VERSION = "hidrico-v2-t3-g3-experimental-v1"
METODOLOGIA_HIDRICO_V2 = (
    "EXPOSICAO_HIDRICA_METEOROLOGICA_COM_SUSCETIBILIDADE_"
    "TERRITORIAL_T3_G3_EXPERIMENTAL_V1"
)
AVISO_EXPERIMENTAL = "EXPERIMENTAL — NÃO CALIBRADO CONTRA SINISTROS REAIS."
LIMITACOES_METODOLOGICAS = (
    AVISO_EXPERIMENTAL,
    "Normalizações territoriais fixadas no baseline experimental de seis fazendas.",
    "Localização pontual não representa necessariamente todo o polígono segurado.",
    "MERIT representa drenagem raster, não geometria cadastral exata de rios.",
    "O resultado não representa probabilidade atuarial de sinistro.",
    "Declividade não participa do Hídrico V2 experimental.",
)
PESOS_SCORE_EXPERIMENTAL = {
    "EXPOSICAO_HIDRICA": 0.4,
    "INSTABILIDADE": 0.266666666666667,
    "INCENDIO": 0.2,
    "TEMPESTADES": 0.133333333333333,
    "TRAFEGABILIDADE": 0.0,
}


class ParametrosTerritoriaisExperimentais(ModeloDominio):
    """Parâmetros imutáveis recuperados da simulação T3_g3."""

    mediana_distancia_m: float = 1868.12508034684
    area_log_min: float = 2.53850909780559
    area_log_max: float = 10.0608666649158
    mediana_posicao_m: float = 7.6517377036555
    iqr_posicao_m: float = 13.8746841685139
    peso_d2: float = 0.40
    peso_a2: float = 0.35
    peso_p2: float = 0.25
    fator_incremento: float = 0.30
    origem: str = "baseline_v1/simulacao_hidrico_v2"
    calibrado_contra_sinistros: bool = False

    @model_validator(mode="after")
    def validar(self) -> "ParametrosTerritoriaisExperimentais":
        if self.area_log_max <= self.area_log_min or self.iqr_posicao_m <= 0:
            raise ValueError("parâmetros de normalização inválidos")
        if not math.isclose(
            self.peso_d2 + self.peso_a2 + self.peso_p2,
            1.0,
            rel_tol=0,
            abs_tol=1e-12,
        ):
            raise ValueError("pesos de T3 devem somar 1")
        return self

    model_config = {"frozen": True}


PARAMETROS_T3_G3 = ParametrosTerritoriaisExperimentais()


class ContextoTerritorialHidricoV2(ModeloDominio):
    distancia_drenagem_m: float | None = Field(default=None, ge=0)
    area_drenagem_montante_km2: float | None = Field(default=None, ge=0)
    posicao_topografica_relativa_m: float | None = None
    fonte_distancia: str = "MERIT_HYDRO"
    fonte_area_montante: str = "MERIT_HYDRO"
    fonte_posicao_topografica: str = "SRTM"


class SuscetibilidadeTerritorialT3(ModeloDominio):
    d2: float | None = Field(default=None, ge=0, le=100)
    a2: float | None = Field(default=None, ge=0, le=100)
    p2: float | None = Field(default=None, ge=0, le=100)
    t3: float | None = Field(default=None, ge=0, le=100)


class ResultadoHidricoV2Diario(ModeloDominio):
    data: date
    h1_meteorologico: float | None = Field(default=None, ge=0, le=100)
    classificacao_h1: ClassificacaoIndice | None = None
    acumulado_3d: float | None = Field(default=None, ge=0)
    g3: float | None = Field(default=None, ge=0, le=1)
    distancia_drenagem_m: float | None = Field(default=None, ge=0)
    area_drenagem_montante_km2: float | None = Field(default=None, ge=0)
    posicao_topografica_relativa_m: float | None = None
    d2: float | None = Field(default=None, ge=0, le=100)
    a2: float | None = Field(default=None, ge=0, le=100)
    p2: float | None = Field(default=None, ge=0, le=100)
    t3: float | None = Field(default=None, ge=0, le=100)
    incremento_territorial: float | None = Field(default=None, ge=0)
    h2_final: float | None = Field(default=None, ge=0, le=100)
    classificacao_h2: ClassificacaoIndice | None = None
    percentual_incremento_territorial: float | None = Field(default=None, ge=0, le=100)
    metodologia: str = METODOLOGIA_HIDRICO_V2
    experimental: bool = True
    calibrado_contra_sinistros: bool = False

    @model_validator(mode="after")
    def validar_invariantes(self) -> "ResultadoHidricoV2Diario":
        disponivel = self.h2_final is not None
        campos = (self.h1_meteorologico, self.g3, self.t3, self.incremento_territorial)
        if disponivel != all(valor is not None for valor in campos):
            raise ValueError("H2 exige H1, g3, T3 e incremento disponíveis")
        if disponivel:
            assert self.h1_meteorologico is not None
            assert self.incremento_territorial is not None
            if self.h2_final < self.h1_meteorologico:
                raise ValueError("H2 não pode reduzir H1")
            if self.incremento_territorial < 0:
                raise ValueError("incremento não pode ser negativo")
            if self.classificacao_h1 is None or self.classificacao_h2 is None:
                raise ValueError("índices disponíveis exigem classificação")
        elif self.classificacao_h2 is not None:
            raise ValueError("H2 indisponível não possui classificação")
        return self


class ResultadoHidricoV2Agregado(ModeloDominio):
    indice_hidrico_v1_90d: float | None = Field(default=None, ge=0, le=100)
    classificacao_hidrica_v1_90d: ClassificacaoIndice | None = None
    indice_hidrico_v2_90d: float | None = Field(default=None, ge=0, le=100)
    classificacao_hidrica_v2_90d: ClassificacaoIndice | None = None
    delta_hidrico_90d: float | None = None
    agregacao_v1: ResultadoAgregacaoPerigo
    agregacao_v2: ResultadoAgregacaoPerigo
    metodologia: str = METODOLOGIA_HIDRICO_V2
    experimental: bool = True


class ResultadoScoreHidricoV2Experimental(ModeloDominio):
    score_v1: float | None = Field(default=None, ge=0, le=100)
    score_v2_experimental: float | None = Field(default=None, ge=0, le=100)
    delta_score: float | None = None
    classificacao_v1: ClassificacaoIndice | None = None
    classificacao_v2_experimental: ClassificacaoIndice | None = None
    peso_hidrico: float = 0.4
    peso_instabilidade: float = 0.266666666666667
    peso_incendio: float = 0.2
    peso_tempestades: float = 0.133333333333333
    peso_trafegabilidade: float = 0.0
    instabilidade_permanece_baseada_em_h1: bool = True
    experimental: bool = True


def _numero_finito_nao_negativo(valor: float | None, nome: str) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise TypeError(f"{nome} deve ser numérico")
    numero = float(valor)
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(f"{nome} deve ser finito e não negativo")
    return numero


def calcular_d2(
    distancia_drenagem_m: float | None,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> float | None:
    distancia = _numero_finito_nao_negativo(distancia_drenagem_m, "distância")
    if distancia is None:
        return None
    resultado = (
        100
        * parametros.mediana_distancia_m
        / (parametros.mediana_distancia_m + distancia)
    )
    return min(100.0, max(0.0, resultado))


def calcular_a2(
    area_montante_km2: float | None,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> float | None:
    area = _numero_finito_nao_negativo(area_montante_km2, "área montante")
    if area is None:
        return None
    resultado = (
        100
        * (math.log1p(area) - parametros.area_log_min)
        / (parametros.area_log_max - parametros.area_log_min)
    )
    return min(100.0, max(0.0, resultado))


def calcular_p2(
    posicao_topografica_m: float | None,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> float | None:
    if posicao_topografica_m is None:
        return None
    if isinstance(posicao_topografica_m, bool) or not isinstance(
        posicao_topografica_m, (int, float)
    ):
        raise TypeError("posição topográfica deve ser numérica")
    posicao = float(posicao_topografica_m)
    if not math.isfinite(posicao):
        raise ValueError("posição topográfica deve ser finita")
    expoente = (posicao - parametros.mediana_posicao_m) / parametros.iqr_posicao_m
    if expoente >= 0:
        exp_negativo = math.exp(-expoente) if expoente < 746 else 0.0
        resultado = 100 * exp_negativo / (1 + exp_negativo)
    else:
        exp_positivo = math.exp(expoente) if expoente > -746 else 0.0
        resultado = 100 / (1 + exp_positivo)
    return min(100.0, max(0.0, resultado))


def calcular_t3(
    contexto: ContextoTerritorialHidricoV2,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> SuscetibilidadeTerritorialT3:
    if not isinstance(contexto, ContextoTerritorialHidricoV2):
        raise TypeError("contexto deve ser ContextoTerritorialHidricoV2")
    d2 = calcular_d2(contexto.distancia_drenagem_m, parametros)
    a2 = calcular_a2(contexto.area_drenagem_montante_km2, parametros)
    p2 = calcular_p2(contexto.posicao_topografica_relativa_m, parametros)
    t3 = (
        None
        if any(v is None for v in (d2, a2, p2))
        else parametros.peso_d2 * d2 + parametros.peso_a2 * a2 + parametros.peso_p2 * p2
    )
    return SuscetibilidadeTerritorialT3(d2=d2, a2=a2, p2=p2, t3=t3)


def calcular_h2_experimental(
    h1: float | None,
    g3: float | None,
    t3: float | None,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> tuple[float | None, float | None, float | None]:
    """Aplica somente H2=min(100, H1+0,30*g3*T3), preservando missing."""

    if h1 is None or g3 is None or t3 is None:
        return None, None, None
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) for v in (h1, g3, t3)
    ):
        raise TypeError("H1, g3 e T3 devem ser numéricos")
    if not all(math.isfinite(float(v)) for v in (h1, g3, t3)):
        raise ValueError("H1, g3 e T3 devem ser finitos")
    if not 0 <= h1 <= 100 or not 0 <= g3 <= 1 or not 0 <= t3 <= 100:
        raise ValueError("H1, g3 ou T3 fora do domínio")
    incremento = parametros.fator_incremento * g3 * t3
    h2 = min(100.0, h1 + incremento)
    percentual = incremento / h2 * 100 if h2 > 0 else 0.0
    return h2, incremento, percentual


def calcular_hidrico_v2_diario(
    *,
    data: date,
    h1_meteorologico: float | None,
    acumulado_3d: float | None,
    contexto: ContextoTerritorialHidricoV2,
    politica: PoliticaExposicaoEquipamentos,
    parametros: ParametrosTerritoriaisExperimentais = PARAMETROS_T3_G3,
) -> ResultadoHidricoV2Diario:
    h1 = _numero_finito_nao_negativo(h1_meteorologico, "H1")
    if h1 is not None and h1 > 100:
        raise ValueError("H1 deve estar em 0..100")
    chuva = _numero_finito_nao_negativo(acumulado_3d, "acumulado_3d")
    susc = calcular_t3(contexto, parametros)
    g3 = None if chuva is None else normalizar_precipitacao(chuva, politica) / 100
    h2, incremento, percentual = calcular_h2_experimental(h1, g3, susc.t3, parametros)
    return ResultadoHidricoV2Diario(
        data=data,
        h1_meteorologico=h1,
        classificacao_h1=politica.classificar_indice(h1) if h1 is not None else None,
        acumulado_3d=chuva,
        g3=g3,
        distancia_drenagem_m=contexto.distancia_drenagem_m,
        area_drenagem_montante_km2=contexto.area_drenagem_montante_km2,
        posicao_topografica_relativa_m=contexto.posicao_topografica_relativa_m,
        d2=susc.d2,
        a2=susc.a2,
        p2=susc.p2,
        t3=susc.t3,
        incremento_territorial=incremento,
        h2_final=h2,
        classificacao_h2=politica.classificar_indice(h2) if h2 is not None else None,
        percentual_incremento_territorial=percentual,
    )


def agregar_hidrico_v2_experimental(
    resultados: Iterable[ResultadoHidricoV2Diario],
    janela: JanelaHistorica,
    politica: PoliticaExposicaoEquipamentos,
) -> ResultadoHidricoV2Agregado:
    itens = tuple(resultados)
    valores_v1 = tuple(
        ValorIndiceDiario(data=x.data, indice=x.h1_meteorologico) for x in itens
    )
    valores_v2 = tuple(ValorIndiceDiario(data=x.data, indice=x.h2_final) for x in itens)
    agregado_v1 = agregar_indice_historico(
        criar_indices_diarios(janela, valores_v1, politica), politica
    )
    agregado_v2 = agregar_indice_historico(
        criar_indices_diarios(janela, valores_v2, politica), politica
    )
    delta = (
        None
        if agregado_v1.indice_agregado is None or agregado_v2.indice_agregado is None
        else agregado_v2.indice_agregado - agregado_v1.indice_agregado
    )
    return ResultadoHidricoV2Agregado(
        indice_hidrico_v1_90d=agregado_v1.indice_agregado,
        classificacao_hidrica_v1_90d=agregado_v1.classificacao_agregada,
        indice_hidrico_v2_90d=agregado_v2.indice_agregado,
        classificacao_hidrica_v2_90d=agregado_v2.classificacao_agregada,
        delta_hidrico_90d=delta,
        agregacao_v1=agregado_v1,
        agregacao_v2=agregado_v2,
    )


def calcular_score_paralelo(
    *,
    score_v1: float | None,
    indice_hidrico_v1_90d: float | None,
    indice_hidrico_v2_90d: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> ResultadoScoreHidricoV2Experimental:
    if (
        score_v1 is None
        or indice_hidrico_v1_90d is None
        or indice_hidrico_v2_90d is None
    ):
        return ResultadoScoreHidricoV2Experimental()
    score2 = score_v1 + PESOS_SCORE_EXPERIMENTAL["EXPOSICAO_HIDRICA"] * (
        indice_hidrico_v2_90d - indice_hidrico_v1_90d
    )
    score2 = min(100.0, max(0.0, score2))
    return ResultadoScoreHidricoV2Experimental(
        score_v1=score_v1,
        score_v2_experimental=score2,
        delta_score=score2 - score_v1,
        classificacao_v1=politica.classificar_indice(score_v1),
        classificacao_v2_experimental=politica.classificar_indice(score2),
    )


__all__ = [
    "AVISO_EXPERIMENTAL",
    "HIDRICO_V2_EXPERIMENTAL_VERSION",
    "LIMITACOES_METODOLOGICAS",
    "METODOLOGIA_HIDRICO_V2",
    "PARAMETROS_T3_G3",
    "PESOS_SCORE_EXPERIMENTAL",
    "ContextoTerritorialHidricoV2",
    "ParametrosTerritoriaisExperimentais",
    "ResultadoHidricoV2Agregado",
    "ResultadoHidricoV2Diario",
    "ResultadoScoreHidricoV2Experimental",
    "SuscetibilidadeTerritorialT3",
    "agregar_hidrico_v2_experimental",
    "calcular_a2",
    "calcular_d2",
    "calcular_h2_experimental",
    "calcular_hidrico_v2_diario",
    "calcular_p2",
    "calcular_score_paralelo",
    "calcular_t3",
]
