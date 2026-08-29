"""Proxy meteorologico de exposicao a tempestades severas.

O vento medio diario forma o nucleo do indice e a precipitacao do mesmo dia
atua somente como amplificador. O modulo nao consulta fontes, persiste dados
ou representa alerta meteorologico oficial.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Callable

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
from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    TipoProdutoHistorico,
)
from backend.exposicao.politica import (
    EstadoDisponibilidade,
    ParametrosTempestade,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import FonteDado, ModeloDominio, NaturezaDado


PERIGO_TEMPESTADE_VERSION = "exposicao-tempestade-v1"
TIPO_EXPOSICAO_TEMPESTADE = "TEMPESTADE_SEVERA_PROXY"
METODOLOGIA_TEMPESTADE = "PROXY_METEOROLOGICO_TEMPESTADE_V1"
AVISO_METODOLOGIA_TEMPESTADE = (
    "Indice demonstrativo baseado em velocidade media do vento e precipitacao "
    "diaria. Nao representa alerta oficial INMET, vendaval confirmado, rajada, "
    "granizo, descarga atmosferica, probabilidade de tempestade ou probabilidade "
    "de sinistro."
)
MOTIVO_AMPLIFICACAO_CHUVA_APLICADA = "AMPLIFICACAO_CHUVA_APLICADA"
MOTIVO_VENTO_INDISPONIVEL = "VENTO_INDISPONIVEL"
MOTIVO_PRECIPITACAO_INDISPONIVEL = "PRECIPITACAO_INDISPONIVEL"


class TempestadeDiaria(ModeloDominio):
    data: date
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)
    precipitacao_d0: float | None = Field(default=None, ge=0)
    componente_vento: float | None = Field(default=None, ge=0, le=1)
    componente_chuva: float | None = Field(default=None, ge=0, le=1)
    indice_vento: float | None = Field(default=None, ge=0, le=100)
    fator_amplificacao_chuva: float | None = Field(default=None, ge=0, le=1)
    amplificacao_chuva_aplicada: bool
    motivo: str = Field(min_length=1)
    indice_exposicao_tempestade: float | None = Field(default=None, ge=0, le=100)
    granizo: EstadoDisponibilidade = EstadoDisponibilidade.INDISPONIVEL
    descargas_atmosfericas: EstadoDisponibilidade = EstadoDisponibilidade.INDISPONIVEL
    metodologia: str = METODOLOGIA_TEMPESTADE
    politica_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_coerencia(self) -> "TempestadeDiaria":
        if self.granizo != EstadoDisponibilidade.INDISPONIVEL:
            raise ValueError("granizo permanece indisponivel na metodologia v1")
        if self.descargas_atmosfericas != EstadoDisponibilidade.INDISPONIVEL:
            raise ValueError("descargas permanecem indisponiveis na metodologia v1")
        if (self.velocidade_vento_media_m_s is None) != (self.componente_vento is None):
            raise ValueError("componente de vento deve refletir a observacao")
        if (self.precipitacao_d0 is None) != (self.componente_chuva is None):
            raise ValueError("componente de chuva deve refletir a observacao")

        if self.componente_vento is None:
            if any(
                valor is not None
                for valor in (
                    self.indice_vento,
                    self.fator_amplificacao_chuva,
                    self.indice_exposicao_tempestade,
                )
            ):
                raise ValueError("vento ausente torna a tempestade indisponivel")
            if self.amplificacao_chuva_aplicada:
                raise ValueError("chuva nao amplifica sem nucleo de vento")
            if self.motivo != MOTIVO_VENTO_INDISPONIVEL:
                raise ValueError("ausencia de vento deve permanecer explicita")
            return self

        indice_vento_esperado = self.componente_vento * 100.0
        if self.indice_vento is None or not math.isclose(
            self.indice_vento,
            indice_vento_esperado,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("indice de vento diverge do componente")

        if self.componente_chuva is None:
            if self.fator_amplificacao_chuva is not None:
                raise ValueError("chuva ausente nao possui fator de amplificacao")
            if self.indice_exposicao_tempestade is not None:
                raise ValueError("chuva ausente torna a tempestade indisponivel")
            if self.amplificacao_chuva_aplicada:
                raise ValueError("chuva ausente nao pode ser aplicada")
            if self.motivo != MOTIVO_PRECIPITACAO_INDISPONIVEL:
                raise ValueError("ausencia de chuva deve permanecer explicita")
            return self

        if self.fator_amplificacao_chuva is None:
            raise ValueError("chuva disponivel exige fator de amplificacao")
        if not self.amplificacao_chuva_aplicada:
            raise ValueError("chuva disponivel deve aplicar a formula completa")
        if self.motivo != MOTIVO_AMPLIFICACAO_CHUVA_APLICADA:
            raise ValueError("amplificacao aplicada deve possuir motivo coerente")
        if self.indice_exposicao_tempestade is None:
            raise ValueError("componentes disponiveis exigem indice de tempestade")
        esperado = min(
            self.indice_vento * self.fator_amplificacao_chuva,
            100.0,
        )
        if not math.isclose(
            self.indice_exposicao_tempestade,
            esperado,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("indice de tempestade diverge da metodologia")
        return self


class ResultadoTempestade(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.TEMPESTADES
    tipo_exposicao: str = TIPO_EXPOSICAO_TEMPESTADE
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado
    tipo_produto: TipoProdutoHistorico
    dataset: str
    referencia_temporal: ReferenciaTemporalHistorica
    proveniencia_vento: dict[str, Any]
    periodo_features: JanelaHistorica
    janela_analisada: JanelaHistorica
    dias_contexto_calendario: int = Field(ge=0)
    tempestades_diarias: tuple[TempestadeDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_tempestade: ParametrosTempestade
    metodologia: str = METODOLOGIA_TEMPESTADE
    aviso_metodologia: str = AVISO_METODOLOGIA_TEMPESTADE
    versao: str = PERIGO_TEMPESTADE_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoTempestade":
        if self.perigo != PerigoExposicao.TEMPESTADES:
            raise ValueError("resultado aceita somente exposicao a tempestades")
        if self.tipo_exposicao != TIPO_EXPOSICAO_TEMPESTADE:
            raise ValueError("tipo de exposicao incoerente")
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("tempestade exige uma unica serie historica")
        if not (
            self.periodo_features.inicio <= self.janela_analisada.inicio
            and self.janela_analisada.fim <= self.periodo_features.fim
        ):
            raise ValueError("janela analisada deve estar contida nas features")
        if (
            self.dias_contexto_calendario
            != (self.janela_analisada.inicio - self.periodo_features.inicio).days
        ):
            raise ValueError("quantidade de dias de contexto incoerente")
        if self.indices_diarios.periodo != self.janela_analisada:
            raise ValueError("indices devem representar a janela analisada")
        if (
            self.agregacao_90d.inicio != self.janela_analisada.inicio
            or self.agregacao_90d.fim != self.janela_analisada.fim
        ):
            raise ValueError("agregacao deve representar a janela analisada")
        if any(
            politica_id != self.politica_id
            for politica_id in (
                self.indices_diarios.politica_id,
                self.agregacao_90d.politica_id,
                *(item.politica_id for item in self.tempestades_diarias),
            )
        ):
            raise ValueError("politica incoerente no resultado")
        if tuple(item.data for item in self.tempestades_diarias) != tuple(
            item.data for item in self.indices_diarios.indices
        ):
            raise ValueError("detalhes e indices devem compartilhar o calendario")
        if any(
            detalhe.indice_exposicao_tempestade != indice.indice
            for detalhe, indice in zip(
                self.tempestades_diarias,
                self.indices_diarios.indices,
            )
        ):
            raise ValueError("detalhes e indices devem preservar os mesmos valores")
        if any(
            item.velocidade_vento_media_m_s is not None
            for item in self.tempestades_diarias
        ):
            campos = {
                "parametro_fonte",
                "variavel_canonica",
                "unidade",
                "altura_m",
                "agregacao_temporal",
                "referencia_temporal",
            }
            if not campos.issubset(self.proveniencia_vento):
                raise ValueError("vento disponivel exige proveniencia completa")
            if (
                self.proveniencia_vento["variavel_canonica"]
                != "velocidade_vento_media_m_s"
                or self.proveniencia_vento["unidade"] != "m/s"
            ):
                raise ValueError("proveniencia do vento diverge do contrato canonico")
        return self


def _validar_numero(
    valor: float | None,
    nome: str,
    *,
    minimo: float | None = None,
    maximo: float | None = None,
) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise TypeError(f"{nome} deve ser numerico")
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError(f"{nome} deve ser finito")
    if minimo is not None and numero < minimo:
        raise ValueError(f"{nome} abaixo do dominio permitido")
    if maximo is not None and numero > maximo:
        raise ValueError(f"{nome} acima do dominio permitido")
    return numero


def _interpolar(
    valor: float,
    pontos: tuple[Any, ...],
    obter_x: Callable[[Any], float],
) -> float:
    if valor <= obter_x(pontos[0]):
        return pontos[0].componente
    for inferior, superior in zip(pontos, pontos[1:]):
        x_inferior = obter_x(inferior)
        x_superior = obter_x(superior)
        if valor <= x_superior:
            proporcao = (valor - x_inferior) / (x_superior - x_inferior)
            return inferior.componente + proporcao * (
                superior.componente - inferior.componente
            )
    return pontos[-1].componente


def normalizar_vento_tempestade(
    velocidade_vento_media_m_s: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    """Reutiliza exatamente a curva demonstrativa de vento medio da Fase 6B."""

    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    valor = _validar_numero(
        velocidade_vento_media_m_s,
        "velocidade media do vento",
        minimo=0,
    )
    if valor is None:
        return None
    return _interpolar(
        valor,
        politica.parametros_propagacao_fogo.curva_velocidade_vento_media,
        lambda ponto: ponto.velocidade_m_s,
    )


def normalizar_chuva_tempestade(
    precipitacao_d0_mm: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    valor = _validar_numero(
        precipitacao_d0_mm,
        "precipitacao do dia",
        minimo=0,
    )
    if valor is None:
        return None
    return _interpolar(
        valor,
        politica.parametros_tempestade.curva_precipitacao_d0,
        lambda ponto: ponto.precipitacao_mm,
    )


def calcular_indice_tempestade(
    componente_vento: float | None,
    componente_chuva: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> tuple[float | None, float | None, float | None]:
    """Retorna indice de vento, fator de chuva e indice final, sem imputacao."""

    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    if componente_vento is None:
        return None, None, None
    vento = _validar_numero(componente_vento, "componente de vento", minimo=0, maximo=1)
    indice_vento = vento * 100.0
    if componente_chuva is None:
        return indice_vento, None, None
    chuva = _validar_numero(componente_chuva, "componente de chuva", minimo=0, maximo=1)
    parametros = politica.parametros_tempestade
    fator = parametros.peso_base_vento + parametros.peso_amplificacao_chuva * chuva
    return indice_vento, fator, min(indice_vento * fator, 100.0)


def calcular_tempestade_diaria(
    feature: FeatureDiariaCompartilhada,
    politica: PoliticaExposicaoEquipamentos,
) -> TempestadeDiaria:
    if not isinstance(feature, FeatureDiariaCompartilhada):
        raise TypeError("feature deve ser FeatureDiariaCompartilhada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")

    componente_vento = normalizar_vento_tempestade(
        feature.velocidade_vento_media_m_s,
        politica,
    )
    componente_chuva = normalizar_chuva_tempestade(
        feature.precipitacao_d0,
        politica,
    )
    indice_vento, fator, indice_final = calcular_indice_tempestade(
        componente_vento,
        componente_chuva,
        politica,
    )

    if componente_vento is None:
        amplificacao_aplicada = False
        motivo = MOTIVO_VENTO_INDISPONIVEL
    elif componente_chuva is None:
        amplificacao_aplicada = False
        motivo = MOTIVO_PRECIPITACAO_INDISPONIVEL
    else:
        amplificacao_aplicada = True
        motivo = MOTIVO_AMPLIFICACAO_CHUVA_APLICADA

    return TempestadeDiaria(
        data=feature.data,
        velocidade_vento_media_m_s=feature.velocidade_vento_media_m_s,
        precipitacao_d0=feature.precipitacao_d0,
        componente_vento=componente_vento,
        componente_chuva=componente_chuva,
        indice_vento=indice_vento,
        fator_amplificacao_chuva=fator,
        amplificacao_chuva_aplicada=amplificacao_aplicada,
        motivo=motivo,
        indice_exposicao_tempestade=indice_final,
        politica_id=politica.id_politica,
    )


def calcular_exposicao_tempestade(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoTempestade:
    if not isinstance(features, FeaturesDiariasCompartilhadas):
        raise TypeError("features deve ser FeaturesDiariasCompartilhadas")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    alvo = janela_alvo or features.periodo
    if not isinstance(alvo, JanelaHistorica):
        raise TypeError("janela_alvo deve ser JanelaHistorica")
    if not (
        features.periodo.inicio <= alvo.inicio and alvo.fim <= features.periodo.fim
    ):
        raise ValueError("janela alvo deve estar contida nas features")

    detalhes = tuple(
        calcular_tempestade_diaria(feature, politica)
        for feature in features.dias
        if alvo.inicio <= feature.data <= alvo.fim
    )
    indices = criar_indices_diarios(
        alvo,
        (
            ValorIndiceDiario(
                data=item.data,
                indice=item.indice_exposicao_tempestade,
            )
            for item in detalhes
        ),
        politica,
    )
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoTempestade(
        id_fazenda=features.id_fazenda,
        fonte=features.fonte,
        natureza=features.natureza,
        tipo_produto=features.tipo_produto,
        dataset=features.dataset,
        referencia_temporal=features.referencia_temporal,
        proveniencia_vento=dict(features.metadados_vento),
        periodo_features=features.periodo,
        janela_analisada=alvo,
        dias_contexto_calendario=(alvo.inicio - features.periodo.inicio).days,
        tempestades_diarias=detalhes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_tempestade=politica.parametros_tempestade,
    )


__all__ = [
    "AVISO_METODOLOGIA_TEMPESTADE",
    "METODOLOGIA_TEMPESTADE",
    "MOTIVO_AMPLIFICACAO_CHUVA_APLICADA",
    "MOTIVO_PRECIPITACAO_INDISPONIVEL",
    "MOTIVO_VENTO_INDISPONIVEL",
    "PERIGO_TEMPESTADE_VERSION",
    "TIPO_EXPOSICAO_TEMPESTADE",
    "ResultadoTempestade",
    "TempestadeDiaria",
    "calcular_exposicao_tempestade",
    "calcular_indice_tempestade",
    "calcular_tempestade_diaria",
    "normalizar_chuva_tempestade",
    "normalizar_vento_tempestade",
]
