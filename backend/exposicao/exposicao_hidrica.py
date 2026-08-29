"""Exposição Hídrica oficial com ativação territorial.

O núcleo meteorológico permanece explícito como variável intermediária. A
série oficial, sua agregação e seus eventos são produzidos uma única vez a
partir da combinação desse núcleo com MERIT Hydro e SRTM.
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
    AVISO_DEPENDENCIA_HIDRICA,
    DIAS_CONTEXTO_HIDRICO,
    GRUPO_DEPENDENCIA_HIDRICA,
    CondicaoHidricaDiaria,
    calcular_condicoes_hidricas,
    normalizar_precipitacao,
)
from backend.exposicao.politica import (
    PARAMETROS_TERRITORIAIS_HIDRICOS,
    ClassificacaoIndice,
    ParametrosCondicaoHidrica,
    ParametrosTerritoriaisHidricos,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import AnaliseGeoespacialNormalizada, ModeloDominio


EXPOSICAO_HIDRICA_VERSION = "exposicao-hidrica-territorial-t3-g3-v1"
METODOLOGIA_EXPOSICAO_HIDRICA = (
    "EXPOSICAO_HIDRICA_METEOROLOGICA_COM_SUSCETIBILIDADE_TERRITORIAL_T3_G3"
)

# ParametrosTerritoriaisHidricos agora vive em backend.exposicao.politica (ao
# lado dos demais Parametros* configuraveis de PoliticaExposicaoEquipamentos).
# Reexportado aqui para nao quebrar quem ja importa deste modulo.


class SuscetibilidadeTerritorialHidrica(ModeloDominio):
    proximidade_drenagem: float | None = Field(default=None, ge=0, le=100)
    relevancia_area_montante: float | None = Field(default=None, ge=0, le=100)
    posicao_topografica: float | None = Field(default=None, ge=0, le=100)
    indice: float | None = Field(default=None, ge=0, le=100)


class ExposicaoHidricaDiaria(ModeloDominio):
    data: date
    condicao_meteorologica_base: float | None = Field(default=None, ge=0, le=100)
    acumulado_3d_mm: float | None = Field(default=None, ge=0)
    ativacao_chuva_3d: float | None = Field(default=None, ge=0, le=1)
    suscetibilidade_territorial: float | None = Field(default=None, ge=0, le=100)
    incremento_territorial: float | None = Field(default=None, ge=0)
    indice_exposicao_hidrica: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None

    @model_validator(mode="after")
    def validar_disponibilidade(self) -> "ExposicaoHidricaDiaria":
        entradas = (
            self.condicao_meteorologica_base,
            self.ativacao_chuva_3d,
            self.suscetibilidade_territorial,
        )
        disponivel = all(valor is not None for valor in entradas)
        if disponivel != (self.indice_exposicao_hidrica is not None):
            raise ValueError("índice hídrico exige todas as entradas disponíveis")
        if disponivel != (self.incremento_territorial is not None):
            raise ValueError(
                "incremento territorial exige todas as entradas disponíveis"
            )
        if disponivel != (self.classificacao is not None):
            raise ValueError(
                "classificação deve acompanhar a disponibilidade do índice"
            )
        return self


class ResultadoExposicaoHidrica(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.EXPOSICAO_HIDRICA
    periodo_features: JanelaHistorica
    janela_analisada: JanelaHistorica
    dias_contexto_calendario: int = Field(ge=0, le=DIAS_CONTEXTO_HIDRICO)
    condicoes_hidricas_base: tuple[CondicaoHidricaDiaria, ...]
    suscetibilidade_territorial: SuscetibilidadeTerritorialHidrica
    detalhes_diarios: tuple[ExposicaoHidricaDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_condicao_hidrica: ParametrosCondicaoHidrica
    parametros_territoriais: ParametrosTerritoriaisHidricos = (
        PARAMETROS_TERRITORIAIS_HIDRICOS
    )
    metodologia: str = METODOLOGIA_EXPOSICAO_HIDRICA
    contexto_territorial_aplicado: bool = True
    grupo_dependencia: str = GRUPO_DEPENDENCIA_HIDRICA
    nucleo_meteorologico_compartilhado: bool = True
    evidencia_independente: bool = False
    aviso_dependencia: str = AVISO_DEPENDENCIA_HIDRICA
    versao: str = EXPOSICAO_HIDRICA_VERSION

    @property
    def condicoes_hidricas(self) -> tuple[CondicaoHidricaDiaria, ...]:
        """Compatibilidade de leitura para o endpoint diagnóstico legado."""

        return self.condicoes_hidricas_base

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoExposicaoHidrica":
        if self.perigo != PerigoExposicao.EXPOSICAO_HIDRICA:
            raise ValueError("resultado deve representar Exposição Hídrica")
        if not self.contexto_territorial_aplicado:
            raise ValueError("resultado oficial exige contexto territorial")
        if self.indices_diarios.periodo != self.janela_analisada:
            raise ValueError("índices devem representar a janela analisada")
        if self.politica_id != self.indices_diarios.politica_id:
            raise ValueError("política dos índices diários é incoerente")
        if self.politica_id != self.agregacao_90d.politica_id:
            raise ValueError("política da agregação é incoerente")
        if (
            self.agregacao_90d.inicio != self.janela_analisada.inicio
            or self.agregacao_90d.fim != self.janela_analisada.fim
        ):
            raise ValueError("agregação e janela devem compartilhar o período")
        calendarios = (
            tuple(item.data for item in self.condicoes_hidricas_base),
            tuple(item.data for item in self.detalhes_diarios),
            tuple(item.data for item in self.indices_diarios.indices),
        )
        if not calendarios[0] == calendarios[1] == calendarios[2]:
            raise ValueError(
                "núcleo, detalhes e índices devem compartilhar o calendário"
            )
        for detalhe, indice in zip(self.detalhes_diarios, self.indices_diarios.indices):
            if detalhe.indice_exposicao_hidrica != indice.indice:
                raise ValueError("série oficial diverge do detalhamento hídrico")
        return self


def _numero_finito_nao_negativo(valor: float | None, nome: str) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise TypeError(f"{nome} deve ser numérico")
    numero = float(valor)
    if not math.isfinite(numero) or numero < 0:
        raise ValueError(f"{nome} deve ser finito e não negativo")
    return numero


def calcular_proximidade_drenagem(
    distancia_m: float | None,
    parametros: ParametrosTerritoriaisHidricos = PARAMETROS_TERRITORIAIS_HIDRICOS,
) -> float | None:
    distancia = _numero_finito_nao_negativo(distancia_m, "distância")
    if distancia is None:
        return None
    resultado = (
        100
        * parametros.mediana_distancia_m
        / (parametros.mediana_distancia_m + distancia)
    )
    return min(100.0, max(0.0, resultado))


def calcular_relevancia_area_montante(
    area_km2: float | None,
    parametros: ParametrosTerritoriaisHidricos = PARAMETROS_TERRITORIAIS_HIDRICOS,
) -> float | None:
    area = _numero_finito_nao_negativo(area_km2, "área montante")
    if area is None:
        return None
    resultado = (
        100
        * (math.log1p(area) - parametros.area_log_min)
        / (parametros.area_log_max - parametros.area_log_min)
    )
    return min(100.0, max(0.0, resultado))


def calcular_posicao_topografica(
    posicao_m: float | None,
    parametros: ParametrosTerritoriaisHidricos = PARAMETROS_TERRITORIAIS_HIDRICOS,
) -> float | None:
    if posicao_m is None:
        return None
    if isinstance(posicao_m, bool) or not isinstance(posicao_m, (int, float)):
        raise TypeError("posição topográfica deve ser numérica")
    posicao = float(posicao_m)
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


def calcular_suscetibilidade_territorial(
    analise_geoespacial: AnaliseGeoespacialNormalizada,
    parametros: ParametrosTerritoriaisHidricos = PARAMETROS_TERRITORIAIS_HIDRICOS,
) -> SuscetibilidadeTerritorialHidrica:
    if not isinstance(analise_geoespacial, AnaliseGeoespacialNormalizada):
        raise TypeError("analise_geoespacial deve possuir contrato normalizado")
    proximidade = calcular_proximidade_drenagem(
        analise_geoespacial.distancia_drenagem_m.valor, parametros
    )
    area = calcular_relevancia_area_montante(
        analise_geoespacial.area_drenagem_montante_km2.valor, parametros
    )
    posicao = calcular_posicao_topografica(
        analise_geoespacial.posicao_topografica_relativa_m.valor, parametros
    )
    indice = None
    if all(valor is not None for valor in (proximidade, area, posicao)):
        assert proximidade is not None and area is not None and posicao is not None
        indice = (
            parametros.peso_proximidade_drenagem * proximidade
            + parametros.peso_area_montante * area
            + parametros.peso_posicao_topografica * posicao
        )
    return SuscetibilidadeTerritorialHidrica(
        proximidade_drenagem=proximidade,
        relevancia_area_montante=area,
        posicao_topografica=posicao,
        indice=indice,
    )


def calcular_exposicao_hidrica_diaria(
    *,
    data: date,
    condicao_meteorologica_base: float | None,
    acumulado_3d_mm: float | None,
    suscetibilidade_territorial: float | None,
    politica: PoliticaExposicaoEquipamentos,
    parametros: ParametrosTerritoriaisHidricos = PARAMETROS_TERRITORIAIS_HIDRICOS,
) -> ExposicaoHidricaDiaria:
    base = _numero_finito_nao_negativo(
        condicao_meteorologica_base, "condição meteorológica base"
    )
    chuva = _numero_finito_nao_negativo(acumulado_3d_mm, "acumulado de três dias")
    suscetibilidade = _numero_finito_nao_negativo(
        suscetibilidade_territorial, "suscetibilidade territorial"
    )
    if base is not None and base > 100:
        raise ValueError("condição meteorológica base deve estar em 0..100")
    if suscetibilidade is not None and suscetibilidade > 100:
        raise ValueError("suscetibilidade territorial deve estar em 0..100")
    ativacao = None if chuva is None else normalizar_precipitacao(chuva, politica) / 100
    incremento = None
    indice = None
    if base is not None and ativacao is not None and suscetibilidade is not None:
        incremento = parametros.fator_incremento * ativacao * suscetibilidade
        indice = min(100.0, base + incremento)
    return ExposicaoHidricaDiaria(
        data=data,
        condicao_meteorologica_base=base,
        acumulado_3d_mm=chuva,
        ativacao_chuva_3d=ativacao,
        suscetibilidade_territorial=suscetibilidade,
        incremento_territorial=incremento,
        indice_exposicao_hidrica=indice,
        classificacao=(
            politica.classificar_indice(indice) if indice is not None else None
        ),
    )


def calcular_exposicao_hidrica(
    features: FeaturesDiariasCompartilhadas,
    analise_geoespacial: AnaliseGeoespacialNormalizada,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoExposicaoHidrica:
    """Calcula a única série e agregação oficiais de Exposição Hídrica."""

    if not isinstance(features, FeaturesDiariasCompartilhadas):
        raise TypeError("features deve ser FeaturesDiariasCompartilhadas")
    if not isinstance(analise_geoespacial, AnaliseGeoespacialNormalizada):
        raise TypeError("analise_geoespacial deve possuir contrato normalizado")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    alvo = janela_alvo or features.periodo
    parametros_territoriais = politica.parametros_territoriais_hidricos
    condicoes = calcular_condicoes_hidricas(features, politica, alvo)
    suscetibilidade = calcular_suscetibilidade_territorial(
        analise_geoespacial, parametros_territoriais
    )
    features_por_data = {item.data: item for item in features.dias}
    detalhes = tuple(
        calcular_exposicao_hidrica_diaria(
            data=condicao.data,
            condicao_meteorologica_base=condicao.indice_hidrico_meteorologico,
            acumulado_3d_mm=features_por_data[condicao.data].acumulado_3d,
            suscetibilidade_territorial=suscetibilidade.indice,
            politica=politica,
            parametros=parametros_territoriais,
        )
        for condicao in condicoes
    )
    indices = criar_indices_diarios(
        alvo,
        (
            ValorIndiceDiario(
                data=item.data,
                indice=item.indice_exposicao_hidrica,
            )
            for item in detalhes
        ),
        politica,
    )
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoExposicaoHidrica(
        periodo_features=features.periodo,
        janela_analisada=alvo,
        dias_contexto_calendario=min(
            DIAS_CONTEXTO_HIDRICO,
            (alvo.inicio - features.periodo.inicio).days,
        ),
        condicoes_hidricas_base=condicoes,
        suscetibilidade_territorial=suscetibilidade,
        detalhes_diarios=detalhes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_condicao_hidrica=politica.parametros_condicao_hidrica,
        parametros_territoriais=parametros_territoriais,
    )


__all__ = [
    "EXPOSICAO_HIDRICA_VERSION",
    "METODOLOGIA_EXPOSICAO_HIDRICA",
    "PARAMETROS_TERRITORIAIS_HIDRICOS",
    "ExposicaoHidricaDiaria",
    "ParametrosTerritoriaisHidricos",
    "ResultadoExposicaoHidrica",
    "SuscetibilidadeTerritorialHidrica",
    "calcular_exposicao_hidrica",
    "calcular_exposicao_hidrica_diaria",
    "calcular_posicao_topografica",
    "calcular_proximidade_drenagem",
    "calcular_relevancia_area_montante",
    "calcular_suscetibilidade_territorial",
]
