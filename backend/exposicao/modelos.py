"""Modelos puros para séries meteorológicas históricas.

Este módulo representa calendários, observações e qualidade. Ele não consulta
fontes externas, não persiste resultados e não toma decisões operacionais.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Iterable

from pydantic import Field, field_validator, model_validator

from backend.risco.modelos import FonteDado, ModeloDominio, NaturezaDado


VARIAVEIS_METEOROLOGICAS = (
    "precipitacao_mm",
    "temperatura_media_c",
    "temperatura_maxima_c",
    "temperatura_minima_c",
    "umidade_media_pct",
    "velocidade_vento_media_m_s",
)


class FinalidadeJanela(str, Enum):
    ATUAL = "ATUAL"
    COMPARACAO_ANTERIOR = "COMPARACAO_ANTERIOR"


class TipoProdutoHistorico(str, Enum):
    HISTORICO_REGIONAL = "HISTORICO_REGIONAL"
    REANALISE_MODELADA = "REANALISE_MODELADA"


class TipoReferenciaTemporal(str, Enum):
    UTC = "UTC"
    TIMEZONE_CIVIL = "TIMEZONE_CIVIL"
    LOCAL_SOLAR_TIME = "LOCAL_SOLAR_TIME"
    OUTRA = "OUTRA"


class ReferenciaTemporalHistorica(ModeloDominio):
    tipo: TipoReferenciaTemporal
    timezone: str | None = None
    descricao: str | None = None

    @model_validator(mode="after")
    def validar_documentacao(self) -> "ReferenciaTemporalHistorica":
        if self.tipo == TipoReferenciaTemporal.TIMEZONE_CIVIL and not self.timezone:
            raise ValueError("timezone civil exige identificador de timezone")
        if (
            self.tipo
            in {
                TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
                TipoReferenciaTemporal.OUTRA,
            }
            and not self.descricao
        ):
            raise ValueError("referência temporal exige descrição explícita")
        return self


class JanelaHistorica(ModeloDominio):
    data_referencia: date
    inicio: date
    fim: date
    dias_esperados: int = Field(ge=1)
    finalidade: FinalidadeJanela

    @model_validator(mode="after")
    def validar_intervalo_inclusivo(self) -> "JanelaHistorica":
        if self.fim < self.inicio:
            raise ValueError("fim deve ser igual ou posterior ao início")
        if self.fim > self.data_referencia:
            raise ValueError("fim não pode ser posterior à data de referência")
        if (
            self.finalidade == FinalidadeJanela.ATUAL
            and self.fim != self.data_referencia
        ):
            raise ValueError(
                "janela atual deve terminar exatamente na data de referência"
            )
        duracao = (self.fim - self.inicio).days + 1
        if self.dias_esperados != duracao:
            raise ValueError("dias_esperados deve refletir o intervalo inclusivo")
        return self

    @classmethod
    def criar_atual(cls, data_referencia: date, dias: int = 90) -> "JanelaHistorica":
        if dias < 1:
            raise ValueError("dias deve ser positivo")
        return cls(
            data_referencia=data_referencia,
            inicio=data_referencia - timedelta(days=dias - 1),
            fim=data_referencia,
            dias_esperados=dias,
            finalidade=FinalidadeJanela.ATUAL,
        )

    @classmethod
    def criar_aquisicao_180(cls, data_referencia: date) -> "JanelaHistorica":
        return cls.criar_atual(data_referencia, dias=180)

    def dividir_em_periodos_90(self) -> tuple["JanelaHistorica", "JanelaHistorica"]:
        if (
            self.finalidade != FinalidadeJanela.ATUAL
            or self.dias_esperados != 180
            or self.fim != self.data_referencia
        ):
            raise ValueError("a divisão exige janela atual de 180 dias até D0")
        inicio_atual = self.data_referencia - timedelta(days=89)
        anterior = JanelaHistorica(
            data_referencia=self.data_referencia,
            inicio=self.inicio,
            fim=inicio_atual - timedelta(days=1),
            dias_esperados=90,
            finalidade=FinalidadeJanela.COMPARACAO_ANTERIOR,
        )
        atual = JanelaHistorica.criar_atual(self.data_referencia, dias=90)
        return anterior, atual


class RegistroMeteorologicoDiario(ModeloDominio):
    data: date
    precipitacao_mm: float | None = Field(default=None, ge=0)
    temperatura_media_c: float | None = None
    temperatura_maxima_c: float | None = None
    temperatura_minima_c: float | None = None
    umidade_media_pct: float | None = Field(default=None, ge=0, le=100)
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)
    variaveis_ausentes: tuple[str, ...] = ()
    flags_qualidade: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def completar_e_validar_ausencias(cls, dados: Any) -> Any:
        if not isinstance(dados, dict):
            return dados
        dados = dict(dados)
        calculadas = tuple(
            variavel
            for variavel in VARIAVEIS_METEOROLOGICAS
            if dados.get(variavel) is None
        )
        if "variaveis_ausentes" in dados:
            informadas = tuple(dados["variaveis_ausentes"] or ())
            if set(informadas) != set(calculadas) or len(informadas) != len(
                set(informadas)
            ):
                raise ValueError("variaveis_ausentes diverge dos valores ausentes")
        dados["variaveis_ausentes"] = calculadas
        return dados

    @field_validator(
        "precipitacao_mm",
        "temperatura_media_c",
        "temperatura_maxima_c",
        "temperatura_minima_c",
        "umidade_media_pct",
        "velocidade_vento_media_m_s",
        mode="before",
    )
    @classmethod
    def rejeitar_booleano_como_numero(cls, valor: Any) -> Any:
        if isinstance(valor, bool):
            raise ValueError("valor meteorológico deve ser numérico")
        return valor

    @field_validator("flags_qualidade", mode="after")
    @classmethod
    def ordenar_flags(cls, flags: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(flags)))

    def possui_algum_dado(self) -> bool:
        return any(
            getattr(self, variavel) is not None for variavel in VARIAVEIS_METEOROLOGICAS
        )


class GapTemporal(ModeloDominio):
    inicio: date
    fim: date
    duracao_dias: int = Field(ge=1)
    variaveis_afetadas: tuple[str, ...]

    @field_validator("variaveis_afetadas", mode="after")
    @classmethod
    def validar_variaveis(cls, variaveis: tuple[str, ...]) -> tuple[str, ...]:
        desconhecidas = set(variaveis) - set(VARIAVEIS_METEOROLOGICAS)
        if desconhecidas:
            raise ValueError(
                f"variáveis meteorológicas desconhecidas: {sorted(desconhecidas)}"
            )
        if not variaveis:
            raise ValueError("gap deve afetar ao menos uma variável")
        if len(variaveis) != len(set(variaveis)):
            raise ValueError("variáveis afetadas não podem se repetir")
        return tuple(v for v in VARIAVEIS_METEOROLOGICAS if v in variaveis)

    @model_validator(mode="after")
    def validar_duracao(self) -> "GapTemporal":
        if self.fim < self.inicio:
            raise ValueError("fim do gap deve ser igual ou posterior ao início")
        if self.duracao_dias != (self.fim - self.inicio).days + 1:
            raise ValueError("duração do gap deve refletir o intervalo inclusivo")
        return self


class IntervaloTemporalHistorico(ModeloDominio):
    inicio: date
    fim: date

    @model_validator(mode="after")
    def validar_intervalo(self) -> "IntervaloTemporalHistorico":
        if self.fim < self.inicio:
            raise ValueError("fim deve ser igual ou posterior ao início")
        return self


class QualidadeHistorica(ModeloDominio):
    dias_esperados: int = Field(ge=1)
    dias_com_algum_dado: int = Field(ge=0)
    cobertura_pct: float = Field(ge=0, le=100)
    dias_disponiveis_por_variavel: dict[str, int]
    cobertura_por_variavel_pct: dict[str, float]
    gaps: tuple[GapTemporal, ...] = ()
    ultima_data_disponivel_por_variavel: dict[str, date | None]

    @model_validator(mode="after")
    def validar_coerencia(self) -> "QualidadeHistorica":
        if self.dias_com_algum_dado > self.dias_esperados:
            raise ValueError("dias com dados não pode exceder dias esperados")
        esperado_geral = round(100 * self.dias_com_algum_dado / self.dias_esperados, 2)
        if self.cobertura_pct != esperado_geral:
            raise ValueError("cobertura geral incoerente com a contagem de dias")

        chaves = set(VARIAVEIS_METEOROLOGICAS)
        if set(self.dias_disponiveis_por_variavel) != chaves:
            raise ValueError("contagem por variável deve conter todas as variáveis")
        if set(self.cobertura_por_variavel_pct) != chaves:
            raise ValueError("cobertura por variável deve conter todas as variáveis")
        if set(self.ultima_data_disponivel_por_variavel) != chaves:
            raise ValueError("última data deve conter todas as variáveis")

        for variavel in VARIAVEIS_METEOROLOGICAS:
            dias = self.dias_disponiveis_por_variavel[variavel]
            if isinstance(dias, bool) or not 0 <= dias <= self.dias_esperados:
                raise ValueError("contagem disponível por variável fora do domínio")
            esperado = round(100 * dias / self.dias_esperados, 2)
            if self.cobertura_por_variavel_pct[variavel] != esperado:
                raise ValueError("cobertura por variável incoerente com a contagem")
        return self

    @classmethod
    def calcular(
        cls,
        janela: JanelaHistorica,
        registros: Iterable[RegistroMeteorologicoDiario],
    ) -> "QualidadeHistorica":
        ordenados = tuple(sorted(registros, key=lambda registro: registro.data))
        datas = [registro.data for registro in ordenados]
        if len(datas) != len(set(datas)):
            raise ValueError("datas duplicadas não são permitidas")
        if any(data < janela.inicio or data > janela.fim for data in datas):
            raise ValueError("registro fora do período solicitado")

        por_data = {registro.data: registro for registro in ordenados}
        dias_com_algum = sum(registro.possui_algum_dado() for registro in ordenados)
        contagens = {
            variavel: sum(
                getattr(registro, variavel) is not None for registro in ordenados
            )
            for variavel in VARIAVEIS_METEOROLOGICAS
        }
        ultimas = {
            variavel: max(
                (
                    registro.data
                    for registro in ordenados
                    if getattr(registro, variavel) is not None
                ),
                default=None,
            )
            for variavel in VARIAVEIS_METEOROLOGICAS
        }

        gaps: list[GapTemporal] = []
        inicio_gap: date | None = None
        fim_gap: date | None = None
        variaveis_gap: tuple[str, ...] | None = None
        dia = janela.inicio
        while dia <= janela.fim:
            registro = por_data.get(dia)
            ausentes = (
                VARIAVEIS_METEOROLOGICAS
                if registro is None
                else registro.variaveis_ausentes
            )
            if ausentes:
                if inicio_gap is not None and ausentes == variaveis_gap:
                    fim_gap = dia
                else:
                    if inicio_gap is not None and fim_gap is not None and variaveis_gap:
                        gaps.append(
                            GapTemporal(
                                inicio=inicio_gap,
                                fim=fim_gap,
                                duracao_dias=(fim_gap - inicio_gap).days + 1,
                                variaveis_afetadas=variaveis_gap,
                            )
                        )
                    inicio_gap = fim_gap = dia
                    variaveis_gap = ausentes
            elif inicio_gap is not None and fim_gap is not None and variaveis_gap:
                gaps.append(
                    GapTemporal(
                        inicio=inicio_gap,
                        fim=fim_gap,
                        duracao_dias=(fim_gap - inicio_gap).days + 1,
                        variaveis_afetadas=variaveis_gap,
                    )
                )
                inicio_gap = fim_gap = None
                variaveis_gap = None
            dia += timedelta(days=1)
        if inicio_gap is not None and fim_gap is not None and variaveis_gap:
            gaps.append(
                GapTemporal(
                    inicio=inicio_gap,
                    fim=fim_gap,
                    duracao_dias=(fim_gap - inicio_gap).days + 1,
                    variaveis_afetadas=variaveis_gap,
                )
            )

        return cls(
            dias_esperados=janela.dias_esperados,
            dias_com_algum_dado=dias_com_algum,
            cobertura_pct=round(100 * dias_com_algum / janela.dias_esperados, 2),
            dias_disponiveis_por_variavel=contagens,
            cobertura_por_variavel_pct={
                variavel: round(100 * dias / janela.dias_esperados, 2)
                for variavel, dias in contagens.items()
            },
            gaps=tuple(gaps),
            ultima_data_disponivel_por_variavel=ultimas,
        )


class SerieHistoricaFonte(ModeloDominio):
    id_fazenda: str | None = None
    fonte: FonteDado
    natureza: NaturezaDado = NaturezaDado.HISTORICO
    tipo_produto: TipoProdutoHistorico
    dataset: str = Field(min_length=1)
    periodo_solicitado: JanelaHistorica
    periodo_efetivo: IntervaloTemporalHistorico | None = None
    referencia_temporal: ReferenciaTemporalHistorica
    registros: tuple[RegistroMeteorologicoDiario, ...]
    qualidade: QualidadeHistorica
    coletado_em_utc: datetime
    metadados_origem: dict[str, Any] = Field(default_factory=dict)

    @field_validator("registros", mode="after")
    @classmethod
    def ordenar_e_rejeitar_duplicatas(
        cls, registros: tuple[RegistroMeteorologicoDiario, ...]
    ) -> tuple[RegistroMeteorologicoDiario, ...]:
        datas = [registro.data for registro in registros]
        if len(datas) != len(set(datas)):
            raise ValueError("datas duplicadas não são permitidas")
        return tuple(sorted(registros, key=lambda registro: registro.data))

    @field_validator("coletado_em_utc", mode="after")
    @classmethod
    def exigir_utc(cls, instante: datetime) -> datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("coletado_em_utc exige datetime com timezone")
        return instante.astimezone(timezone.utc)

    @field_validator("metadados_origem", mode="before")
    @classmethod
    def copiar_metadados(cls, metadados: Any) -> Any:
        return deepcopy(metadados)

    @model_validator(mode="after")
    def validar_serie(self) -> "SerieHistoricaFonte":
        if self.natureza != NaturezaDado.HISTORICO:
            raise ValueError("série histórica exige natureza HISTORICO")
        produtos_por_fonte = {
            FonteDado.NASA_POWER: TipoProdutoHistorico.HISTORICO_REGIONAL,
            FonteDado.OPEN_METEO: TipoProdutoHistorico.REANALISE_MODELADA,
        }
        esperado = produtos_por_fonte.get(self.fonte)
        if esperado is not None and self.tipo_produto != esperado:
            raise ValueError("tipo de produto incoerente com a fonte")
        if any(
            registro.data < self.periodo_solicitado.inicio
            or registro.data > self.periodo_solicitado.fim
            for registro in self.registros
        ):
            raise ValueError("registro fora do período solicitado")

        observados = [
            registro.data for registro in self.registros if registro.possui_algum_dado()
        ]
        efetivo_esperado = (
            IntervaloTemporalHistorico(inicio=min(observados), fim=max(observados))
            if observados
            else None
        )
        if self.periodo_efetivo != efetivo_esperado:
            raise ValueError("período efetivo diverge das observações disponíveis")

        qualidade_esperada = QualidadeHistorica.calcular(
            self.periodo_solicitado, self.registros
        )
        if self.qualidade != qualidade_esperada:
            raise ValueError("qualidade diverge dos registros e do período solicitado")
        return self

    @classmethod
    def criar(
        cls,
        *,
        fonte: FonteDado,
        tipo_produto: TipoProdutoHistorico,
        dataset: str,
        periodo_solicitado: JanelaHistorica,
        referencia_temporal: ReferenciaTemporalHistorica,
        registros: Iterable[RegistroMeteorologicoDiario],
        coletado_em_utc: datetime,
        id_fazenda: str | None = None,
        metadados_origem: dict[str, Any] | None = None,
    ) -> "SerieHistoricaFonte":
        registros_ordenados = tuple(
            sorted(registros, key=lambda registro: registro.data)
        )
        datas = [registro.data for registro in registros_ordenados]
        if len(datas) != len(set(datas)):
            raise ValueError("datas duplicadas não são permitidas")
        observados = [
            registro.data
            for registro in registros_ordenados
            if registro.possui_algum_dado()
        ]
        periodo_efetivo = (
            IntervaloTemporalHistorico(inicio=min(observados), fim=max(observados))
            if observados
            else None
        )
        return cls(
            id_fazenda=id_fazenda,
            fonte=fonte,
            natureza=NaturezaDado.HISTORICO,
            tipo_produto=tipo_produto,
            dataset=dataset,
            periodo_solicitado=periodo_solicitado,
            periodo_efetivo=periodo_efetivo,
            referencia_temporal=referencia_temporal,
            registros=registros_ordenados,
            qualidade=QualidadeHistorica.calcular(
                periodo_solicitado, registros_ordenados
            ),
            coletado_em_utc=coletado_em_utc,
            metadados_origem=deepcopy(metadados_origem or {}),
        )


__all__ = [
    "VARIAVEIS_METEOROLOGICAS",
    "FinalidadeJanela",
    "GapTemporal",
    "IntervaloTemporalHistorico",
    "JanelaHistorica",
    "QualidadeHistorica",
    "ReferenciaTemporalHistorica",
    "RegistroMeteorologicoDiario",
    "SerieHistoricaFonte",
    "TipoProdutoHistorico",
    "TipoReferenciaTemporal",
]
