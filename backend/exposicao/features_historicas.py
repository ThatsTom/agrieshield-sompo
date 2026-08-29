"""Cálculo puro e neutro de features meteorológicas históricas."""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean
from typing import Callable, Iterable

from pydantic import Field, model_validator

from backend.exposicao.modelos import (
    JanelaHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
)
from backend.risco.modelos import FonteDado, ModeloDominio, NaturezaDado


FEATURES_HISTORICAS_VERSION = "exposicao-features-v1"


class FeatureHistorica(ModeloDominio):
    nome: str
    valor: float | None = None
    unidade: str
    data_associada: date | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    periodo: JanelaHistorica
    dias_esperados: int = Field(ge=1)
    dias_disponiveis: int = Field(ge=0)
    cobertura_pct: float = Field(ge=0, le=100)
    versao: str = FEATURES_HISTORICAS_VERSION
    linhagem: tuple[str, ...]

    @model_validator(mode="after")
    def validar_coerencia(self) -> "FeatureHistorica":
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("feature histórica exige natureza HISTORICO")
        if self.dias_esperados != self.periodo.dias_esperados:
            raise ValueError("dias esperados deve refletir o período da feature")
        if self.dias_disponiveis > self.dias_esperados:
            raise ValueError("dias disponíveis não pode exceder dias esperados")
        cobertura_esperada = round(100 * self.dias_disponiveis / self.dias_esperados, 2)
        if self.cobertura_pct != cobertura_esperada:
            raise ValueError("cobertura incoerente com os dias disponíveis")
        if self.valor is None and self.dias_disponiveis != 0:
            raise ValueError("valor ausente exige zero dias disponíveis")
        if self.valor is not None and self.dias_disponiveis == 0:
            raise ValueError("valor exige ao menos um dia disponível")
        if self.data_associada is not None and not (
            self.periodo.inicio <= self.data_associada <= self.periodo.fim
        ):
            raise ValueError("data associada deve pertencer ao período da feature")
        if not self.linhagem:
            raise ValueError("feature histórica exige linhagem")
        return self


class FeaturesHistoricas(ModeloDominio):
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    periodo: JanelaHistorica
    versao: str = FEATURES_HISTORICAS_VERSION
    precipitacao_acumulada_90d_mm: FeatureHistorica
    precipitacao_acumulada_30d_mm: FeatureHistorica
    precipitacao_media_diaria_mm: FeatureHistorica
    maior_precipitacao_diaria_mm: FeatureHistorica
    temperatura_media_90d_c: FeatureHistorica
    temperatura_maxima_90d_c: FeatureHistorica
    temperatura_minima_90d_c: FeatureHistorica
    umidade_media_90d_pct: FeatureHistorica
    umidade_minima_90d_pct: FeatureHistorica
    umidade_maxima_90d_pct: FeatureHistorica

    @model_validator(mode="after")
    def validar_origem_unica(self) -> "FeaturesHistoricas":
        if self.periodo.dias_esperados != 90:
            raise ValueError("conjunto de features exige período de 90 dias")
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("conjunto histórico exige natureza HISTORICO")
        for feature in self.todas():
            if (
                feature.fonte != self.fonte
                or feature.natureza != self.natureza
                or feature.tipo_produto != self.tipo_produto
                or feature.dataset != self.dataset
            ):
                raise ValueError("features não podem misturar origens")
        return self

    def todas(self) -> tuple[FeatureHistorica, ...]:
        return (
            self.precipitacao_acumulada_90d_mm,
            self.precipitacao_acumulada_30d_mm,
            self.precipitacao_media_diaria_mm,
            self.maior_precipitacao_diaria_mm,
            self.temperatura_media_90d_c,
            self.temperatura_maxima_90d_c,
            self.temperatura_minima_90d_c,
            self.umidade_media_90d_pct,
            self.umidade_minima_90d_pct,
            self.umidade_maxima_90d_pct,
        )

    def buscar(self, nome: str) -> FeatureHistorica:
        for feature in self.todas():
            if feature.nome == nome:
                return feature
        raise KeyError(nome)


class ComparacaoFeatureHistorica(ModeloDominio):
    nome: str
    unidade: str
    valor_atual: float | None = None
    valor_anterior: float | None = None
    diferenca_absoluta: float | None = None
    variacao_pct: float | None = None
    motivo_variacao_indisponivel: str | None = None
    fonte: FonteDado
    dataset: str
    periodo_atual: JanelaHistorica
    periodo_anterior: JanelaHistorica
    versao: str = FEATURES_HISTORICAS_VERSION

    @model_validator(mode="after")
    def validar_comparacao(self) -> "ComparacaoFeatureHistorica":
        if self.periodo_atual.dias_esperados != 90:
            raise ValueError("período atual deve conter 90 dias")
        if self.periodo_anterior.dias_esperados != 90:
            raise ValueError("período anterior deve conter 90 dias")
        if self.periodo_anterior.fim + timedelta(days=1) != self.periodo_atual.inicio:
            raise ValueError("períodos comparados devem ser contíguos")
        if self.valor_atual is None or self.valor_anterior is None:
            if self.diferenca_absoluta is not None or self.variacao_pct is not None:
                raise ValueError(
                    "comparação com valor ausente não pode inventar resultado"
                )
        return self


class ComparacaoPeriodosHistoricos(ModeloDominio):
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    periodo_atual: FeaturesHistoricas
    periodo_anterior: FeaturesHistoricas
    comparacoes: tuple[ComparacaoFeatureHistorica, ...]
    versao: str = FEATURES_HISTORICAS_VERSION

    @model_validator(mode="after")
    def validar_origem_e_periodos(self) -> "ComparacaoPeriodosHistoricos":
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("comparação histórica exige natureza HISTORICO")
        for conjunto in (self.periodo_atual, self.periodo_anterior):
            if (
                conjunto.fonte != self.fonte
                or conjunto.natureza != self.natureza
                or conjunto.tipo_produto != self.tipo_produto
                or conjunto.dataset != self.dataset
            ):
                raise ValueError("comparação não pode misturar fontes")
        if (
            self.periodo_anterior.periodo.fim + timedelta(days=1)
            != self.periodo_atual.periodo.inicio
        ):
            raise ValueError("períodos comparados devem ser contíguos")
        return self

    def buscar(self, nome: str) -> ComparacaoFeatureHistorica:
        for comparacao in self.comparacoes:
            if comparacao.nome == nome:
                return comparacao
        raise KeyError(nome)


def _janela_30d(janela_90d: JanelaHistorica) -> JanelaHistorica:
    return JanelaHistorica(
        data_referencia=janela_90d.data_referencia,
        inicio=janela_90d.fim - timedelta(days=29),
        fim=janela_90d.fim,
        dias_esperados=30,
        finalidade=janela_90d.finalidade,
    )


def _validar_janela_na_serie(
    serie: SerieHistoricaFonte, janela: JanelaHistorica
) -> None:
    if janela.dias_esperados != 90:
        raise ValueError("features históricas exigem uma janela de 90 dias")
    solicitado = serie.periodo_solicitado
    if janela.inicio < solicitado.inicio or janela.fim > solicitado.fim:
        raise ValueError("janela de features deve estar contida na série")


def _registros_no_periodo(
    registros: Iterable[RegistroMeteorologicoDiario], janela: JanelaHistorica
) -> tuple[RegistroMeteorologicoDiario, ...]:
    return tuple(
        registro
        for registro in registros
        if janela.inicio <= registro.data <= janela.fim
    )


def _criar_feature(
    *,
    serie: SerieHistoricaFonte,
    periodo: JanelaHistorica,
    nome: str,
    unidade: str,
    variavel: str,
    operacao: str,
    agregador: Callable[[list[float]], float],
    data_associada: bool = False,
) -> FeatureHistorica:
    pares = [
        (registro.data, valor)
        for registro in _registros_no_periodo(serie.registros, periodo)
        if (valor := getattr(registro, variavel)) is not None
    ]
    valores = [valor for _, valor in pares]
    valor_feature = agregador(valores) if valores else None
    data_feature: date | None = None
    if data_associada and pares:
        if operacao == "maximo":
            data_feature = min(data for data, valor in pares if valor == valor_feature)
        elif operacao == "minimo":
            data_feature = min(data for data, valor in pares if valor == valor_feature)
    dias_disponiveis = len(valores)
    return FeatureHistorica(
        nome=nome,
        valor=valor_feature,
        unidade=unidade,
        data_associada=data_feature,
        fonte=serie.fonte,
        natureza=serie.natureza,
        tipo_produto=serie.tipo_produto,
        dataset=serie.dataset,
        periodo=periodo,
        dias_esperados=periodo.dias_esperados,
        dias_disponiveis=dias_disponiveis,
        cobertura_pct=round(100 * dias_disponiveis / periodo.dias_esperados, 2),
        linhagem=(
            f"SerieHistoricaFonte.registros.{variavel}",
            f"operacao={operacao}_valores_validos",
            "ausencia=None_sem_imputacao",
        ),
    )


def calcular_features_historicas(
    serie: SerieHistoricaFonte,
    janela: JanelaHistorica | None = None,
) -> FeaturesHistoricas:
    """Calcula estatísticas neutras na janela fixa D-89 a D0."""

    if not isinstance(serie, SerieHistoricaFonte):
        raise TypeError("serie deve ser uma SerieHistoricaFonte")
    periodo = janela or JanelaHistorica.criar_atual(
        serie.periodo_solicitado.data_referencia, 90
    )
    _validar_janela_na_serie(serie, periodo)
    periodo_30d = _janela_30d(periodo)

    def feature(**kwargs: object) -> FeatureHistorica:
        return _criar_feature(serie=serie, periodo=periodo, **kwargs)

    precipitacao_90 = feature(
        nome="precipitacao_acumulada_90d_mm",
        unidade="mm",
        variavel="precipitacao_mm",
        operacao="soma",
        agregador=sum,
    )
    precipitacao_30 = _criar_feature(
        serie=serie,
        periodo=periodo_30d,
        nome="precipitacao_acumulada_30d_mm",
        unidade="mm",
        variavel="precipitacao_mm",
        operacao="soma",
        agregador=sum,
    )
    precipitacao_media = feature(
        nome="precipitacao_media_diaria_mm",
        unidade="mm/dia_disponivel",
        variavel="precipitacao_mm",
        operacao="media",
        agregador=fmean,
    )
    maior_precipitacao = feature(
        nome="maior_precipitacao_diaria_mm",
        unidade="mm",
        variavel="precipitacao_mm",
        operacao="maximo",
        agregador=max,
        data_associada=True,
    )
    temperatura_media = feature(
        nome="temperatura_media_90d_c",
        unidade="°C",
        variavel="temperatura_media_c",
        operacao="media",
        agregador=fmean,
    )
    temperatura_maxima = feature(
        nome="temperatura_maxima_90d_c",
        unidade="°C",
        variavel="temperatura_maxima_c",
        operacao="maximo",
        agregador=max,
        data_associada=True,
    )
    temperatura_minima = feature(
        nome="temperatura_minima_90d_c",
        unidade="°C",
        variavel="temperatura_minima_c",
        operacao="minimo",
        agregador=min,
        data_associada=True,
    )
    umidade_media = feature(
        nome="umidade_media_90d_pct",
        unidade="%",
        variavel="umidade_media_pct",
        operacao="media",
        agregador=fmean,
    )
    umidade_minima = feature(
        nome="umidade_minima_90d_pct",
        unidade="%",
        variavel="umidade_media_pct",
        operacao="minimo",
        agregador=min,
        data_associada=True,
    )
    umidade_maxima = feature(
        nome="umidade_maxima_90d_pct",
        unidade="%",
        variavel="umidade_media_pct",
        operacao="maximo",
        agregador=max,
        data_associada=True,
    )
    return FeaturesHistoricas(
        id_fazenda=serie.id_fazenda,
        fonte=serie.fonte,
        natureza=serie.natureza,
        tipo_produto=serie.tipo_produto,
        dataset=serie.dataset,
        periodo=periodo,
        precipitacao_acumulada_90d_mm=precipitacao_90,
        precipitacao_acumulada_30d_mm=precipitacao_30,
        precipitacao_media_diaria_mm=precipitacao_media,
        maior_precipitacao_diaria_mm=maior_precipitacao,
        temperatura_media_90d_c=temperatura_media,
        temperatura_maxima_90d_c=temperatura_maxima,
        temperatura_minima_90d_c=temperatura_minima,
        umidade_media_90d_pct=umidade_media,
        umidade_minima_90d_pct=umidade_minima,
        umidade_maxima_90d_pct=umidade_maxima,
    )


def _comparar_feature(
    atual: FeatureHistorica,
    anterior: FeatureHistorica,
    *,
    permite_variacao_pct: bool,
) -> ComparacaoFeatureHistorica:
    if atual.nome != anterior.nome or atual.unidade != anterior.unidade:
        raise ValueError("comparação exige features equivalentes")
    diferenca: float | None = None
    variacao: float | None = None
    motivo: str | None = None
    if atual.valor is None or anterior.valor is None:
        motivo = "VALOR_AUSENTE"
    else:
        diferenca = atual.valor - anterior.valor
        if not permite_variacao_pct:
            motivo = "VARIACAO_PERCENTUAL_NAO_APLICAVEL"
        elif anterior.valor == 0:
            motivo = "PERIODO_ANTERIOR_ZERO"
        else:
            variacao = round(100 * diferenca / abs(anterior.valor), 2)
    return ComparacaoFeatureHistorica(
        nome=atual.nome,
        unidade=atual.unidade,
        valor_atual=atual.valor,
        valor_anterior=anterior.valor,
        diferenca_absoluta=diferenca,
        variacao_pct=variacao,
        motivo_variacao_indisponivel=motivo,
        fonte=atual.fonte,
        dataset=atual.dataset,
        periodo_atual=atual.periodo,
        periodo_anterior=anterior.periodo,
    )


def comparar_periodos_90d(
    serie: SerieHistoricaFonte,
) -> ComparacaoPeriodosHistoricos:
    """Divide D-179..D0 e compara estatísticas equivalentes sem interpretação."""

    if not isinstance(serie, SerieHistoricaFonte):
        raise TypeError("serie deve ser uma SerieHistoricaFonte")
    anterior, atual = serie.periodo_solicitado.dividir_em_periodos_90()
    features_anterior = calcular_features_historicas(serie, anterior)
    features_atual = calcular_features_historicas(serie, atual)

    nomes_com_variacao = {
        "precipitacao_acumulada_90d_mm",
        "precipitacao_media_diaria_mm",
        "maior_precipitacao_diaria_mm",
        "umidade_media_90d_pct",
        "umidade_minima_90d_pct",
        "umidade_maxima_90d_pct",
    }
    nomes_comparados = (
        "precipitacao_acumulada_90d_mm",
        "precipitacao_media_diaria_mm",
        "maior_precipitacao_diaria_mm",
        "temperatura_media_90d_c",
        "temperatura_maxima_90d_c",
        "temperatura_minima_90d_c",
        "umidade_media_90d_pct",
        "umidade_minima_90d_pct",
        "umidade_maxima_90d_pct",
    )
    comparacoes = tuple(
        _comparar_feature(
            features_atual.buscar(nome),
            features_anterior.buscar(nome),
            permite_variacao_pct=nome in nomes_com_variacao,
        )
        for nome in nomes_comparados
    )
    return ComparacaoPeriodosHistoricos(
        id_fazenda=serie.id_fazenda,
        fonte=serie.fonte,
        natureza=serie.natureza,
        tipo_produto=serie.tipo_produto,
        dataset=serie.dataset,
        periodo_atual=features_atual,
        periodo_anterior=features_anterior,
        comparacoes=comparacoes,
    )


__all__ = [
    "FEATURES_HISTORICAS_VERSION",
    "ComparacaoFeatureHistorica",
    "ComparacaoPeriodosHistoricos",
    "FeatureHistorica",
    "FeaturesHistoricas",
    "calcular_features_historicas",
    "comparar_periodos_90d",
]
