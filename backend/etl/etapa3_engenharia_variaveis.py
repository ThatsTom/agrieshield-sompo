# =============================================================================
# AgriShield — Etapa 3: engenharia de variáveis + critérios de risco
#
# Entrada : DataFrame bruto da Etapa 2.
# Saídas  : CSV enriquecido, CSV consolidado para dashboard e objetos JSON para API.
# Critérios demonstrados:
#   - chuva acumulada em 7 dias
#   - solo encharcado
#   - condição operacional atual
#   - score 0-100 explicável
#   - risco de alagamento combinando NASA POWER + previsão Open-Meteo
# =============================================================================

from pathlib import Path
from typing import Any, Dict, List, Optional
import json

import pandas as pd

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
PASTA_DADOS.mkdir(parents=True, exist_ok=True)

COLUNAS_NUMERICAS = [
    "temp_media_c",
    "temp_maxima_c",
    "temp_minima_c",
    "precipitacao_mm",
    "umidade_relativa_pct",
    "radiacao_solar_mj",
    "vento_ms",
]


def classificar_risco_agroclimatico(row: pd.Series) -> str:
    """Regra simples, transparente e explicável para o protótipo."""
    precip = float(row["precipitacao_mm"])
    temp_max = float(row["temp_maxima_c"])
    umidade = float(row["umidade_relativa_pct"])

    if precip < 1.0 and (temp_max > 40.0 or umidade < 30.0):
        return "Crítico"
    if precip < 5.0 or temp_max >= 38.0 or umidade < 40.0:
        return "Alerta"
    if precip < 20.0 or temp_max >= 35.0 or umidade < 60.0:
        return "Atenção"
    return "Normal"


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["data"] = pd.to_datetime(df["data"])

    for col in COLUNAS_NUMERICAS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].median())

    df["precipitacao_mm"] = df["precipitacao_mm"].clip(lower=0.0)

    contador = 0
    sequencia = []
    for precip in df["precipitacao_mm"]:
        contador = contador + 1 if precip < 1.0 else 0
        sequencia.append(contador)
    df["dias_sem_chuva_consecutivos"] = sequencia

    bins = [-1, 3, 7, 14, 21, float("inf")]
    labels = [
        "0-3 dias (baixa persistência)",
        "4-7 dias (estiagem curta)",
        "8-14 dias (estiagem moderada)",
        "15-21 dias (estiagem prolongada)",
        ">=22 dias (estiagem severa)",
    ]
    df["faixa_dias_sem_chuva"] = pd.cut(
        df["dias_sem_chuva_consecutivos"], bins=bins, labels=labels
    )
    df["nivel_risco_agroclimatico"] = df.apply(classificar_risco_agroclimatico, axis=1)
    df["chuva_acumulada_7d"] = (
        df["precipitacao_mm"].rolling(window=7, min_periods=1).sum().round(1)
    )
    df["chuva_acumulada_3d"] = (
        df["precipitacao_mm"].rolling(window=3, min_periods=1).sum().round(1)
    )
    df["umidade_media_3d"] = (
        df["umidade_relativa_pct"].rolling(window=3, min_periods=1).mean().round(1)
    )
    df["solo_encharcado"] = (df["chuva_acumulada_7d"] > 50.0) & (
        df["umidade_media_3d"] > 70.0
    )

    def condicao(row: pd.Series) -> str:
        if bool(row["solo_encharcado"]) or row["nivel_risco_agroclimatico"] in (
            "Crítico",
            "Alerta",
        ):
            return "Restrição"
        if row["nivel_risco_agroclimatico"] == "Atenção":
            return "Atenção"
        return "Ideais"

    df["condicao_operacional"] = df.apply(condicao, axis=1)
    return df


def _calcular_score(
    ultimo: pd.Series, tipo_operacao: str, proximidade_agua: bool
) -> tuple[int, List[Dict[str, Any]]]:
    fatores = []
    score = 0.0

    chuva7 = float(ultimo["chuva_acumulada_7d"])
    if chuva7 > 80:
        pontos, impacto = 30, "Alto impacto"
    elif chuva7 > 50:
        pontos, impacto = 22, "Alto impacto"
    elif chuva7 > 25:
        pontos, impacto = 12, "Médio impacto"
    else:
        pontos, impacto = 4, "Baixo impacto"
    score += pontos
    fatores.append(
        {
            "fator": "Chuva acumulada (7 dias)",
            "detalhe": f"{chuva7:.0f} mm nos últimos 7 dias",
            "impacto": impacto,
            "pontos": pontos,
        }
    )

    umid3 = float(ultimo["umidade_media_3d"])
    if bool(ultimo["solo_encharcado"]) or umid3 > 85:
        pontos, impacto, detalhe = 28, "Alto impacto", "Solo encharcado"
    elif umid3 > 70:
        pontos, impacto, detalhe = 16, "Médio impacto", "Umidade elevada do solo"
    else:
        pontos, impacto, detalhe = 5, "Baixo impacto", "Umidade dentro do normal"
    score += pontos
    fatores.append(
        {
            "fator": "Umidade do solo",
            "detalhe": detalhe,
            "impacto": impacto,
            "pontos": pontos,
        }
    )

    if proximidade_agua:
        pontos, impacto = (22, "Alto impacto") if chuva7 > 50 else (12, "Médio impacto")
        detalhe = "Áreas de risco a até 1 km"
    else:
        pontos, impacto, detalhe = 2, "Baixo impacto", "Sem áreas alagáveis próximas"
    score += pontos
    fatores.append(
        {
            "fator": "Proximidade de áreas alagáveis",
            "detalhe": detalhe,
            "impacto": impacto,
            "pontos": pontos,
        }
    )

    # Fator 4: condição agroclimática do dia (restrição operacional imediata)
    nivel = str(ultimo.get("nivel_risco_agroclimatico", "Normal"))
    if nivel in ("Crítico", "Alerta"):
        pontos, impacto = 35, "Alto impacto"
        detalhe = f"Nível agroclimático atual: {nivel}"
    elif nivel == "Atenção":
        pontos, impacto = 15, "Médio impacto"
        detalhe = "Nível agroclimático atual: Atenção"
    else:
        pontos, impacto = 0, "Baixo impacto"
        detalhe = "Nível agroclimático atual: Normal"
    if pontos:
        score += pontos
        fatores.append(
            {
                "fator": "Condição agroclimática do dia",
                "detalhe": detalhe,
                "impacto": impacto,
                "pontos": pontos,
            }
        )

    if str(tipo_operacao).lower() == "transporte":
        ajuste = 10 if chuva7 > 25 else 4
        score += ajuste
        fatores.append(
            {
                "fator": "Tipo de operação: transporte",
                "detalhe": "Deslocamento sensível a condições de pista",
                "impacto": "Médio impacto" if ajuste >= 8 else "Baixo impacto",
                "pontos": ajuste,
            }
        )

    score_final = int(min(100, round(score)))
    return score_final, sorted(fatores, key=lambda f: f["pontos"], reverse=True)


def consolidar_para_dashboard(
    df: pd.DataFrame, tipo_operacao: str = "campo", proximidade_agua: bool = False
) -> Dict[str, Any]:
    df = df.sort_values("data").reset_index(drop=True)
    ultimo = df.iloc[-1]
    janela = df.tail(30)
    dist = janela["condicao_operacional"].value_counts()
    total = int(len(janela))
    score, fatores = _calcular_score(ultimo, tipo_operacao, proximidade_agua)

    if score >= 60:
        condicao_atual = "RESTRIÇÃO"
    elif score >= 35:
        condicao_atual = "ATENÇÃO"
    else:
        condicao_atual = "IDEAIS"

    return {
        "score": score,
        "condicao_atual": condicao_atual,
        "data_referencia": str(pd.to_datetime(ultimo["data"]).date()),
        "distribuicao_30d": {
            "ideais": int(dist.get("Ideais", 0)),
            "atencao": int(dist.get("Atenção", 0)),
            "restricao": int(dist.get("Restrição", 0)),
            "total": total,
        },
        "fatores_risco": fatores,
        "metricas_dia": {
            "chuva_acumulada_7d": float(ultimo["chuva_acumulada_7d"]),
            "chuva_acumulada_3d": float(ultimo["chuva_acumulada_3d"]),
            "umidade_media_3d": float(ultimo["umidade_media_3d"]),
            "umidade_relativa_pct": float(ultimo["umidade_relativa_pct"]),
            "precipitacao_mm": float(ultimo["precipitacao_mm"]),
            "temp_maxima_c": float(ultimo["temp_maxima_c"]),
            "solo_encharcado": bool(ultimo["solo_encharcado"]),
            "dias_sem_chuva": int(ultimo["dias_sem_chuva_consecutivos"]),
        },
    }


def avaliar_risco_alagamento(
    resumo: Dict[str, Any], previsao_dias: List[Dict[str, Any]], proximidade_agua: bool
) -> Optional[Dict[str, str]]:
    """Regra simples combinando NASA POWER (solo/chuva recente) + Open-Meteo (chuva futura)."""
    metricas = resumo.get("metricas_dia", {})
    chuva7 = float(metricas.get("chuva_acumulada_7d", 0))
    solo_encharcado = bool(metricas.get("solo_encharcado", False))
    chuva_prevista_5d = sum(float(d.get("precipitacao_mm") or 0) for d in previsao_dias)
    maior_chuva_dia = max(
        [float(d.get("precipitacao_mm") or 0) for d in previsao_dias] or [0]
    )

    pontos = 0
    pontos += 35 if proximidade_agua else 5
    pontos += 30 if solo_encharcado else 0
    pontos += 20 if chuva7 > 50 else (10 if chuva7 > 25 else 0)
    pontos += (
        15
        if chuva_prevista_5d > 45 or maior_chuva_dia > 30
        else (8 if chuva_prevista_5d > 25 else 0)
    )

    if pontos >= 70:
        return {
            "tipo": "Risco de alagamento",
            "severidade": "Alta",
            "detalhe": f"Chuva 7d={chuva7:.0f} mm; previsão 5d={chuva_prevista_5d:.0f} mm",
            "data": "próximos 5 dias",
        }
    if pontos >= 45:
        return {
            "tipo": "Risco de alagamento",
            "severidade": "Média",
            "detalhe": f"Chuva 7d={chuva7:.0f} mm; previsão 5d={chuva_prevista_5d:.0f} mm",
            "data": "próximos 5 dias",
        }
    return None


def salvar_enriquecido_csv(df: pd.DataFrame, id_fazenda: str) -> Path:
    arq = PASTA_DADOS / f"nasa_power_enriquecido_{id_fazenda}.csv"
    df.to_csv(arq, index=False, encoding="utf-8-sig", sep=";", decimal=",")
    return arq


def salvar_dashboard_csv(
    id_fazenda: str, resumo: Dict[str, Any], origem_dados: str
) -> Path:
    arq = PASTA_DADOS / f"dashboard_indicadores_{id_fazenda}.csv"
    linha = {
        "id_fazenda": id_fazenda,
        "data_referencia": resumo.get("data_referencia"),
        "score": resumo.get("score"),
        "condicao_atual": resumo.get("condicao_atual"),
        "origem_dados": origem_dados,
        "distribuicao_30d_json": json.dumps(
            resumo.get("distribuicao_30d", {}), ensure_ascii=False
        ),
        "metricas_dia_json": json.dumps(
            resumo.get("metricas_dia", {}), ensure_ascii=False
        ),
        "fatores_risco_json": json.dumps(
            resumo.get("fatores_risco", []), ensure_ascii=False
        ),
    }
    pd.DataFrame([linha]).to_csv(arq, index=False, encoding="utf-8-sig", sep=";")
    return arq


if __name__ == "__main__":
    import sys
    from datetime import datetime, timedelta

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from etapa2_coleta_nasa_power import coletar_nasa_power

    print("AgriShield — Etapa 3: enriquecimento + indicadores")
    fim = datetime.now()
    inicio = fim - timedelta(days=40)
    df_bruto, origem = coletar_nasa_power(
        -12.5450,
        -55.7210,
        inicio.strftime("%Y%m%d"),
        fim.strftime("%Y%m%d"),
        salvar_csv=False,
    )
    df_final = enriquecer(df_bruto)
    arq = salvar_enriquecido_csv(df_final, "1")
    resumo = consolidar_para_dashboard(
        df_final, tipo_operacao="campo", proximidade_agua=True
    )
    csv_dashboard = salvar_dashboard_csv("1", resumo, origem)
    print("CSV enriquecido:", arq.resolve())
    print("CSV dashboard:", csv_dashboard.resolve())
    print("Score:", resumo["score"], resumo["condicao_atual"])
