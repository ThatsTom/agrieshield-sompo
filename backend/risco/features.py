"""Cálculo de features climáticas neutras sobre séries normalizadas.

Política temporal da versão ``risk-features-v2``:

* para NASA POWER real, cada variável usa sua última observação válida na data
  solicitada ou nos três dias anteriores; a referência efetiva fica explícita;
* janelas de N dias usam o intervalo civil inclusivo ``efetiva-(N-1)`` até
  ``efetiva``; não usam quantidade de linhas;
* datas duplicadas são rejeitadas, pois o valor diário seria ambíguo;
* dias ausentes e valores ``None`` não são preenchidos;
* soma/média com parte da janela disponível é retornada como ``PARCIAL`` e
  informa dias esperados/disponíveis; sem nenhum valor, retorna ``None``;
* a sequência de dias sem chuva usa a definição legada ``precipitação < 1
  mm/dia`` e é interrompida/sinalizada diante de lacuna temporal.

O limiar de 1 mm define somente esta feature histórica; não é classificação
nem threshold de risco.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from statistics import fmean
from typing import Callable

from .modelos import (
    AgregacaoTemporal,
    ContextoTemporalFeature,
    DadoNormalizado,
    FEATURES_VERSION,
    FeatureNeutra,
    FonteDado,
    FreshnessStatus,
    GrupoFeatures,
    LinhagemFeature,
    NaturezaDado,
    QualidadeDado,
    ReferenciaTemporal,
    SerieDadosNormalizados,
    StatusQualidade,
)


LIMIAR_LEGADO_DIA_SEM_CHUVA_MM = 1.0
LIMITE_FRESHNESS_NASA_DIAS = 3

PRECIPITACAO = "precipitacao_diaria_mm"
UMIDADE = "umidade_relativa_media_diaria_pct"
TEMPERATURA_MAXIMA = "temperatura_maxima_diaria_c"

UNIDADES_ESPERADAS = {
    PRECIPITACAO: "mm/dia",
    UMIDADE: "%",
    TEMPERATURA_MAXIMA: "°C",
}


def _dia(referencia: ReferenciaTemporal) -> date:
    valor = referencia.inicio
    return valor.date() if isinstance(valor, datetime) else valor


def _validar_e_indexar(
    serie: SerieDadosNormalizados,
) -> dict[str, dict[date, DadoNormalizado]]:
    if serie.agregacao != AgregacaoTemporal.DIARIA:
        raise ValueError("features climáticas exigem série DIARIA")
    fontes = {dado.fonte for dado in serie.dados}
    naturezas = {dado.natureza for dado in serie.dados}
    if fontes and (len(fontes) != 1 or fontes != {serie.fonte}):
        raise ValueError("não é permitido misturar fontes na mesma série")
    if naturezas and (len(naturezas) != 1 or naturezas != {serie.natureza}):
        raise ValueError("não é permitido misturar naturezas na mesma série")

    indice: dict[str, dict[date, DadoNormalizado]] = {
        PRECIPITACAO: {},
        UMIDADE: {},
        TEMPERATURA_MAXIMA: {},
    }
    for dado in serie.dados:
        if dado.variavel not in indice:
            continue
        if dado.referencia_temporal is None:
            raise ValueError("dado climático sem referência temporal")
        if dado.referencia_temporal.agregacao != AgregacaoTemporal.DIARIA:
            raise ValueError("granularidades diferentes na mesma série")
        if dado.unidade != UNIDADES_ESPERADAS[dado.variavel]:
            raise ValueError(f"unidade incompatível para {dado.variavel}")
        dia = _dia(dado.referencia_temporal)
        if dia in indice[dado.variavel]:
            raise ValueError(f"data duplicada para {dado.variavel}: {dia.isoformat()}")
        indice[dado.variavel][dia] = dado
    return indice


def _linhagem(
    *,
    fonte: FonteDado,
    natureza: NaturezaDado,
    algoritmo: str,
    janela: str,
    entradas: tuple[str, ...],
) -> LinhagemFeature:
    return LinhagemFeature(
        algoritmo=algoritmo,
        versao=FEATURES_VERSION,
        fonte=fonte,
        natureza=natureza,
        janela=janela,
        entradas=entradas,
    )


def _qualidade_janela(
    *,
    esperados: int,
    disponiveis: int,
    simulado: bool,
    flags_origem: tuple[str, ...],
) -> QualidadeDado:
    cobertura = disponiveis * 100.0 / esperados
    if disponiveis == 0:
        status = StatusQualidade.AUSENTE
    elif disponiveis < esperados:
        status = StatusQualidade.PARCIAL
    else:
        status = StatusQualidade.DISPONIVEL
    flags = list(flags_origem)
    if disponiveis < esperados:
        flags.append("JANELA_INCOMPLETA")
    return QualidadeDado(
        status=status,
        simulado=simulado,
        cobertura_pct=cobertura,
        flags=tuple(dict.fromkeys(flags)),
    )


def _referencia_efetiva(
    *,
    variavel: str,
    data_solicitada: date,
    indice: dict[str, dict[date, DadoNormalizado]],
    serie: SerieDadosNormalizados,
) -> tuple[date | None, date | None, int | None, FreshnessStatus | None]:
    """Retorna referência para cálculo e diagnóstico, sem usar datas futuras."""
    if serie.qualidade.simulado:
        return data_solicitada, None, None, FreshnessStatus.AUSENTE
    if serie.fonte != FonteDado.NASA_POWER:
        return data_solicitada, None, None, None

    datas_validas = [
        dia
        for dia, dado in indice[variavel].items()
        if dia <= data_solicitada and dado.valor is not None
    ]
    if not datas_validas:
        return None, None, None, FreshnessStatus.AUSENTE

    efetiva = max(datas_validas)
    defasagem = (data_solicitada - efetiva).days
    if defasagem == 0:
        freshness = FreshnessStatus.ATUAL
    elif defasagem <= LIMITE_FRESHNESS_NASA_DIAS:
        freshness = FreshnessStatus.DEFASADO
    else:
        freshness = FreshnessStatus.DESATUALIZADO
    referencia_calculo = (
        efetiva
        if freshness in {FreshnessStatus.ATUAL, FreshnessStatus.DEFASADO}
        else None
    )
    return referencia_calculo, efetiva, defasagem, freshness


def _flags_freshness(freshness: FreshnessStatus | None) -> tuple[str, ...]:
    return {
        FreshnessStatus.DEFASADO: ("DADO_DEFASADO",),
        FreshnessStatus.DESATUALIZADO: ("DADO_DESATUALIZADO",),
        FreshnessStatus.AUSENTE: ("REFERENCIA_EFETIVA_AUSENTE",),
    }.get(freshness, ())


def _contexto_temporal(
    *,
    data_solicitada: date,
    data_efetiva: date | None,
    defasagem_dias: int | None,
    freshness: FreshnessStatus | None,
    janela_inicio: date | None,
    janela_fim: date | None,
    dias_esperados: int,
    dias_disponiveis: int,
    cobertura_pct: float | None,
) -> ContextoTemporalFeature | None:
    if freshness is None:
        return None
    return ContextoTemporalFeature(
        data_referencia_solicitada=data_solicitada,
        data_referencia_efetiva=data_efetiva,
        defasagem_dias=defasagem_dias,
        freshness_status=freshness,
        janela_inicio=janela_inicio,
        janela_fim=janela_fim,
        dias_esperados=dias_esperados,
        dias_disponiveis=dias_disponiveis,
        cobertura_pct=cobertura_pct,
    )


def _feature_janela(
    *,
    nome: str,
    unidade: str,
    variavel: str,
    dias: int,
    data_solicitada: date,
    indice: dict[str, dict[date, DadoNormalizado]],
    serie: SerieDadosNormalizados,
    operacao: Callable[[list[float]], float],
    algoritmo: str,
) -> FeatureNeutra:
    referencia, efetiva_diagnostico, defasagem, freshness = _referencia_efetiva(
        variavel=variavel,
        data_solicitada=data_solicitada,
        indice=indice,
        serie=serie,
    )
    if referencia is None:
        flags = tuple(
            dict.fromkeys(
                [
                    *serie.qualidade.flags,
                    *_flags_freshness(freshness),
                ]
            )
        )
        return FeatureNeutra(
            nome=nome,
            valor=None,
            unidade=unidade,
            fonte=serie.fonte,
            natureza=serie.natureza,
            referencia_temporal=None,
            qualidade=QualidadeDado(
                status=StatusQualidade.AUSENTE,
                simulado=serie.qualidade.simulado,
                cobertura_pct=None,
                flags=flags,
            ),
            linhagem=_linhagem(
                fonte=serie.fonte,
                natureza=serie.natureza,
                algoritmo=algoritmo,
                janela=f"{dias}_dias_calendario_inclusivos",
                entradas=(variavel,),
            ),
            contexto_temporal=_contexto_temporal(
                data_solicitada=data_solicitada,
                data_efetiva=efetiva_diagnostico,
                defasagem_dias=defasagem,
                freshness=freshness,
                janela_inicio=None,
                janela_fim=None,
                dias_esperados=dias,
                dias_disponiveis=0,
                cobertura_pct=None,
            ),
            metadados={"dias_esperados": dias, "dias_disponiveis": 0},
        )

    inicio = referencia - timedelta(days=dias - 1)
    datas = [inicio + timedelta(days=i) for i in range(dias)]
    valores = []
    for dia in datas:
        dado = indice[variavel].get(dia)
        if dado is not None and dado.valor is not None:
            valores.append(float(dado.valor))
    qualidade = _qualidade_janela(
        esperados=dias,
        disponiveis=len(valores),
        simulado=serie.qualidade.simulado,
        flags_origem=tuple(
            dict.fromkeys(
                [
                    *serie.qualidade.flags,
                    *_flags_freshness(freshness),
                ]
            )
        ),
    )
    valor = operacao(valores) if valores else None
    return FeatureNeutra(
        nome=nome,
        valor=valor,
        unidade=unidade,
        fonte=serie.fonte,
        natureza=serie.natureza,
        referencia_temporal=ReferenciaTemporal(
            inicio=inicio,
            fim=referencia,
            timezone=None,
            agregacao=AgregacaoTemporal.DIARIA,
        ),
        qualidade=qualidade,
        linhagem=_linhagem(
            fonte=serie.fonte,
            natureza=serie.natureza,
            algoritmo=algoritmo,
            janela=f"{dias}_dias_calendario_inclusivos",
            entradas=(variavel,),
        ),
        contexto_temporal=_contexto_temporal(
            data_solicitada=data_solicitada,
            data_efetiva=efetiva_diagnostico,
            defasagem_dias=defasagem,
            freshness=freshness,
            janela_inicio=inicio,
            janela_fim=referencia,
            dias_esperados=dias,
            dias_disponiveis=len(valores),
            cobertura_pct=qualidade.cobertura_pct,
        ),
        metadados={"dias_esperados": dias, "dias_disponiveis": len(valores)},
    )


def _temperatura_referencia(
    data_solicitada: date,
    indice: dict[str, dict[date, DadoNormalizado]],
    serie: SerieDadosNormalizados,
) -> FeatureNeutra:
    referencia, efetiva_diagnostico, defasagem, freshness = _referencia_efetiva(
        variavel=TEMPERATURA_MAXIMA,
        data_solicitada=data_solicitada,
        indice=indice,
        serie=serie,
    )
    if referencia is None:
        valor = None
    else:
        dado = indice[TEMPERATURA_MAXIMA].get(referencia)
        valor = None if dado is None or dado.valor is None else float(dado.valor)
    qualidade = _qualidade_janela(
        esperados=1,
        disponiveis=int(valor is not None),
        simulado=serie.qualidade.simulado,
        flags_origem=tuple(
            dict.fromkeys(
                [
                    *serie.qualidade.flags,
                    *_flags_freshness(freshness),
                ]
            )
        ),
    )
    return FeatureNeutra(
        nome="temperatura_maxima_dia_referencia_c",
        valor=valor,
        unidade="°C",
        fonte=serie.fonte,
        natureza=serie.natureza,
        referencia_temporal=(
            ReferenciaTemporal(
                inicio=referencia,
                fim=referencia,
                timezone=None,
                agregacao=AgregacaoTemporal.DIARIA,
            )
            if referencia is not None
            else None
        ),
        qualidade=qualidade,
        linhagem=_linhagem(
            fonte=serie.fonte,
            natureza=serie.natureza,
            algoritmo="valor_dia_referencia",
            janela="dia_referencia",
            entradas=(TEMPERATURA_MAXIMA,),
        ),
        contexto_temporal=_contexto_temporal(
            data_solicitada=data_solicitada,
            data_efetiva=efetiva_diagnostico,
            defasagem_dias=defasagem,
            freshness=freshness,
            janela_inicio=referencia,
            janela_fim=referencia,
            dias_esperados=1,
            dias_disponiveis=int(valor is not None),
            cobertura_pct=qualidade.cobertura_pct,
        ),
        metadados={"dias_esperados": 1, "dias_disponiveis": int(valor is not None)},
    )


def _dias_sem_chuva(
    data_solicitada: date,
    indice: dict[str, dict[date, DadoNormalizado]],
    serie: SerieDadosNormalizados,
) -> FeatureNeutra:
    mapa = indice[PRECIPITACAO]
    referencia, efetiva_diagnostico, defasagem, freshness = _referencia_efetiva(
        variavel=PRECIPITACAO,
        data_solicitada=data_solicitada,
        indice=indice,
        serie=serie,
    )
    flags = [*serie.qualidade.flags, *_flags_freshness(freshness)]
    atual = referencia
    contagem = 0
    observados = 0
    status = StatusQualidade.DISPONIVEL
    valor: int | None

    if referencia is None or not mapa or atual not in mapa or mapa[atual].valor is None:
        valor = None
        status = StatusQualidade.AUSENTE
        flags.append("DIA_REFERENCIA_AUSENTE")
        esperados = 1
    else:
        menor_data = min(mapa)
        while True:
            dado = mapa.get(atual)
            if dado is None or dado.valor is None:
                status = StatusQualidade.PARCIAL
                flags.append("SEQUENCIA_INTERROMPIDA_POR_LACUNA")
                break
            observados += 1
            if float(dado.valor) >= LIMIAR_LEGADO_DIA_SEM_CHUVA_MM:
                break
            contagem += 1
            if atual == menor_data:
                status = StatusQualidade.PARCIAL
                flags.append("INICIO_SERIE_LIMITA_SEQUENCIA")
                break
            atual -= timedelta(days=1)
        valor = contagem
        esperados = observados + int("SEQUENCIA_INTERROMPIDA_POR_LACUNA" in flags)

    cobertura = observados * 100.0 / esperados if esperados else None
    return FeatureNeutra(
        nome="dias_sem_chuva_consecutivos",
        valor=valor,
        unidade="dias",
        fonte=serie.fonte,
        natureza=serie.natureza,
        referencia_temporal=(
            ReferenciaTemporal(
                inicio=atual if valor is not None else data_solicitada,
                fim=referencia if referencia is not None else data_solicitada,
                timezone=None,
                agregacao=AgregacaoTemporal.DIARIA,
            )
            if referencia is not None
            else None
        ),
        qualidade=QualidadeDado(
            status=status,
            simulado=serie.qualidade.simulado,
            cobertura_pct=cobertura,
            flags=tuple(dict.fromkeys(flags)),
        ),
        linhagem=_linhagem(
            fonte=serie.fonte,
            natureza=serie.natureza,
            algoritmo="sequencia_dias_precipitacao_menor_1mm",
            janela="retroativa_ate_chuva_ou_interrupcao",
            entradas=(PRECIPITACAO,),
        ),
        contexto_temporal=_contexto_temporal(
            data_solicitada=data_solicitada,
            data_efetiva=efetiva_diagnostico,
            defasagem_dias=defasagem,
            freshness=freshness,
            janela_inicio=(atual if valor is not None else None),
            janela_fim=(referencia if valor is not None else None),
            dias_esperados=esperados,
            dias_disponiveis=observados,
            cobertura_pct=cobertura,
        ),
        metadados={
            "limiar_definicao_feature_mm_dia": LIMIAR_LEGADO_DIA_SEM_CHUVA_MM,
            "dias_esperados": esperados,
            "dias_disponiveis": observados,
        },
    )


def _qualidade_grupo(features: tuple[FeatureNeutra, ...]) -> QualidadeDado:
    if not features or all(
        f.qualidade.status == StatusQualidade.AUSENTE for f in features
    ):
        status = StatusQualidade.AUSENTE
    elif all(f.qualidade.status == StatusQualidade.DISPONIVEL for f in features):
        status = StatusQualidade.DISPONIVEL
    else:
        status = StatusQualidade.PARCIAL
    coberturas = [
        f.qualidade.cobertura_pct
        for f in features
        if f.qualidade.cobertura_pct is not None
    ]
    flags = tuple(
        dict.fromkeys(flag for feature in features for flag in feature.qualidade.flags)
    )
    return QualidadeDado(
        status=status,
        simulado=any(f.qualidade.simulado for f in features),
        cobertura_pct=(sum(coberturas) / len(coberturas) if coberturas else None),
        flags=flags,
    )


def calcular_features_climaticas(
    serie: SerieDadosNormalizados,
    *,
    data_referencia: date | None = None,
) -> GrupoFeatures:
    """Calcula cinco features neutras usando datas civis, nunca número de linhas."""
    indice = _validar_e_indexar(serie)
    datas = [dia for mapa in indice.values() for dia in mapa]
    if data_referencia is None:
        if not datas:
            return GrupoFeatures(
                qualidade=QualidadeDado(status=StatusQualidade.AUSENTE),
                contexto={"motivo": "serie_sem_dados_compativeis"},
            )
        data_referencia = max(datas)

    features = (
        _feature_janela(
            nome="chuva_acumulada_3_dias_mm",
            unidade="mm",
            variavel=PRECIPITACAO,
            dias=3,
            data_solicitada=data_referencia,
            indice=indice,
            serie=serie,
            operacao=sum,
            algoritmo="soma_precipitacao_janela_calendario",
        ),
        _feature_janela(
            nome="chuva_acumulada_7_dias_mm",
            unidade="mm",
            variavel=PRECIPITACAO,
            dias=7,
            data_solicitada=data_referencia,
            indice=indice,
            serie=serie,
            operacao=sum,
            algoritmo="soma_precipitacao_janela_calendario",
        ),
        _dias_sem_chuva(data_referencia, indice, serie),
        _feature_janela(
            nome="umidade_relativa_media_3_dias_pct",
            unidade="%",
            variavel=UMIDADE,
            dias=3,
            data_solicitada=data_referencia,
            indice=indice,
            serie=serie,
            operacao=fmean,
            algoritmo="media_umidade_janela_calendario",
        ),
        _temperatura_referencia(data_referencia, indice, serie),
    )
    return GrupoFeatures(
        features=features,
        qualidade=_qualidade_grupo(features),
        contexto={
            "data_referencia": data_referencia.isoformat(),
            "data_referencia_solicitada": data_referencia.isoformat(),
            "fonte": serie.fonte.value,
            "natureza": serie.natureza.value,
            "politica_temporal": (
                "referencia_efetiva_por_variavel_ate_3_dias_sem_imputacao"
            ),
        },
    )


__all__ = [
    "LIMIAR_LEGADO_DIA_SEM_CHUVA_MM",
    "LIMITE_FRESHNESS_NASA_DIAS",
    "calcular_features_climaticas",
]
