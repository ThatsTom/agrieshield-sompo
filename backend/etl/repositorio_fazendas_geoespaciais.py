"""Persistência CSV do resultado geoespacial vigente de cada fazenda."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
ARQUIVO_FAZENDAS_GEOESPACIAIS = PASTA_DADOS / "fazendas_geoespaciais.csv"

COLUNAS_GEOESPACIAIS = [
    "id_fazenda",
    "status",
    "latitude_referencia",
    "longitude_referencia",
    "area_ha_referencia",
    "raio_equivalente_m",
    "metodo_geometria",
    "raio_analise_m",
    "limiar_drenagem_km2",
    "raio_busca_drenagem_m",
    "declividade_media_graus",
    "posicao_topografica_relativa_m",
    "distancia_drenagem_m",
    "area_drenagem_montante_km2",
    "schema_version",
    "algorithm_version",
    "fontes_json",
    "qualidade_json",
    "erros_json",
    "cache_chave",
    "input_fingerprint",
    "calculado_em_utc",
]


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _float_opcional(valor: Any) -> Optional[float]:
    if valor in (None, ""):
        return None
    numero = float(valor)
    return numero if math.isfinite(numero) else None


def calcular_raio_equivalente_m(area_ha: Any) -> Optional[float]:
    area = _float_opcional(area_ha)
    if area is None:
        return None
    if area <= 0:
        raise ValueError("area_ha deve ser maior que zero")
    return math.sqrt(area * 10_000.0 / math.pi)


def criar_base_geoespacial_se_nao_existir() -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    if ARQUIVO_FAZENDAS_GEOESPACIAIS.exists():
        return
    with open(
        ARQUIVO_FAZENDAS_GEOESPACIAIS, "w", newline="", encoding="utf-8-sig"
    ) as f:
        csv.DictWriter(f, fieldnames=COLUNAS_GEOESPACIAIS, delimiter=";").writeheader()


def listar_registros_geoespaciais() -> List[Dict[str, str]]:
    criar_base_geoespacial_se_nao_existir()
    with open(
        ARQUIVO_FAZENDAS_GEOESPACIAIS, "r", encoding="utf-8-sig", newline=""
    ) as f:
        return list(csv.DictReader(f, delimiter=";"))


def buscar_registro_geoespacial(id_fazenda: str) -> Optional[Dict[str, Any]]:
    for registro in listar_registros_geoespaciais():
        if str(registro.get("id_fazenda")) == str(id_fazenda):
            return normalizar_registro_geoespacial(registro)
    return None


def _valor_atributo(resultado: Dict[str, Any], nome: str) -> Any:
    return resultado.get("atributos", {}).get(nome, {}).get("valor")


def _fingerprint(fazenda: Dict[str, Any], resultado: Dict[str, Any]) -> str:
    payload = {
        "latitude": _float_opcional(fazenda.get("latitude")),
        "longitude": _float_opcional(fazenda.get("longitude")),
        "area_ha": _float_opcional(fazenda.get("area_ha")),
        "parametros": resultado.get("parametros", {}),
        "schema_version": resultado.get("schema_version"),
        "algorithm_version": resultado.get("algorithm_version"),
        "fontes": resultado.get("fontes", []),
    }
    bruto = json.dumps(
        payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def montar_registro_geoespacial(
    fazenda: Dict[str, Any], resultado: Dict[str, Any]
) -> Dict[str, str]:
    area = _float_opcional(fazenda.get("area_ha"))
    raio = calcular_raio_equivalente_m(area)
    parametros = resultado.get("parametros", {})
    registro = {
        "id_fazenda": str(fazenda["id_fazenda"]),
        "status": str(resultado.get("status") or "erro"),
        "latitude_referencia": fazenda.get("latitude", ""),
        "longitude_referencia": fazenda.get("longitude", ""),
        "area_ha_referencia": "" if area is None else area,
        "raio_equivalente_m": "" if raio is None else raio,
        "metodo_geometria": "" if raio is None else "circulo_equivalente_por_area",
        "raio_analise_m": parametros.get("raio_analise_m", 1000),
        "limiar_drenagem_km2": parametros.get("limiar_drenagem_km2", 10),
        "raio_busca_drenagem_m": parametros.get("raio_busca_drenagem_m", 50000),
        "declividade_media_graus": _valor_atributo(resultado, "declividade_media"),
        "posicao_topografica_relativa_m": _valor_atributo(
            resultado, "posicao_topografica_relativa"
        ),
        "distancia_drenagem_m": _valor_atributo(resultado, "distancia_drenagem"),
        "area_drenagem_montante_km2": _valor_atributo(
            resultado, "area_drenagem_montante"
        ),
        "schema_version": resultado.get("schema_version", ""),
        "algorithm_version": resultado.get("algorithm_version", ""),
        "fontes_json": _json(resultado.get("fontes", [])),
        "qualidade_json": _json(resultado.get("qualidade", {})),
        "erros_json": _json(resultado.get("erros", [])),
        "cache_chave": resultado.get("cache", {}).get("chave", ""),
        "input_fingerprint": _fingerprint(fazenda, resultado),
        "calculado_em_utc": datetime.now(timezone.utc).isoformat(),
    }
    return {
        coluna: "" if registro.get(coluna) is None else str(registro.get(coluna, ""))
        for coluna in COLUNAS_GEOESPACIAIS
    }


def upsert_registro_geoespacial(registro: Dict[str, Any]) -> Dict[str, Any]:
    criar_base_geoespacial_se_nao_existir()
    id_fazenda = str(registro.get("id_fazenda") or "")
    if not id_fazenda:
        raise ValueError("id_fazenda é obrigatório")
    linha = {
        coluna: "" if registro.get(coluna) is None else str(registro.get(coluna, ""))
        for coluna in COLUNAS_GEOESPACIAIS
    }
    existentes = listar_registros_geoespaciais()
    atualizados = [
        item for item in existentes if str(item.get("id_fazenda")) != id_fazenda
    ]
    atualizados.append(linha)

    temporario = ARQUIVO_FAZENDAS_GEOESPACIAIS.with_name(
        f".{ARQUIVO_FAZENDAS_GEOESPACIAIS.name}.{uuid4().hex}.tmp"
    )
    try:
        with open(temporario, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUNAS_GEOESPACIAIS, delimiter=";")
            writer.writeheader()
            writer.writerows(atualizados)
        os.replace(temporario, ARQUIVO_FAZENDAS_GEOESPACIAIS)
    finally:
        if temporario.exists():
            temporario.unlink()
    return normalizar_registro_geoespacial(linha)


def salvar_resultado_geoespacial(
    fazenda: Dict[str, Any], resultado: Dict[str, Any]
) -> Dict[str, Any]:
    return upsert_registro_geoespacial(montar_registro_geoespacial(fazenda, resultado))


def normalizar_registro_geoespacial(registro: Dict[str, Any]) -> Dict[str, Any]:
    retorno = dict(registro)
    numericos = [
        "latitude_referencia",
        "longitude_referencia",
        "area_ha_referencia",
        "raio_equivalente_m",
        "raio_analise_m",
        "limiar_drenagem_km2",
        "raio_busca_drenagem_m",
        "declividade_media_graus",
        "posicao_topografica_relativa_m",
        "distancia_drenagem_m",
        "area_drenagem_montante_km2",
    ]
    for campo in numericos:
        retorno[campo] = _float_opcional(retorno.get(campo))
    for campo in ("fontes_json", "qualidade_json", "erros_json"):
        nome = campo.removesuffix("_json")
        bruto = retorno.pop(campo, "")
        padrao = "{}" if campo == "qualidade_json" else "[]"
        try:
            retorno[nome] = json.loads(bruto or padrao)
        except (ValueError, TypeError):
            retorno[nome] = {} if campo == "qualidade_json" else []
    return retorno


__all__ = [
    "ARQUIVO_FAZENDAS_GEOESPACIAIS",
    "COLUNAS_GEOESPACIAIS",
    "buscar_registro_geoespacial",
    "calcular_raio_equivalente_m",
    "criar_base_geoespacial_se_nao_existir",
    "listar_registros_geoespaciais",
    "montar_registro_geoespacial",
    "salvar_resultado_geoespacial",
    "upsert_registro_geoespacial",
]
