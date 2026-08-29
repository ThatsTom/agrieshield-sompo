"""Comparacao decisoria isolada entre H1, T3_g3 e T2_gA.

EXPERIMENTAL - NAO CALIBRADO CONTRA SINISTROS REAIS.
Le apenas os artefatos congelados da simulacao anterior e grava resultados em
diretorio separado. Nao integra nem altera o motor produtivo.
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import fmean, median
from typing import Any, Mapping, Sequence

from backend.exposicao.agregacao_perigos import (
    ValorIndiceDiario,
    agregar_indice_historico,
    criar_indices_diarios,
)
from backend.exposicao.modelos import FinalidadeJanela, JanelaHistorica
from backend.exposicao.politica import criar_politica_agrishield_equip_v1


RAIZ = Path(__file__).resolve().parents[2]
BASELINE = RAIZ / "backend" / "data" / "diagnostico_calibracao" / "baseline_v1"
SIMULACAO = (
    RAIZ / "backend" / "data" / "diagnostico_calibracao" / "simulacao_hidrico_v2"
)
SAIDA = (
    RAIZ / "backend" / "data" / "diagnostico_calibracao" / "comparacao_final_hidrico_v2"
)

CHALLENGER_A = "T3_g3"
CHALLENGER_B = "T2_gA"
TOLERANCIA = 1e-10
ARQUIVOS_SAIDA = (
    "01_comparacao_diaria.csv",
    "02_casos_limitrofes.csv",
    "03_eventos_90d.csv",
    "04_impacto_score.csv",
    "05_posicao_topografica.csv",
    "06_casos_reais.csv",
    "RELATORIO_DECISAO_HIDRICO_V2.md",
)


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _numero(valor: Any) -> float | None:
    if valor is None or str(valor).strip() == "":
        return None
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError("numero nao finito")
    return numero


def _percentil_linear(valores: Sequence[float], percentil: float) -> float:
    ordenados = sorted(valores)
    posicao = (len(ordenados) - 1) * percentil / 100.0
    inferior = math.floor(posicao)
    superior = math.ceil(posicao)
    if inferior == superior:
        return ordenados[inferior]
    return ordenados[inferior] * (superior - posicao) + ordenados[superior] * (
        posicao - inferior
    )


def _snapshot(diretorio: Path) -> dict[str, str]:
    return {
        caminho.relative_to(diretorio)
        .as_posix(): hashlib.sha256(caminho.read_bytes())
        .hexdigest()
        for caminho in sorted(diretorio.rglob("*"))
        if caminho.is_file()
    }


def _classe(valor: float | None) -> str | None:
    if valor is None:
        return None
    politica = criar_politica_agrishield_equip_v1()
    return politica.classificar_indice(min(100.0, max(0.0, valor))).value


def _serializar(valor: Any) -> Any:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return format(valor, ".15g")
    return valor


def _salvar_csv(caminho: Path, linhas: Sequence[Mapping[str, Any]]) -> None:
    if not linhas:
        raise ValueError(f"arquivo sem linhas: {caminho.name}")
    campos = list(linhas[0])
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo, fieldnames=campos, delimiter=";", lineterminator="\n"
        )
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow(
                {campo: _serializar(linha.get(campo)) for campo in campos}
            )


def montar_comparacao_diaria(
    diarios_origem: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    selecionados = [
        item
        for item in diarios_origem
        if item["combinacao"] in {CHALLENGER_A, CHALLENGER_B}
    ]
    por_chave = {
        (item["combinacao"], int(item["id_fazenda"]), item["data"]): item
        for item in selecionados
    }
    chaves_base = sorted(
        {(int(item["id_fazenda"]), item["data"]) for item in selecionados}
    )
    linhas: list[dict[str, Any]] = []
    for id_fazenda, data_texto in chaves_base:
        a = por_chave[(CHALLENGER_A, id_fazenda, data_texto)]
        b = por_chave[(CHALLENGER_B, id_fazenda, data_texto)]
        for campo in ("nome", "janela", "h1", "classificacao_h1"):
            if a[campo] != b[campo]:
                raise ValueError(f"divergencia de baseline diario em {campo}")
        h1 = _numero(a["h1"])
        h_a = _numero(a["h2"])
        h_b = _numero(b["h2"])
        diferenca = h_a - h_b if h_a is not None and h_b is not None else None
        linhas.append(
            {
                "id_fazenda": id_fazenda,
                "nome": a["nome"],
                "data": data_texto,
                "janela": a["janela"],
                "h1": h1,
                "classificacao_h1": a["classificacao_h1"] or None,
                "h2_t3_g3": h_a,
                "classificacao_t3_g3": a["classificacao_h2"] or None,
                "g3": _numero(a["g"]),
                "s_t3": _numero(a["suscetibilidade_territorial"]),
                "incremento_t3_g3": _numero(a["incremento_territorial"]),
                "pct_incremento_t3_sobre_h2": _numero(
                    a["percentual_incremento_sobre_h2"]
                ),
                "h2_t2_ga": h_b,
                "classificacao_t2_ga": b["classificacao_h2"] or None,
                "gA": _numero(b["g"]),
                "s_t2": _numero(b["suscetibilidade_territorial"]),
                "incremento_t2_ga": _numero(b["incremento_territorial"]),
                "pct_incremento_t2_sobre_h2": _numero(
                    b["percentual_incremento_sobre_h2"]
                ),
                "diferenca_t3_menos_t2": diferenca,
                "diferenca_absoluta": abs(diferenca) if diferenca is not None else None,
                "classes_challengers_diferem": (
                    "SIM"
                    if h_a is not None
                    and h_b is not None
                    and a["classificacao_h2"] != b["classificacao_h2"]
                    else "NAO"
                ),
                "t3_muda_classe_h1": (
                    "SIM"
                    if h1 is not None and a["classificacao_h1"] != a["classificacao_h2"]
                    else "NAO"
                ),
                "t2_muda_classe_h1": (
                    "SIM"
                    if h1 is not None and b["classificacao_h1"] != b["classificacao_h2"]
                    else "NAO"
                ),
                "precipitacao_d0": _numero(a["precipitacao_d0"]),
                "precipitacao_d1_d3": _numero(a["precipitacao_d1_d3"]),
                "precipitacao_d4_d7": _numero(a["precipitacao_d4_d7"]),
                "acumulado_3d": _numero(a["acumulado_3d"]),
                "acumulado_7d": _numero(a["acumulado_7d"]),
                "experimental_nao_calibrado": "SIM",
            }
        )
    if len(linhas) != 6 * 180:
        raise ValueError("quantidade inesperada de dias comparados")
    return linhas


def montar_casos_limitrofes(
    diarios: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for item in diarios:
        h1 = item["h1"]
        if h1 is None or not 20.0 <= float(h1) < 25.0:
            continue
        linhas.append(
            {
                "id_fazenda": item["id_fazenda"],
                "nome": item["nome"],
                "data": item["data"],
                "janela": item["janela"],
                "h1": h1,
                "classificacao_h1": item["classificacao_h1"],
                "h2_t3_g3": item["h2_t3_g3"],
                "classificacao_t3_g3": item["classificacao_t3_g3"],
                "atravessa_25_t3_g3": (
                    "SIM" if float(item["h2_t3_g3"]) >= 25.0 else "NAO"
                ),
                "incremento_t3_g3": item["incremento_t3_g3"],
                "h2_t2_ga": item["h2_t2_ga"],
                "classificacao_t2_ga": item["classificacao_t2_ga"],
                "atravessa_25_t2_ga": (
                    "SIM" if float(item["h2_t2_ga"]) >= 25.0 else "NAO"
                ),
                "incremento_t2_ga": item["incremento_t2_ga"],
                "diferenca_t3_menos_t2": item["diferenca_t3_menos_t2"],
                "precipitacao_d0": item["precipitacao_d0"],
                "precipitacao_d1_d3": item["precipitacao_d1_d3"],
                "precipitacao_d4_d7": item["precipitacao_d4_d7"],
                "acumulado_3d": item["acumulado_3d"],
                "acumulado_7d": item["acumulado_7d"],
                "experimental_nao_calibrado": "SIM",
            }
        )
    return linhas


def montar_eventos_90d(
    origem: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    selecionados = [
        item for item in origem if item["combinacao"] in {CHALLENGER_A, CHALLENGER_B}
    ]
    por_chave = {
        (int(item["id_fazenda"]), item["janela"], item["combinacao"]): item
        for item in selecionados
    }
    linhas: list[dict[str, Any]] = []
    for id_fazenda, janela in sorted(
        {(int(item["id_fazenda"]), item["janela"]) for item in selecionados}
    ):
        a = por_chave[(id_fazenda, janela, CHALLENGER_A)]
        b = por_chave[(id_fazenda, janela, CHALLENGER_B)]
        if not math.isclose(float(a["h1_90d"]), float(b["h1_90d"]), abs_tol=TOLERANCIA):
            raise ValueError("H1 90d divergente entre challengers")
        linhas.append(
            {
                "id_fazenda": id_fazenda,
                "nome": a["nome"],
                "janela": janela,
                "h1_90d": _numero(a["h1_90d"]),
                "classificacao_h1_90d": a["classificacao_h1_90d"],
                "h90_t3_g3": _numero(a["h2_90d"]),
                "classificacao_h90_t3_g3": a["classificacao_h2_90d"],
                "delta_h90_t3_g3": _numero(a["delta_h_90d"]),
                "novos_dias_relevantes_t3_g3": int(a["novos_dias_relevantes"]),
                "novos_eventos_t3_g3": int(a["novos_eventos"]),
                "eventos_h1": int(a["eventos_h1"]),
                "eventos_t3_g3": int(a["eventos_h2"]),
                "mudanca_classe_h90_t3_g3": (
                    "SIM"
                    if a["classificacao_h1_90d"] != a["classificacao_h2_90d"]
                    else "NAO"
                ),
                "h90_t2_ga": _numero(b["h2_90d"]),
                "classificacao_h90_t2_ga": b["classificacao_h2_90d"],
                "delta_h90_t2_ga": _numero(b["delta_h_90d"]),
                "novos_dias_relevantes_t2_ga": int(b["novos_dias_relevantes"]),
                "novos_eventos_t2_ga": int(b["novos_eventos"]),
                "eventos_t2_ga": int(b["eventos_h2"]),
                "mudanca_classe_h90_t2_ga": (
                    "SIM"
                    if b["classificacao_h1_90d"] != b["classificacao_h2_90d"]
                    else "NAO"
                ),
                "experimental_nao_calibrado": "SIM",
            }
        )
    return linhas


def _dominante(item: Mapping[str, str], hidrico: float) -> str:
    contribuicoes = {
        "EXPOSICAO_HIDRICA": hidrico * float(item["peso_hidrico"]),
        "INSTABILIDADE": float(item["instabilidade_90d"])
        * float(item["peso_instabilidade"]),
        "INCENDIO": float(item["incendio_90d"]) * float(item["peso_incendio"]),
        "TEMPESTADES": float(item["tempestades_90d"]) * float(item["peso_tempestades"]),
    }
    maior = max(contribuicoes.values())
    if maior <= TOLERANCIA:
        return "SEM_DOMINANTE"
    return "|".join(
        perigo
        for perigo, contribuicao in contribuicoes.items()
        if math.isclose(contribuicao, maior, abs_tol=TOLERANCIA)
    )


def montar_impacto_score(
    origem: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    selecionados = [
        item for item in origem if item["combinacao"] in {CHALLENGER_A, CHALLENGER_B}
    ]
    por_chave = {
        (int(item["id_fazenda"]), item["janela"], item["combinacao"]): item
        for item in selecionados
    }
    linhas: list[dict[str, Any]] = []
    for id_fazenda, janela in sorted(
        {(int(item["id_fazenda"]), item["janela"]) for item in selecionados}
    ):
        a = por_chave[(id_fazenda, janela, CHALLENGER_A)]
        b = por_chave[(id_fazenda, janela, CHALLENGER_B)]
        score_v1 = float(a["score_v1"])
        if not math.isclose(score_v1, float(b["score_v1"]), abs_tol=TOLERANCIA):
            raise ValueError("score v1 divergente")
        hidrico_v1 = float(a["hidrico_v1_90d"])
        linhas.append(
            {
                "id_fazenda": id_fazenda,
                "nome": a["nome"],
                "janela": janela,
                "score_v1": score_v1,
                "classificacao_score_v1": a["classificacao_score_v1"],
                "perigo_dominante_v1": _dominante(a, hidrico_v1),
                "score_t3_g3": _numero(a["score_experimental"]),
                "delta_score_t3_g3": _numero(a["delta_score"]),
                "classificacao_score_t3_g3": a["classificacao_score_experimental"],
                "mudanca_classe_score_t3_g3": (
                    "SIM"
                    if a["classificacao_score_v1"]
                    != a["classificacao_score_experimental"]
                    else "NAO"
                ),
                "perigo_dominante_t3_g3": _dominante(a, float(a["hidrico_h2_90d"])),
                "score_t2_ga": _numero(b["score_experimental"]),
                "delta_score_t2_ga": _numero(b["delta_score"]),
                "classificacao_score_t2_ga": b["classificacao_score_experimental"],
                "mudanca_classe_score_t2_ga": (
                    "SIM"
                    if b["classificacao_score_v1"]
                    != b["classificacao_score_experimental"]
                    else "NAO"
                ),
                "perigo_dominante_t2_ga": _dominante(b, float(b["hidrico_h2_90d"])),
                "hidrico_v1_90d": hidrico_v1,
                "hidrico_t3_g3_90d": _numero(a["hidrico_h2_90d"]),
                "hidrico_t2_ga_90d": _numero(b["hidrico_h2_90d"]),
                "instabilidade_90d": _numero(a["instabilidade_90d"]),
                "incendio_90d": _numero(a["incendio_90d"]),
                "tempestades_90d": _numero(a["tempestades_90d"]),
                "peso_hidrico": _numero(a["peso_hidrico"]),
                "peso_trafegabilidade": _numero(a["peso_trafegabilidade"]),
                "experimental_nao_calibrado": "SIM",
            }
        )
    return linhas


def _agregar_lista(linhas: Sequence[Mapping[str, Any]], campo: str) -> Any:
    ordenadas = sorted(linhas, key=lambda item: item["data"])
    janela = ordenadas[0]["janela"]
    periodo = JanelaHistorica(
        data_referencia=date(2026, 8, 15),
        inicio=date.fromisoformat(ordenadas[0]["data"]),
        fim=date.fromisoformat(ordenadas[-1]["data"]),
        dias_esperados=90,
        finalidade=(
            FinalidadeJanela.ATUAL
            if janela == "ATUAL"
            else FinalidadeJanela.COMPARACAO_ANTERIOR
        ),
    )
    politica = criar_politica_agrishield_equip_v1()
    serie = criar_indices_diarios(
        periodo,
        [
            ValorIndiceDiario(data=date.fromisoformat(item["data"]), indice=item[campo])
            for item in ordenadas
        ],
        politica,
    )
    return agregar_indice_historico(serie, politica)


def montar_posicao_topografica(
    suscetibilidades: Sequence[Mapping[str, str]],
    diarios: Sequence[Mapping[str, Any]],
    impactos: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    por_id = {int(item["id_fazenda"]): item for item in suscetibilidades}
    impacto_por_chave = {
        (int(item["id_fazenda"]), item["janela"]): item for item in impactos
    }
    linhas_saida: list[dict[str, Any]] = []
    for id_fazenda in sorted(por_id):
        s = por_id[id_fazenda]
        d2, a2, p2 = float(s["d2"]), float(s["a2"]), float(s["p2"])
        t2, t3 = float(s["t2"]), float(s["t3"])
        componente_p2 = 0.25 * p2
        t3_sem_p2 = 0.40 * d2 + 0.35 * a2
        efeito_reponderacao = (t3 - t2) - componente_p2
        dias_fazenda = [
            item for item in diarios if int(item["id_fazenda"]) == id_fazenda
        ]

        mudancas_diretas_p2 = 0
        mudancas_liquidas_t2_t3 = 0
        for item in dias_fazenda:
            if item["h1"] is None:
                item["h2_t3_sem_p2"] = None
                item["h2_controle_t2_mesmo_g3"] = None
                continue
            h1, g3 = float(item["h1"]), float(item["g3"])
            h_sem_p2 = min(100.0, h1 + 0.30 * g3 * t3_sem_p2)
            h_controle_t2 = min(100.0, h1 + 0.30 * g3 * t2)
            item["h2_t3_sem_p2"] = h_sem_p2
            item["h2_controle_t2_mesmo_g3"] = h_controle_t2
            mudancas_diretas_p2 += _classe(h_sem_p2) != item["classificacao_t3_g3"]
            mudancas_liquidas_t2_t3 += (
                _classe(h_controle_t2) != item["classificacao_t3_g3"]
            )

        for janela in ("ANTERIOR", "ATUAL"):
            grupo = [item for item in dias_fazenda if item["janela"] == janela]
            agregado_sem_p2 = _agregar_lista(grupo, "h2_t3_sem_p2")
            agregado_controle_t2 = _agregar_lista(grupo, "h2_controle_t2_mesmo_g3")
            impacto = impacto_por_chave[(id_fazenda, janela)]
            h_full = float(impacto["hidrico_t3_g3_90d"])
            score_full = float(impacto["score_t3_g3"])
            parcela_fixa = score_full - 0.40 * h_full
            score_sem_p2 = max(
                0.0, parcela_fixa + 0.40 * float(agregado_sem_p2.indice_agregado)
            )
            score_controle_t2 = max(
                0.0,
                parcela_fixa + 0.40 * float(agregado_controle_t2.indice_agregado),
            )
            linhas_saida.append(
                {
                    "id_fazenda": id_fazenda,
                    "nome": s["nome"],
                    "janela": janela,
                    "d2": d2,
                    "a2": a2,
                    "p2": p2,
                    "componente_direto_025_p2": componente_p2,
                    "s_t2": t2,
                    "s_t3": t3,
                    "variacao_liquida_s_t3_menos_t2": t3 - t2,
                    "efeito_reponderacao_d_a": efeito_reponderacao,
                    "mudancas_classe_diaria_devidas_componente_p2": mudancas_diretas_p2,
                    "mudancas_classe_diaria_t2_para_t3_mesmo_g3": mudancas_liquidas_t2_t3,
                    "h90_t3_sem_componente_p2": agregado_sem_p2.indice_agregado,
                    "classe_h90_t3_sem_componente_p2": agregado_sem_p2.classificacao_agregada.value,
                    "h90_t3_com_p2": h_full,
                    "classe_h90_t3_com_p2": _classe(h_full),
                    "p2_muda_classe_h90": (
                        "SIM"
                        if agregado_sem_p2.classificacao_agregada.value
                        != _classe(h_full)
                        else "NAO"
                    ),
                    "score_t3_sem_componente_p2": score_sem_p2,
                    "classe_score_t3_sem_componente_p2": _classe(score_sem_p2),
                    "score_t3_com_p2": score_full,
                    "classe_score_t3_com_p2": impacto["classificacao_score_t3_g3"],
                    "p2_muda_classe_score": (
                        "SIM"
                        if _classe(score_sem_p2) != impacto["classificacao_score_t3_g3"]
                        else "NAO"
                    ),
                    "h90_controle_t2_mesmo_g3": agregado_controle_t2.indice_agregado,
                    "classe_h90_controle_t2_mesmo_g3": agregado_controle_t2.classificacao_agregada.value,
                    "troca_t2_t3_muda_classe_h90": (
                        "SIM"
                        if agregado_controle_t2.classificacao_agregada.value
                        != _classe(h_full)
                        else "NAO"
                    ),
                    "score_controle_t2_mesmo_g3": score_controle_t2,
                    "classe_score_controle_t2_mesmo_g3": _classe(score_controle_t2),
                    "troca_t2_t3_muda_classe_score": (
                        "SIM"
                        if _classe(score_controle_t2)
                        != impacto["classificacao_score_t3_g3"]
                        else "NAO"
                    ),
                    "observacao": (
                        "P2 direto isolado por T3 sem 0.25*P2; comparacao T2-T3 "
                        "tambem inclui reponderacao de D2/A2"
                    ),
                    "experimental_nao_calibrado": "SIM",
                }
            )
    return linhas_saida


def montar_casos_reais(
    diarios: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    por_fazenda = defaultdict(list)
    for item in diarios:
        if item["janela"] == "ATUAL" and item["h1"] is not None:
            por_fazenda[int(item["id_fazenda"])].append(item)
    escolhas: list[tuple[str, Mapping[str, Any]]] = []
    escolhas.append(
        (
            "EMBRAPA_SOJA_18_05",
            next(item for item in por_fazenda[7] if item["data"] == "2026-05-18"),
        )
    )
    escolhas.append(
        (
            "EMBRAPA_ACRE_09_06",
            next(item for item in por_fazenda[5] if item["data"] == "2026-06-09"),
        )
    )
    for id_fazenda in (1, 2, 3, 6):
        maior = max(
            por_fazenda[id_fazenda],
            key=lambda item: (float(item["h1"]), item["data"]),
        )
        escolhas.append(("MAIOR_H1_ATUAL", maior))

    return [
        {
            "tipo_caso": tipo,
            "id_fazenda": item["id_fazenda"],
            "nome": item["nome"],
            "data": item["data"],
            "h1": item["h1"],
            "classificacao_h1": item["classificacao_h1"],
            "precipitacao_d0": item["precipitacao_d0"],
            "precipitacao_d1_d3": item["precipitacao_d1_d3"],
            "precipitacao_d4_d7": item["precipitacao_d4_d7"],
            "acumulado_3d": item["acumulado_3d"],
            "acumulado_7d": item["acumulado_7d"],
            "s_t3": item["s_t3"],
            "g3": item["g3"],
            "incremento_t3_g3": item["incremento_t3_g3"],
            "h2_t3_g3": item["h2_t3_g3"],
            "classificacao_t3_g3": item["classificacao_t3_g3"],
            "s_t2": item["s_t2"],
            "gA": item["gA"],
            "incremento_t2_ga": item["incremento_t2_ga"],
            "h2_t2_ga": item["h2_t2_ga"],
            "classificacao_t2_ga": item["classificacao_t2_ga"],
            "diferenca_t3_menos_t2": item["diferenca_t3_menos_t2"],
            "experimental_nao_calibrado": "SIM",
        }
        for tipo, item in escolhas
    ]


def calcular_metricas(
    diarios: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    metricas: dict[str, dict[str, Any]] = {}
    configuracoes = {
        CHALLENGER_A: (
            "h2_t3_g3",
            "incremento_t3_g3",
            "pct_incremento_t3_sobre_h2",
            "classificacao_t3_g3",
        ),
        CHALLENGER_B: (
            "h2_t2_ga",
            "incremento_t2_ga",
            "pct_incremento_t2_sobre_h2",
            "classificacao_t2_ga",
        ),
    }
    for nome, (
        campo_h2,
        campo_incremento,
        campo_pct,
        campo_classe,
    ) in configuracoes.items():
        avaliados = [item for item in diarios if item[campo_h2] is not None]
        incrementos = [float(item[campo_incremento]) for item in avaliados]
        positivos = [item for item in avaliados if float(item[campo_h2]) > 0]
        metricas[nome] = {
            "dias_avaliados": len(avaliados),
            "incremento_medio": fmean(incrementos),
            "incremento_mediano": median(incrementos),
            "incremento_p90": _percentil_linear(incrementos, 90),
            "incremento_maximo": max(incrementos),
            "dias_mudam_classe": sum(
                item["classificacao_h1"] != item[campo_classe] for item in avaliados
            ),
            "normal_para_atencao": sum(
                item["classificacao_h1"] == "NORMAL" and item[campo_classe] == "ATENCAO"
                for item in avaliados
            ),
            "atencao_para_alerta": sum(
                item["classificacao_h1"] == "ATENCAO" and item[campo_classe] == "ALERTA"
                for item in avaliados
            ),
            "mudancas_para_critico": sum(
                item["classificacao_h1"] != "CRITICO"
                and item[campo_classe] == "CRITICO"
                for item in avaliados
            ),
            "pct_dominancia_maior_30": 100.0
            * sum(float(item[campo_pct]) > 30.0 for item in positivos)
            / len(positivos),
            "h1_menor_10_h2_maior_igual_25": sum(
                float(item["h1"]) < 10.0 and float(item[campo_h2]) >= 25.0
                for item in avaliados
            ),
            "h1_menor_5_h2_maior_igual_25": sum(
                float(item["h1"]) < 5.0 and float(item[campo_h2]) >= 25.0
                for item in avaliados
            ),
        }

    diferencas = [item for item in diarios if item["diferenca_absoluta"] is not None]
    comparacao = {
        "dias_maior_2": sum(
            float(item["diferenca_absoluta"]) > 2 for item in diferencas
        ),
        "dias_maior_5": sum(
            float(item["diferenca_absoluta"]) > 5 for item in diferencas
        ),
        "dias_maior_10": sum(
            float(item["diferenca_absoluta"]) > 10 for item in diferencas
        ),
    }
    fazendas: list[dict[str, Any]] = []
    for id_fazenda in sorted({int(item["id_fazenda"]) for item in diferencas}):
        itens = [item for item in diferencas if int(item["id_fazenda"]) == id_fazenda]
        fazendas.append(
            {
                "id_fazenda": id_fazenda,
                "nome": itens[0]["nome"],
                "dias_maior_2": sum(
                    float(item["diferenca_absoluta"]) > 2 for item in itens
                ),
                "dias_maior_5": sum(
                    float(item["diferenca_absoluta"]) > 5 for item in itens
                ),
                "dias_maior_10": sum(
                    float(item["diferenca_absoluta"]) > 10 for item in itens
                ),
                "diferenca_media_absoluta": fmean(
                    float(item["diferenca_absoluta"]) for item in itens
                ),
                "diferenca_maxima_absoluta": max(
                    float(item["diferenca_absoluta"]) for item in itens
                ),
            }
        )
    return metricas, comparacao, fazendas


def _fmt(valor: Any, casas: int = 2) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, (int, float)):
        return f"{float(valor):.{casas}f}"
    return str(valor)


def gerar_relatorio(
    diarios: Sequence[Mapping[str, Any]],
    limitrofes: Sequence[Mapping[str, Any]],
    eventos: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]],
    posicao: Sequence[Mapping[str, Any]],
    casos: Sequence[Mapping[str, Any]],
    metricas: Mapping[str, Mapping[str, Any]],
    comparacao: Mapping[str, Any],
    diferencas_fazenda: Sequence[Mapping[str, Any]],
    estabilidade: Sequence[Mapping[str, str]],
) -> str:
    a, b = metricas[CHALLENGER_A], metricas[CHALLENGER_B]
    cruza_a = sum(item["atravessa_25_t3_g3"] == "SIM" for item in limitrofes)
    cruza_b = sum(item["atravessa_25_t2_ga"] == "SIM" for item in limitrofes)
    estabilidade_por_modelo = {
        modelo: fmean(
            abs(float(item["variacao"]))
            for item in estabilidade
            if item["modelo"] == modelo
        )
        for modelo in ("T2", "T3")
    }
    p2_por_fazenda = {
        int(item["id_fazenda"]): int(
            item["mudancas_classe_diaria_devidas_componente_p2"]
        )
        for item in posicao
    }
    p2_diarios = sum(p2_por_fazenda.values())
    p2_h90 = sum(item["p2_muda_classe_h90"] == "SIM" for item in posicao)
    p2_score = sum(item["p2_muda_classe_score"] == "SIM" for item in posicao)
    linhas = [
        "# Decisão Metodológica Final — Hídrico V2",
        "",
        "> **EXPERIMENTAL — NÃO CALIBRADO CONTRA SINISTROS REAIS.** Esta decisão não altera o Hídrico v1 nem o motor produtivo.",
        "",
        "## 1. Comparação diária",
        "",
        "| Métrica | T3_g3 | T2_gA |",
        "|---|---:|---:|",
        f"| Dias avaliados | {a['dias_avaliados']} | {b['dias_avaliados']} |",
        f"| Incremento médio | {_fmt(a['incremento_medio'])} | {_fmt(b['incremento_medio'])} |",
        f"| Mediana | {_fmt(a['incremento_mediano'])} | {_fmt(b['incremento_mediano'])} |",
        f"| P90 | {_fmt(a['incremento_p90'])} | {_fmt(b['incremento_p90'])} |",
        f"| Máximo | {_fmt(a['incremento_maximo'])} | {_fmt(b['incremento_maximo'])} |",
        f"| Dias que mudam de classe | {a['dias_mudam_classe']} | {b['dias_mudam_classe']} |",
        f"| NORMAL→ATENÇÃO | {a['normal_para_atencao']} | {b['normal_para_atencao']} |",
        f"| ATENÇÃO→ALERTA | {a['atencao_para_alerta']} | {b['atencao_para_alerta']} |",
        f"| Mudança para CRÍTICO | {a['mudancas_para_critico']} | {b['mudancas_para_critico']} |",
        f"| Contribuição territorial >30% de H2 | {_fmt(a['pct_dominancia_maior_30'])}% | {_fmt(b['pct_dominancia_maior_30'])}% |",
        "",
        "## 2. Diferença direta entre challengers",
        "",
        f"- `|T3_g3−T2_gA| >2`: **{comparacao['dias_maior_2']} dias**.",
        f"- `>5`: **{comparacao['dias_maior_5']} dias**.",
        f"- `>10`: **{comparacao['dias_maior_10']} dias**.",
        "",
        "| Fazenda | >2 | >5 | >10 | Dif. média | Dif. máxima |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in diferencas_fazenda:
        linhas.append(
            f"| {item['nome']} | {item['dias_maior_2']} | {item['dias_maior_5']} | {item['dias_maior_10']} | {_fmt(item['diferenca_media_absoluta'])} | {_fmt(item['diferenca_maxima_absoluta'])} |"
        )

    linhas.extend(
        [
            "",
            "## 3. Casos limítrofes — 20≤H1<25",
            "",
            f"Foram encontrados **{len(limitrofes)} dias**. T3_g3 atravessa 25 em **{cruza_a}**; T2_gA em **{cruza_b}**.",
            "",
            "| Fazenda | Data | H1 | T3_g3 | Cruza | T2_gA | Cruza |",
            "|---|---|---:|---:|---|---:|---|",
        ]
    )
    for item in limitrofes:
        linhas.append(
            f"| {item['nome']} | {item['data']} | {_fmt(item['h1'])} | {_fmt(item['h2_t3_g3'])} | {item['atravessa_25_t3_g3']} | {_fmt(item['h2_t2_ga'])} | {item['atravessa_25_t2_ga']} |"
        )

    linhas.extend(
        [
            "",
            "## 4. Agregação 90d",
            "",
            "| Fazenda | Janela | H1 | T3_g3 | Novos dias/eventos | Classe | T2_gA | Novos dias/eventos | Classe |",
            "|---|---|---:|---:|---:|---|---:|---:|---|",
        ]
    )
    for item in eventos:
        linhas.append(
            f"| {item['nome']} | {item['janela']} | {_fmt(item['h1_90d'])} | {_fmt(item['h90_t3_g3'])} | {item['novos_dias_relevantes_t3_g3']}/{item['novos_eventos_t3_g3']} | {item['classificacao_h1_90d']}→{item['classificacao_h90_t3_g3']} | {_fmt(item['h90_t2_ga'])} | {item['novos_dias_relevantes_t2_ga']}/{item['novos_eventos_t2_ga']} | {item['classificacao_h1_90d']}→{item['classificacao_h90_t2_ga']} |"
        )

    linhas.extend(
        [
            "",
            "## 5. Impacto no score final",
            "",
            "| Fazenda | Janela | Score v1 | T3_g3 (Δ/classe) | T2_gA (Δ/classe) | Dominante v1/T3/T2 |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for item in scores:
        linhas.append(
            f"| {item['nome']} | {item['janela']} | {_fmt(item['score_v1'])} {item['classificacao_score_v1']} | {_fmt(item['score_t3_g3'])} ({_fmt(item['delta_score_t3_g3'])}; {item['classificacao_score_t3_g3']}) | {_fmt(item['score_t2_ga'])} ({_fmt(item['delta_score_t2_ga'])}; {item['classificacao_score_t2_ga']}) | {item['perigo_dominante_v1']} / {item['perigo_dominante_t3_g3']} / {item['perigo_dominante_t2_ga']} |"
        )

    linhas.extend(
        [
            "",
            "## 6. Teste específico de P2",
            "",
            "T3 não é simplesmente T2+P2: ao incluir `0,25·P2`, também reduz os pesos de D2 e A2. Por isso são mostrados o componente P2 direto e a variação líquida T3−T2.",
            "",
            "| Fazenda | 0,25·P2 | T2 | T3 | T3−T2 | Reponderação D/A | Mudanças diárias pelo P2 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    por_fazenda_posicao = {}
    for item in posicao:
        por_fazenda_posicao[int(item["id_fazenda"])] = item
    for item in por_fazenda_posicao.values():
        linhas.append(
            f"| {item['nome']} | {_fmt(item['componente_direto_025_p2'])} | {_fmt(item['s_t2'])} | {_fmt(item['s_t3'])} | {_fmt(item['variacao_liquida_s_t3_menos_t2'])} | {_fmt(item['efeito_reponderacao_d_a'])} | {item['mudancas_classe_diaria_devidas_componente_p2']} |"
        )
    linhas.extend(
        [
            "",
            f"O componente P2 isolado muda **{p2_diarios} classes diárias** no total, **{p2_h90} classe H90** e **{p2_score} classes do score final**. A troca líquida T2→T3, pareada com o mesmo g3, muda cinco classes diárias, uma classe H90 e nenhuma classe final do score.",
            "",
            "## 7. Casos reais",
            "",
            "| Caso | Fazenda/data | D0 / D1–D3 / D4–D7 | Acum. 3d / 7d | H1 | T3: S / g / inc. / H2 | T2: S / g / inc. / H2 | Dif. |",
            "|---|---|---|---|---:|---|---|---:|",
        ]
    )
    for item in casos:
        linhas.append(
            f"| {item['tipo_caso']} | {item['nome']} / {item['data']} | {_fmt(item['precipitacao_d0'])} / {_fmt(item['precipitacao_d1_d3'])} / {_fmt(item['precipitacao_d4_d7'])} | {_fmt(item['acumulado_3d'])} / {_fmt(item['acumulado_7d'])} | {_fmt(item['h1'])} | {_fmt(item['s_t3'])} / {_fmt(item['g3'], 4)} / {_fmt(item['incremento_t3_g3'])} / {_fmt(item['h2_t3_g3'])} {item['classificacao_t3_g3']} | {_fmt(item['s_t2'])} / {_fmt(item['gA'], 4)} / {_fmt(item['incremento_t2_ga'])} / {_fmt(item['h2_t2_ga'])} {item['classificacao_t2_ga']} | {_fmt(item['diferenca_t3_menos_t2'])} |"
        )

    linhas.extend(
        [
            "",
            "## 8. Dominância territorial",
            "",
            "| Controle | T3_g3 | T2_gA |",
            "|---|---:|---:|",
            f"| Contribuição >30% de H2 | {_fmt(a['pct_dominancia_maior_30'])}% | {_fmt(b['pct_dominancia_maior_30'])}% |",
            f"| H1<10 e H2≥25 | {a['h1_menor_10_h2_maior_igual_25']} | {b['h1_menor_10_h2_maior_igual_25']} |",
            f"| H1<5 e H2≥25 | {a['h1_menor_5_h2_maior_igual_25']} | {b['h1_menor_5_h2_maior_igual_25']} |",
            f"| Maior delta territorial | {_fmt(a['incremento_maximo'])} | {_fmt(b['incremento_maximo'])} |",
            "",
            "## 9. Matriz final",
            "",
            "| Critério | H1 | T3_g3 | T2_gA |",
            "|---|---|---|---|",
            "| Sensibilidade territorial | Nenhuma | Alta: D2+A2+P2; 26 mudanças diárias | Moderada: D2+A2; 17 mudanças diárias |",
            "| Parcimônia | Maior | Menor que T2_gA | Maior que T3_g3 |",
            "| Explicabilidade | Alta | Média: três variáveis e acumulado 3d | Alta: duas variáveis e antecedente já conhecido |",
            f"| Estabilidade amostral | Não aplicável | Variação média T3={estabilidade_por_modelo['T3']:.2f} | Variação média T2={estabilidade_por_modelo['T2']:.2f} |",
            f"| Dominância territorial | 0% | {a['pct_dominancia_maior_30']:.2f}% | {b['pct_dominancia_maior_30']:.2f}% |",
            "| Double counting | Chuva apenas na fórmula oficial | Acumulado 3d sobrepõe D0/antecedente de H1 | gA repete diretamente o núcleo antecedente de H1 |",
            "| Diferenciação entre propriedades | Nenhuma territorial | Inclui posição topográfica | Forte separação MERIT, sem posição |",
            "| Auditabilidade | Máxima | Média/alta | Alta |",
            "| Impacto no score | Baseline | Uma fazenda muda classe no conjunto de janelas | Duas fazendas mudam classe no conjunto de janelas |",
            "| Complexidade | Atual | Maior | Menor |",
            "",
            "## 10. Decisão metodológica",
            "",
            "### Candidato único: T3_g3",
            "",
            "**EXPERIMENTAL — NÃO CALIBRADO CONTRA SINISTROS REAIS.**",
            "",
            f"T3_g3 é preferível porque limita melhor a dominância territorial ({a['pct_dominancia_maior_30']:.2f}% contra {b['pct_dominancia_maior_30']:.2f}%), sem gerar nenhum caso H1<10→H2≥25 ou mudança diária para ALERTA/CRÍTICO. Ele reconhece {a['normal_para_atencao']} dias NORMAL→ATENÇÃO contra {b['normal_para_atencao']} e atravessa 25 em {cruza_a} dos 28 casos limítrofes contra {cruza_b}.",
            "",
            "Na janela atual, T3_g3 cria um evento hídrico em Acre e um em Soja; T2_gA não cria evento atual nessas duas propriedades. No caso Soja de 18/05, T3_g3 chega a 25,45, enquanto T2_gA fica em 24,67.",
            "",
            f"O custo é complexidade maior e estabilidade amostral média ligeiramente pior ({estabilidade_por_modelo['T3']:.2f} contra {estabilidade_por_modelo['T2']:.2f}). Esse custo é quantitativamente pequeno diante da redução de 17,26 pontos percentuais na dominância e da maior sensibilidade aos casos reais prioritários. O máximo territorial é apenas 1,25 ponto superior (12,02 contra 10,78), e nenhum challenger produz diferença diária superior a 10 pontos em relação ao outro.",
            "",
            "A decisão é apenas sobre qual challenger avançar para validação; H1 permanece a regra oficial.",
        ]
    )
    return "\n".join(linhas) + "\n"


def validar(
    diarios: Sequence[Mapping[str, Any]],
    limitrofes: Sequence[Mapping[str, Any]],
    eventos: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]],
    posicao: Sequence[Mapping[str, Any]],
    casos: Sequence[Mapping[str, Any]],
    metricas: Mapping[str, Mapping[str, Any]],
    comparacao: Mapping[str, Any],
) -> None:
    if len(diarios) != 1080 or len(eventos) != 12 or len(scores) != 12:
        raise ValueError("dimensoes finais inesperadas")
    if len(limitrofes) != 28 or len(posicao) != 12 or len(casos) != 6:
        raise ValueError("quantidade inesperada de casos especializados")
    if sum(item["atravessa_25_t3_g3"] == "SIM" for item in limitrofes) != 24:
        raise ValueError("cruzamentos limitrofes T3 divergentes")
    if sum(item["atravessa_25_t2_ga"] == "SIM" for item in limitrofes) != 13:
        raise ValueError("cruzamentos limitrofes T2 divergentes")
    if comparacao != {"dias_maior_2": 74, "dias_maior_5": 10, "dias_maior_10": 0}:
        raise ValueError("comparacao direta diverge do resultado auditado")
    for item in diarios:
        if item["h1"] is None:
            if item["h2_t3_g3"] is not None or item["h2_t2_ga"] is not None:
                raise ValueError("missing transformado em valor")
            continue
        if float(item["h2_t3_g3"]) + TOLERANCIA < float(item["h1"]):
            raise ValueError("T3 reduziu H1")
        if float(item["h2_t2_ga"]) + TOLERANCIA < float(item["h1"]):
            raise ValueError("T2 reduziu H1")
    if metricas[CHALLENGER_A]["mudancas_para_critico"] != 0:
        raise ValueError("mudanca inesperada para CRITICO em T3")
    if metricas[CHALLENGER_B]["mudancas_para_critico"] != 0:
        raise ValueError("mudanca inesperada para CRITICO em T2")
    if any(float(item["peso_trafegabilidade"]) != 0.0 for item in scores):
        raise ValueError("Trafegabilidade entrou no score")
    p2_por_fazenda = {
        int(item["id_fazenda"]): int(
            item["mudancas_classe_diaria_devidas_componente_p2"]
        )
        for item in posicao
    }
    if sum(p2_por_fazenda.values()) != 7:
        raise ValueError("efeito diario P2 divergente")
    if sum(item["p2_muda_classe_h90"] == "SIM" for item in posicao) != 1:
        raise ValueError("efeito H90 P2 divergente")
    if any(item["p2_muda_classe_score"] == "SIM" for item in posicao):
        raise ValueError("efeito inesperado de P2 na classe final")


def executar() -> None:
    hashes_baseline = _snapshot(BASELINE)
    hashes_simulacao = _snapshot(SIMULACAO)
    suscetibilidades = _ler_csv(SIMULACAO / "01_suscetibilidade_territorial.csv")
    diarios_origem = _ler_csv(SIMULACAO / "02_resultados_diarios_h2.csv")
    eventos_origem = _ler_csv(SIMULACAO / "03_resultados_90d.csv")
    scores_origem = _ler_csv(SIMULACAO / "04_impacto_score.csv")
    estabilidade = _ler_csv(SIMULACAO / "07_estabilidade_amostral.csv")

    diarios = montar_comparacao_diaria(diarios_origem)
    limitrofes = montar_casos_limitrofes(diarios)
    eventos = montar_eventos_90d(eventos_origem)
    scores = montar_impacto_score(scores_origem)
    posicao = montar_posicao_topografica(suscetibilidades, diarios, scores)
    casos = montar_casos_reais(diarios)
    metricas, comparacao, diferencas_fazenda = calcular_metricas(diarios)
    validar(diarios, limitrofes, eventos, scores, posicao, casos, metricas, comparacao)

    SAIDA.mkdir(parents=True, exist_ok=True)
    _salvar_csv(SAIDA / "01_comparacao_diaria.csv", diarios)
    _salvar_csv(SAIDA / "02_casos_limitrofes.csv", limitrofes)
    _salvar_csv(SAIDA / "03_eventos_90d.csv", eventos)
    _salvar_csv(SAIDA / "04_impacto_score.csv", scores)
    _salvar_csv(SAIDA / "05_posicao_topografica.csv", posicao)
    _salvar_csv(SAIDA / "06_casos_reais.csv", casos)
    relatorio = gerar_relatorio(
        diarios,
        limitrofes,
        eventos,
        scores,
        posicao,
        casos,
        metricas,
        comparacao,
        diferencas_fazenda,
        estabilidade,
    )
    (SAIDA / "RELATORIO_DECISAO_HIDRICO_V2.md").write_text(relatorio, encoding="utf-8")

    if hashes_baseline != _snapshot(BASELINE):
        raise RuntimeError("baseline_v1 foi alterado")
    if hashes_simulacao != _snapshot(SIMULACAO):
        raise RuntimeError("simulacao_hidrico_v2 foi alterada")
    if {item.name for item in SAIDA.iterdir()} != set(ARQUIVOS_SAIDA):
        raise RuntimeError("conjunto inesperado de artefatos finais")
    print(f"Comparacao final concluida: {SAIDA}")
    print(f"Dias: {len(diarios)}; limitrofes: {len(limitrofes)}")
    print("Baseline e simulacao anterior preservados: SIM")


if __name__ == "__main__":
    executar()
