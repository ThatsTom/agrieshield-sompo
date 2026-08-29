"""Contratos internos tipados da camada neutra de risco.

Os modelos deliberadamente não conhecem FastAPI, repositórios, arquivos ou
clientes externos. Assim, podem receber dados equivalentes vindos do legado,
de memória, de testes ou futuramente do Supabase.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


FEATURES_VERSION = "risk-features-v2"


class NaturezaDado(str, Enum):
    CADASTRAL = "CADASTRAL"
    OBSERVADO = "OBSERVADO"
    PREVISTO = "PREVISTO"
    HISTORICO = "HISTORICO"
    ESTRUTURAL = "ESTRUTURAL"


class NivelProcessamento(str, Enum):
    BRUTO = "BRUTO"
    NORMALIZADO = "NORMALIZADO"
    DERIVADO = "DERIVADO"


class FonteDado(str, Enum):
    CADASTRO = "CADASTRO"
    BASE_CEP = "BASE_CEP"
    NASA_POWER = "NASA_POWER"
    OPEN_METEO = "OPEN_METEO"
    INMET = "INMET"
    SRTM = "SRTM"
    MERIT_HYDRO = "MERIT_HYDRO"
    MAPBIOMAS = "MAPBIOMAS"
    SIMULADOR_INTERNO = "SIMULADOR_INTERNO"


class StatusQualidade(str, Enum):
    DISPONIVEL = "DISPONIVEL"
    AUSENTE = "AUSENTE"
    PARCIAL = "PARCIAL"
    INVALIDO = "INVALIDO"


class FreshnessStatus(str, Enum):
    ATUAL = "ATUAL"
    DEFASADO = "DEFASADO"
    DESATUALIZADO = "DESATUALIZADO"
    AUSENTE = "AUSENTE"


class AgregacaoTemporal(str, Enum):
    INSTANTANEA = "INSTANTANEA"
    HORARIA = "HORARIA"
    DIARIA = "DIARIA"
    ANUAL = "ANUAL"


class ModeloDominio(BaseModel):
    """Base imutável: normalizadores não devem produzir estado mutável oculto."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
    )


class QualidadeDado(ModeloDominio):
    status: StatusQualidade = StatusQualidade.DISPONIVEL
    imputado: bool = False
    simulado: bool = False
    cobertura_pct: float | None = Field(default=None, ge=0, le=100)
    flags: tuple[str, ...] = ()


class ReferenciaTemporal(ModeloDominio):
    inicio: date | datetime
    fim: date | datetime | None = None
    timezone: str | None = None
    agregacao: AgregacaoTemporal

    @model_validator(mode="after")
    def validar_intervalo(self) -> "ReferenciaTemporal":
        fim = self.fim if self.fim is not None else self.inicio
        if type(self.inicio) is not type(fim):
            raise ValueError("inicio e fim devem usar o mesmo tipo temporal")
        if fim < self.inicio:
            raise ValueError("fim deve ser igual ou posterior ao início")
        if self.agregacao == AgregacaoTemporal.HORARIA:
            if not isinstance(self.inicio, datetime) or self.inicio.tzinfo is None:
                raise ValueError("referência horária exige datetime com timezone")
            if self.timezone is None:
                raise ValueError("referência horária exige timezone explícito")
        return self


ValorEscalar = float | int | bool | str | None


class DadoNormalizado(ModeloDominio):
    variavel: str
    valor: ValorEscalar = None
    unidade: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    nivel_processamento: NivelProcessamento
    referencia_temporal: ReferenciaTemporal | None = None
    coletado_em_utc: datetime | None = None
    qualidade: QualidadeDado = Field(default_factory=QualidadeDado)
    metadados: dict[str, Any] = Field(default_factory=dict)


class SerieDadosNormalizados(ModeloDominio):
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    agregacao: AgregacaoTemporal
    dados: tuple[DadoNormalizado, ...]
    qualidade: QualidadeDado
    contexto: dict[str, Any] = Field(default_factory=dict)


class CadastroNormalizado(ModeloDominio):
    id_fazenda: str
    nome: str
    numero_apolice: str
    cep: str
    cidade: str
    uf: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_ha: float | None = Field(default=None, gt=0)
    tipo_operacao: str
    proximidade_agua_declarada: bool | None
    fonte: FonteDado = FonteDado.CADASTRO
    natureza: NaturezaDado = NaturezaDado.CADASTRAL
    nivel_processamento: NivelProcessamento = NivelProcessamento.NORMALIZADO


class ReferenciaEspacial(ModeloDominio):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_ha: float | None = Field(default=None, gt=0)
    raio_equivalente_m: float | None = Field(default=None, gt=0)


class AtributoGeoespacial(ModeloDominio):
    variavel: str
    valor: float | None = None
    unidade: str
    fonte: FonteDado
    dataset: str
    banda: str
    resolucao_m: float = Field(gt=0)
    metodologia: str
    qualidade: QualidadeDado


class ParametrosGeoespaciais(ModeloDominio):
    raio_analise_m: float = Field(gt=0)
    limiar_drenagem_km2: float = Field(gt=0)
    raio_busca_drenagem_m: float = Field(gt=0)


class AnaliseGeoespacialNormalizada(ModeloDominio):
    referencia: ReferenciaEspacial
    declividade_media_graus: AtributoGeoespacial
    posicao_topografica_relativa_m: AtributoGeoespacial
    distancia_drenagem_m: AtributoGeoespacial
    area_drenagem_montante_km2: AtributoGeoespacial
    parametros: ParametrosGeoespaciais
    qualidade: QualidadeDado
    qualidade_contexto: dict[str, Any] = Field(default_factory=dict)
    fontes: tuple[dict[str, Any], ...] = ()
    schema_version: str
    algorithm_version: str
    calculado_em_utc: datetime | None = None
    status_fonte: str


class ContextoGeometriaTerritorial(ModeloDominio):
    tipo_geometria: str
    metodo_geometria: str
    origem_coordenada: str
    precisao_espacial: str
    warning: str


class DistribuicaoClasseTerritorial(ModeloDominio):
    codigo: int
    nome: str
    area_m2: float = Field(ge=0)
    percentual_area_valida: float = Field(ge=0, le=100)


class QualidadeTerritorial(ModeloDominio):
    area_nominal_m2: float = Field(ge=0)
    area_geometria_m2: float = Field(ge=0)
    area_grade_analisada_m2: float = Field(ge=0)
    area_mapeada_m2: float = Field(ge=0)
    area_valida_m2: float = Field(ge=0)
    area_nao_observada_m2: float = Field(ge=0)
    area_codigo_27_m2: float = Field(ge=0)
    area_no_data_m2: float = Field(ge=0)
    cobertura_valida_pct: float = Field(ge=0, le=100)
    soma_percentuais_validos: float = Field(ge=0)


class AnaliseTerritorialNormalizada(ModeloDominio):
    id_fazenda: str
    referencia: ReferenciaEspacial
    geometria: ContextoGeometriaTerritorial
    ano_referencia: int
    asset_id: str
    colecao: str
    asset_version: str
    banda: str
    legend_version: str
    algorithm_version: str
    schema_version: str
    fingerprint: str
    classe_predominante_codigo: int
    classe_predominante_nome: str
    agricultura_pct: float = Field(ge=0, le=100)
    pastagem_pct: float = Field(ge=0, le=100)
    vegetacao_nativa_pct: float = Field(ge=0, le=100)
    agua_pct: float = Field(ge=0, le=100)
    outros_pct: float = Field(ge=0, le=100)
    distribuicao_bruta: tuple[DistribuicaoClasseTerritorial, ...]
    qualidade_territorial: QualidadeTerritorial
    qualidade: QualidadeDado
    calculado_em_utc: datetime


class LinhagemFeature(ModeloDominio):
    algoritmo: str
    versao: str = FEATURES_VERSION
    fonte: FonteDado
    natureza: NaturezaDado
    janela: str
    entradas: tuple[str, ...]


class ContextoTemporalFeature(ModeloDominio):
    data_referencia_solicitada: date
    data_referencia_efetiva: date | None = None
    defasagem_dias: int | None = Field(default=None, ge=0)
    freshness_status: FreshnessStatus
    janela_inicio: date | None = None
    janela_fim: date | None = None
    dias_esperados: int = Field(ge=1)
    dias_disponiveis: int = Field(ge=0)
    cobertura_pct: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validar_coerencia_temporal(self) -> "ContextoTemporalFeature":
        if self.dias_disponiveis > self.dias_esperados:
            raise ValueError("dias_disponiveis não pode exceder dias_esperados")
        if (self.janela_inicio is None) != (self.janela_fim is None):
            raise ValueError("janela temporal deve informar início e fim conjuntamente")
        if self.janela_inicio is not None and self.janela_fim < self.janela_inicio:
            raise ValueError("janela_fim deve ser igual ou posterior a janela_inicio")
        if self.data_referencia_efetiva is None:
            if self.defasagem_dias is not None:
                raise ValueError("defasagem exige data_referencia_efetiva")
        else:
            if self.data_referencia_efetiva > self.data_referencia_solicitada:
                raise ValueError("data efetiva não pode ser futura à data solicitada")
            defasagem = (
                self.data_referencia_solicitada - self.data_referencia_efetiva
            ).days
            if self.defasagem_dias != defasagem:
                raise ValueError("defasagem_dias incoerente com as datas de referência")
        return self


class FeatureNeutra(ModeloDominio):
    nome: str
    valor: ValorEscalar = None
    unidade: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    referencia_temporal: ReferenciaTemporal | None = None
    qualidade: QualidadeDado
    linhagem: LinhagemFeature
    contexto_temporal: ContextoTemporalFeature | None = None
    metadados: dict[str, Any] = Field(default_factory=dict)


class GrupoFeatures(ModeloDominio):
    features: tuple[FeatureNeutra, ...] = ()
    qualidade: QualidadeDado
    contexto: dict[str, Any] = Field(default_factory=dict)


class ConjuntoFeatures(ModeloDominio):
    id_fazenda: str
    calculado_em_utc: datetime
    versao: str = FEATURES_VERSION
    climaticas: GrupoFeatures
    geoespaciais_hidrologicas: GrupoFeatures
    territoriais: GrupoFeatures
    operacionais: GrupoFeatures
    qualidade_global: QualidadeDado


__all__ = [
    "FEATURES_VERSION",
    "AgregacaoTemporal",
    "AnaliseGeoespacialNormalizada",
    "AnaliseTerritorialNormalizada",
    "AtributoGeoespacial",
    "CadastroNormalizado",
    "ConjuntoFeatures",
    "ContextoTemporalFeature",
    "ContextoGeometriaTerritorial",
    "DadoNormalizado",
    "DistribuicaoClasseTerritorial",
    "FeatureNeutra",
    "FreshnessStatus",
    "FonteDado",
    "GrupoFeatures",
    "LinhagemFeature",
    "NaturezaDado",
    "NivelProcessamento",
    "ParametrosGeoespaciais",
    "QualidadeDado",
    "QualidadeTerritorial",
    "ReferenciaEspacial",
    "ReferenciaTemporal",
    "SerieDadosNormalizados",
    "StatusQualidade",
]
