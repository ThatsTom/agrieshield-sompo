"""Validacao conjunta dos cinco perigos do MVP, sem compor score.

A camada apenas executa os calculos existentes sobre uma janela e uma fonte
meteorologica comuns. Dependencias metodologicas e evidencias compartilhadas
sao mantidas explicitas como documentacao. Trafegabilidade tem metodologia
meteorologica propria (chuva do dia, acumulado de 3 dias e recuperacao por
secagem) e nao reutiliza mais o nucleo da Exposicao Hidrica; a chuva
continua sendo evidencia compartilhada entre varios perigos, mas alimenta
mecanismos diferentes em cada um.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from backend.exposicao.features_diarias import FeaturesDiariasCompartilhadas
from backend.exposicao.exposicao_hidrica import (
    ResultadoExposicaoHidrica,
    calcular_exposicao_hidrica,
)
from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    TipoProdutoHistorico,
)
from backend.exposicao.perigo_instabilidade import (
    ResultadoExposicaoInstabilidade,
    calcular_exposicao_instabilidade,
)
from backend.exposicao.perigo_propagacao_fogo import (
    ResultadoPropagacaoFogo,
    calcular_exposicao_propagacao_fogo,
)
from backend.exposicao.perigo_tempestade import (
    ResultadoTempestade,
    calcular_exposicao_tempestade,
)
from backend.exposicao.perigo_trafegabilidade import (
    ResultadoTrafegabilidade,
    calcular_trafegabilidade_desfavoravel,
)
from backend.exposicao.perigos_hidricos import GRUPO_DEPENDENCIA_HIDRICA
from backend.exposicao.politica import (
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import (
    AnaliseGeoespacialNormalizada,
    FonteDado,
    ModeloDominio,
    NaturezaDado,
)


VALIDACAO_INTEGRADA_VERSION = "exposicao-validacao-integrada-v1"
AVISO_INSTABILIDADE_HIDRICA = "INSTABILIDADE_DEPENDE_DE_NUCLEO_HIDRICO"
AVISO_FOGO_TEMPESTADE_VENTO = "INCENDIO_E_TEMPESTADE_COMPARTILHAM_VENTO"
AVISO_CHUVA_COMPARTILHADA = "CHUVA_EVIDENCIA_COMPARTILHADA_MULTIPLOS_PERIGOS"
GRUPO_INSTABILIDADE_PARCIAL = "ATIVACAO_HIDRICA_COM_SUSCETIBILIDADE_TOPOGRAFICA_V1"
GRUPO_VENTO_COMPARTILHADO = "VENTO_METEOROLOGICO_COMPARTILHADO_V1"
GRUPO_TRAFEGABILIDADE_METEOROLOGICA = "TRAFEGABILIDADE_METEOROLOGICA_PROPRIA_V1"


class TipoDependenciaMetodologica(str, Enum):
    NUCLEO_IDENTICO = "NUCLEO_IDENTICO"
    DEPENDENCIA_PARCIAL = "DEPENDENCIA_PARCIAL"
    EVIDENCIA_COMPARTILHADA = "EVIDENCIA_COMPARTILHADA"


class DependenciaPerigo(ModeloDominio):
    perigo: PerigoExposicao
    evidencias_principais: tuple[str, ...] = Field(min_length=1)
    grupo_dependencia: str = Field(min_length=1)
    tipo_dependencia: TipoDependenciaMetodologica
    evidencia_independente: bool
    composicao_independente_permitida: bool
    observacao: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_semantica(self) -> "DependenciaPerigo":
        if self.evidencia_independente or self.composicao_independente_permitida:
            raise ValueError("a validacao v1 nao conclui independencia estatistica")
        if len(set(self.evidencias_principais)) != len(self.evidencias_principais):
            raise ValueError("evidencias principais nao podem se repetir")
        return self


class EvidenciaCompartilhada(ModeloDominio):
    evidencia: str = Field(min_length=1)
    perigos: tuple[PerigoExposicao, ...] = Field(min_length=2)
    mesmo_mecanismo: bool
    observacao: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_perigos(self) -> "EvidenciaCompartilhada":
        if len(set(self.perigos)) != len(self.perigos):
            raise ValueError("evidencia compartilhada nao pode repetir perigos")
        return self


class CoberturaPerigo(ModeloDominio):
    perigo: PerigoExposicao
    dias_esperados: int = Field(gt=0)
    dias_disponiveis: int = Field(ge=0)
    cobertura_percentual: float = Field(ge=0, le=100)
    qualidade_suficiente: bool

    @model_validator(mode="after")
    def validar_cobertura(self) -> "CoberturaPerigo":
        if self.dias_disponiveis > self.dias_esperados:
            raise ValueError("dias disponiveis nao podem exceder os esperados")
        esperado = 100.0 * self.dias_disponiveis / self.dias_esperados
        if abs(self.cobertura_percentual - esperado) > 1e-12:
            raise ValueError("cobertura diverge das contagens")
        return self


def _dependencias_padrao() -> tuple[DependenciaPerigo, ...]:
    return (
        DependenciaPerigo(
            perigo=PerigoExposicao.EXPOSICAO_HIDRICA,
            evidencias_principais=(
                "nucleo_hidrico_meteorologico",
                "distancia_drenagem_merit",
                "area_montante_merit",
                "posicao_topografica_srtm",
            ),
            grupo_dependencia=GRUPO_DEPENDENCIA_HIDRICA,
            tipo_dependencia=TipoDependenciaMetodologica.DEPENDENCIA_PARCIAL,
            evidencia_independente=False,
            composicao_independente_permitida=False,
            observacao=(
                "Combina o nucleo meteorologico proprio com evidencias "
                "territoriais; Trafegabilidade tem metodologia meteorologica "
                "propria e nao compartilha mais este nucleo."
            ),
        ),
        DependenciaPerigo(
            perigo=PerigoExposicao.TRAFEGABILIDADE,
            evidencias_principais=(
                "precipitacao_d0",
                "acumulado_3d",
                "dias_desde_ultima_chuva_relevante",
            ),
            grupo_dependencia=GRUPO_TRAFEGABILIDADE_METEOROLOGICA,
            tipo_dependencia=TipoDependenciaMetodologica.EVIDENCIA_COMPARTILHADA,
            evidencia_independente=False,
            composicao_independente_permitida=False,
            observacao=(
                "Metodologia meteorologica propria (chuva do dia, acumulado de "
                "3 dias e recuperacao/secagem); compartilha apenas a evidencia "
                "de precipitacao com os demais perigos, sem reutilizar o "
                "nucleo da Exposicao Hidrica."
            ),
        ),
        DependenciaPerigo(
            perigo=PerigoExposicao.INSTABILIDADE,
            evidencias_principais=(
                "nucleo_hidrico_meteorologico",
                "declividade_media_srtm",
            ),
            grupo_dependencia=GRUPO_INSTABILIDADE_PARCIAL,
            tipo_dependencia=TipoDependenciaMetodologica.DEPENDENCIA_PARCIAL,
            evidencia_independente=False,
            composicao_independente_permitida=False,
            observacao=(
                "Possui suscetibilidade topografica propria, mas depende "
                "temporalmente da ativacao pelo nucleo hidrico."
            ),
        ),
        DependenciaPerigo(
            perigo=PerigoExposicao.INCENDIO,
            evidencias_principais=(
                "temperatura_maxima",
                "umidade_relativa",
                "velocidade_vento_media_m_s",
                "dias_desde_ultima_chuva_relevante",
            ),
            grupo_dependencia=GRUPO_VENTO_COMPARTILHADO,
            tipo_dependencia=TipoDependenciaMetodologica.EVIDENCIA_COMPARTILHADA,
            evidencia_independente=False,
            composicao_independente_permitida=False,
            observacao=(
                "Combina temperatura, umidade e vento por media geometrica; "
                "compartilhar vento nao demonstra independencia estatistica."
            ),
        ),
        DependenciaPerigo(
            perigo=PerigoExposicao.TEMPESTADES,
            evidencias_principais=(
                "velocidade_vento_media_m_s",
                "precipitacao_d0",
            ),
            grupo_dependencia=GRUPO_VENTO_COMPARTILHADO,
            tipo_dependencia=TipoDependenciaMetodologica.EVIDENCIA_COMPARTILHADA,
            evidencia_independente=False,
            composicao_independente_permitida=False,
            observacao=(
                "Usa vento como nucleo e chuva D0 como amplificador; o mecanismo "
                "nao e duplicacao da propagacao de fogo."
            ),
        ),
    )


def _evidencias_compartilhadas_padrao() -> tuple[EvidenciaCompartilhada, ...]:
    return (
        EvidenciaCompartilhada(
            evidencia="precipitacao",
            perigos=(
                PerigoExposicao.EXPOSICAO_HIDRICA,
                PerigoExposicao.TRAFEGABILIDADE,
                PerigoExposicao.INSTABILIDADE,
                PerigoExposicao.INCENDIO,
                PerigoExposicao.TEMPESTADES,
            ),
            mesmo_mecanismo=False,
            observacao=(
                "Chuva alimenta mecanismos diferentes: nucleo hidrico proprio, "
                "composicao meteorologica propria de Trafegabilidade (dia + "
                "acumulado + recuperacao), ativacao indireta da Instabilidade, "
                "contexto de secura do Incendio e amplificacao da Tempestade "
                "no mesmo dia."
            ),
        ),
        EvidenciaCompartilhada(
            evidencia="velocidade_vento_media_m_s",
            perigos=(PerigoExposicao.INCENDIO, PerigoExposicao.TEMPESTADES),
            mesmo_mecanismo=False,
            observacao=(
                "Fogo usa media geometrica com temperatura e umidade; tempestade "
                "usa vento como nucleo amplificado por chuva D0."
            ),
        ),
    )


def _cobertura(
    perigo: PerigoExposicao,
    resultado: (
        ResultadoExposicaoHidrica
        | ResultadoTrafegabilidade
        | ResultadoExposicaoInstabilidade
        | ResultadoPropagacaoFogo
        | ResultadoTempestade
    ),
) -> CoberturaPerigo:
    agregado = resultado.agregacao_90d
    return CoberturaPerigo(
        perigo=perigo,
        dias_esperados=agregado.dias_esperados,
        dias_disponiveis=agregado.dias_disponiveis,
        cobertura_percentual=agregado.cobertura_percentual,
        qualidade_suficiente=agregado.qualidade_suficiente,
    )


class ResultadoValidacaoIntegradaPerigos(ModeloDominio):
    id_fazenda: str | None = None
    fonte_meteorologica: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    referencia_temporal: ReferenciaTemporalHistorica
    periodo_features: JanelaHistorica
    janela: JanelaHistorica
    politica_id: str = Field(min_length=1)
    exposicao_hidrica: ResultadoExposicaoHidrica
    trafegabilidade: ResultadoTrafegabilidade
    instabilidade: ResultadoExposicaoInstabilidade
    propagacao_fogo: ResultadoPropagacaoFogo
    tempestade: ResultadoTempestade
    coberturas: tuple[CoberturaPerigo, ...] = Field(min_length=5, max_length=5)
    dependencias: tuple[DependenciaPerigo, ...] = Field(min_length=5, max_length=5)
    evidencias_compartilhadas: tuple[EvidenciaCompartilhada, ...] = Field(min_length=1)
    conflitos_para_composicao: tuple[str, ...]
    avisos: tuple[str, ...]
    versao: str = VALIDACAO_INTEGRADA_VERSION

    @model_validator(mode="after")
    def validar_integracao(self) -> "ResultadoValidacaoIntegradaPerigos":
        resultados = (
            self.exposicao_hidrica,
            self.trafegabilidade,
            self.instabilidade,
            self.propagacao_fogo,
            self.tempestade,
        )
        perigos_esperados = tuple(PerigoExposicao)
        if tuple(resultado.perigo for resultado in resultados) != perigos_esperados:
            raise ValueError("resultado integrado deve conter os cinco perigos")
        if any(resultado.janela_analisada != self.janela for resultado in resultados):
            raise ValueError("todos os perigos devem compartilhar a janela alvo")
        if any(
            resultado.periodo_features != self.periodo_features
            for resultado in resultados
        ):
            raise ValueError(
                "todos os perigos devem compartilhar o periodo de features"
            )
        if any(resultado.politica_id != self.politica_id for resultado in resultados):
            raise ValueError("todos os perigos devem compartilhar a politica")
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("validacao integrada exige serie historica unica")
        for resultado in (self.propagacao_fogo, self.tempestade):
            if (
                resultado.fonte != self.fonte_meteorologica
                or resultado.natureza != self.natureza
                or resultado.tipo_produto != self.tipo_produto
                or resultado.dataset != self.dataset
                or resultado.referencia_temporal != self.referencia_temporal
            ):
                raise ValueError("fonte meteorologica divergente entre perigos")

        avisos_obrigatorios = {
            AVISO_INSTABILIDADE_HIDRICA,
            AVISO_FOGO_TEMPESTADE_VENTO,
            AVISO_CHUVA_COMPARTILHADA,
        }
        if not avisos_obrigatorios.issubset(self.avisos):
            raise ValueError("avisos de dependencia incompletos")

        perigos_cobertura = tuple(item.perigo for item in self.coberturas)
        perigos_dependencia = tuple(item.perigo for item in self.dependencias)
        if perigos_cobertura != perigos_esperados:
            raise ValueError("coberturas devem representar os cinco perigos")
        if perigos_dependencia != perigos_esperados:
            raise ValueError("dependencias devem representar os cinco perigos")
        if self.dependencias != _dependencias_padrao():
            raise ValueError("mapa de dependencias metodologicas divergente")
        if self.evidencias_compartilhadas != _evidencias_compartilhadas_padrao():
            raise ValueError("mapa de evidencias compartilhadas divergente")
        for cobertura, resultado in zip(self.coberturas, resultados):
            agregado = resultado.agregacao_90d
            if (
                cobertura.dias_esperados != agregado.dias_esperados
                or cobertura.dias_disponiveis != agregado.dias_disponiveis
                or cobertura.cobertura_percentual != agregado.cobertura_percentual
                or cobertura.qualidade_suficiente != agregado.qualidade_suficiente
            ):
                raise ValueError("cobertura integrada diverge do perigo")
        return self

    def cobertura_de(self, perigo: PerigoExposicao) -> CoberturaPerigo:
        for cobertura in self.coberturas:
            if cobertura.perigo == perigo:
                return cobertura
        raise KeyError(perigo)


def validar_cinco_perigos(
    features: FeaturesDiariasCompartilhadas,
    analise_geoespacial: AnaliseGeoespacialNormalizada,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoValidacaoIntegradaPerigos:
    """Executa os cinco perigos existentes sem somar ou ponderar resultados."""

    if not isinstance(features, FeaturesDiariasCompartilhadas):
        raise TypeError("features deve ser FeaturesDiariasCompartilhadas")
    if not isinstance(analise_geoespacial, AnaliseGeoespacialNormalizada):
        raise TypeError("analise_geoespacial deve possuir contrato normalizado")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    alvo = janela_alvo or features.periodo
    if not isinstance(alvo, JanelaHistorica):
        raise TypeError("janela_alvo deve ser JanelaHistorica")
    if not (
        features.periodo.inicio <= alvo.inicio and alvo.fim <= features.periodo.fim
    ):
        raise ValueError("janela alvo deve estar contida nas features")

    hidrico = calcular_exposicao_hidrica(
        features,
        analise_geoespacial,
        politica,
        janela_alvo=alvo,
    )
    trafegabilidade = calcular_trafegabilidade_desfavoravel(
        features,
        politica,
        janela_alvo=alvo,
    )
    instabilidade = calcular_exposicao_instabilidade(
        features,
        analise_geoespacial,
        politica,
        janela_alvo=alvo,
    )
    fogo = calcular_exposicao_propagacao_fogo(
        features,
        politica,
        janela_alvo=alvo,
    )
    tempestade = calcular_exposicao_tempestade(
        features,
        politica,
        janela_alvo=alvo,
    )
    resultados = (hidrico, trafegabilidade, instabilidade, fogo, tempestade)
    return ResultadoValidacaoIntegradaPerigos(
        id_fazenda=features.id_fazenda,
        fonte_meteorologica=features.fonte,
        natureza=features.natureza,
        tipo_produto=features.tipo_produto,
        dataset=features.dataset,
        referencia_temporal=features.referencia_temporal,
        periodo_features=features.periodo,
        janela=alvo,
        politica_id=politica.id_politica,
        exposicao_hidrica=hidrico,
        trafegabilidade=trafegabilidade,
        instabilidade=instabilidade,
        propagacao_fogo=fogo,
        tempestade=tempestade,
        coberturas=tuple(
            _cobertura(perigo, resultado)
            for perigo, resultado in zip(PerigoExposicao, resultados)
        ),
        dependencias=_dependencias_padrao(),
        evidencias_compartilhadas=_evidencias_compartilhadas_padrao(),
        conflitos_para_composicao=(),
        avisos=(
            AVISO_INSTABILIDADE_HIDRICA,
            AVISO_FOGO_TEMPESTADE_VENTO,
            AVISO_CHUVA_COMPARTILHADA,
        ),
    )


__all__ = [
    "AVISO_CHUVA_COMPARTILHADA",
    "AVISO_FOGO_TEMPESTADE_VENTO",
    "AVISO_INSTABILIDADE_HIDRICA",
    "GRUPO_INSTABILIDADE_PARCIAL",
    "GRUPO_TRAFEGABILIDADE_METEOROLOGICA",
    "GRUPO_VENTO_COMPARTILHADO",
    "VALIDACAO_INTEGRADA_VERSION",
    "CoberturaPerigo",
    "DependenciaPerigo",
    "EvidenciaCompartilhada",
    "ResultadoValidacaoIntegradaPerigos",
    "TipoDependenciaMetodologica",
    "validar_cinco_perigos",
]
