"""Orquestração MapBiomas por fazenda, isolada dos fluxos de risco."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Callable, Dict, Optional

from .cliente import (
    ANO_DEFAULT,
    ANO_FINAL,
    ANO_INICIAL,
    ASSET_ID,
    ASSET_VERSION,
    COLECAO,
    ClienteEarthEngineMapBiomas,
    ErroDadosMapBiomas,
    banda_para_ano,
)
from .legenda import (
    CATEGORIAS,
    CODIGOS_NAO_OBSERVADOS,
    LEGENDA_VERSION,
    agregar_areas,
    nome_classe,
)
from .repositorio import RepositorioMapBiomas


SCHEMA_VERSION = "1"
ALGORITHM_VERSION = "mapbiomas-territorial-v1"
WARNING_GEOMETRIA = (
    "Geometria circular estimada por área e coordenada de CEP; não representa "
    "o limite real, cadastral ou fundiário da propriedade e pode incluir áreas vizinhas."
)


class FazendaMapBiomasNaoEncontrada(LookupError):
    pass


class ResultadoMapBiomasNaoEncontrado(LookupError):
    pass


class ErroDominioMapBiomas(ValueError):
    """Entrada da fazenda incompatível com uma análise territorial."""


def _numero_finito(valor: Any, campo: str) -> float:
    if valor in (None, "") or isinstance(valor, bool):
        raise ErroDominioMapBiomas(f"{campo} é obrigatório")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ErroDominioMapBiomas(f"{campo} deve ser numérico") from exc
    if not math.isfinite(numero):
        raise ErroDominioMapBiomas(f"{campo} deve ser finito")
    return numero


def calcular_raio_equivalente_m(area_ha: Any) -> float:
    area = _numero_finito(area_ha, "area_ha")
    if area <= 0:
        raise ErroDominioMapBiomas("area_ha deve ser positiva")
    return math.sqrt(area * 10_000.0 / math.pi)


def _normalizar_referencia(fazenda: Dict[str, Any]) -> Dict[str, float]:
    latitude = _numero_finito(fazenda.get("latitude"), "latitude")
    longitude = _numero_finito(fazenda.get("longitude"), "longitude")
    area_ha = _numero_finito(fazenda.get("area_ha"), "area_ha")
    if not -90 <= latitude <= 90:
        raise ErroDominioMapBiomas("latitude deve estar entre -90 e 90")
    if not -180 <= longitude <= 180:
        raise ErroDominioMapBiomas("longitude deve estar entre -180 e 180")
    if area_ha <= 0:
        raise ErroDominioMapBiomas("area_ha deve ser positiva")
    return {"latitude": latitude, "longitude": longitude, "area_ha": area_ha}


def _area_finita(valor: Any, campo: str) -> float:
    if valor in (None, "") or isinstance(valor, bool):
        raise ErroDadosMapBiomas(f"Resposta MapBiomas sem {campo}")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ErroDadosMapBiomas(f"Resposta MapBiomas com {campo} inválida") from exc
    if not math.isfinite(numero):
        raise ErroDadosMapBiomas(f"Resposta MapBiomas com {campo} inválida")
    if numero < 0:
        raise ErroDadosMapBiomas(f"Resposta MapBiomas com {campo} negativa")
    return numero


def _normalizar_grupos(grupos: Any) -> Dict[int, float]:
    if not isinstance(grupos, list):
        raise ErroDadosMapBiomas("Resposta MapBiomas sem distribuição de classes")
    distribuicao: Dict[int, float] = {}
    for grupo in grupos:
        if not isinstance(grupo, dict) or "codigo" not in grupo or "sum" not in grupo:
            raise ErroDadosMapBiomas("Distribuição de classes MapBiomas inválida")
        try:
            codigo_numero = float(grupo["codigo"])
        except (TypeError, ValueError) as exc:
            raise ErroDadosMapBiomas("Código de classe MapBiomas inválido") from exc
        if not math.isfinite(codigo_numero) or not codigo_numero.is_integer():
            raise ErroDadosMapBiomas("Código de classe MapBiomas inválido")
        codigo = int(codigo_numero)
        area_m2 = _area_finita(grupo["sum"], "area_m2 da classe")
        distribuicao[codigo] = distribuicao.get(codigo, 0.0) + area_m2
    return distribuicao


def _fingerprint(
    *,
    latitude: float,
    longitude: float,
    area_ha: float,
    raio_equivalente_m: float,
    asset_id: str,
    ano: int,
    banda: str,
) -> str:
    conteudo = {
        "latitude": latitude,
        "longitude": longitude,
        "area_ha": area_ha,
        "raio_equivalente_m": raio_equivalente_m,
        "asset_id": asset_id,
        "colecao": COLECAO,
        "asset_version": ASSET_VERSION,
        "ano": ano,
        "banda": banda,
        "versao_legenda": LEGENDA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
    }
    serializado = json.dumps(
        conteudo,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


class ServicoMapBiomas:
    def __init__(
        self,
        *,
        cliente: ClienteEarthEngineMapBiomas,
        repositorio: RepositorioMapBiomas,
        buscar_fazenda: Callable[[str], Optional[Dict[str, Any]]],
        agora_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._cliente = cliente
        self._repositorio = repositorio
        self._buscar_fazenda = buscar_fazenda
        self._agora_utc = agora_utc or (lambda: datetime.now(timezone.utc))

    def _fazenda(self, id_fazenda: str) -> Dict[str, Any]:
        fazenda = self._buscar_fazenda(str(id_fazenda))
        if not fazenda:
            raise FazendaMapBiomasNaoEncontrada("Fazenda não encontrada")
        return fazenda

    def analisar(
        self,
        id_fazenda: str,
        *,
        ano: int = ANO_DEFAULT,
    ) -> Dict[str, Any]:
        fazenda = self._fazenda(id_fazenda)
        referencia = _normalizar_referencia(fazenda)
        if isinstance(ano, bool):
            raise ErroDominioMapBiomas("ano de referência inválido")
        try:
            ano = int(ano)
        except (TypeError, ValueError) as exc:
            raise ErroDominioMapBiomas("ano de referência inválido") from exc
        if not ANO_INICIAL <= ano <= ANO_FINAL:
            raise ErroDominioMapBiomas(
                f"ano deve estar entre {ANO_INICIAL} e {ANO_FINAL}"
            )

        raio = calcular_raio_equivalente_m(referencia["area_ha"])
        bruto = self._cliente.reduzir_territorio(
            latitude=referencia["latitude"],
            longitude=referencia["longitude"],
            raio_equivalente_m=raio,
            ano=ano,
        )
        distribuicao_total = _normalizar_grupos(bruto.get("grupos"))
        area_geometria = _area_finita(
            bruto.get("area_geometria_m2"), "area_geometria_m2"
        )
        area_grade = _area_finita(bruto.get("area_grade_m2"), "area_grade_m2")
        area_mapeada = sum(distribuicao_total.values())
        if area_mapeada > area_grade + max(1.0, area_grade * 0.000001):
            raise ErroDadosMapBiomas(
                "Área classificada MapBiomas excede a grade territorial analisada"
            )
        area_codigo_27 = sum(
            area
            for codigo, area in distribuicao_total.items()
            if codigo in CODIGOS_NAO_OBSERVADOS
        )
        area_no_data = max(0.0, area_grade - area_mapeada)
        area_valida = area_mapeada - area_codigo_27
        if area_grade <= 0:
            raise ErroDadosMapBiomas("A geometria não produziu pixels analisáveis")
        if area_valida <= 0:
            raise ErroDadosMapBiomas(
                "A geometria não possui cobertura MapBiomas válida"
            )

        distribuicao_valida = {
            codigo: area
            for codigo, area in distribuicao_total.items()
            if codigo not in CODIGOS_NAO_OBSERVADOS
        }
        distribuicao_bruta = [
            {
                "codigo": codigo,
                "nome": nome_classe(codigo),
                "area_m2": round(area, 3),
                "percentual_area_valida": round(area * 100.0 / area_valida, 6),
            }
            for codigo, area in sorted(distribuicao_valida.items())
        ]

        areas_categorias = agregar_areas(distribuicao_valida)
        percentuais = {
            categoria: round(areas_categorias[categoria] * 100.0 / area_valida, 6)
            for categoria in CATEGORIAS
        }
        predominante = min(
            distribuicao_valida,
            key=lambda codigo: (-distribuicao_valida[codigo], codigo),
        )
        banda_resultado = banda_para_ano(ano)
        if bruto.get("banda") != banda_resultado:
            raise ErroDadosMapBiomas(
                "Resposta MapBiomas com banda incompatível com o ano solicitado"
            )
        asset_resultado = str(bruto.get("asset_id") or ASSET_ID)
        fingerprint = _fingerprint(
            latitude=referencia["latitude"],
            longitude=referencia["longitude"],
            area_ha=referencia["area_ha"],
            raio_equivalente_m=raio,
            asset_id=asset_resultado,
            ano=ano,
            banda=banda_resultado,
        )
        resultado = {
            "id_fazenda": str(id_fazenda),
            "referencia": {
                **referencia,
                "raio_equivalente_m": raio,
                "tipo_geometria": "ESTIMADA",
                "metodo_geometria": "circulo_equivalente_por_area",
                "origem_coordenada": "CEP",
                "precisao_espacial": "APROXIMADA",
            },
            "mapbiomas": {
                "asset_id": asset_resultado,
                "colecao": COLECAO,
                "asset_version": ASSET_VERSION,
                "ano_referencia": ano,
                "banda": banda_resultado,
                "versao_legenda": LEGENDA_VERSION,
                "algorithm_version": ALGORITHM_VERSION,
            },
            "cobertura": {
                "classe_predominante_codigo": predominante,
                "classe_predominante_nome": nome_classe(predominante),
                "agricultura_pct": percentuais["agricultura"],
                "pastagem_pct": percentuais["pastagem"],
                "vegetacao_nativa_pct": percentuais["vegetacao_nativa"],
                "agua_pct": percentuais["agua"],
                "outros_pct": percentuais["outros"],
            },
            "qualidade": {
                "area_nominal_m2": referencia["area_ha"] * 10_000.0,
                "area_geometria_m2": round(area_geometria, 3),
                "area_grade_analisada_m2": round(area_grade, 3),
                "area_mapeada_m2": round(area_mapeada, 3),
                "area_valida_m2": round(area_valida, 3),
                "area_nao_observada_m2": round(area_codigo_27 + area_no_data, 3),
                "area_codigo_27_m2": round(area_codigo_27, 3),
                "area_no_data_m2": round(area_no_data, 3),
                "cobertura_valida_pct": round(area_valida * 100.0 / area_grade, 6),
                "soma_percentuais_validos": round(sum(percentuais.values()), 6),
            },
            "distribuicao_bruta": distribuicao_bruta,
            "metadados": {
                "fonte": "MAPBIOMAS",
                "calculado_em_utc": self._agora_utc()
                .astimezone(timezone.utc)
                .isoformat(),
                "schema_version": SCHEMA_VERSION,
                "input_fingerprint": fingerprint,
                "warning_geometria": WARNING_GEOMETRIA,
            },
        }
        return self._repositorio.salvar(str(id_fazenda), resultado)

    def obter(self, id_fazenda: str) -> Dict[str, Any]:
        self._fazenda(id_fazenda)
        resultado = self._repositorio.buscar(str(id_fazenda))
        if resultado is None:
            raise ResultadoMapBiomasNaoEncontrado(
                "Análise MapBiomas não encontrada para a fazenda"
            )
        return resultado


__all__ = [
    "ALGORITHM_VERSION",
    "ErroDominioMapBiomas",
    "FazendaMapBiomasNaoEncontrada",
    "ResultadoMapBiomasNaoEncontrado",
    "SCHEMA_VERSION",
    "ServicoMapBiomas",
    "WARNING_GEOMETRIA",
    "calcular_raio_equivalente_m",
]
