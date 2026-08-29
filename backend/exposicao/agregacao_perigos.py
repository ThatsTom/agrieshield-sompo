"""Infraestrutura genérica para eventos e agregação histórica de perigos.

O módulo recebe índices diários já calculados. Não conhece meteorologia,
fórmulas ou thresholds específicos de qualquer perigo.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import fmean
from typing import Iterable

from pydantic import Field, field_validator, model_validator

from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.politica import (
    ClassificacaoIndice,
    EstadoDisponibilidade,
    PoliticaExposicaoEquipamentos,
)
from backend.risco.modelos import ModeloDominio


AGREGACAO_PERIGOS_VERSION = "exposicao-agregacao-perigos-v1"


class ValorIndiceDiario(ModeloDominio):
    data: date
    indice: float | None = Field(default=None, ge=0, le=100)

    @field_validator("indice", mode="before")
    @classmethod
    def rejeitar_booleano(cls, valor: object) -> object:
        if isinstance(valor, bool):
            raise ValueError("índice diário deve ser numérico")
        return valor


class IndiceDiarioPerigo(ModeloDominio):
    data: date
    indice: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None
    disponibilidade: EstadoDisponibilidade
    relevante: bool = False

    @model_validator(mode="after")
    def validar_disponibilidade(self) -> "IndiceDiarioPerigo":
        if self.disponibilidade == EstadoDisponibilidade.DISPONIVEL:
            if self.indice is None or self.classificacao is None:
                raise ValueError("índice disponível exige valor e classificação")
        elif self.indice is not None or self.classificacao is not None:
            raise ValueError("índice indisponível ou não aplicável não possui valor")
        if self.disponibilidade != EstadoDisponibilidade.DISPONIVEL and self.relevante:
            raise ValueError("dia indisponível ou não aplicável não pode ser relevante")
        return self


class SerieIndicesDiariosPerigo(ModeloDominio):
    periodo: JanelaHistorica
    indices: tuple[IndiceDiarioPerigo, ...]
    politica_id: str = Field(min_length=1)
    versao: str = AGREGACAO_PERIGOS_VERSION

    @model_validator(mode="after")
    def validar_calendario(self) -> "SerieIndicesDiariosPerigo":
        if len(self.indices) != self.periodo.dias_esperados:
            raise ValueError("série de índices deve representar toda a janela")
        datas_esperadas = tuple(
            self.periodo.inicio + timedelta(days=indice)
            for indice in range(self.periodo.dias_esperados)
        )
        if tuple(item.data for item in self.indices) != datas_esperadas:
            raise ValueError("índices devem seguir o calendário da janela")
        return self

    def por_data(self, data_consulta: date) -> IndiceDiarioPerigo:
        if not self.periodo.inicio <= data_consulta <= self.periodo.fim:
            raise KeyError(data_consulta)
        return self.indices[(data_consulta - self.periodo.inicio).days]


class EventoPerigo(ModeloDominio):
    """Sequência de dias relevantes consecutivos.

    `classificacao_maxima` pode ser NORMAL quando o perigo usa um
    `limiar_relevancia` próprio (ver `criar_indices_diarios`) mais baixo que
    as faixas globais de classificação: um dia pode ser relevante para
    agregação sem deixar de ser classificado como NORMAL.
    """

    inicio: date
    fim: date
    duracao_dias: int = Field(gt=0)
    indice_maximo: float = Field(ge=0, le=100)
    indice_medio: float = Field(ge=0, le=100)
    classificacao_maxima: ClassificacaoIndice
    severidade_evento: float = Field(ge=0, le=100)
    quantidade_dias_relevantes: int = Field(gt=0)

    @model_validator(mode="after")
    def validar_periodo(self) -> "EventoPerigo":
        duracao_calendario = (self.fim - self.inicio).days + 1
        if self.duracao_dias != duracao_calendario:
            raise ValueError("duração deve refletir dias calendário consecutivos")
        if self.quantidade_dias_relevantes != self.duracao_dias:
            raise ValueError("todo dia de um evento deve ser relevante")
        return self


class ResultadoAgregacaoPerigo(ModeloDominio):
    inicio: date
    fim: date
    dias_esperados: int = Field(gt=0)
    dias_disponiveis: int = Field(ge=0)
    cobertura_percentual: float = Field(ge=0, le=100)
    cobertura_minima_percentual: float = Field(ge=0, le=100)
    qualidade_suficiente: bool

    quantidade_dias_relevantes: int = Field(ge=0)
    quantidade_eventos: int = Field(ge=0)
    maior_duracao_evento: int = Field(ge=0)

    severidade_score: float = Field(ge=0, le=100)
    frequencia_score: float = Field(ge=0, le=100)
    duracao_score: float = Field(ge=0, le=100)
    recorrencia_score: float = Field(ge=0, le=100)

    indice_agregado: float | None = Field(default=None, ge=0, le=100)
    classificacao_agregada: ClassificacaoIndice | None = None
    eventos: tuple[EventoPerigo, ...]
    politica_id: str = Field(min_length=1)
    versao: str = AGREGACAO_PERIGOS_VERSION

    @model_validator(mode="after")
    def validar_coerencia(self) -> "ResultadoAgregacaoPerigo":
        if self.dias_esperados != (self.fim - self.inicio).days + 1:
            raise ValueError("dias esperados deve refletir o intervalo inclusivo")
        if self.dias_disponiveis > self.dias_esperados:
            raise ValueError("dias disponíveis não pode exceder dias esperados")
        cobertura_esperada = 100.0 * self.dias_disponiveis / self.dias_esperados
        if not math.isclose(
            self.cobertura_percentual,
            cobertura_esperada,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("cobertura incoerente com os dias disponíveis")
        if self.qualidade_suficiente != (
            self.cobertura_percentual >= self.cobertura_minima_percentual
        ):
            raise ValueError("qualidade suficiente incoerente com a cobertura")
        if self.quantidade_eventos != len(self.eventos):
            raise ValueError("quantidade de eventos incoerente")
        if self.quantidade_dias_relevantes != sum(
            evento.quantidade_dias_relevantes for evento in self.eventos
        ):
            raise ValueError("quantidade de dias relevantes incoerente")
        maior_duracao = max((evento.duracao_dias for evento in self.eventos), default=0)
        if self.maior_duracao_evento != maior_duracao:
            raise ValueError("maior duração de evento incoerente")
        if self.dias_disponiveis == 0:
            if (
                self.indice_agregado is not None
                or self.classificacao_agregada is not None
            ):
                raise ValueError(
                    "ausência total não pode fabricar índice ou classificação"
                )
        elif self.indice_agregado is None or self.classificacao_agregada is None:
            raise ValueError("resultado com dados exige índice e classificação")
        return self


def _validar_periodo_e_politica(
    periodo: JanelaHistorica,
    politica: PoliticaExposicaoEquipamentos,
) -> None:
    if not isinstance(periodo, JanelaHistorica):
        raise TypeError("periodo deve ser uma JanelaHistorica")
    if not isinstance(politica, PoliticaExposicaoEquipamentos):
        raise TypeError("politica deve ser uma PoliticaExposicaoEquipamentos")
    if periodo.dias_esperados != politica.janela_historica_dias:
        raise ValueError("janela deve possuir a duração definida pela política")


def criar_indices_diarios(
    periodo: JanelaHistorica,
    valores: Iterable[ValorIndiceDiario],
    politica: PoliticaExposicaoEquipamentos,
    *,
    limiar_relevancia: float | None = None,
) -> SerieIndicesDiariosPerigo:
    """Classifica valores e explicita como indisponível cada data sem índice.

    `limiar_relevancia`, quando informado, decide isoladamente quais dias
    contam como relevantes para agrupamento de eventos e agregação
    (``indice >= limiar_relevancia``), sem alterar a classificação diária
    (que continua vindo das faixas globais da política). Quando omitido
    (padrão), a relevância volta a coincidir com "classificação diferente de
    NORMAL", como sempre foi — nenhum chamador existente muda de
    comportamento.
    """

    _validar_periodo_e_politica(periodo, politica)
    if limiar_relevancia is not None:
        if isinstance(limiar_relevancia, bool) or not isinstance(
            limiar_relevancia, (int, float)
        ):
            raise TypeError("limiar_relevancia deve ser numérico")
        if not math.isfinite(limiar_relevancia) or not 0 <= limiar_relevancia <= 100:
            raise ValueError("limiar_relevancia deve estar entre 0 e 100")
    informados = tuple(valores)
    if not all(isinstance(item, ValorIndiceDiario) for item in informados):
        raise TypeError("valores deve conter somente ValorIndiceDiario")
    datas = [item.data for item in informados]
    if len(datas) != len(set(datas)):
        raise ValueError("datas duplicadas não são permitidas")
    if any(data < periodo.inicio or data > periodo.fim for data in datas):
        raise ValueError("índice diário fora da janela solicitada")
    por_data = {item.data: item for item in informados}

    indices: list[IndiceDiarioPerigo] = []
    data_atual = periodo.inicio
    while data_atual <= periodo.fim:
        informado = por_data.get(data_atual)
        indice = informado.indice if informado is not None else None
        if indice is None:
            indices.append(
                IndiceDiarioPerigo(
                    data=data_atual,
                    disponibilidade=EstadoDisponibilidade.INDISPONIVEL,
                )
            )
        else:
            classificacao = politica.classificar_indice(indice)
            relevante = (
                indice >= limiar_relevancia
                if limiar_relevancia is not None
                else classificacao != ClassificacaoIndice.NORMAL
            )
            indices.append(
                IndiceDiarioPerigo(
                    data=data_atual,
                    indice=indice,
                    classificacao=classificacao,
                    disponibilidade=EstadoDisponibilidade.DISPONIVEL,
                    relevante=relevante,
                )
            )
        data_atual += timedelta(days=1)

    return SerieIndicesDiariosPerigo(
        periodo=periodo,
        indices=tuple(indices),
        politica_id=politica.id_politica,
    )


def _criar_evento(
    dias: list[IndiceDiarioPerigo],
    politica: PoliticaExposicaoEquipamentos,
) -> EventoPerigo:
    indices = [item.indice for item in dias if item.indice is not None]
    classificacao_maxima = max(
        (item.classificacao for item in dias if item.classificacao is not None),
        key=politica.severidades_representativas.valor,
    )
    return EventoPerigo(
        inicio=dias[0].data,
        fim=dias[-1].data,
        duracao_dias=len(dias),
        indice_maximo=max(indices),
        indice_medio=fmean(indices),
        classificacao_maxima=classificacao_maxima,
        severidade_evento=politica.severidades_representativas.valor(
            classificacao_maxima
        ),
        quantidade_dias_relevantes=len(dias),
    )


def agrupar_eventos(
    serie: SerieIndicesDiariosPerigo,
    politica: PoliticaExposicaoEquipamentos,
) -> tuple[EventoPerigo, ...]:
    """Agrupa somente dias relevantes consecutivos, sem tolerância a gaps."""

    if not isinstance(serie, SerieIndicesDiariosPerigo):
        raise TypeError("serie deve ser uma SerieIndicesDiariosPerigo")
    _validar_periodo_e_politica(serie.periodo, politica)
    if serie.politica_id != politica.id_politica:
        raise ValueError("série foi classificada com outra política")
    for item in serie.indices:
        if item.disponibilidade == EstadoDisponibilidade.DISPONIVEL:
            classificacao_esperada = politica.classificar_indice(item.indice)
            if item.classificacao != classificacao_esperada:
                raise ValueError("classificação diária diverge da política")

    eventos: list[EventoPerigo] = []
    evento_atual: list[IndiceDiarioPerigo] = []
    for indice in serie.indices:
        if indice.relevante:
            evento_atual.append(indice)
        elif evento_atual:
            eventos.append(_criar_evento(evento_atual, politica))
            evento_atual = []
    if evento_atual:
        eventos.append(_criar_evento(evento_atual, politica))
    return tuple(eventos)


def agregar_indice_historico(
    serie: SerieIndicesDiariosPerigo,
    politica: PoliticaExposicaoEquipamentos,
) -> ResultadoAgregacaoPerigo:
    """Calcula componentes e índice agregado sem ajustar valores pela cobertura."""

    eventos = agrupar_eventos(serie, politica)
    dias_disponiveis = sum(
        item.disponibilidade == EstadoDisponibilidade.DISPONIVEL
        for item in serie.indices
    )
    dias_relevantes = sum(item.relevante for item in serie.indices)
    quantidade_eventos = len(eventos)
    maior_duracao = max((evento.duracao_dias for evento in eventos), default=0)

    parametros = politica.parametros_normalizacao_90d
    severidade_score = (
        fmean([evento.severidade_evento for evento in eventos]) if eventos else 0.0
    )
    frequencia_score = min(
        dias_relevantes / parametros.frequencia_saturacao_dias * 100.0,
        100.0,
    )
    duracao_score = min(
        maior_duracao / parametros.duracao_saturacao_dias * 100.0,
        100.0,
    )
    recorrencia_score = min(
        quantidade_eventos / parametros.recorrencia_saturacao_eventos * 100.0,
        100.0,
    )

    indice_agregado: float | None = None
    classificacao_agregada: ClassificacaoIndice | None = None
    if dias_disponiveis:
        pesos = politica.pesos_agregacao_90d
        indice_agregado = min(
            max(
                severidade_score * pesos.severidade
                + frequencia_score * pesos.frequencia
                + duracao_score * pesos.duracao
                + recorrencia_score * pesos.recorrencia,
                0.0,
            ),
            100.0,
        )
        classificacao_agregada = politica.classificar_indice(indice_agregado)

    cobertura = 100.0 * dias_disponiveis / serie.periodo.dias_esperados
    cobertura_minima = parametros.cobertura_minima_percentual
    return ResultadoAgregacaoPerigo(
        inicio=serie.periodo.inicio,
        fim=serie.periodo.fim,
        dias_esperados=serie.periodo.dias_esperados,
        dias_disponiveis=dias_disponiveis,
        cobertura_percentual=cobertura,
        cobertura_minima_percentual=cobertura_minima,
        qualidade_suficiente=cobertura >= cobertura_minima,
        quantidade_dias_relevantes=dias_relevantes,
        quantidade_eventos=quantidade_eventos,
        maior_duracao_evento=maior_duracao,
        severidade_score=severidade_score,
        frequencia_score=frequencia_score,
        duracao_score=duracao_score,
        recorrencia_score=recorrencia_score,
        indice_agregado=indice_agregado,
        classificacao_agregada=classificacao_agregada,
        eventos=eventos,
        politica_id=politica.id_politica,
    )


__all__ = [
    "AGREGACAO_PERIGOS_VERSION",
    "EventoPerigo",
    "IndiceDiarioPerigo",
    "ResultadoAgregacaoPerigo",
    "SerieIndicesDiariosPerigo",
    "ValorIndiceDiario",
    "agregar_indice_historico",
    "agrupar_eventos",
    "criar_indices_diarios",
]
