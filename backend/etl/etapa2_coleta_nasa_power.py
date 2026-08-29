# =============================================================================
# AgriShield — Etapa 2: coleta NASA POWER -> CSV bruto
#
# A função coletar_nasa_power(lat, lon, inicio, fim) consulta a API pública NASA
# POWER. Se a internet estiver indisponível, usa uma série simulada realista e
# determinística para a região de Mato Grosso, mantendo o protótipo funcional.
# =============================================================================

from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
import requests

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
PASTA_DADOS.mkdir(parents=True, exist_ok=True)

PARAMETROS = "T2M,T2M_MAX,T2M_MIN,PRECTOTCORR,RH2M,ALLSKY_SFC_SW_DWN,WS2M"
RENOMEAR = {
    "T2M": "temp_media_c",
    "T2M_MAX": "temp_maxima_c",
    "T2M_MIN": "temp_minima_c",
    "PRECTOTCORR": "precipitacao_mm",
    "RH2M": "umidade_relativa_pct",
    "ALLSKY_SFC_SW_DWN": "radiacao_solar_mj",
    "WS2M": "vento_ms",
}
COLUNAS_NUMERICAS = list(RENOMEAR.values())
SENTINELA = -999.0


def _montar_url(lat: float, lon: float, inicio: str, fim: str) -> str:
    return (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters={PARAMETROS}"
        "&community=AG"
        f"&longitude={lon}"
        f"&latitude={lat}"
        f"&start={inicio}"
        f"&end={fim}"
        "&format=JSON"
    )


def _parse_nasa_json(dados_json: dict) -> pd.DataFrame:
    parametros = dados_json["properties"]["parameter"]
    registros = {}
    for nome_param, serie in parametros.items():
        for data_str, valor in serie.items():
            registros.setdefault(data_str, {})[nome_param] = valor

    df = pd.DataFrame.from_dict(registros, orient="index")
    df.index.name = "data_raw"
    df = df.reset_index()
    df["data"] = pd.to_datetime(df["data_raw"], format="%Y%m%d")
    df["ano"] = df["data"].dt.year
    df["mes"] = df["data"].dt.month
    df["dia"] = df["data"].dt.day
    df = df.drop(columns=["data_raw"]).rename(columns=RENOMEAR)

    for col in COLUNAS_NUMERICAS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").replace(SENTINELA, pd.NA)

    return df.sort_values("data").reset_index(drop=True)


def _simular_serie(lat: float, lon: float, inicio: str, fim: str) -> pd.DataFrame:
    d0 = datetime.strptime(inicio, "%Y%m%d")
    d1 = datetime.strptime(fim, "%Y%m%d")
    total_dias = (d1 - d0).days + 1
    rng = np.random.default_rng(seed=int(abs(lat * 1000) + abs(lon * 1000)))

    linhas = []
    for i in range(total_dias):
        dt = d0 + timedelta(days=i)
        estacao_chuvosa = dt.month in (11, 12, 1, 2, 3, 4)
        prob_chuva = 0.62 if estacao_chuvosa else 0.22
        chove = rng.random() < prob_chuva
        precip = float(max(0.0, rng.gamma(2.0, 8.5))) if chove else 0.0
        # injeta alguns eventos críticos para a tela demonstrar alertas
        if i in (total_dias - 8, total_dias - 4):
            precip += float(rng.uniform(22, 38))

        temp_media = 26 + rng.normal(0, 1.8) + (1.5 if estacao_chuvosa else -0.5)
        temp_max = temp_media + rng.uniform(4.5, 8.5)
        temp_min = temp_media - rng.uniform(4.0, 7.5)
        umidade = (77 if estacao_chuvosa else 56) + rng.normal(0, 7)
        umidade = min(100, max(20, float(umidade)))
        radiacao = max(8, float(rng.normal(19 if estacao_chuvosa else 23, 3)))
        vento = max(0.2, float(rng.normal(2.3, 0.7)))

        linhas.append(
            {
                "data": dt,
                "ano": dt.year,
                "mes": dt.month,
                "dia": dt.day,
                "temp_media_c": round(temp_media, 2),
                "temp_maxima_c": round(temp_max, 2),
                "temp_minima_c": round(temp_min, 2),
                "precipitacao_mm": round(precip, 2),
                "umidade_relativa_pct": round(umidade, 2),
                "radiacao_solar_mj": round(radiacao, 2),
                "vento_ms": round(vento, 2),
            }
        )
    return pd.DataFrame(linhas)


def coletar_nasa_power(
    lat: float,
    lon: float,
    inicio: str,
    fim: str,
    salvar_csv: bool = True,
    id_fazenda: str | None = None,
) -> Tuple[pd.DataFrame, str]:
    """Retorna (DataFrame, origem), onde origem é 'nasa_power' ou 'simulado'."""
    origem = "nasa_power"
    try:
        resp = requests.get(_montar_url(lat, lon, inicio, fim), timeout=(5, 30))
        resp.raise_for_status()
        df = _parse_nasa_json(resp.json())
    except Exception as exc:
        print(
            f"[aviso] NASA POWER indisponível ({type(exc).__name__}). Usando série simulada."
        )
        df = _simular_serie(float(lat), float(lon), inicio, fim)
        origem = "simulado"

    if salvar_csv:
        sufixo = f"_{id_fazenda}" if id_fazenda else ""
        arq = PASTA_DADOS / f"nasa_power_bruto{sufixo}.csv"
        df.to_csv(arq, index=False, encoding="utf-8-sig", sep=";", decimal=",")
        print(f"CSV bruto salvo: {arq.name} | registros={len(df)} | origem={origem}")
    return df, origem


if __name__ == "__main__":
    print("AgriShield — Etapa 2: coleta NASA POWER")
    fim = datetime.now()
    inicio = fim - timedelta(days=40)
    df, origem = coletar_nasa_power(
        lat=-12.5450,
        lon=-55.7210,
        inicio=inicio.strftime("%Y%m%d"),
        fim=fim.strftime("%Y%m%d"),
        salvar_csv=True,
        id_fazenda="1",
    )
    print("Origem:", origem)
    print(df.tail().to_string(index=False))
