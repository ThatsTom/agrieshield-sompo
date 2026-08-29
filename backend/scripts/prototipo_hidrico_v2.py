"""Executa offline o protótipo paralelo T3_g3 sobre artefatos do baseline."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from backend.exposicao.hidrico_v2_experimental import (
    AVISO_EXPERIMENTAL,
    LIMITACOES_METODOLOGICAS,
    PARAMETROS_T3_G3,
    ContextoTerritorialHidricoV2,
    agregar_hidrico_v2_experimental,
    calcular_hidrico_v2_diario,
    calcular_score_paralelo,
)
from backend.exposicao.modelos import FinalidadeJanela, JanelaHistorica
from backend.exposicao.politica import criar_politica_agrishield_equip_v1


RAIZ = Path(__file__).resolve().parents[1] / "data" / "diagnostico_calibracao"
BASELINE = RAIZ / "baseline_v1"
COMPARACAO = RAIZ / "comparacao_final_hidrico_v2"
SAIDA = RAIZ / "prototipo_hidrico_v2"


def _ler(caminho: Path) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _numero(valor: str | None) -> float | None:
    if valor is None or not str(valor).strip():
        return None
    return float(valor)


def _salvar(caminho: Path, linhas: list[dict[str, object]]) -> None:
    if not linhas:
        raise ValueError("não há linhas para salvar")
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo, fieldnames=tuple(linhas[0]), delimiter=";", lineterminator="\n"
        )
        escritor.writeheader()
        escritor.writerows(linhas)


def executar(saida: Path = SAIDA) -> dict[str, object]:
    politica = criar_politica_agrishield_equip_v1()
    contextos = {
        int(x["id_fazenda"]): x for x in _ler(BASELINE / "02_contexto_territorial.csv")
    }
    resumos = {
        int(x["id_fazenda"]): x for x in _ler(BASELINE / "01_resumo_fazendas.csv")
    }
    features = [
        x
        for x in _ler(BASELINE / "05_features_diarias.csv")
        if x["janela"] in {"ANTERIOR", "ATUAL"}
    ]
    esperados_diarios = {
        (int(x["id_fazenda"]), x["data"]): x
        for x in _ler(COMPARACAO / "01_comparacao_diaria.csv")
    }
    esperados_90 = {
        (int(x["id_fazenda"]), x["janela"]): x
        for x in _ler(COMPARACAO / "03_eventos_90d.csv")
    }
    esperados_score = {
        (int(x["id_fazenda"]), x["janela"]): x
        for x in _ler(COMPARACAO / "04_impacto_score.csv")
    }

    diarios_obj = []
    diarios_csv: list[dict[str, object]] = []
    divergencias: list[str] = []
    por_grupo: dict[tuple[int, str], list] = defaultdict(list)
    nomes: dict[int, str] = {}
    for item in features:
        fid = int(item["id_fazenda"])
        nomes[fid] = item["nome"]
        ctx = contextos[fid]
        territorial = ContextoTerritorialHidricoV2(
            distancia_drenagem_m=_numero(ctx["distancia_drenagem_m"]),
            area_drenagem_montante_km2=_numero(ctx["area_drenagem_montante_km2"]),
            posicao_topografica_relativa_m=_numero(
                ctx["posicao_topografica_relativa_m"]
            ),
        )
        resultado = calcular_hidrico_v2_diario(
            data=date.fromisoformat(item["data"]),
            h1_meteorologico=_numero(item["indice_hidrico"]),
            acumulado_3d=_numero(item["acumulado_3d"]),
            contexto=territorial,
            politica=politica,
        )
        diarios_obj.append(resultado)
        por_grupo[(fid, item["janela"])].append(resultado)
        esperado = esperados_diarios[(fid, item["data"])]
        if (
            resultado.h2_final is not None
            and abs(resultado.h2_final - float(esperado["h2_T3_g3"])) > 1e-10
        ):
            divergencias.append(f"diário {fid} {item['data']}")
        dados = resultado.model_dump(mode="json")
        dados = {
            "id_fazenda": fid,
            "nome": item["nome"],
            "janela": item["janela"],
            **dados,
        }
        diarios_csv.append(dados)

    agregados_csv: list[dict[str, object]] = []
    for (fid, janela_nome), itens in por_grupo.items():
        inicio, fim = itens[0].data, itens[-1].data
        janela = JanelaHistorica(
            data_referencia=date(2026, 8, 15),
            inicio=inicio,
            fim=fim,
            dias_esperados=90,
            finalidade=(
                FinalidadeJanela.ATUAL
                if janela_nome == "ATUAL"
                else FinalidadeJanela.COMPARACAO_ANTERIOR
            ),
        )
        agregado = agregar_hidrico_v2_experimental(itens, janela, politica)
        resumo = resumos[fid]
        score_v1 = _numero(
            resumo["score_atual"]
            if janela_nome == "ATUAL"
            else resumo["score_anterior"]
        )
        score = calcular_score_paralelo(
            score_v1=score_v1,
            indice_hidrico_v1_90d=agregado.indice_hidrico_v1_90d,
            indice_hidrico_v2_90d=agregado.indice_hidrico_v2_90d,
            politica=politica,
        )
        e90, escore = (
            esperados_90[(fid, janela_nome)],
            esperados_score[(fid, janela_nome)],
        )
        if abs(agregado.indice_hidrico_v2_90d - float(e90["h2_90d_T3_g3"])) > 1e-10:
            divergencias.append(f"90d {fid} {janela_nome}")
        if abs(score.score_v2_experimental - float(escore["score_T3_g3"])) > 1e-10:
            divergencias.append(f"score {fid} {janela_nome}")
        agregados_csv.append(
            {
                "id_fazenda": fid,
                "nome": nomes[fid],
                "janela": janela_nome,
                "h1_90d": agregado.indice_hidrico_v1_90d,
                "classificacao_h1_90d": agregado.classificacao_hidrica_v1_90d.value,
                "h2_90d": agregado.indice_hidrico_v2_90d,
                "classificacao_h2_90d": agregado.classificacao_hidrica_v2_90d.value,
                "delta_hidrico_90d": agregado.delta_hidrico_90d,
                "novos_dias_relevantes": agregado.agregacao_v2.quantidade_dias_relevantes
                - agregado.agregacao_v1.quantidade_dias_relevantes,
                "eventos_v1": agregado.agregacao_v1.quantidade_eventos,
                "eventos_v2": agregado.agregacao_v2.quantidade_eventos,
                "score_v1": score.score_v1,
                "score_v2_experimental": score.score_v2_experimental,
                "delta_score": score.delta_score,
                "classificacao_score_v1": score.classificacao_v1.value,
                "classificacao_score_v2": score.classificacao_v2_experimental.value,
                "aderente_simulacao": "SIM",
                "experimental_nao_calibrado": "SIM",
            }
        )

    if divergencias:
        raise AssertionError(
            "divergências contra comparação final: " + ", ".join(divergencias[:10])
        )
    saida.mkdir(parents=True, exist_ok=True)
    _salvar(saida / "01_resultados_diarios_t3_g3.csv", diarios_csv)
    _salvar(saida / "02_resultados_90d_score.csv", agregados_csv)
    p = PARAMETROS_T3_G3
    linhas = [
        "# Protótipo paralelo — Hídrico V2 T3_g3",
        "",
        f"> **{AVISO_EXPERIMENTAL}**",
        "",
        "## Arquitetura",
        "",
        "Serviço interno experimental e script offline. O endpoint oficial `/api/v1/exposicao/{id_fazenda}` não foi alterado. O protótipo reutiliza a curva de precipitação, a classificação e o agregador 90d oficiais; Trafegabilidade e Instabilidade continuam consumindo H1 no fluxo v1.",
        "",
        "## Parâmetros fixos do baseline experimental",
        "",
        f"- mediana_distancia_m: `{p.mediana_distancia_m!r}`",
        f"- area_log_min: `{p.area_log_min!r}`",
        f"- area_log_max: `{p.area_log_max!r}`",
        f"- mediana_posicao_m: `{p.mediana_posicao_m!r}`",
        f"- iqr_posicao_m: `{p.iqr_posicao_m!r}`",
        "- T3: `0.40*D2 + 0.35*A2 + 0.25*P2`",
        "- incremento: `0.30*g3*T3`",
        "",
        "## Resultado das seis fazendas",
        "",
        "| Fazenda | Janela | H1 90d | H2 90d | Delta H | Score v1 | Score v2 | Delta score | Classe v1 | Classe v2 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for x in agregados_csv:
        linhas.append(
            f"| {x['nome']} | {x['janela']} | {x['h1_90d']:.2f} | {x['h2_90d']:.2f} | {x['delta_hidrico_90d']:.2f} | {x['score_v1']:.2f} | {x['score_v2_experimental']:.2f} | {x['delta_score']:.2f} | {x['classificacao_score_v1']} | {x['classificacao_score_v2']} |"
        )
    linhas += [
        "",
        "## Aderência",
        "",
        f"Os {len(diarios_csv)} registros diários e os {len(agregados_csv)} pares fazenda–janela coincidiram com os artefatos de `comparacao_final_hidrico_v2/` dentro de tolerância absoluta `1e-10`.",
        "",
        "## Proveniência",
        "",
        "- Meteorologia: NASA_POWER, conforme baseline selecionado.",
        "- MERIT_HYDRO: distância à drenagem e área drenada a montante.",
        "- SRTM: posição topográfica relativa.",
        "- Declividade: não participa.",
        "",
        "## Limitações",
        "",
    ]
    linhas += [f"- {x}" for x in LIMITACOES_METODOLOGICAS]
    linhas += ["", f"> **{AVISO_EXPERIMENTAL}**", ""]
    (saida / "RELATORIO_PROTOTIPO_HIDRICO_V2.md").write_text(
        "\n".join(linhas), encoding="utf-8"
    )
    return {
        "diarios": diarios_csv,
        "agregados": agregados_csv,
        "divergencias": divergencias,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA)
    args = parser.parse_args()
    resultado = executar(args.saida)
    print(
        f"Hídrico V2 experimental: {len(resultado['diarios'])} dias, {len(resultado['agregados'])} agregações, 0 divergências"
    )


if __name__ == "__main__":
    main()
