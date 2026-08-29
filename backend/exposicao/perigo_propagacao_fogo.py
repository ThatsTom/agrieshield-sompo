"""Proxy meteorologico de condicao favoravel a propagacao de fogo.

O calculo combina temperatura maxima diaria, umidade relativa media diaria e
velocidade media do vento da mesma serie historica. Nao consulta fontes,
persiste dados ou toma decisoes operacionais.
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
    ParametrosPropagacaoFogo,
    PerigoExposicao,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import FonteDado, ModeloDominio, NaturezaDado


PERIGO_PROPAGACAO_FOGO_VERSION = "exposicao-propagacao-fogo-v1"
TIPO_EXPOSICAO_PROPAGACAO_FOGO = "CONDICAO_FAVORAVEL_PROPAGACAO_FOGO"
METODOLOGIA_PROPAGACAO_FOGO = "PROXY_METEOROLOGICO_PROPAGACAO_FOGO_V1"
AVISO_METODOLOGIA_PROPAGACAO_FOGO = (
    "Indice demonstrativo baseado em temperatura maxima diaria, umidade relativa "
    "media diaria e velocidade media do vento. Nao reproduz diretamente produto "
    "oficial de risco de fogo nem representa probabilidade de incendio."
)
MOTIVO_SECURA_APLICADA = "SECURA_ANTECEDENTE_APLICADA"
MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL = "CONTEXTO_PRECIPITACAO_INDISPONIVEL"
MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL = "COMPONENTE_ESSENCIAL_INDISPONIVEL"


class PropagacaoFogoDiaria(ModeloDominio):
    data: date
    temperatura_maxima_c: float | None = None
    umidade_relativa_media_pct: float | None = Field(default=None, ge=0, le=100)
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)
    dias_desde_ultima_chuva_relevante: int | None = Field(default=None, ge=0)

    componente_temperatura: float | None = Field(default=None, ge=0, le=1)
    componente_baixa_umidade: float | None = Field(default=None, ge=0, le=1)
    componente_vento: float | None = Field(default=None, ge=0, le=1)

    indice_fogo_base: float | None = Field(default=None, ge=0, le=100)
    multiplicador_secura: float | None = Field(default=None, gt=0)
    secura_antecedente_aplicada: bool
    motivo: str = Field(min_length=1)
    indice_exposicao_propagacao_fogo: float | None = Field(default=None, ge=0, le=100)
    metodologia: str = METODOLOGIA_PROPAGACAO_FOGO
    politica_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_coerencia(self) -> "PropagacaoFogoDiaria":
        pares = (
            (self.temperatura_maxima_c, self.componente_temperatura),
            (self.umidade_relativa_media_pct, self.componente_baixa_umidade),
            (self.velocidade_vento_media_m_s, self.componente_vento),
        )
        if any((valor is None) != (componente is None) for valor, componente in pares):
            raise ValueError("componentes devem refletir a disponibilidade observada")

        componentes = (
            self.componente_temperatura,
            self.componente_baixa_umidade,
            self.componente_vento,
        )
        if any(componente is None for componente in componentes):
            if self.indice_fogo_base is not None:
                raise ValueError("componente ausente torna fogo base indisponivel")
            if self.indice_exposicao_propagacao_fogo is not None:
                raise ValueError("componente ausente torna exposicao indisponivel")
            if self.secura_antecedente_aplicada:
                raise ValueError("secura nao se aplica sem fogo base")
            if self.multiplicador_secura is not None:
                raise ValueError("fogo base indisponivel nao recebe multiplicador")
            if self.motivo != MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL:
                raise ValueError("ausencia essencial deve permanecer explicita")
            return self

        if self.indice_fogo_base is None:
            raise ValueError("componentes disponiveis exigem fogo base")
        base_esperada = math.prod(componentes) ** (1.0 / 3.0) * 100.0
        if not math.isclose(
            self.indice_fogo_base,
            base_esperada,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("fogo base diverge da media geometrica")

        if self.dias_desde_ultima_chuva_relevante is None:
            if self.multiplicador_secura is not None:
                raise ValueError("contexto ausente nao possui multiplicador")
            if self.secura_antecedente_aplicada:
                raise ValueError("contexto ausente nao pode aplicar secura")
            if self.motivo != MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL:
                raise ValueError("ausencia de contexto deve permanecer explicita")
            esperado = self.indice_fogo_base
        else:
            if self.multiplicador_secura is None:
                raise ValueError("contexto disponivel exige multiplicador")
            if not self.secura_antecedente_aplicada:
                raise ValueError("contexto disponivel deve aplicar secura")
            if self.motivo != MOTIVO_SECURA_APLICADA:
                raise ValueError("secura aplicada deve possuir motivo coerente")
            esperado = min(
                self.indice_fogo_base * self.multiplicador_secura,
                100.0,
            )
        if self.indice_exposicao_propagacao_fogo is None or not math.isclose(
            self.indice_exposicao_propagacao_fogo,
            esperado,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("indice final diverge da metodologia")
        return self


class ResultadoPropagacaoFogo(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.INCENDIO
    tipo_exposicao: str = TIPO_EXPOSICAO_PROPAGACAO_FOGO
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
    propagacao_fogo_diaria: tuple[PropagacaoFogoDiaria, ...]
    indices_diarios: SerieIndicesDiariosPerigo
    agregacao_90d: ResultadoAgregacaoPerigo
    politica_id: str = Field(min_length=1)
    parametros_propagacao_fogo: ParametrosPropagacaoFogo
    metodologia: str = METODOLOGIA_PROPAGACAO_FOGO
    aviso_metodologia: str = AVISO_METODOLOGIA_PROPAGACAO_FOGO
    versao: str = PERIGO_PROPAGACAO_FOGO_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoPropagacaoFogo":
        if self.perigo != PerigoExposicao.INCENDIO:
            raise ValueError("resultado aceita somente exposicao a propagacao de fogo")
        if self.tipo_exposicao != TIPO_EXPOSICAO_PROPAGACAO_FOGO:
            raise ValueError("tipo de exposicao incoerente")
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("propagacao de fogo exige uma unica serie historica")
        if not (
            self.periodo_features.inicio <= self.janela_analisada.inicio
            and self.janela_analisada.fim <= self.periodo_features.fim
        ):
            raise ValueError("janela analisada deve estar contida nas features")
        contexto_esperado = (
            self.janela_analisada.inicio - self.periodo_features.inicio
        ).days
        if self.dias_contexto_calendario != contexto_esperado:
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
                *(item.politica_id for item in self.propagacao_fogo_diaria),
            )
        ):
            raise ValueError("politica incoerente no resultado")
        if tuple(item.data for item in self.propagacao_fogo_diaria) != tuple(
            item.data for item in self.indices_diarios.indices
        ):
            raise ValueError("detalhes e indices devem compartilhar o calendario")
        if any(
            detalhe.indice_exposicao_propagacao_fogo != indice.indice
            for detalhe, indice in zip(
                self.propagacao_fogo_diaria,
                self.indices_diarios.indices,
            )
        ):
            raise ValueError("detalhes e indices devem preservar os mesmos valores")
        if any(
            item.velocidade_vento_media_m_s is not None
            for item in self.propagacao_fogo_diaria
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


def normalizar_temperatura_fogo(
    temperatura_maxima_c: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    valor = _validar_numero(temperatura_maxima_c, "temperatura maxima")
    if valor is None:
        return None
    return _interpolar(
        valor,
        politica.parametros_propagacao_fogo.curva_temperatura_maxima,
        lambda ponto: ponto.temperatura_c,
    )


def normalizar_baixa_umidade_fogo(
    umidade_relativa_media_pct: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    valor = _validar_numero(
        umidade_relativa_media_pct,
        "umidade relativa media",
        minimo=0,
        maximo=100,
    )
    if valor is None:
        return None
    return _interpolar(
        valor,
        politica.parametros_propagacao_fogo.curva_baixa_umidade_media,
        lambda ponto: ponto.umidade_pct,
    )


def normalizar_vento_fogo(
    velocidade_vento_media_m_s: float | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
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


def calcular_indice_fogo_base(
    componente_temperatura: float | None,
    componente_baixa_umidade: float | None,
    componente_vento: float | None,
) -> float | None:
    componentes = (
        componente_temperatura,
        componente_baixa_umidade,
        componente_vento,
    )
    if any(componente is None for componente in componentes):
        return None
    validados = tuple(
        _validar_numero(componente, "componente", minimo=0, maximo=1)
        for componente in componentes
    )
    return math.prod(validados) ** (1.0 / 3.0) * 100.0


def obter_multiplicador_secura(
    dias_desde_ultima_chuva_relevante: int | None,
    politica: PoliticaExposicaoEquipamentos,
) -> float | None:
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")
    if dias_desde_ultima_chuva_relevante is None:
        return None
    if isinstance(dias_desde_ultima_chuva_relevante, bool) or not isinstance(
        dias_desde_ultima_chuva_relevante, int
    ):
        raise TypeError("dias desde chuva deve ser inteiro")
    if dias_desde_ultima_chuva_relevante < 0:
        raise ValueError("dias desde chuva deve ser nao negativo")
    selecionada = politica.parametros_propagacao_fogo.faixas_secura_antecedente[0]
    for faixa in politica.parametros_propagacao_fogo.faixas_secura_antecedente:
        if dias_desde_ultima_chuva_relevante < faixa.inicio_dias:
            break
        selecionada = faixa
    return selecionada.multiplicador


def calcular_propagacao_fogo_diaria(
    feature: FeatureDiariaCompartilhada,
    politica: PoliticaExposicaoEquipamentos,
) -> PropagacaoFogoDiaria:
    if not isinstance(feature, FeatureDiariaCompartilhada):
        raise TypeError("feature deve ser FeatureDiariaCompartilhada")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser PoliticaExposicaoEquipamentos")

    componente_temperatura = normalizar_temperatura_fogo(
        feature.temperatura_maxima,
        politica,
    )
    componente_umidade = normalizar_baixa_umidade_fogo(
        feature.umidade_relativa,
        politica,
    )
    componente_vento = normalizar_vento_fogo(
        feature.velocidade_vento_media_m_s,
        politica,
    )
    fogo_base = calcular_indice_fogo_base(
        componente_temperatura,
        componente_umidade,
        componente_vento,
    )
    multiplicador = obter_multiplicador_secura(
        feature.dias_desde_ultima_chuva_relevante,
        politica,
    )

    if fogo_base is None:
        indice_final = None
        secura_aplicada = False
        motivo = MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL
    elif multiplicador is None:
        indice_final = fogo_base
        secura_aplicada = False
        motivo = MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL
    else:
        indice_final = min(fogo_base * multiplicador, 100.0)
        secura_aplicada = True
        motivo = MOTIVO_SECURA_APLICADA

    return PropagacaoFogoDiaria(
        data=feature.data,
        temperatura_maxima_c=feature.temperatura_maxima,
        umidade_relativa_media_pct=feature.umidade_relativa,
        velocidade_vento_media_m_s=feature.velocidade_vento_media_m_s,
        dias_desde_ultima_chuva_relevante=(feature.dias_desde_ultima_chuva_relevante),
        componente_temperatura=componente_temperatura,
        componente_baixa_umidade=componente_umidade,
        componente_vento=componente_vento,
        indice_fogo_base=fogo_base,
        multiplicador_secura=multiplicador if fogo_base is not None else None,
        secura_antecedente_aplicada=secura_aplicada,
        motivo=motivo,
        indice_exposicao_propagacao_fogo=indice_final,
        politica_id=politica.id_politica,
    )


def calcular_exposicao_propagacao_fogo(
    features: FeaturesDiariasCompartilhadas,
    politica: PoliticaExposicaoEquipamentos,
    *,
    janela_alvo: JanelaHistorica | None = None,
) -> ResultadoPropagacaoFogo:
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
        calcular_propagacao_fogo_diaria(feature, politica)
        for feature in features.dias
        if alvo.inicio <= feature.data <= alvo.fim
    )
    indices = criar_indices_diarios(
        alvo,
        (
            ValorIndiceDiario(
                data=item.data,
                indice=item.indice_exposicao_propagacao_fogo,
            )
            for item in detalhes
        ),
        politica,
    )
    agregacao = agregar_indice_historico(indices, politica)
    return ResultadoPropagacaoFogo(
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
        propagacao_fogo_diaria=detalhes,
        indices_diarios=indices,
        agregacao_90d=agregacao,
        politica_id=politica.id_politica,
        parametros_propagacao_fogo=politica.parametros_propagacao_fogo,
    )


__all__ = [
    "AVISO_METODOLOGIA_PROPAGACAO_FOGO",
    "METODOLOGIA_PROPAGACAO_FOGO",
    "MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL",
    "MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL",
    "MOTIVO_SECURA_APLICADA",
    "PERIGO_PROPAGACAO_FOGO_VERSION",
    "TIPO_EXPOSICAO_PROPAGACAO_FOGO",
    "PropagacaoFogoDiaria",
    "ResultadoPropagacaoFogo",
    "calcular_exposicao_propagacao_fogo",
    "calcular_indice_fogo_base",
    "calcular_propagacao_fogo_diaria",
    "normalizar_baixa_umidade_fogo",
    "normalizar_temperatura_fogo",
    "normalizar_vento_fogo",
    "obter_multiplicador_secura",
]
