"""Teste simples e explícito da conexão pública com a NASA POWER."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "etl"))

from etapa2_coleta_nasa_power import COLUNAS_NUMERICAS, coletar_nasa_power  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Testa a API pública NASA POWER")
    parser.add_argument("--latitude", type=float, default=-12.545)
    parser.add_argument("--longitude", type=float, default=-55.721)
    parser.add_argument("--dias", type=int, default=7)
    args = parser.parse_args()
    if not 1 <= args.dias <= 366:
        parser.error("--dias deve estar entre 1 e 366")

    # A grade near-real-time pode publicar os dias mais recentes ainda com a
    # sentinela -999. Um pequeno atraso torna o teste de conectividade estável.
    fim = datetime.now() - timedelta(days=10)
    inicio = fim - timedelta(days=args.dias - 1)
    dados, origem = coletar_nasa_power(
        lat=args.latitude,
        lon=args.longitude,
        inicio=inicio.strftime("%Y%m%d"),
        fim=fim.strftime("%Y%m%d"),
        salvar_csv=False,
    )

    colunas_climaticas = [coluna for coluna in COLUNAS_NUMERICAS if coluna in dados]
    tem_medicao = bool(colunas_climaticas) and bool(
        dados[colunas_climaticas].notna().any().any()
    )
    if origem != "nasa_power":
        print("[ERRO] A NASA POWER não respondeu; o coletor usou dados simulados.")
        print("Verifique internet, proxy/firewall e tente novamente.")
        return 2
    if not tem_medicao:
        print("[ERRO] A NASA POWER respondeu, mas sem medições disponíveis.")
        print("Tente novamente ou use um intervalo mais antigo.")
        return 2

    print("[OK] NASA POWER acessível sem chave ou login.")
    print(f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}")
    print(f"Coordenadas: {args.latitude}, {args.longitude}")
    print(f"Registros recebidos: {len(dados)}")
    print(dados.tail(min(3, len(dados))).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
