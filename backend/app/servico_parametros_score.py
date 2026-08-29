"""Camada de aplicacao dos parametros configuraveis do modelo AgriShield-EQUIP.

Traduz entre o repositorio CSV generico (grupo/indicador/parametro) e os
contratos que o motor de calculo ja consome: PesosPerigos,
ParametrosTerritoriaisHidricos, ParametrosInstabilidade,
ParametrosPropagacaoFogo e ParametrosTempestade. O motor nunca importa o
repositorio diretamente; so conhece esses contratos ja validados.

A validacao de cada grupo reaproveita os proprios validadores desses
contratos (soma unitaria, monotonicidade, faixas de dominio) em vez de
duplicar a regra aqui: tentamos construir o objeto real e traduzimos uma
falha de validacao numa mensagem especifica do grupo.
"""

from __future__ import annotations

import logging
import math

from pydantic import Field, ValidationError, model_validator

from backend.etl.repositorio_parametros_score import (
    CHAVES_ESPERADAS,
    ChaveParametro,
    ErroRepositorioParametrosModeloCorrompido,
    carregar_linhas_parametros_modelo,
    salvar_parametros_modelo,
)
from backend.exposicao.politica import (
    FaixaAtivacaoHidrica,
    FaixaSecuraAntecedente,
    ParametrosInstabilidade,
    ParametrosPropagacaoFogo,
    ParametrosTempestade,
    ParametrosTerritoriaisHidricos,
    ParametrosTrafegabilidade,
    PesosPerigos,
    criar_politica_agrishield_equip_v1,
)
from backend.risco.modelos import ModeloDominio


logger = logging.getLogger(__name__)

MENSAGEM_SOMA_PESOS_INVALIDA = "Os pesos do índice devem totalizar 100%."
MENSAGEM_SOMA_HIDRICO_INVALIDA = (
    "Os pesos internos da Exposição Hídrica devem totalizar 100%."
)
MENSAGEM_INSTABILIDADE_INVALIDA = (
    "Os fatores de ativação da Instabilidade devem estar entre 0 e 1 e não "
    "podem diminuir entre as faixas Normal → Atenção → Alerta → Crítico."
)
MENSAGEM_FOGO_INVALIDA = (
    "Os multiplicadores de secura do Incêndio devem ser maiores que zero e "
    "não podem diminuir entre as faixas."
)
MENSAGEM_TEMPESTADES_INVALIDA = (
    "A base do fator vento–chuva e a influência da chuva das Tempestades "
    "Severas devem somar 1,00."
)
MENSAGEM_TRAFEGABILIDADE_INVALIDA = (
    "Os pesos internos da Trafegabilidade devem totalizar 100% e o limiar "
    "de dia relevante deve estar entre 0 e 100."
)
MENSAGEM_ESTRUTURA_INVALIDA = (
    "Os 22 parâmetros do modelo devem ser informados, sem duplicidade."
)
MENSAGEM_CONFIGURACAO_PERSISTIDA_INVALIDA = (
    "A configuração persistida de parâmetros do modelo está inválida e não "
    "pode ser aplicada."
)

_ORDEM_ATIVACAO = ("normal", "atencao", "alerta", "critico")
_ORDEM_SECURA = ("0_1_dia", "2_3_dias", "4_6_dias", "7_mais_dias")


class ErroParametrosScoreInvalidos(ValueError):
    """Um ou mais grupos de parametros nao passaram na validacao.

    `erros` preserva quais grupos falharam e por que, para que nenhum erro
    seja mascarado por outro.
    """

    def __init__(self, erros: list[tuple[str, str]]) -> None:
        self.erros = list(erros)
        super().__init__("; ".join(mensagem for _, mensagem in self.erros))


class ErroParametrosScorePersistidosInvalidos(RuntimeError):
    """A configuracao persistida nao pode ser aplicada ao motor com seguranca."""


class ParametroModeloApresentacao(ModeloDominio):
    grupo: str = Field(min_length=1)
    indicador: str = Field(min_length=1)
    parametro: str = Field(min_length=1)
    valor_atual: float
    valor_padrao: float
    tipo: str = Field(min_length=1)
    atualizado_em: str = Field(min_length=1)


class ConfiguracaoParametrosModeloApresentacao(ModeloDominio):
    parametros: tuple[ParametroModeloApresentacao, ...] = Field(
        min_length=len(CHAVES_ESPERADAS), max_length=len(CHAVES_ESPERADAS)
    )

    @model_validator(mode="after")
    def validar(self) -> "ConfiguracaoParametrosModeloApresentacao":
        chaves = tuple(
            (item.grupo, item.indicador, item.parametro) for item in self.parametros
        )
        if chaves != CHAVES_ESPERADAS:
            raise ValueError("parametros devem conter as chaves oficiais, em ordem")
        return self


class OverridesParametrosModelo(ModeloDominio):
    """Pacote pronto para sobrescrever PoliticaExposicaoEquipamentos.

    Cada campo ja e um contrato validado do motor; a aplicacao acontece com
    um unico `politica.model_copy(update=...)`.
    """

    pesos_perigos: PesosPerigos
    parametros_territoriais_hidricos: ParametrosTerritoriaisHidricos
    parametros_instabilidade: ParametrosInstabilidade
    parametros_propagacao_fogo: ParametrosPropagacaoFogo
    parametros_tempestade: ParametrosTempestade
    parametros_trafegabilidade: ParametrosTrafegabilidade


def _mapa_valores(linhas) -> dict[ChaveParametro, float]:
    return {
        (linha["grupo"], linha["indicador"], linha["parametro"]): linha["valor_atual"]
        for linha in linhas
    }


def _construir_pesos_perigos(mapa: dict[ChaveParametro, float]) -> PesosPerigos:
    return PesosPerigos(
        exposicao_hidrica=mapa[("SCORE", "EXPOSICAO_HIDRICA", "peso")],
        trafegabilidade=mapa[("SCORE", "TRAFEGABILIDADE", "peso")],
        instabilidade=mapa[("SCORE", "INSTABILIDADE", "peso")],
        incendio=mapa[("SCORE", "INCENDIO", "peso")],
        tempestades=mapa[("SCORE", "TEMPESTADES", "peso")],
    )


def _construir_territoriais(
    mapa: dict[ChaveParametro, float],
) -> ParametrosTerritoriaisHidricos:
    dados = (
        criar_politica_agrishield_equip_v1().parametros_territoriais_hidricos.model_dump()
    )
    dados["peso_proximidade_drenagem"] = mapa[
        ("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem")
    ]
    dados["peso_area_montante"] = mapa[
        ("EXPOSICAO_HIDRICA", "T3", "relevancia_area_montante")
    ]
    dados["peso_posicao_topografica"] = mapa[
        ("EXPOSICAO_HIDRICA", "T3", "posicao_topografica")
    ]
    return ParametrosTerritoriaisHidricos(**dados)


def _construir_instabilidade(
    mapa: dict[ChaveParametro, float], base_instabilidade: ParametrosInstabilidade
) -> ParametrosInstabilidade:
    faixas = tuple(
        FaixaAtivacaoHidrica(
            inicio_indice_hidrico=faixa.inicio_indice_hidrico,
            fator_ativacao=mapa[("INSTABILIDADE", "ATIVACAO", nome)],
        )
        for faixa, nome in zip(
            base_instabilidade.faixas_ativacao_hidrica, _ORDEM_ATIVACAO
        )
    )
    return ParametrosInstabilidade(
        curva_declividade=base_instabilidade.curva_declividade,
        faixas_ativacao_hidrica=faixas,
    )


def _construir_fogo(
    mapa: dict[ChaveParametro, float], base_fogo: ParametrosPropagacaoFogo
) -> ParametrosPropagacaoFogo:
    faixas = tuple(
        FaixaSecuraAntecedente(
            inicio_dias=faixa.inicio_dias,
            multiplicador=mapa[("INCENDIO", "SECURA", nome)],
        )
        for faixa, nome in zip(base_fogo.faixas_secura_antecedente, _ORDEM_SECURA)
    )
    return ParametrosPropagacaoFogo(
        curva_temperatura_maxima=base_fogo.curva_temperatura_maxima,
        curva_baixa_umidade_media=base_fogo.curva_baixa_umidade_media,
        curva_velocidade_vento_media=base_fogo.curva_velocidade_vento_media,
        faixas_secura_antecedente=faixas,
    )


def _construir_tempestade(
    mapa: dict[ChaveParametro, float], base_tempestade: ParametrosTempestade
) -> ParametrosTempestade:
    return ParametrosTempestade(
        curva_precipitacao_d0=base_tempestade.curva_precipitacao_d0,
        peso_base_vento=mapa[("TEMPESTADES", "VENTO_CHUVA", "base")],
        peso_amplificacao_chuva=mapa[
            ("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva")
        ],
    )


def _construir_trafegabilidade(
    mapa: dict[ChaveParametro, float],
) -> ParametrosTrafegabilidade:
    return ParametrosTrafegabilidade(
        peso_dia=mapa[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")],
        peso_acumulado=mapa[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")],
        peso_recuperacao=mapa[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")],
        limiar_relevancia=mapa[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")],
    )


def obter_configuracao_parametros_modelo() -> ConfiguracaoParametrosModeloApresentacao:
    """Le a configuracao persistida, inicializando os defaults se necessario."""

    linhas = carregar_linhas_parametros_modelo()
    return ConfiguracaoParametrosModeloApresentacao(
        parametros=tuple(ParametroModeloApresentacao(**linha) for linha in linhas)
    )


def carregar_overrides_parametros_modelo() -> OverridesParametrosModelo:
    """Le a configuracao persistida como o contrato que o motor consome."""

    try:
        linhas = carregar_linhas_parametros_modelo()
    except ErroRepositorioParametrosModeloCorrompido as exc:
        raise ErroParametrosScorePersistidosInvalidos(
            MENSAGEM_CONFIGURACAO_PERSISTIDA_INVALIDA
        ) from exc

    mapa = _mapa_valores(linhas)
    base = criar_politica_agrishield_equip_v1()
    try:
        return OverridesParametrosModelo(
            pesos_perigos=_construir_pesos_perigos(mapa),
            parametros_territoriais_hidricos=_construir_territoriais(mapa),
            parametros_instabilidade=_construir_instabilidade(
                mapa, base.parametros_instabilidade
            ),
            parametros_propagacao_fogo=_construir_fogo(
                mapa, base.parametros_propagacao_fogo
            ),
            parametros_tempestade=_construir_tempestade(
                mapa, base.parametros_tempestade
            ),
            parametros_trafegabilidade=_construir_trafegabilidade(mapa),
        )
    except ValidationError as exc:
        logger.error(
            "configuracao persistida de parametros do modelo nao passa nas "
            "regras do dominio",
            exc_info=True,
        )
        raise ErroParametrosScorePersistidosInvalidos(
            MENSAGEM_CONFIGURACAO_PERSISTIDA_INVALIDA
        ) from exc


def salvar_configuracao_parametros_modelo(
    valores: dict[ChaveParametro, float],
) -> ConfiguracaoParametrosModeloApresentacao:
    """Valida cada grupo separadamente e persiste atomicamente os 22 valores.

    Os valores nao sao normalizados automaticamente: o analista precisa saber
    exatamente quais numeros serao usados, entao uma configuracao invalida e
    rejeitada em vez de ajustada silenciosamente. Nenhum grupo valido e
    descartado por causa de outro grupo invalido: todos sao verificados e
    todos os erros encontrados sao reportados juntos.
    """

    if set(valores) != set(CHAVES_ESPERADAS):
        raise ErroParametrosScoreInvalidos([("ESTRUTURA", MENSAGEM_ESTRUTURA_INVALIDA)])
    for valor in valores.values():
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise ErroParametrosScoreInvalidos(
                [("ESTRUTURA", MENSAGEM_ESTRUTURA_INVALIDA)]
            )
        if not math.isfinite(valor):
            raise ErroParametrosScoreInvalidos(
                [("ESTRUTURA", MENSAGEM_ESTRUTURA_INVALIDA)]
            )

    base = criar_politica_agrishield_equip_v1()
    erros: list[tuple[str, str]] = []

    try:
        _construir_pesos_perigos(valores)
    except ValidationError:
        erros.append(("SCORE", MENSAGEM_SOMA_PESOS_INVALIDA))
    try:
        _construir_territoriais(valores)
    except ValidationError:
        erros.append(("EXPOSICAO_HIDRICA", MENSAGEM_SOMA_HIDRICO_INVALIDA))
    try:
        _construir_instabilidade(valores, base.parametros_instabilidade)
    except ValidationError:
        erros.append(("INSTABILIDADE", MENSAGEM_INSTABILIDADE_INVALIDA))
    try:
        _construir_fogo(valores, base.parametros_propagacao_fogo)
    except ValidationError:
        erros.append(("INCENDIO", MENSAGEM_FOGO_INVALIDA))
    try:
        _construir_tempestade(valores, base.parametros_tempestade)
    except ValidationError:
        erros.append(("TEMPESTADES", MENSAGEM_TEMPESTADES_INVALIDA))
    try:
        _construir_trafegabilidade(valores)
    except ValidationError:
        erros.append(("TRAFEGABILIDADE", MENSAGEM_TRAFEGABILIDADE_INVALIDA))

    if erros:
        raise ErroParametrosScoreInvalidos(erros)

    salvar_parametros_modelo({chave: float(valor) for chave, valor in valores.items()})
    return obter_configuracao_parametros_modelo()


__all__ = [
    "MENSAGEM_CONFIGURACAO_PERSISTIDA_INVALIDA",
    "MENSAGEM_ESTRUTURA_INVALIDA",
    "MENSAGEM_FOGO_INVALIDA",
    "MENSAGEM_INSTABILIDADE_INVALIDA",
    "MENSAGEM_SOMA_HIDRICO_INVALIDA",
    "MENSAGEM_SOMA_PESOS_INVALIDA",
    "MENSAGEM_TEMPESTADES_INVALIDA",
    "MENSAGEM_TRAFEGABILIDADE_INVALIDA",
    "ConfiguracaoParametrosModeloApresentacao",
    "ErroParametrosScoreInvalidos",
    "ErroParametrosScorePersistidosInvalidos",
    "OverridesParametrosModelo",
    "ParametroModeloApresentacao",
    "carregar_overrides_parametros_modelo",
    "obter_configuracao_parametros_modelo",
    "salvar_configuracao_parametros_modelo",
]
