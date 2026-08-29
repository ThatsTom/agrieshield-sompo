"""Contrato versionado da política demonstrativa de exposição de equipamentos.

Este módulo contém somente configuração, validações e classificação do índice.
Ele não calcula perigos, eventos, séries históricas ou scores de fazendas.
"""

from __future__ import annotations

import math
from enum import Enum

from pydantic import Field, field_validator, model_validator

from backend.risco.modelos import ModeloDominio


POLITICA_AGRISHIELD_EQUIP_V1_ID = "AGRISHIELD-EQUIP-v1.0"
TOLERANCIA_SOMA_PESOS = 1e-9


class PerigoExposicao(str, Enum):
    EXPOSICAO_HIDRICA = "EXPOSICAO_HIDRICA"
    TRAFEGABILIDADE = "TRAFEGABILIDADE"
    INSTABILIDADE = "INSTABILIDADE"
    INCENDIO = "INCENDIO"
    TEMPESTADES = "TEMPESTADES"


class ClassificacaoIndice(str, Enum):
    NORMAL = "NORMAL"
    ATENCAO = "ATENCAO"
    ALERTA = "ALERTA"
    CRITICO = "CRITICO"


class EstadoDisponibilidade(str, Enum):
    DISPONIVEL = "DISPONIVEL"
    INDISPONIVEL = "INDISPONIVEL"
    NAO_APLICAVEL = "NAO_APLICAVEL"


def _validar_soma_unitaria(valores: tuple[float, ...], contexto: str) -> None:
    if not math.isclose(
        math.fsum(valores),
        1.0,
        rel_tol=0.0,
        abs_tol=TOLERANCIA_SOMA_PESOS,
    ):
        raise ValueError(f"a soma dos pesos de {contexto} deve ser 1.0")


class PesosPerigos(ModeloDominio):
    exposicao_hidrica: float = Field(ge=0, le=1)
    trafegabilidade: float = Field(ge=0, le=1)
    instabilidade: float = Field(ge=0, le=1)
    incendio: float = Field(ge=0, le=1)
    tempestades: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validar_soma(self) -> "PesosPerigos":
        _validar_soma_unitaria(
            (
                self.exposicao_hidrica,
                self.trafegabilidade,
                self.instabilidade,
                self.incendio,
                self.tempestades,
            ),
            "perigos",
        )
        return self

    def peso(self, perigo: PerigoExposicao) -> float:
        campos = {
            PerigoExposicao.EXPOSICAO_HIDRICA: self.exposicao_hidrica,
            PerigoExposicao.TRAFEGABILIDADE: self.trafegabilidade,
            PerigoExposicao.INSTABILIDADE: self.instabilidade,
            PerigoExposicao.INCENDIO: self.incendio,
            PerigoExposicao.TEMPESTADES: self.tempestades,
        }
        return campos[perigo]


class PesosAgregacao90d(ModeloDominio):
    severidade: float = Field(ge=0, le=1)
    frequencia: float = Field(ge=0, le=1)
    duracao: float = Field(ge=0, le=1)
    recorrencia: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validar_soma(self) -> "PesosAgregacao90d":
        _validar_soma_unitaria(
            (
                self.severidade,
                self.frequencia,
                self.duracao,
                self.recorrencia,
            ),
            "agregação de 90 dias",
        )
        return self


class FaixasClassificacaoIndice(ModeloDominio):
    inicio_atencao: float = Field(ge=0, le=100)
    inicio_alerta: float = Field(ge=0, le=100)
    inicio_critico: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validar_ordem(self) -> "FaixasClassificacaoIndice":
        if not (
            0 < self.inicio_atencao < self.inicio_alerta < self.inicio_critico < 100
        ):
            raise ValueError(
                "thresholds de classificação devem ser estritamente ordenados"
            )
        return self


class SeveridadesRepresentativas(ModeloDominio):
    normal: float = Field(ge=0, le=100)
    atencao: float = Field(ge=0, le=100)
    alerta: float = Field(ge=0, le=100)
    critico: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validar_ordem(self) -> "SeveridadesRepresentativas":
        if not self.normal < self.atencao < self.alerta < self.critico:
            raise ValueError("severidades representativas devem ser crescentes")
        return self

    def valor(self, classificacao: ClassificacaoIndice) -> float:
        valores = {
            ClassificacaoIndice.NORMAL: self.normal,
            ClassificacaoIndice.ATENCAO: self.atencao,
            ClassificacaoIndice.ALERTA: self.alerta,
            ClassificacaoIndice.CRITICO: self.critico,
        }
        return valores[classificacao]


class ParametrosNormalizacao90d(ModeloDominio):
    frequencia_saturacao_dias: int = Field(gt=0)
    duracao_saturacao_dias: int = Field(gt=0)
    recorrencia_saturacao_eventos: int = Field(gt=0)
    cobertura_minima_percentual: float = Field(ge=0, le=100)


class PontoCurvaPrecipitacao(ModeloDominio):
    precipitacao_mm: float = Field(ge=0)
    indice: float = Field(ge=0, le=100)


class ParametrosCondicaoHidrica(ModeloDominio):
    curva_precipitacao: tuple[PontoCurvaPrecipitacao, ...] = Field(min_length=2)
    peso_antecedente_d1_d3: float = Field(ge=0, le=1)
    peso_antecedente_d4_d7: float = Field(ge=0, le=1)
    peso_chuva_atual: float = Field(ge=0, le=1)
    peso_chuva_antecedente: float = Field(ge=0, le=1)
    multiplicador_persistencia_0_1_dia: float = Field(gt=0)
    multiplicador_persistencia_2_3_dias: float = Field(gt=0)
    multiplicador_persistencia_4_mais_dias: float = Field(gt=0)

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosCondicaoHidrica":
        precipitacoes = [ponto.precipitacao_mm for ponto in self.curva_precipitacao]
        indices = [ponto.indice for ponto in self.curva_precipitacao]
        if any(
            atual >= seguinte
            for atual, seguinte in zip(precipitacoes, precipitacoes[1:])
        ):
            raise ValueError("pontos de precipitação devem ser estritamente crescentes")
        if any(atual > seguinte for atual, seguinte in zip(indices, indices[1:])):
            raise ValueError(
                "índices da curva de precipitação devem ser não decrescentes"
            )
        _validar_soma_unitaria(
            (self.peso_antecedente_d1_d3, self.peso_antecedente_d4_d7),
            "chuva antecedente",
        )
        _validar_soma_unitaria(
            (self.peso_chuva_atual, self.peso_chuva_antecedente),
            "condição hídrica",
        )
        if not (
            self.multiplicador_persistencia_0_1_dia
            <= self.multiplicador_persistencia_2_3_dias
            <= self.multiplicador_persistencia_4_mais_dias
        ):
            raise ValueError(
                "multiplicadores de persistência devem ser não decrescentes"
            )
        return self


class ParametrosTrafegabilidade(ModeloDominio):
    """Composição interna da metodologia meteorológica própria de Trafegabilidade.

    A curva de precipitação (expoente e normalizador) e a janela de
    recuperação/secagem permanecem fixas no código: fazem parte da
    metodologia, não da parametrização de negócio exposta nesta versão.
    """

    peso_dia: float = Field(ge=0, le=1)
    peso_acumulado: float = Field(ge=0, le=1)
    peso_recuperacao: float = Field(ge=0, le=1)
    limiar_relevancia: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosTrafegabilidade":
        _validar_soma_unitaria(
            (self.peso_dia, self.peso_acumulado, self.peso_recuperacao),
            "composição de Trafegabilidade",
        )
        return self

    model_config = {"frozen": True}


class ParametrosTerritoriaisHidricos(ModeloDominio):
    """Parâmetros promovidos sem recalibração da metodologia selecionada."""

    mediana_distancia_m: float = 1868.12508034684
    area_log_min: float = 2.53850909780559
    area_log_max: float = 10.0608666649158
    mediana_posicao_m: float = 7.6517377036555
    iqr_posicao_m: float = 13.8746841685139
    peso_proximidade_drenagem: float = 0.40
    peso_area_montante: float = 0.35
    peso_posicao_topografica: float = 0.25
    fator_incremento: float = 0.30
    origem: str = "baseline_v1/simulacao_hidrico_v2"
    calibrado_contra_sinistros: bool = False

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosTerritoriaisHidricos":
        if self.area_log_max <= self.area_log_min or self.iqr_posicao_m <= 0:
            raise ValueError("parâmetros de normalização territorial inválidos")
        soma = (
            self.peso_proximidade_drenagem
            + self.peso_area_montante
            + self.peso_posicao_topografica
        )
        if not math.isclose(soma, 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("pesos territoriais devem somar 1")
        return self

    model_config = {"frozen": True}


PARAMETROS_TERRITORIAIS_HIDRICOS = ParametrosTerritoriaisHidricos()


class PontoCurvaDeclividade(ModeloDominio):
    declividade_graus: float = Field(ge=0)
    indice: float = Field(ge=0, le=100)


class FaixaAtivacaoHidrica(ModeloDominio):
    inicio_indice_hidrico: float = Field(ge=0, le=100)
    fator_ativacao: float = Field(ge=0, le=1)


class ParametrosInstabilidade(ModeloDominio):
    curva_declividade: tuple[PontoCurvaDeclividade, ...] = Field(min_length=2)
    faixas_ativacao_hidrica: tuple[FaixaAtivacaoHidrica, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosInstabilidade":
        declividades = [ponto.declividade_graus for ponto in self.curva_declividade]
        indices = [ponto.indice for ponto in self.curva_declividade]
        if declividades[0] != 0:
            raise ValueError("curva de declividade deve iniciar em zero grau")
        if any(
            atual >= seguinte for atual, seguinte in zip(declividades, declividades[1:])
        ):
            raise ValueError("pontos de declividade devem ser estritamente crescentes")
        if any(atual > seguinte for atual, seguinte in zip(indices, indices[1:])):
            raise ValueError(
                "indices da curva de declividade devem ser nao decrescentes"
            )

        inicios = [
            faixa.inicio_indice_hidrico for faixa in self.faixas_ativacao_hidrica
        ]
        fatores = [faixa.fator_ativacao for faixa in self.faixas_ativacao_hidrica]
        if inicios[0] != 0:
            raise ValueError("faixas de ativacao hidrica devem iniciar em zero")
        if any(atual >= seguinte for atual, seguinte in zip(inicios, inicios[1:])):
            raise ValueError("faixas de ativacao hidrica devem ser crescentes")
        if any(atual > seguinte for atual, seguinte in zip(fatores, fatores[1:])):
            raise ValueError("fatores de ativacao devem ser nao decrescentes")
        return self


class PontoCurvaTemperaturaFogo(ModeloDominio):
    temperatura_c: float
    componente: float = Field(ge=0, le=1)


class PontoCurvaUmidadeFogo(ModeloDominio):
    umidade_pct: float = Field(ge=0, le=100)
    componente: float = Field(ge=0, le=1)


class PontoCurvaVentoFogo(ModeloDominio):
    velocidade_m_s: float = Field(ge=0)
    componente: float = Field(ge=0, le=1)


class FaixaSecuraAntecedente(ModeloDominio):
    inicio_dias: int = Field(ge=0)
    multiplicador: float = Field(gt=0)


class ParametrosPropagacaoFogo(ModeloDominio):
    curva_temperatura_maxima: tuple[PontoCurvaTemperaturaFogo, ...] = Field(
        min_length=2
    )
    curva_baixa_umidade_media: tuple[PontoCurvaUmidadeFogo, ...] = Field(min_length=2)
    curva_velocidade_vento_media: tuple[PontoCurvaVentoFogo, ...] = Field(min_length=2)
    faixas_secura_antecedente: tuple[FaixaSecuraAntecedente, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosPropagacaoFogo":
        temperaturas = [p.temperatura_c for p in self.curva_temperatura_maxima]
        componentes_temperatura = [p.componente for p in self.curva_temperatura_maxima]
        umidades = [p.umidade_pct for p in self.curva_baixa_umidade_media]
        componentes_umidade = [p.componente for p in self.curva_baixa_umidade_media]
        ventos = [p.velocidade_m_s for p in self.curva_velocidade_vento_media]
        componentes_vento = [p.componente for p in self.curva_velocidade_vento_media]
        inicios_secura = [p.inicio_dias for p in self.faixas_secura_antecedente]
        multiplicadores = [p.multiplicador for p in self.faixas_secura_antecedente]

        for valores, nome in (
            (temperaturas, "temperatura"),
            (umidades, "umidade"),
            (ventos, "vento"),
            (inicios_secura, "secura antecedente"),
        ):
            if any(atual >= seguinte for atual, seguinte in zip(valores, valores[1:])):
                raise ValueError(f"pontos de {nome} devem ser estritamente crescentes")
        if any(
            atual > seguinte
            for atual, seguinte in zip(
                componentes_temperatura, componentes_temperatura[1:]
            )
        ):
            raise ValueError("componentes de temperatura devem ser nao decrescentes")
        if any(
            atual < seguinte
            for atual, seguinte in zip(componentes_umidade, componentes_umidade[1:])
        ):
            raise ValueError("componentes de baixa umidade devem ser nao crescentes")
        if any(
            atual > seguinte
            for atual, seguinte in zip(componentes_vento, componentes_vento[1:])
        ):
            raise ValueError("componentes de vento devem ser nao decrescentes")
        if inicios_secura[0] != 0:
            raise ValueError("faixas de secura antecedente devem iniciar em zero")
        if any(
            atual > seguinte
            for atual, seguinte in zip(multiplicadores, multiplicadores[1:])
        ):
            raise ValueError("multiplicadores de secura devem ser nao decrescentes")
        return self


class PontoCurvaPrecipitacaoTempestade(ModeloDominio):
    precipitacao_mm: float = Field(ge=0)
    componente: float = Field(ge=0, le=1)


class ParametrosTempestade(ModeloDominio):
    curva_precipitacao_d0: tuple[PontoCurvaPrecipitacaoTempestade, ...] = Field(
        min_length=2
    )
    peso_base_vento: float = Field(ge=0, le=1)
    peso_amplificacao_chuva: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validar_parametros(self) -> "ParametrosTempestade":
        precipitacoes = [p.precipitacao_mm for p in self.curva_precipitacao_d0]
        componentes = [p.componente for p in self.curva_precipitacao_d0]
        if any(
            atual >= seguinte
            for atual, seguinte in zip(precipitacoes, precipitacoes[1:])
        ):
            raise ValueError(
                "pontos de precipitacao da tempestade devem ser crescentes"
            )
        if any(
            atual > seguinte for atual, seguinte in zip(componentes, componentes[1:])
        ):
            raise ValueError(
                "componentes de chuva da tempestade devem ser nao decrescentes"
            )
        _validar_soma_unitaria(
            (self.peso_base_vento, self.peso_amplificacao_chuva),
            "tempestade",
        )
        return self


class PoliticaExposicaoEquipamentos(ModeloDominio):
    id_politica: str = Field(min_length=1)
    versao: str = Field(min_length=1)
    descricao: str = Field(min_length=1)
    demonstrativa: bool
    janela_historica_dias: int = Field(gt=0)
    comparacao_anterior_dias: int = Field(gt=0)
    pesos_perigos: PesosPerigos
    pesos_agregacao_90d: PesosAgregacao90d
    faixas_classificacao: FaixasClassificacaoIndice
    severidades_representativas: SeveridadesRepresentativas
    parametros_normalizacao_90d: ParametrosNormalizacao90d
    parametros_condicao_hidrica: ParametrosCondicaoHidrica
    parametros_instabilidade: ParametrosInstabilidade
    parametros_propagacao_fogo: ParametrosPropagacaoFogo
    parametros_tempestade: ParametrosTempestade
    parametros_territoriais_hidricos: ParametrosTerritoriaisHidricos
    parametros_trafegabilidade: ParametrosTrafegabilidade

    @field_validator("id_politica", "versao", "descricao", mode="before")
    @classmethod
    def rejeitar_texto_vazio(cls, valor: object) -> object:
        if isinstance(valor, str) and not valor.strip():
            raise ValueError("texto obrigatório não pode ser vazio")
        return valor

    def classificar_indice(self, valor: float) -> ClassificacaoIndice:
        """Classifica exclusivamente um índice numérico no domínio de 0 a 100."""

        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise TypeError("índice deve ser numérico")
        if not math.isfinite(valor) or not 0 <= valor <= 100:
            raise ValueError("índice deve estar entre 0 e 100")
        faixas = self.faixas_classificacao
        if valor < faixas.inicio_atencao:
            return ClassificacaoIndice.NORMAL
        if valor < faixas.inicio_alerta:
            return ClassificacaoIndice.ATENCAO
        if valor < faixas.inicio_critico:
            return ClassificacaoIndice.ALERTA
        return ClassificacaoIndice.CRITICO


def criar_politica_agrishield_equip_v1() -> PoliticaExposicaoEquipamentos:
    """Cria explicitamente a configuração demonstrativa AGRISHIELD-EQUIP-v1.0."""

    return PoliticaExposicaoEquipamentos(
        id_politica=POLITICA_AGRISHIELD_EQUIP_V1_ID,
        versao="1.0",
        descricao=(
            "Política demonstrativa e não atuarial para estimar exposição ambiental "
            "e territorial de máquinas e equipamentos agrícolas a condições "
            "potencialmente associadas a sinistros; não constitui limite operacional "
            "universal nem recomendação de fabricante."
        ),
        demonstrativa=True,
        janela_historica_dias=90,
        comparacao_anterior_dias=90,
        pesos_perigos=PesosPerigos(
            exposicao_hidrica=0.30,
            trafegabilidade=0.25,
            instabilidade=0.20,
            incendio=0.15,
            tempestades=0.10,
        ),
        pesos_agregacao_90d=PesosAgregacao90d(
            severidade=0.40,
            frequencia=0.30,
            duracao=0.20,
            recorrencia=0.10,
        ),
        faixas_classificacao=FaixasClassificacaoIndice(
            inicio_atencao=25,
            inicio_alerta=50,
            inicio_critico=75,
        ),
        severidades_representativas=SeveridadesRepresentativas(
            normal=0,
            atencao=33,
            alerta=67,
            critico=100,
        ),
        parametros_normalizacao_90d=ParametrosNormalizacao90d(
            frequencia_saturacao_dias=15,
            duracao_saturacao_dias=7,
            recorrencia_saturacao_eventos=5,
            cobertura_minima_percentual=80.0,
        ),
        parametros_condicao_hidrica=ParametrosCondicaoHidrica(
            curva_precipitacao=(
                PontoCurvaPrecipitacao(precipitacao_mm=0, indice=0),
                PontoCurvaPrecipitacao(precipitacao_mm=20, indice=25),
                PontoCurvaPrecipitacao(precipitacao_mm=50, indice=50),
                PontoCurvaPrecipitacao(precipitacao_mm=100, indice=100),
            ),
            peso_antecedente_d1_d3=0.70,
            peso_antecedente_d4_d7=0.30,
            peso_chuva_atual=0.70,
            peso_chuva_antecedente=0.30,
            multiplicador_persistencia_0_1_dia=1.00,
            multiplicador_persistencia_2_3_dias=1.10,
            multiplicador_persistencia_4_mais_dias=1.20,
        ),
        parametros_instabilidade=ParametrosInstabilidade(
            curva_declividade=(
                PontoCurvaDeclividade(declividade_graus=0, indice=0),
                PontoCurvaDeclividade(declividade_graus=5, indice=15),
                PontoCurvaDeclividade(declividade_graus=10, indice=35),
                PontoCurvaDeclividade(declividade_graus=15, indice=60),
                PontoCurvaDeclividade(declividade_graus=20, indice=80),
                PontoCurvaDeclividade(declividade_graus=25, indice=100),
            ),
            faixas_ativacao_hidrica=(
                FaixaAtivacaoHidrica(inicio_indice_hidrico=0, fator_ativacao=0.00),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=25, fator_ativacao=0.35),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=50, fator_ativacao=0.65),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=75, fator_ativacao=1.00),
            ),
        ),
        parametros_propagacao_fogo=ParametrosPropagacaoFogo(
            curva_temperatura_maxima=(
                PontoCurvaTemperaturaFogo(temperatura_c=20, componente=0.00),
                PontoCurvaTemperaturaFogo(temperatura_c=25, componente=0.25),
                PontoCurvaTemperaturaFogo(temperatura_c=30, componente=0.60),
                PontoCurvaTemperaturaFogo(temperatura_c=35, componente=0.85),
                PontoCurvaTemperaturaFogo(temperatura_c=40, componente=1.00),
            ),
            curva_baixa_umidade_media=(
                PontoCurvaUmidadeFogo(umidade_pct=20, componente=1.00),
                PontoCurvaUmidadeFogo(umidade_pct=30, componente=0.75),
                PontoCurvaUmidadeFogo(umidade_pct=40, componente=0.50),
                PontoCurvaUmidadeFogo(umidade_pct=50, componente=0.25),
                PontoCurvaUmidadeFogo(umidade_pct=70, componente=0.00),
            ),
            curva_velocidade_vento_media=(
                PontoCurvaVentoFogo(velocidade_m_s=0, componente=0.00),
                PontoCurvaVentoFogo(velocidade_m_s=2, componente=0.20),
                PontoCurvaVentoFogo(velocidade_m_s=4, componente=0.50),
                PontoCurvaVentoFogo(velocidade_m_s=6, componente=0.75),
                PontoCurvaVentoFogo(velocidade_m_s=8, componente=1.00),
            ),
            faixas_secura_antecedente=(
                FaixaSecuraAntecedente(inicio_dias=0, multiplicador=0.90),
                FaixaSecuraAntecedente(inicio_dias=2, multiplicador=1.00),
                FaixaSecuraAntecedente(inicio_dias=4, multiplicador=1.05),
                FaixaSecuraAntecedente(inicio_dias=7, multiplicador=1.10),
            ),
        ),
        parametros_tempestade=ParametrosTempestade(
            curva_precipitacao_d0=(
                PontoCurvaPrecipitacaoTempestade(precipitacao_mm=0, componente=0.00),
                PontoCurvaPrecipitacaoTempestade(precipitacao_mm=10, componente=0.20),
                PontoCurvaPrecipitacaoTempestade(precipitacao_mm=20, componente=0.40),
                PontoCurvaPrecipitacaoTempestade(precipitacao_mm=50, componente=0.70),
                PontoCurvaPrecipitacaoTempestade(precipitacao_mm=100, componente=1.00),
            ),
            peso_base_vento=0.75,
            peso_amplificacao_chuva=0.25,
        ),
        parametros_territoriais_hidricos=ParametrosTerritoriaisHidricos(),
        parametros_trafegabilidade=ParametrosTrafegabilidade(
            peso_dia=0.35,
            peso_acumulado=0.45,
            peso_recuperacao=0.20,
            limiar_relevancia=25.0,
        ),
    )


__all__ = [
    "POLITICA_AGRISHIELD_EQUIP_V1_ID",
    "ClassificacaoIndice",
    "EstadoDisponibilidade",
    "FaixaAtivacaoHidrica",
    "FaixaSecuraAntecedente",
    "FaixasClassificacaoIndice",
    "ParametrosCondicaoHidrica",
    "ParametrosInstabilidade",
    "ParametrosPropagacaoFogo",
    "ParametrosTempestade",
    "ParametrosNormalizacao90d",
    "ParametrosTerritoriaisHidricos",
    "PARAMETROS_TERRITORIAIS_HIDRICOS",
    "ParametrosTrafegabilidade",
    "PerigoExposicao",
    "PesosAgregacao90d",
    "PesosPerigos",
    "PoliticaExposicaoEquipamentos",
    "PontoCurvaDeclividade",
    "PontoCurvaTemperaturaFogo",
    "PontoCurvaUmidadeFogo",
    "PontoCurvaVentoFogo",
    "PontoCurvaPrecipitacao",
    "PontoCurvaPrecipitacaoTempestade",
    "SeveridadesRepresentativas",
    "criar_politica_agrishield_equip_v1",
]
