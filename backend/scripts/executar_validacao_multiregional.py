"""CLI explícita do TESTE_DE_MESA multi-regional; não é endpoint de produção."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from backend.validacao import (
    ExecutorValidacaoMultiregional,
    carregar_cenarios,
    salvar_relatorios,
)


BASE = Path(__file__).resolve().parents[1]
CENARIOS_PADRAO = BASE / "validacao" / "cenarios_multiregionais.json"
SAIDA_PADRAO = BASE / "data" / "validacao"


def _data(texto: str) -> date:
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use data no formato YYYY-MM-DD") from exc


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa validação multi-regional sequencial e observacional."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--todos", action="store_true", help="executa todos os fixtures")
    grupo.add_argument(
        "--cenario",
        action="append",
        dest="cenarios",
        help="id_cenario a executar; pode ser repetido",
    )
    parser.add_argument("--arquivo-cenarios", type=Path, default=CENARIOS_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    parser.add_argument(
        "--data-referencia",
        type=_data,
        default=date.today() - timedelta(days=1),
        help="data final NASA/INMET (default: ontem)",
    )
    parser.add_argument("--ano-mapbiomas", type=int, default=2024)
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = criar_parser().parse_args(argv)
    cenarios = carregar_cenarios(argumentos.arquivo_cenarios)
    if argumentos.cenarios:
        solicitados = set(argumentos.cenarios)
        cenarios = [item for item in cenarios if item.id_cenario in solicitados]
        encontrados = {item.id_cenario for item in cenarios}
        ausentes = sorted(solicitados - encontrados)
        if ausentes:
            raise SystemExit(f"Cenários não encontrados: {', '.join(ausentes)}")
    execucao = ExecutorValidacaoMultiregional().executar(
        cenarios,
        data_referencia=argumentos.data_referencia,
        ano_mapbiomas=argumentos.ano_mapbiomas,
    )
    json_path, csv_path = salvar_relatorios(execucao, argumentos.saida)
    print(f"VALIDACAO concluída: {len(cenarios)} cenário(s)")
    for resultado in execucao["resultados"]:
        fontes = ", ".join(
            f"{nome}={dados['status']}" for nome, dados in resultado["fontes"].items()
        )
        print(
            f"- {resultado['id_cenario']}: {resultado['status_execucao']} | "
            f"{resultado['duracoes_ms']['total_ms']} ms | {fontes}"
        )
    print(f"JSON: {json_path}")
    print(f"CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
