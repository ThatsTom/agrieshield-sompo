"""Persistencia CSV generica dos parametros configuraveis do modelo AgriShield-EQUIP.

Isola o mecanismo de armazenamento para que o motor de score e os perigos
nunca dependam de como os parametros sao guardados: backend/exposicao/*.py
conhece apenas os contratos PesosPerigos, ParametrosTerritoriaisHidricos,
ParametrosInstabilidade, ParametrosPropagacaoFogo e ParametrosTempestade, ja
validados pela camada de aplicacao (backend/app/servico_parametros_score.py).
Se no futuro este repositorio for substituido por um banco (ex.: Supabase),
apenas este modulo precisa mudar.

A tabela e generica (grupo/indicador/parametro) para nao exigir um CSV novo a
cada vez que um perigo ganhar um coeficiente configuravel.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import logging
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4


logger = logging.getLogger(__name__)

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
ARQUIVO_PARAMETROS_SCORE = PASTA_DADOS / "parametros_score.csv"

COLUNAS_PARAMETROS_MODELO = [
    "grupo",
    "indicador",
    "parametro",
    "valor_atual",
    "valor_padrao",
    "tipo",
    "atualizado_em",
]

ChaveParametro = Tuple[str, str, str]

# Fonte unica dos defaults do modelo: (grupo, indicador, parametro, valor_padrao, tipo).
# "percentual" = soma obrigatoria de 100% dentro do grupo; "fator" = coeficiente
# decimal validado pela propria regra do dominio (ex.: monotonicidade, faixa 0..1).
PARAMETROS_MODELO_PADRAO: Tuple[Tuple[str, str, str, float, str], ...] = (
    ("SCORE", "EXPOSICAO_HIDRICA", "peso", 0.30, "percentual"),
    ("SCORE", "TRAFEGABILIDADE", "peso", 0.25, "percentual"),
    ("SCORE", "INSTABILIDADE", "peso", 0.20, "percentual"),
    ("SCORE", "INCENDIO", "peso", 0.15, "percentual"),
    ("SCORE", "TEMPESTADES", "peso", 0.10, "percentual"),
    ("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem", 0.40, "percentual"),
    ("EXPOSICAO_HIDRICA", "T3", "relevancia_area_montante", 0.35, "percentual"),
    ("EXPOSICAO_HIDRICA", "T3", "posicao_topografica", 0.25, "percentual"),
    ("INSTABILIDADE", "ATIVACAO", "normal", 0.00, "fator"),
    ("INSTABILIDADE", "ATIVACAO", "atencao", 0.35, "fator"),
    ("INSTABILIDADE", "ATIVACAO", "alerta", 0.65, "fator"),
    ("INSTABILIDADE", "ATIVACAO", "critico", 1.00, "fator"),
    ("INCENDIO", "SECURA", "0_1_dia", 0.90, "fator"),
    ("INCENDIO", "SECURA", "2_3_dias", 1.00, "fator"),
    ("INCENDIO", "SECURA", "4_6_dias", 1.05, "fator"),
    ("INCENDIO", "SECURA", "7_mais_dias", 1.10, "fator"),
    ("TEMPESTADES", "VENTO_CHUVA", "base", 0.75, "fator"),
    ("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva", 0.25, "fator"),
    ("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia", 0.35, "percentual"),
    ("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado", 0.45, "percentual"),
    ("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao", 0.20, "percentual"),
    ("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia", 25, "fator"),
)

CHAVES_ESPERADAS: Tuple[ChaveParametro, ...] = tuple(
    (grupo, indicador, parametro)
    for grupo, indicador, parametro, _, _ in PARAMETROS_MODELO_PADRAO
)
_TIPO_POR_CHAVE: Dict[ChaveParametro, str] = {
    (grupo, indicador, parametro): tipo
    for grupo, indicador, parametro, _, tipo in PARAMETROS_MODELO_PADRAO
}
_PADRAO_POR_CHAVE: Dict[ChaveParametro, float] = {
    (grupo, indicador, parametro): padrao
    for grupo, indicador, parametro, padrao, _ in PARAMETROS_MODELO_PADRAO
}


class ErroRepositorioParametrosModeloCorrompido(RuntimeError):
    """O CSV de parametros existe, mas esta estruturalmente invalido.

    Nunca deve ser tratado como "usar defaults silenciosamente": quem chama
    este repositorio precisa propagar o erro, nao inventar zeros.
    """


def _chave(linha: Dict[str, Any]) -> ChaveParametro:
    return (linha["grupo"], linha["indicador"], linha["parametro"])


def _escrever_parametros(valores_atuais: Dict[ChaveParametro, float]) -> None:
    agora = datetime.now(timezone.utc).isoformat()
    linhas = [
        {
            "grupo": grupo,
            "indicador": indicador,
            "parametro": parametro,
            "valor_atual": str(valores_atuais[(grupo, indicador, parametro)]),
            "valor_padrao": str(padrao),
            "tipo": tipo,
            "atualizado_em": agora,
        }
        for grupo, indicador, parametro, padrao, tipo in PARAMETROS_MODELO_PADRAO
    ]
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    temporario = ARQUIVO_PARAMETROS_SCORE.with_name(
        f".{ARQUIVO_PARAMETROS_SCORE.name}.{uuid4().hex}.tmp"
    )
    try:
        with open(temporario, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=COLUNAS_PARAMETROS_MODELO, delimiter=";"
            )
            writer.writeheader()
            writer.writerows(linhas)
        os.replace(temporario, ARQUIVO_PARAMETROS_SCORE)
    finally:
        if temporario.exists():
            temporario.unlink()


def criar_base_parametros_score_se_nao_existir() -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    if ARQUIVO_PARAMETROS_SCORE.exists():
        return
    _escrever_parametros(
        dict(zip(CHAVES_ESPERADAS, (p for *_, p, _ in PARAMETROS_MODELO_PADRAO)))
    )


def _validar_estrutura(linhas: List[Dict[str, Any]]) -> Dict[ChaveParametro, float]:
    """Confere que o arquivo contem exatamente os parametros esperados.

    Nao aceita linhas a mais, a menos, duplicadas ou com valor nao numerico:
    qualquer uma dessas condicoes e tratada como corrupcao estrutural, nunca
    como "usar o default para essa linha".
    """

    valores: Dict[ChaveParametro, float] = {}
    for linha in linhas:
        try:
            chave = _chave(linha)
        except KeyError as exc:
            raise ErroRepositorioParametrosModeloCorrompido(
                f"linha sem coluna obrigatoria: {exc}"
            ) from exc
        if chave not in _TIPO_POR_CHAVE:
            raise ErroRepositorioParametrosModeloCorrompido(
                f"parametro desconhecido no arquivo: {chave}"
            )
        if chave in valores:
            raise ErroRepositorioParametrosModeloCorrompido(
                f"parametro duplicado no arquivo: {chave}"
            )
        bruto = linha.get("valor_atual")
        try:
            valor = float(bruto)
        except (TypeError, ValueError) as exc:
            raise ErroRepositorioParametrosModeloCorrompido(
                f"valor_atual invalido para {chave}: {bruto!r}"
            ) from exc
        if isinstance(bruto, bool) or not math.isfinite(valor):
            raise ErroRepositorioParametrosModeloCorrompido(
                f"valor_atual nao finito para {chave}: {bruto!r}"
            )
        valores[chave] = valor
    faltantes = set(CHAVES_ESPERADAS) - set(valores)
    if faltantes:
        raise ErroRepositorioParametrosModeloCorrompido(
            f"parametros ausentes no arquivo: {sorted(faltantes)}"
        )
    return valores


def carregar_linhas_parametros_modelo() -> List[Dict[str, Any]]:
    """Le, valida estruturalmente e devolve as 22 linhas na ordem oficial.

    `valor_padrao` sempre vem da constante `PARAMETROS_MODELO_PADRAO` (nunca do
    arquivo), garantindo uma unica fonte de verdade para os defaults mesmo que
    o arquivo tenha sido editado manualmente.
    """

    criar_base_parametros_score_se_nao_existir()
    with open(ARQUIVO_PARAMETROS_SCORE, "r", encoding="utf-8-sig", newline="") as f:
        brutas = list(csv.DictReader(f, delimiter=";"))
    try:
        valores = _validar_estrutura(brutas)
    except ErroRepositorioParametrosModeloCorrompido:
        logger.error(
            "arquivo de parametros do modelo estruturalmente invalido: %s",
            ARQUIVO_PARAMETROS_SCORE,
            exc_info=True,
        )
        raise
    por_chave = {_chave(linha): linha for linha in brutas}
    return [
        {
            "grupo": grupo,
            "indicador": indicador,
            "parametro": parametro,
            "valor_atual": valores[(grupo, indicador, parametro)],
            "valor_padrao": padrao,
            "tipo": tipo,
            "atualizado_em": por_chave[(grupo, indicador, parametro)]["atualizado_em"],
        }
        for grupo, indicador, parametro, padrao, tipo in PARAMETROS_MODELO_PADRAO
    ]


def salvar_parametros_modelo(
    valores: Dict[ChaveParametro, float]
) -> List[Dict[str, Any]]:
    """Substitui atomicamente a configuracao vigente pelos valores informados."""

    if set(valores) != set(CHAVES_ESPERADAS):
        raise ValueError("valores devem informar exatamente os parametros esperados")
    _escrever_parametros(valores)
    return carregar_linhas_parametros_modelo()


__all__ = [
    "ARQUIVO_PARAMETROS_SCORE",
    "CHAVES_ESPERADAS",
    "COLUNAS_PARAMETROS_MODELO",
    "PARAMETROS_MODELO_PADRAO",
    "ChaveParametro",
    "ErroRepositorioParametrosModeloCorrompido",
    "carregar_linhas_parametros_modelo",
    "criar_base_parametros_score_se_nao_existir",
    "salvar_parametros_modelo",
]
