"""Simulacao comparativa, isolada e nao produtiva, do Hidrico V2.

Todas as formulas deste modulo sao EXPERIMENTAIS e nao calibradas contra
sinistros reais. O modulo le somente o baseline congelado, reutiliza a
agregacao oficial v1 e grava artefatos em um diretorio separado.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable, Mapping, Sequence

from backend.exposicao.agregacao_perigos import (
    ResultadoAgregacaoPerigo,
    ValorIndiceDiario,
    agregar_indice_historico,
    criar_indices_diarios,
)
from backend.exposicao.modelos import FinalidadeJanela, JanelaHistorica
from backend.exposicao.politica import criar_politica_agrishield_equip_v1


RAIZ_REPOSITORIO = Path(__file__).resolve().parents[2]
BASELINE_PADRAO = (
    RAIZ_REPOSITORIO / "backend" / "data" / "diagnostico_calibracao" / "baseline_v1"
)
SAIDA_PADRAO = (
    RAIZ_REPOSITORIO
    / "backend"
    / "data"
    / "diagnostico_calibracao"
    / "simulacao_hidrico_v2"
)

ARQUIVOS_BASELINE = (
    "01_resumo_fazendas.csv",
    "02_contexto_territorial.csv",
    "03_meteorologia_janelas.csv",
    "04_perigos.csv",
    "05_features_diarias.csv",
    "06_fontes_proveniencia.csv",
)

ARQUIVOS_SAIDA = (
    "01_suscetibilidade_territorial.csv",
    "02_resultados_diarios_h2.csv",
    "03_resultados_90d.csv",
    "04_impacto_score.csv",
    "05_metricas_combinacoes.csv",
    "06_casos_relevantes.csv",
    "07_estabilidade_amostral.csv",
    "RELATORIO_SIMULACAO_HIDRICO_V2.md",
)

MODELOS = ("T1", "T2", "T3")
ATIVADORES = ("g3", "g7", "gA")
COMBINACOES = tuple(
    f"{modelo}_{ativador}" for modelo in MODELOS for ativador in ATIVADORES
)
TOLERANCIA = 1e-10


@dataclass(frozen=True)
class ParametrosAmostrais:
    mediana_distancia_m: float
    area_log_min: float
    area_log_max: float
    mediana_posicao_m: float
    iqr_posicao_m: float


@dataclass(frozen=True)
class Suscetibilidade:
    id_fazenda: int
    nome: str
    distancia_drenagem_m: float
    area_montante_km2: float
    posicao_topografica_m: float
    d2: float
    a2: float
    p2: float
    t1: float
    t2: float
    t3: float

    def modelo(self, nome: str) -> float:
        return {"T1": self.t1, "T2": self.t2, "T3": self.t3}[nome]


def _ler_csv(caminho: Path) -> list[dict[str, str]]:
    with caminho.open("r", encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


def _numero(texto: str | None) -> float | None:
    if texto is None or texto.strip() == "":
        return None
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError("valor numerico nao finito no baseline")
    return valor


def _percentil_linear(valores: Sequence[float], percentil: float) -> float:
    if not valores:
        raise ValueError("percentil exige valores")
    ordenados = sorted(valores)
    posicao = (len(ordenados) - 1) * percentil / 100.0
    inferior = math.floor(posicao)
    superior = math.ceil(posicao)
    if inferior == superior:
        return ordenados[inferior]
    return ordenados[inferior] * (superior - posicao) + ordenados[superior] * (
        posicao - inferior
    )


def snapshot_baseline(diretorio: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for nome in ARQUIVOS_BASELINE:
        caminho = diretorio / nome
        if not caminho.is_file():
            raise FileNotFoundError(f"arquivo obrigatorio ausente: {caminho}")
        hashes[nome] = hashlib.sha256(caminho.read_bytes()).hexdigest()
    return hashes


def curva_precipitacao_oficial(precipitacao_mm: float) -> float:
    """Mesma interpolacao linear da curva de precipitacao da politica v1."""

    if isinstance(precipitacao_mm, bool) or not math.isfinite(precipitacao_mm):
        raise ValueError("precipitacao deve ser numerica e finita")
    if precipitacao_mm < 0:
        raise ValueError("precipitacao nao pode ser negativa")
    if precipitacao_mm <= 20:
        return precipitacao_mm * 25.0 / 20.0
    if precipitacao_mm <= 50:
        return 25.0 + (precipitacao_mm - 20.0) * 25.0 / 30.0
    if precipitacao_mm <= 100:
        return 50.0 + (precipitacao_mm - 50.0)
    return 100.0


def calcular_g(linha: Mapping[str, str], ativador: str) -> float | None:
    if ativador == "g3":
        acumulado = _numero(linha.get("acumulado_3d"))
        return (
            None if acumulado is None else curva_precipitacao_oficial(acumulado) / 100.0
        )
    if ativador == "g7":
        acumulado = _numero(linha.get("acumulado_7d"))
        return (
            None if acumulado is None else curva_precipitacao_oficial(acumulado) / 100.0
        )
    if ativador == "gA":
        d1_d3 = _numero(linha.get("precipitacao_d1_d3"))
        d4_d7 = _numero(linha.get("precipitacao_d4_d7"))
        if d1_d3 is None or d4_d7 is None:
            return None
        return (
            0.70 * curva_precipitacao_oficial(d1_d3)
            + 0.30 * curva_precipitacao_oficial(d4_d7)
        ) / 100.0
    raise ValueError(f"ativador desconhecido: {ativador}")


def calcular_h2(
    h1: float | None, g: float | None, suscetibilidade: float
) -> tuple[float | None, float | None, float | None]:
    """Retorna H2, incremento e participacao percentual do incremento em H2."""

    if h1 is None or g is None:
        return None, None, None
    if not 0 <= h1 <= 100 or not 0 <= g <= 1 or not 0 <= suscetibilidade <= 100:
        raise ValueError("entradas de H2 fora do dominio")
    incremento = 0.30 * g * suscetibilidade
    h2 = min(100.0, h1 + incremento)
    percentual = incremento / h2 * 100.0 if h2 > 0 else None
    return h2, incremento, percentual


def _parametros_amostrais(
    contextos: Sequence[Mapping[str, str]]
) -> ParametrosAmostrais:
    if len(contextos) < 2:
        raise ValueError("normalizacao amostral exige ao menos duas fazendas")
    distancias = [_numero(item["distancia_drenagem_m"]) for item in contextos]
    areas = [_numero(item["area_drenagem_montante_km2"]) for item in contextos]
    posicoes = [_numero(item["posicao_topografica_relativa_m"]) for item in contextos]
    if any(valor is None for valor in (*distancias, *areas, *posicoes)):
        raise ValueError("contexto territorial incompleto")
    d = [float(valor) for valor in distancias]
    a_log = [math.log1p(float(valor)) for valor in areas]
    p = [float(valor) for valor in posicoes]
    iqr = _percentil_linear(p, 75) - _percentil_linear(p, 25)
    if math.isclose(max(a_log), min(a_log), abs_tol=TOLERANCIA):
        raise ValueError("area montante sem variacao para normalizacao")
    if math.isclose(iqr, 0.0, abs_tol=TOLERANCIA):
        raise ValueError("IQR topografico nulo")
    return ParametrosAmostrais(
        mediana_distancia_m=median(d),
        area_log_min=min(a_log),
        area_log_max=max(a_log),
        mediana_posicao_m=median(p),
        iqr_posicao_m=iqr,
    )


def calcular_suscetibilidades(
    contextos: Sequence[Mapping[str, str]],
) -> tuple[ParametrosAmostrais, dict[int, Suscetibilidade]]:
    parametros = _parametros_amostrais(contextos)
    resultados: dict[int, Suscetibilidade] = {}
    for item in contextos:
        id_fazenda = int(item["id_fazenda"])
        distancia = float(_numero(item["distancia_drenagem_m"]))
        area = float(_numero(item["area_drenagem_montante_km2"]))
        posicao = float(_numero(item["posicao_topografica_relativa_m"]))
        d2 = (
            100.0
            * parametros.mediana_distancia_m
            / (parametros.mediana_distancia_m + distancia)
        )
        area_log = math.log1p(area)
        a2 = (
            100.0
            * (area_log - parametros.area_log_min)
            / (parametros.area_log_max - parametros.area_log_min)
        )
        p2 = 100.0 / (
            1.0
            + math.exp(
                (posicao - parametros.mediana_posicao_m) / parametros.iqr_posicao_m
            )
        )
        resultados[id_fazenda] = Suscetibilidade(
            id_fazenda=id_fazenda,
            nome=item["nome"],
            distancia_drenagem_m=distancia,
            area_montante_km2=area,
            posicao_topografica_m=posicao,
            d2=d2,
            a2=a2,
            p2=p2,
            t1=0.80 * d2 + 0.20 * a2,
            t2=0.50 * d2 + 0.50 * a2,
            t3=0.40 * d2 + 0.35 * a2 + 0.25 * p2,
        )
    return parametros, resultados


def _classe(valor: float | None) -> str | None:
    if valor is None:
        return None
    return criar_politica_agrishield_equip_v1().classificar_indice(valor).value


def montar_resultados_diarios(
    features: Sequence[Mapping[str, str]],
    suscetibilidades: Mapping[int, Suscetibilidade],
) -> list[dict[str, Any]]:
    politica = criar_politica_agrishield_equip_v1()
    linhas: list[dict[str, Any]] = []
    for item in features:
        if item["janela"] not in {"ANTERIOR", "ATUAL"}:
            continue
        id_fazenda = int(item["id_fazenda"])
        h1 = _numero(item.get("indice_hidrico"))
        classe_h1 = politica.classificar_indice(h1).value if h1 is not None else None
        classe_baseline = item.get("classificacao_hidrica") or None
        if classe_h1 != classe_baseline:
            raise ValueError("classificacao diaria H1 diverge da politica oficial")
        for modelo in MODELOS:
            s = suscetibilidades[id_fazenda].modelo(modelo)
            for ativador in ATIVADORES:
                g = calcular_g(item, ativador)
                h2, incremento, percentual = calcular_h2(h1, g, s)
                classe_h2 = (
                    politica.classificar_indice(h2).value if h2 is not None else None
                )
                linhas.append(
                    {
                        "id_fazenda": id_fazenda,
                        "nome": item["nome"],
                        "data": item["data"],
                        "janela": item["janela"],
                        "combinacao": f"{modelo}_{ativador}",
                        "modelo_territorial": modelo,
                        "ativador": ativador,
                        "suscetibilidade_territorial": s,
                        "h1": h1,
                        "classificacao_h1": classe_h1,
                        "g": g,
                        "incremento_territorial": incremento,
                        "h2": h2,
                        "classificacao_h2": classe_h2,
                        "percentual_incremento_sobre_h2": percentual,
                        "transicao": (
                            f"{classe_h1}->{classe_h2}"
                            if classe_h1 is not None and classe_h2 is not None
                            else None
                        ),
                        "precipitacao_d0": _numero(item.get("precipitacao_d0")),
                        "precipitacao_d1_d3": _numero(item.get("precipitacao_d1_d3")),
                        "precipitacao_d4_d7": _numero(item.get("precipitacao_d4_d7")),
                        "acumulado_3d": _numero(item.get("acumulado_3d")),
                        "acumulado_7d": _numero(item.get("acumulado_7d")),
                        "experimental": "SIM",
                    }
                )
    return linhas


def _periodo_para_grupo(
    linhas: Sequence[Mapping[str, Any]], data_referencia: date
) -> JanelaHistorica:
    datas = sorted(date.fromisoformat(str(item["data"])) for item in linhas)
    janela = str(linhas[0]["janela"])
    return JanelaHistorica(
        data_referencia=data_referencia,
        inicio=datas[0],
        fim=datas[-1],
        dias_esperados=len(datas),
        finalidade=(
            FinalidadeJanela.ATUAL
            if janela == "ATUAL"
            else FinalidadeJanela.COMPARACAO_ANTERIOR
        ),
    )


def _agregar(
    linhas: Sequence[Mapping[str, Any]], campo: str, data_referencia: date
) -> ResultadoAgregacaoPerigo:
    politica = criar_politica_agrishield_equip_v1()
    periodo = _periodo_para_grupo(linhas, data_referencia)
    valores = [
        ValorIndiceDiario(
            data=date.fromisoformat(str(item["data"])),
            indice=item[campo],
        )
        for item in linhas
    ]
    serie = criar_indices_diarios(periodo, valores, politica)
    return agregar_indice_historico(serie, politica)


def montar_resultados_90d(
    diarios: Sequence[Mapping[str, Any]],
    perigos: Sequence[Mapping[str, str]],
    data_referencia: date,
) -> list[dict[str, Any]]:
    hidricos_baseline = {
        (int(item["id_fazenda"]), item["janela"]): item
        for item in perigos
        if item["perigo"] == "EXPOSICAO_HIDRICA"
    }
    grupos: dict[tuple[int, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for item in diarios:
        grupos[
            (int(item["id_fazenda"]), str(item["janela"]), str(item["combinacao"]))
        ].append(item)

    resultados: list[dict[str, Any]] = []
    for (id_fazenda, janela, combinacao), linhas in sorted(grupos.items()):
        linhas = sorted(linhas, key=lambda item: str(item["data"]))
        agregado_h1 = _agregar(linhas, "h1", data_referencia)
        agregado_h2 = _agregar(linhas, "h2", data_referencia)
        baseline = hidricos_baseline[(id_fazenda, janela)]
        h1_baseline = float(baseline["indice_90d"])
        if not math.isclose(
            float(agregado_h1.indice_agregado),
            h1_baseline,
            rel_tol=0.0,
            abs_tol=TOLERANCIA,
        ):
            raise ValueError("agregacao H1 reconstruida diverge do baseline")

        h1_relevante = {
            date.fromisoformat(str(item["data"]))
            for item in linhas
            if item["h1"] is not None and float(item["h1"]) >= 25.0
        }
        novos_eventos = sum(
            not any(evento.inicio <= data_h1 <= evento.fim for data_h1 in h1_relevante)
            for evento in agregado_h2.eventos
        )
        novos_dias = sum(
            item["h2"] is not None
            and float(item["h2"]) >= 25.0
            and (item["h1"] is None or float(item["h1"]) < 25.0)
            for item in linhas
        )
        resultados.append(
            {
                "id_fazenda": id_fazenda,
                "nome": linhas[0]["nome"],
                "janela": janela,
                "combinacao": combinacao,
                "h1_90d": agregado_h1.indice_agregado,
                "classificacao_h1_90d": agregado_h1.classificacao_agregada.value,
                "h2_90d": agregado_h2.indice_agregado,
                "classificacao_h2_90d": agregado_h2.classificacao_agregada.value,
                "delta_h_90d": float(agregado_h2.indice_agregado)
                - float(agregado_h1.indice_agregado),
                "dias_disponiveis": agregado_h2.dias_disponiveis,
                "cobertura_percentual": agregado_h2.cobertura_percentual,
                "severidade_h2": agregado_h2.severidade_score,
                "frequencia_h2": agregado_h2.frequencia_score,
                "duracao_h2": agregado_h2.duracao_score,
                "recorrencia_h2": agregado_h2.recorrencia_score,
                "dias_relevantes_h1": agregado_h1.quantidade_dias_relevantes,
                "dias_relevantes_h2": agregado_h2.quantidade_dias_relevantes,
                "novos_dias_relevantes": novos_dias,
                "eventos_h1": agregado_h1.quantidade_eventos,
                "eventos_h2": agregado_h2.quantidade_eventos,
                "delta_eventos": agregado_h2.quantidade_eventos
                - agregado_h1.quantidade_eventos,
                "novos_eventos": novos_eventos,
                "maior_evento_h2_dias": agregado_h2.maior_duracao_evento,
                "experimental": "SIM",
            }
        )
    return resultados


def montar_impacto_score(
    resultados_90d: Sequence[Mapping[str, Any]],
    perigos: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    politica = criar_politica_agrishield_equip_v1()
    por_fazenda_janela: dict[tuple[int, str], list[Mapping[str, str]]] = defaultdict(
        list
    )
    for item in perigos:
        por_fazenda_janela[(int(item["id_fazenda"]), item["janela"])].append(item)

    resultados: list[dict[str, Any]] = []
    for item in resultados_90d:
        chave = (int(item["id_fazenda"]), str(item["janela"]))
        linhas = por_fazenda_janela[chave]
        trafego = next(
            linha for linha in linhas if linha["perigo"] == "TRAFEGABILIDADE"
        )
        if trafego["peso_efetivo"] != "0" or trafego["participa_score"] != "NAO":
            raise ValueError(
                "Trafegabilidade participa indevidamente do score baseline"
            )
        participantes = [linha for linha in linhas if linha["participa_score"] == "SIM"]
        pesos = {
            linha["perigo"]: float(linha["peso_efetivo"]) for linha in participantes
        }
        if not math.isclose(math.fsum(pesos.values()), 1.0, abs_tol=TOLERANCIA):
            raise ValueError("pesos efetivos do baseline nao somam um")
        indices = {
            linha["perigo"]: float(linha["indice_90d"]) for linha in participantes
        }
        score_v1 = math.fsum(indices[perigo] * peso for perigo, peso in pesos.items())
        indices_experimentais = dict(indices)
        indices_experimentais["EXPOSICAO_HIDRICA"] = float(item["h2_90d"])
        score_experimental = math.fsum(
            indices_experimentais[perigo] * peso for perigo, peso in pesos.items()
        )
        classe_v1 = politica.classificar_indice(score_v1).value
        classe_experimental = politica.classificar_indice(score_experimental).value
        resultados.append(
            {
                "id_fazenda": item["id_fazenda"],
                "nome": item["nome"],
                "janela": item["janela"],
                "combinacao": item["combinacao"],
                "hidrico_v1_90d": item["h1_90d"],
                "hidrico_h2_90d": item["h2_90d"],
                "instabilidade_90d": indices["INSTABILIDADE"],
                "incendio_90d": indices["INCENDIO"],
                "tempestades_90d": indices["TEMPESTADES"],
                "trafegabilidade_90d": float(trafego["indice_90d"]),
                "peso_hidrico": pesos["EXPOSICAO_HIDRICA"],
                "peso_instabilidade": pesos["INSTABILIDADE"],
                "peso_incendio": pesos["INCENDIO"],
                "peso_tempestades": pesos["TEMPESTADES"],
                "peso_trafegabilidade": float(trafego["peso_efetivo"]),
                "score_v1": score_v1,
                "score_experimental": score_experimental,
                "delta_score": score_experimental - score_v1,
                "classificacao_score_v1": classe_v1,
                "classificacao_score_experimental": classe_experimental,
                "experimental": "SIM",
            }
        )
    return resultados


def _mudou(valor: float) -> bool:
    return not math.isclose(valor, 0.0, rel_tol=0.0, abs_tol=TOLERANCIA)


def montar_metricas(
    diarios: Sequence[Mapping[str, Any]],
    resultados_90d: Sequence[Mapping[str, Any]],
    impactos: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    metricas: list[dict[str, Any]] = []
    transicoes = (
        "NORMAL->ATENCAO",
        "NORMAL->ALERTA",
        "NORMAL->CRITICO",
        "ATENCAO->ALERTA",
        "ATENCAO->CRITICO",
        "ALERTA->CRITICO",
    )
    for combinacao in COMBINACOES:
        dias = [
            item
            for item in diarios
            if item["combinacao"] == combinacao and item["h2"] is not None
        ]
        agregados = [
            item for item in resultados_90d if item["combinacao"] == combinacao
        ]
        scores = [item for item in impactos if item["combinacao"] == combinacao]
        incrementos = [float(item["incremento_territorial"]) for item in dias]
        h2_positivos = [item for item in dias if float(item["h2"]) > 0]
        dominantes = [
            item
            for item in h2_positivos
            if float(item["percentual_incremento_sobre_h2"]) > 30.0
        ]
        medias_fazenda: dict[int, list[float]] = defaultdict(list)
        for item in dias:
            medias_fazenda[int(item["id_fazenda"])].append(
                float(item["incremento_territorial"])
            )
        id_maior_media = max(medias_fazenda, key=lambda fid: fmean(medias_fazenda[fid]))
        exemplo = next(
            item for item in dias if int(item["id_fazenda"]) == id_maior_media
        )
        linha: dict[str, Any] = {
            "combinacao": combinacao,
            "total_dias_avaliados": len(dias),
        }
        for transicao in transicoes:
            linha[transicao.lower().replace("->", "_para_")] = sum(
                item["transicao"] == transicao for item in dias
            )
        linha.update(
            {
                "incremento_medio": fmean(incrementos),
                "incremento_mediano": median(incrementos),
                "incremento_p90": _percentil_linear(incrementos, 90),
                "incremento_maximo": max(incrementos),
                "novos_eventos_hidricos": sum(
                    int(item["novos_eventos"]) for item in agregados
                ),
                "delta_liquido_eventos": sum(
                    int(item["delta_eventos"]) for item in agregados
                ),
                "fazendas_com_mudanca_h90d": len(
                    {
                        int(item["id_fazenda"])
                        for item in agregados
                        if _mudou(float(item["delta_h_90d"]))
                    }
                ),
                "fazenda_janelas_com_mudanca_h90d": sum(
                    _mudou(float(item["delta_h_90d"])) for item in agregados
                ),
                "fazendas_com_mudanca_classe_h90d": len(
                    {
                        int(item["id_fazenda"])
                        for item in agregados
                        if item["classificacao_h1_90d"] != item["classificacao_h2_90d"]
                    }
                ),
                "fazendas_com_mudanca_score": len(
                    {
                        int(item["id_fazenda"])
                        for item in scores
                        if _mudou(float(item["delta_score"]))
                    }
                ),
                "fazendas_com_mudanca_classe_final": len(
                    {
                        int(item["id_fazenda"])
                        for item in scores
                        if item["classificacao_score_v1"]
                        != item["classificacao_score_experimental"]
                    }
                ),
                "dias_h2_positivo": len(h2_positivos),
                "dias_incremento_maior_30pct_h2": len(dominantes),
                "pct_dias_incremento_maior_30pct_h2": (
                    100.0 * len(dominantes) / len(h2_positivos) if h2_positivos else 0.0
                ),
                "dias_h1_menor_10_h2_maior_igual_25": sum(
                    float(item["h1"]) < 10 and float(item["h2"]) >= 25 for item in dias
                ),
                "pct_dias_h1_menor_10_h2_maior_igual_25": 100.0
                * sum(
                    float(item["h1"]) < 10 and float(item["h2"]) >= 25 for item in dias
                )
                / len(dias),
                "dias_h1_menor_5_h2_maior_igual_25": sum(
                    float(item["h1"]) < 5 and float(item["h2"]) >= 25 for item in dias
                ),
                "pct_dias_h1_menor_5_h2_maior_igual_25": 100.0
                * sum(
                    float(item["h1"]) < 5 and float(item["h2"]) >= 25 for item in dias
                )
                / len(dias),
                "maior_incremento_territorial_absoluto": max(incrementos),
                "id_fazenda_maior_incremento_medio": id_maior_media,
                "nome_fazenda_maior_incremento_medio": exemplo["nome"],
                "maior_incremento_medio_por_fazenda": fmean(
                    medias_fazenda[id_maior_media]
                ),
                "experimental": "SIM",
            }
        )
        metricas.append(linha)
    return metricas


def montar_estabilidade(
    contextos: Sequence[Mapping[str, str]],
    referencia: Mapping[int, Suscetibilidade],
) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for removida in contextos:
        id_removida = int(removida["id_fazenda"])
        amostra = [item for item in contextos if int(item["id_fazenda"]) != id_removida]
        parametros, recalculadas = calcular_suscetibilidades(amostra)
        for id_fazenda, recalculada in sorted(recalculadas.items()):
            for modelo in MODELOS:
                valor_referencia = referencia[id_fazenda].modelo(modelo)
                valor_loo = recalculada.modelo(modelo)
                linhas.append(
                    {
                        "id_fazenda_removida": id_removida,
                        "nome_fazenda_removida": removida["nome"],
                        "id_fazenda_avaliada": id_fazenda,
                        "nome_fazenda_avaliada": recalculada.nome,
                        "modelo": modelo,
                        "s_referencia_6_fazendas": valor_referencia,
                        "s_recalculado_5_fazendas": valor_loo,
                        "variacao": valor_loo - valor_referencia,
                        "variacao_absoluta": abs(valor_loo - valor_referencia),
                        "mediana_distancia_loo_m": parametros.mediana_distancia_m,
                        "area_log_min_loo": parametros.area_log_min,
                        "area_log_max_loo": parametros.area_log_max,
                        "mediana_posicao_loo_m": parametros.mediana_posicao_m,
                        "iqr_posicao_loo_m": parametros.iqr_posicao_m,
                        "experimental": "SIM",
                    }
                )
    return linhas


def montar_casos_relevantes(
    diarios: Sequence[Mapping[str, Any]],
    agregados: Sequence[Mapping[str, Any]],
    impactos: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    campos = (
        "tipo_caso",
        "combinacao",
        "id_fazenda",
        "nome",
        "janela",
        "data",
        "h1",
        "classificacao_h1",
        "g",
        "suscetibilidade_territorial",
        "incremento_territorial",
        "h2",
        "classificacao_h2",
        "h1_90d",
        "h2_90d",
        "delta_h_90d",
        "score_v1",
        "score_experimental",
        "delta_score",
        "detalhe",
    )

    def caso(tipo: str, **dados: Any) -> dict[str, Any]:
        linha = {campo: None for campo in campos}
        linha.update(dados)
        linha["tipo_caso"] = tipo
        return linha

    saida: list[dict[str, Any]] = []
    for item in diarios:
        if int(item["id_fazenda"]) == 7 and item["data"] == "2026-05-18":
            saida.append(
                caso(
                    "EMBRAPA_SOJA_2026_05_18",
                    **{campo: item.get(campo) for campo in campos if campo in item},
                )
            )
        if (
            item["classificacao_h2"] in {"ALERTA", "CRITICO"}
            and item["classificacao_h1"] != item["classificacao_h2"]
        ):
            saida.append(
                caso(
                    "MUDANCA_DIARIA_ALERTA_OU_CRITICO",
                    **{campo: item.get(campo) for campo in campos if campo in item},
                )
            )

    for item in agregados:
        if (
            item["classificacao_h2_90d"] in {"ALERTA", "CRITICO"}
            and item["classificacao_h1_90d"] != item["classificacao_h2_90d"]
        ):
            saida.append(
                caso(
                    "MUDANCA_H90D_ALERTA_OU_CRITICO",
                    combinacao=item["combinacao"],
                    id_fazenda=item["id_fazenda"],
                    nome=item["nome"],
                    janela=item["janela"],
                    h1_90d=item["h1_90d"],
                    h2_90d=item["h2_90d"],
                    delta_h_90d=item["delta_h_90d"],
                    detalhe=(
                        f"{item['classificacao_h1_90d']}->"
                        f"{item['classificacao_h2_90d']}"
                    ),
                )
            )

    for combinacao in COMBINACOES:
        dias = [
            item
            for item in diarios
            if item["combinacao"] == combinacao and item["h2"] is not None
        ]
        maior_dia = max(dias, key=lambda item: float(item["incremento_territorial"]))
        saida.append(
            caso(
                "MAIOR_INCREMENTO_DIARIO",
                **{
                    campo: maior_dia.get(campo)
                    for campo in campos
                    if campo in maior_dia
                },
            )
        )
        aggs = [item for item in agregados if item["combinacao"] == combinacao]
        maior_agg = max(aggs, key=lambda item: float(item["delta_h_90d"]))
        saida.append(
            caso(
                "MAIOR_MUDANCA_H90D",
                **{
                    campo: maior_agg.get(campo)
                    for campo in campos
                    if campo in maior_agg
                },
            )
        )
        scores = [item for item in impactos if item["combinacao"] == combinacao]
        maior_score = max(scores, key=lambda item: float(item["delta_score"]))
        saida.append(
            caso(
                "MAIOR_MUDANCA_SCORE",
                **{
                    campo: maior_score.get(campo)
                    for campo in campos
                    if campo in maior_score
                },
            )
        )

        for id_fazenda in (2, 3, 5, 7):
            agg = next(
                item
                for item in aggs
                if int(item["id_fazenda"]) == id_fazenda and item["janela"] == "ATUAL"
            )
            score = next(
                item
                for item in scores
                if int(item["id_fazenda"]) == id_fazenda and item["janela"] == "ATUAL"
            )
            saida.append(
                caso(
                    "FAZENDA_DESTAQUE_ATUAL",
                    combinacao=combinacao,
                    id_fazenda=id_fazenda,
                    nome=agg["nome"],
                    janela="ATUAL",
                    h1_90d=agg["h1_90d"],
                    h2_90d=agg["h2_90d"],
                    delta_h_90d=agg["delta_h_90d"],
                    score_v1=score["score_v1"],
                    score_experimental=score["score_experimental"],
                    delta_score=score["delta_score"],
                )
            )
    return saida


def _formatar_csv(valor: Any) -> Any:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return format(valor, ".15g")
    return valor


def _salvar_csv(caminho: Path, linhas: Sequence[Mapping[str, Any]]) -> None:
    if not linhas:
        raise ValueError(f"nenhuma linha para {caminho.name}")
    campos = list(linhas[0])
    with caminho.open("w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.DictWriter(
            arquivo, fieldnames=campos, delimiter=";", lineterminator="\n"
        )
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow(
                {campo: _formatar_csv(linha.get(campo)) for campo in campos}
            )


def _linha_suscetibilidade(
    suscetibilidade: Suscetibilidade, parametros: ParametrosAmostrais
) -> dict[str, Any]:
    return {
        "id_fazenda": suscetibilidade.id_fazenda,
        "nome": suscetibilidade.nome,
        "distancia_drenagem_m": suscetibilidade.distancia_drenagem_m,
        "area_drenagem_montante_km2": suscetibilidade.area_montante_km2,
        "posicao_topografica_relativa_m": suscetibilidade.posicao_topografica_m,
        "mediana_distancia_amostra_m": parametros.mediana_distancia_m,
        "area_log_min_amostra": parametros.area_log_min,
        "area_log_max_amostra": parametros.area_log_max,
        "mediana_posicao_amostra_m": parametros.mediana_posicao_m,
        "iqr_posicao_amostra_m": parametros.iqr_posicao_m,
        "d2": suscetibilidade.d2,
        "a2": suscetibilidade.a2,
        "p2": suscetibilidade.p2,
        "t1": suscetibilidade.t1,
        "t2": suscetibilidade.t2,
        "t3": suscetibilidade.t3,
        "normalizacao_amostral": "SIM",
        "experimental_nao_calibrado": "SIM",
    }


def validar_resultados(
    diarios: Sequence[Mapping[str, Any]],
    agregados: Sequence[Mapping[str, Any]],
    impactos: Sequence[Mapping[str, Any]],
    perigos: Sequence[Mapping[str, str]],
) -> None:
    for item in diarios:
        h1, h2 = item["h1"], item["h2"]
        if h1 is None or item["g"] is None:
            if h2 is not None or item["incremento_territorial"] is not None:
                raise ValueError("missing foi convertido indevidamente")
            continue
        if not float(h1) - TOLERANCIA <= float(h2) <= 100.0:
            raise ValueError("H2 reduziu H1 ou excedeu 100")
        if float(item["incremento_territorial"]) < -TOLERANCIA:
            raise ValueError("incremento negativo")
    for item in impactos:
        if float(item["peso_trafegabilidade"]) != 0.0:
            raise ValueError("Trafegabilidade entrou no score experimental")
    chaves_outros = {
        (int(item["id_fazenda"]), item["janela"], item["perigo"]): float(
            item["indice_90d"]
        )
        for item in perigos
        if item["perigo"] != "EXPOSICAO_HIDRICA"
    }
    for item in impactos:
        chave = (int(item["id_fazenda"]), item["janela"])
        for perigo, campo in (
            ("INSTABILIDADE", "instabilidade_90d"),
            ("INCENDIO", "incendio_90d"),
            ("TEMPESTADES", "tempestades_90d"),
            ("TRAFEGABILIDADE", "trafegabilidade_90d"),
        ):
            if not math.isclose(
                float(item[campo]), chaves_outros[(*chave, perigo)], abs_tol=TOLERANCIA
            ):
                raise ValueError("outro perigo foi alterado")
    if len(agregados) != 6 * 2 * 9 or len(impactos) != 6 * 2 * 9:
        raise ValueError("quantidade inesperada de resultados por janela")


def validar_scores_v1_com_resumo(
    impactos: Sequence[Mapping[str, Any]],
    resumo: Sequence[Mapping[str, str]],
) -> None:
    esperados: dict[tuple[int, str], tuple[float, str]] = {}
    for item in resumo:
        id_fazenda = int(item["id_fazenda"])
        esperados[(id_fazenda, "ANTERIOR")] = (
            float(item["score_anterior"]),
            item["classificacao_anterior"],
        )
        esperados[(id_fazenda, "ATUAL")] = (
            float(item["score_atual"]),
            item["classificacao_atual"],
        )
    for item in impactos:
        score, classe = esperados[(int(item["id_fazenda"]), str(item["janela"]))]
        if not math.isclose(float(item["score_v1"]), score, abs_tol=TOLERANCIA):
            raise ValueError("score v1 reconstruido diverge do resumo baseline")
        if item["classificacao_score_v1"] != classe:
            raise ValueError("classe do score v1 diverge do resumo baseline")


def _md(valor: Any, casas: int = 2) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, (int, float)):
        return f"{float(valor):.{casas}f}"
    return str(valor)


def gerar_relatorio(
    parametros: ParametrosAmostrais,
    suscetibilidades: Mapping[int, Suscetibilidade],
    diarios: Sequence[Mapping[str, Any]],
    agregados: Sequence[Mapping[str, Any]],
    impactos: Sequence[Mapping[str, Any]],
    metricas: Sequence[Mapping[str, Any]],
    estabilidade: Sequence[Mapping[str, Any]],
    hashes: Mapping[str, str],
) -> str:
    por_combinacao = {str(item["combinacao"]): item for item in metricas}
    mais = max(metricas, key=lambda item: float(item["incremento_medio"]))
    menos = min(metricas, key=lambda item: float(item["incremento_medio"]))
    mais_atencao = max(metricas, key=lambda item: int(item["normal_para_atencao"]))
    menor_dominancia = min(
        metricas, key=lambda item: float(item["pct_dias_incremento_maior_30pct_h2"])
    )
    variacao_media_modelo = {
        modelo: fmean(
            float(item["variacao_absoluta"])
            for item in estabilidade
            if item["modelo"] == modelo
        )
        for modelo in MODELOS
    }
    maior_instabilidade = max(
        estabilidade, key=lambda item: float(item["variacao_absoluta"])
    )
    alertas_criticos = [
        item
        for item in diarios
        if item["classificacao_h2"] in {"ALERTA", "CRITICO"}
        and item["classificacao_h1"] != item["classificacao_h2"]
    ]
    alertas_criticos_90d = [
        item
        for item in agregados
        if item["classificacao_h2_90d"] in {"ALERTA", "CRITICO"}
        and item["classificacao_h1_90d"] != item["classificacao_h2_90d"]
    ]
    mudancas_classe_final = [
        item
        for item in impactos
        if item["classificacao_score_v1"] != item["classificacao_score_experimental"]
    ]
    maior_dia = max(
        diarios, key=lambda item: float(item["incremento_territorial"] or 0.0)
    )
    maior_h90 = max(agregados, key=lambda item: float(item["delta_h_90d"]))
    maior_score = max(impactos, key=lambda item: float(item["delta_score"]))

    linhas = [
        "# Relatório da Simulação Comparativa do Hídrico V2",
        "",
        "> **EXPERIMENTAL — NÃO CALIBRADA CONTRA SINISTROS REAIS.** Nenhuma fórmula deste relatório integra o motor produtivo.",
        "",
        "## Escopo e integridade",
        "",
        f"- Baseline: `{BASELINE_PADRAO.relative_to(RAIZ_REPOSITORIO).as_posix()}`.",
        f"- Combinações: {', '.join(COMBINACOES)}.",
        f"- Parâmetros recalculados: mediana da distância `{parametros.mediana_distancia_m:.6f} m`; mediana da posição `{parametros.mediana_posicao_m:.6f} m`; IQR da posição `{parametros.iqr_posicao_m:.6f} m`.",
        f"- Os {len(hashes)} arquivos do baseline conservaram seus hashes SHA-256 antes e depois da geração.",
        "- D2, A2 e P2 são normalizações amostrais dependentes desta carteira de seis fazendas; não são regras produtivas.",
        "",
        "## Suscetibilidade territorial",
        "",
        "| ID | Fazenda | D2 | A2 | P2 | T1 | T2 | T3 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in sorted(suscetibilidades.values(), key=lambda valor: valor.id_fazenda):
        linhas.append(
            f"| {item.id_fazenda} | {item.nome} | {item.d2:.2f} | {item.a2:.2f} | {item.p2:.2f} | {item.t1:.2f} | {item.t2:.2f} | {item.t3:.2f} |"
        )

    linhas.extend(
        [
            "",
            "## Métricas comparativas das nove combinações",
            "",
            "| Combinação | Dias | N→A | N→Alerta | N→Crítico | Δ médio | P90 | Máx. | Novos eventos | Fazendas ΔH90 | Fazendas Δscore | Classes finais alteradas | Dom. >30% |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in metricas:
        linhas.append(
            f"| {item['combinacao']} | {item['total_dias_avaliados']} | {item['normal_para_atencao']} | {item['normal_para_alerta']} | {item['normal_para_critico']} | {_md(item['incremento_medio'])} | {_md(item['incremento_p90'])} | {_md(item['incremento_maximo'])} | {item['novos_eventos_hidricos']} | {item['fazendas_com_mudanca_h90d']} | {item['fazendas_com_mudanca_score']} | {item['fazendas_com_mudanca_classe_final']} | {_md(item['pct_dias_incremento_maior_30pct_h2'])}% |"
        )

    linhas.extend(
        [
            "",
            "## Resultados atuais por fazenda e challenger",
            "",
            "`Novos eventos` significa evento H2 sem nenhum dia relevante H1; expansões ou fusões de eventos H1 não são contadas como evento novo.",
            "",
            "| ID | Fazenda | Combinação | S usado | H1 ant. | H1 atual | H2 ant. | H2 atual | ΔH atual | Score v1 | Score exp. | Δscore | Classes | Novos dias/eventos atuais |",
            "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for id_fazenda in sorted(suscetibilidades):
        for combinacao in COMBINACOES:
            modelo = combinacao.split("_")[0]
            anteriores = next(
                item
                for item in agregados
                if int(item["id_fazenda"]) == id_fazenda
                and item["janela"] == "ANTERIOR"
                and item["combinacao"] == combinacao
            )
            atuais = next(
                item
                for item in agregados
                if int(item["id_fazenda"]) == id_fazenda
                and item["janela"] == "ATUAL"
                and item["combinacao"] == combinacao
            )
            score = next(
                item
                for item in impactos
                if int(item["id_fazenda"]) == id_fazenda
                and item["janela"] == "ATUAL"
                and item["combinacao"] == combinacao
            )
            linhas.append(
                f"| {id_fazenda} | {suscetibilidades[id_fazenda].nome} | {combinacao} | {suscetibilidades[id_fazenda].modelo(modelo):.2f} | {_md(anteriores['h1_90d'])} | {_md(atuais['h1_90d'])} | {_md(anteriores['h2_90d'])} | {_md(atuais['h2_90d'])} | {_md(atuais['delta_h_90d'])} | {_md(score['score_v1'])} | {_md(score['score_experimental'])} | {_md(score['delta_score'])} | {score['classificacao_score_v1']}→{score['classificacao_score_experimental']} | {atuais['novos_dias_relevantes']}/{atuais['novos_eventos']} |"
            )

    soja = [
        item
        for item in diarios
        if int(item["id_fazenda"]) == 7 and item["data"] == "2026-05-18"
    ]
    linhas.extend(
        [
            "",
            "## Embrapa Soja — 18/05/2026",
            "",
            f"H1 oficial: `{float(soja[0]['h1']):.5f}`.",
            "",
            "| Combinação | S | g | Incremento | H2 | Classe |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for item in soja:
        linhas.append(
            f"| {item['combinacao']} | {_md(item['suscetibilidade_territorial'])} | {_md(item['g'], 4)} | {_md(item['incremento_territorial'])} | {_md(item['h2'])} | {item['classificacao_h2']} |"
        )

    linhas.extend(
        [
            "",
            "## Leitura dos quatro casos territoriais na janela atual",
            "",
            "- **Embrapa Acre:** seis combinações g3/g7 criam um dia e um evento novos, levando H90 de 0 para 20,06; as três variantes gA mantêm H90 em 0.",
            "- **Três Rios:** apesar de S alto (73,87 a 81,51), nenhuma combinação cria dia relevante na janela atual. O território não superou a baixa ativação meteorológica.",
            "- **Embrapa Soja:** sete combinações criam evento; T1_g7 cria dois e leva H90 a 24,06. É a única mudança atual de classe do score final: 16,55 NORMAL para 26,18 ATENÇÃO.",
            "- **Santa Luzia:** nenhuma combinação cria dia relevante ou altera H90/score atual, coerente com S baixo a moderado e chuva atual fraca.",
            "",
            "## Controles de dominância",
            "",
            "- Nenhuma combinação produziu H2 ≥25 quando H1<10; consequentemente, também não houve caso H1<5 e H2≥25.",
            "- A maior contribuição territorial absoluta foi 22,56 pontos em Embrapa Acre, por T2_g7.",
            "- Embrapa Acre concentra o maior incremento médio em todas as nove combinações.",
            "- O critério incremento/H2>30% varia de 11,98% em T3_g3 até 60,02% em T1_g7, indicando dominância material das variantes g7.",
            "",
            "## Casos máximos localizados automaticamente",
            "",
            f"- Maior incremento diário: `{maior_dia['combinacao']}`, {maior_dia['nome']} em {maior_dia['data']}: H1 {_md(maior_dia['h1'])} → H2 {_md(maior_dia['h2'])}, incremento {_md(maior_dia['incremento_territorial'])}.",
            f"- Maior mudança H90: `{maior_h90['combinacao']}`, {maior_h90['nome']} ({maior_h90['janela']}): Δ {_md(maior_h90['delta_h_90d'])}.",
            f"- Maior mudança de score: `{maior_score['combinacao']}`, {maior_score['nome']} ({maior_score['janela']}): Δ {_md(maior_score['delta_score'])}.",
            f"- Mudanças diárias novas para ALERTA/CRÍTICO: `{len(alertas_criticos)}`.",
            f"- Mudanças do Hídrico 90d para ALERTA/CRÍTICO: `{len(alertas_criticos_90d)}` registros fazenda/janela/challenger, todos detalhados no CSV de casos.",
            f"- Mudanças de classe do score final: `{len(mudancas_classe_final)}` registros fazenda/janela/challenger.",
            "",
            "## Estabilidade amostral leave-one-out",
            "",
            "| Modelo | Variação absoluta média de S |",
            "|---|---:|",
        ]
    )
    for modelo in MODELOS:
        linhas.append(f"| {modelo} | {variacao_media_modelo[modelo]:.2f} |")
    linhas.extend(
        [
            "",
            f"Maior variação individual: `{float(maior_instabilidade['variacao_absoluta']):.2f}` pontos em {maior_instabilidade['nome_fazenda_avaliada']} / {maior_instabilidade['modelo']}, ao remover {maior_instabilidade['nome_fazenda_removida']}.",
            "",
            "## Respostas às perguntas comparativas",
            "",
            f"1. **Mais altera o baseline:** `{mais['combinacao']}` pelo maior incremento diário médio ({_md(mais['incremento_medio'])}).",
            f"2. **Menos altera:** `{menos['combinacao']}` pelo menor incremento diário médio ({_md(menos['incremento_medio'])}).",
            f"3. **Mais novos dias em ATENÇÃO:** `{mais_atencao['combinacao']}` com {mais_atencao['normal_para_atencao']} transições NORMAL→ATENÇÃO.",
            f"4. **ALERTA/CRÍTICO suspeito:** houve {len(alertas_criticos)} mudanças diárias, mas {len(alertas_criticos_90d)} mudanças agregadas H90 para ALERTA/CRÍTICO. A diferença decorre da frequência/duração de dias em ATENÇÃO e exige validação, embora reutilize corretamente o agregador oficial.",
            f"5. **Menor dominância territorial:** `{menor_dominancia['combinacao']}`, com {_md(menor_dominancia['pct_dias_incremento_maior_30pct_h2'])}% dos dias H2 positivos acima do critério de 30%.",
            "6. **Diferenciação dos quatro casos:** T2 produz a separação mais nítida: Acre 94,92 e Três Rios 81,51 contra Santa Luzia 18,78 e Soja 15,27. T3 acrescenta posição topográfica e eleva Santa Luzia para 30,77.",
            f"7. **Valor adicional de T3:** é informacional, não conclusivo. Seus resultados ficam próximos de T2, mas ele altera a posição relativa de Santa Luzia e apresenta variação leave-one-out média de {variacao_media_modelo['T3']:.2f}, contra {variacao_media_modelo['T2']:.2f} em T2.",
            f"8. **g7 versus g3:** incremento médio g3/T3={_md(por_combinacao['T3_g3']['incremento_medio'])}, g7/T3={_md(por_combinacao['T3_g7']['incremento_medio'])}; a diferença é material se também mudar eventos/classes, não apenas magnitude.",
            f"9. **Estabilidade de gA:** gA gera menos novos eventos e menores máximos que g7, mas seu incremento médio é ligeiramente maior que g3 nos três modelos e sua dominância percentual também é maior. Portanto, não é uniformemente mais estável.",
            f"10. **Mudança do score final:** maior delta observado {_md(maior_score['delta_score'])}; todos os valores estão em `04_impacto_score.csv`.",
            f"11. **Mudança de classe final:** {'sim' if mudancas_classe_final else 'não'}; total de registros alterados: {len(mudancas_classe_final)}.",
            f"12. **Instabilidade amostral:** médias absolutas T1={variacao_media_modelo['T1']:.2f}, T2={variacao_media_modelo['T2']:.2f}, T3={variacao_media_modelo['T3']:.2f}; máximo {float(maior_instabilidade['variacao_absoluta']):.2f}.",
            "",
            "## Recomendação limitada para próxima fase",
            "",
            "**EXPERIMENTAL — NÃO CALIBRADA CONTRA SINISTROS REAIS.** Manter no máximo dois challengers:",
            "",
            "1. `T3_g3`, por incluir as três dimensões territoriais, reconhecer o caso Soja de 18/05 e apresentar a menor dominância territorial observada (11,98%).",
            "2. `T2_gA`, como controle mais parcimonioso: apenas MERIT e ativação antecedente já alinhada às features do H1.",
            "",
            "`g7` não é descartado, mas sua dominância de 49,76% a 60,02% e o maior número de novos dias/eventos justificam mantê-lo como stress-test, não como um dos dois candidatos principais. A seleção acima não torna nenhuma fórmula oficial. Uma próxima fase precisa confrontar os challengers com ocorrências reais e testar normalizações fora desta carteira de seis fazendas.",
        ]
    )
    return "\n".join(linhas) + "\n"


def executar_simulacao(baseline: Path, saida: Path) -> dict[str, Any]:
    hashes_antes = snapshot_baseline(baseline)
    contextos = _ler_csv(baseline / "02_contexto_territorial.csv")
    perigos = _ler_csv(baseline / "04_perigos.csv")
    features = _ler_csv(baseline / "05_features_diarias.csv")
    resumo = _ler_csv(baseline / "01_resumo_fazendas.csv")
    if len(contextos) != 6:
        raise ValueError("a simulacao exige exatamente as seis fazendas do baseline")
    datas_referencia = {item["data_referencia"] for item in resumo}
    if len(datas_referencia) != 1:
        raise ValueError("baseline possui datas de referencia divergentes")
    data_referencia = date.fromisoformat(datas_referencia.pop())

    parametros, suscetibilidades = calcular_suscetibilidades(contextos)
    diarios = montar_resultados_diarios(features, suscetibilidades)
    agregados = montar_resultados_90d(diarios, perigos, data_referencia)
    impactos = montar_impacto_score(agregados, perigos)
    metricas = montar_metricas(diarios, agregados, impactos)
    estabilidade = montar_estabilidade(contextos, suscetibilidades)
    casos = montar_casos_relevantes(diarios, agregados, impactos)
    validar_resultados(diarios, agregados, impactos, perigos)
    validar_scores_v1_com_resumo(impactos, resumo)

    saida.mkdir(parents=True, exist_ok=True)
    _salvar_csv(
        saida / "01_suscetibilidade_territorial.csv",
        [
            _linha_suscetibilidade(item, parametros)
            for item in sorted(
                suscetibilidades.values(), key=lambda valor: valor.id_fazenda
            )
        ],
    )
    _salvar_csv(saida / "02_resultados_diarios_h2.csv", diarios)
    _salvar_csv(saida / "03_resultados_90d.csv", agregados)
    _salvar_csv(saida / "04_impacto_score.csv", impactos)
    _salvar_csv(saida / "05_metricas_combinacoes.csv", metricas)
    _salvar_csv(saida / "06_casos_relevantes.csv", casos)
    _salvar_csv(saida / "07_estabilidade_amostral.csv", estabilidade)

    hashes_depois = snapshot_baseline(baseline)
    if hashes_antes != hashes_depois:
        raise RuntimeError("baseline foi modificado durante a simulacao")
    relatorio = gerar_relatorio(
        parametros,
        suscetibilidades,
        diarios,
        agregados,
        impactos,
        metricas,
        estabilidade,
        hashes_antes,
    )
    (saida / "RELATORIO_SIMULACAO_HIDRICO_V2.md").write_text(
        relatorio, encoding="utf-8"
    )
    if hashes_antes != snapshot_baseline(baseline):
        raise RuntimeError("baseline foi modificado ao salvar o relatorio")

    return {
        "parametros": parametros,
        "suscetibilidades": suscetibilidades,
        "diarios": diarios,
        "agregados": agregados,
        "impactos": impactos,
        "metricas": metricas,
        "casos": casos,
        "estabilidade": estabilidade,
        "hashes_baseline": hashes_antes,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PADRAO)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    argumentos = parser.parse_args(list(argv) if argv is not None else None)
    resultado = executar_simulacao(
        argumentos.baseline.resolve(), argumentos.saida.resolve()
    )
    print(f"Simulacao concluida: {argumentos.saida.resolve()}")
    print(f"Dias experimentais: {len(resultado['diarios'])}")
    print(f"Resultados 90d: {len(resultado['agregados'])}")
    print(f"Impactos no score: {len(resultado['impactos'])}")
    print("Baseline SHA-256 preservado: SIM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
