"""Provider local do contexto SRTM/MERIT persistido pela Etapa 4."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
import json
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any

from backend.app.servico_avaliacao_exposicao import (
    ContextoTerritorialIncompativel,
    ContextoTerritorialIndisponivel,
)
from backend.etl.etapa4_dados_geoespaciais import (
    MERIT_ID,
    PASTA_CACHE,
    SRTM_ID,
)
from backend.etl.repositorio_fazendas_geoespaciais import (
    buscar_registro_geoespacial,
)
from backend.risco.modelos import AnaliseGeoespacialNormalizada
from backend.risco.normalizacao import normalizar_geoespacial


TOLERANCIA_COORDENADA_GRAUS = 1e-6
CHAVE_CACHE_RE = re.compile(r"^[0-9a-f]{64}$")
ATRIBUTOS_PERSISTIDOS = {
    "declividade_media_graus": "declividade_media",
    "posicao_topografica_relativa_m": "posicao_topografica_relativa",
    "distancia_drenagem_m": "distancia_drenagem",
    "area_drenagem_montante_km2": "area_drenagem_montante",
}
PARAMETROS_PERSISTIDOS = (
    "raio_analise_m",
    "limiar_drenagem_km2",
    "raio_busca_drenagem_m",
)


class CarregadorCacheGeoespacialJson:
    """Le somente o JSON indicado pelo registro vigente da fazenda."""

    def __init__(self, diretorio: Path = PASTA_CACHE) -> None:
        self._diretorio = Path(diretorio)

    def carregar(self, chave: str) -> Mapping[str, Any] | None:
        if not isinstance(chave, str) or not CHAVE_CACHE_RE.fullmatch(chave):
            return None
        try:
            with (self._diretorio / f"{chave}.json").open(
                "r",
                encoding="utf-8",
            ) as arquivo:
                payload = json.load(arquivo)
        except (OSError, ValueError, TypeError):
            return None
        return payload if isinstance(payload, Mapping) else None

    def existe(self, chave: str) -> bool:
        """Distingue cache ausente de um arquivo existente, mas invalido."""

        if not isinstance(chave, str) or not CHAVE_CACHE_RE.fullmatch(chave):
            return False
        try:
            return (self._diretorio / f"{chave}.json").is_file()
        except OSError:
            return False


def _numero_finito(valor: Any) -> float:
    if isinstance(valor, bool):
        raise ValueError("valor numerico invalido")
    numero = float(valor)
    if not isfinite(numero):
        raise ValueError("valor numerico nao finito")
    return numero


def _coordenadas_compativeis(
    latitude_a: Any,
    longitude_a: Any,
    latitude_b: Any,
    longitude_b: Any,
) -> bool:
    try:
        lat_a = _numero_finito(latitude_a)
        lon_a = _numero_finito(longitude_a)
        lat_b = _numero_finito(latitude_b)
        lon_b = _numero_finito(longitude_b)
    except (TypeError, ValueError):
        return False
    return (
        -90 <= lat_a <= 90
        and -90 <= lat_b <= 90
        and -180 <= lon_a <= 180
        and -180 <= lon_b <= 180
        and isclose(
            lat_a,
            lat_b,
            rel_tol=0,
            abs_tol=TOLERANCIA_COORDENADA_GRAUS,
        )
        and isclose(
            lon_a,
            lon_b,
            rel_tol=0,
            abs_tol=TOLERANCIA_COORDENADA_GRAUS,
        )
    )


def _valores_equivalentes(valor_a: Any, valor_b: Any) -> bool:
    if valor_a is None or valor_b is None:
        return valor_a is None and valor_b is None
    try:
        numero_a = _numero_finito(valor_a)
        numero_b = _numero_finito(valor_b)
    except (TypeError, ValueError):
        return False
    return isclose(numero_a, numero_b, rel_tol=0, abs_tol=1e-9)


def _fonte_persistida(
    fontes: Any,
    identificador: str,
) -> Mapping[str, Any]:
    if not isinstance(fontes, list):
        raise ValueError("fontes geoespaciais ausentes")
    for fonte in fontes:
        if isinstance(fonte, Mapping) and fonte.get("identificador") == identificador:
            _numero_finito(fonte.get("resolucao_m"))
            return fonte
    raise ValueError(f"fonte geoespacial ausente: {identificador}")


def _atributo_reconstruido(
    valor: Any,
    *,
    unidade: str,
    metodologia: str,
    fonte: Mapping[str, Any],
    banda: str,
) -> dict[str, Any]:
    if valor is not None:
        valor = _numero_finito(valor)
    return {
        "valor": valor,
        "unidade": unidade,
        "status": "disponivel" if valor is not None else "indisponivel",
        "metodologia": metodologia,
        "fonte": str(fonte["identificador"]),
        "banda": banda,
        "resolucao_m": _numero_finito(fonte["resolucao_m"]),
    }


def _reconstruir_payload_persistido(
    registro: Mapping[str, Any],
    chave_cache: Any,
) -> dict[str, Any]:
    """Recompoe o contrato tipado quando so o cache derivado nao foi distribuido.

    O CSV e a persistencia vigente e ja guarda valores, parametros, qualidade e
    proveniencia. O JSON em ``data/cache`` e uma otimizacao local e e ignorado
    pelo Git; por isso uma instalacao nova precisa conseguir reconstruir o
    contrato sem consultar novamente o Earth Engine.
    """

    if not isinstance(chave_cache, str) or not CHAVE_CACHE_RE.fullmatch(chave_cache):
        raise ValueError("chave do cache geoespacial invalida")
    status = str(registro.get("status") or "")
    if status not in {"sucesso", "parcial"}:
        raise ValueError("resultado geoespacial indisponivel")

    fontes = deepcopy(registro.get("fontes"))
    fonte_srtm = _fonte_persistida(fontes, SRTM_ID)
    fonte_merit = _fonte_persistida(fontes, MERIT_ID)
    qualidade = deepcopy(registro.get("qualidade"))
    erros = deepcopy(registro.get("erros"))
    if not isinstance(qualidade, Mapping) or not isinstance(erros, list):
        raise ValueError("proveniencia geoespacial incompleta")

    atributos = {
        "declividade_media": _atributo_reconstruido(
            registro.get("declividade_media_graus"),
            unidade="graus",
            metodologia="Media da declividade no raio de analise persistido",
            fonte=fonte_srtm,
            banda="elevation_slope",
        ),
        "posicao_topografica_relativa": _atributo_reconstruido(
            registro.get("posicao_topografica_relativa_m"),
            unidade="m",
            metodologia=("Elevacao no ponto menos a elevacao media no raio de analise"),
            fonte=fonte_srtm,
            banda="elevation",
        ),
        "distancia_drenagem": _atributo_reconstruido(
            registro.get("distancia_drenagem_m"),
            unidade="m",
            metodologia="Distancia geodesica ao pixel MERIT selecionado",
            fonte=fonte_merit,
            banda="upa",
        ),
        "area_drenagem_montante": _atributo_reconstruido(
            registro.get("area_drenagem_montante_km2"),
            unidade="km2",
            metodologia="Area de drenagem montante do pixel MERIT selecionado",
            fonte=fonte_merit,
            banda="upa",
        ),
    }
    valores_disponiveis = sum(
        atributo["valor"] is not None for atributo in atributos.values()
    )
    if status == "sucesso" and valores_disponiveis != len(atributos):
        raise ValueError("resultado de sucesso exige quatro atributos")
    if status == "parcial" and not 0 < valores_disponiveis < len(atributos):
        raise ValueError("resultado parcial exige disponibilidade parcial")

    return {
        "schema_version": str(registro.get("schema_version") or ""),
        "algorithm_version": str(registro.get("algorithm_version") or ""),
        "status": status,
        "localizacao": {
            "latitude": _numero_finito(registro.get("latitude_referencia")),
            "longitude": _numero_finito(registro.get("longitude_referencia")),
        },
        "parametros": {
            campo: _numero_finito(registro.get(campo))
            for campo in PARAMETROS_PERSISTIDOS
        },
        "atributos": atributos,
        "qualidade": dict(qualidade),
        "fontes": fontes,
        "cache": {
            "hit": False,
            "chave": chave_cache,
            "reconstruido_do_csv": True,
        },
        "erros": erros,
    }


def _validar_vinculo(
    registro: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    id_fazenda: str,
    latitude: float,
    longitude: float,
    chave_cache: str,
) -> None:
    if str(registro.get("id_fazenda") or "") != id_fazenda:
        raise ContextoTerritorialIncompativel(id_fazenda)
    if not _coordenadas_compativeis(
        registro.get("latitude_referencia"),
        registro.get("longitude_referencia"),
        latitude,
        longitude,
    ):
        raise ContextoTerritorialIncompativel(id_fazenda)

    localizacao = payload.get("localizacao")
    if not isinstance(localizacao, Mapping) or not _coordenadas_compativeis(
        localizacao.get("latitude"),
        localizacao.get("longitude"),
        latitude,
        longitude,
    ):
        raise ContextoTerritorialIncompativel(id_fazenda)

    cache = payload.get("cache")
    if not isinstance(cache, Mapping) or cache.get("chave") != chave_cache:
        raise ValueError("cache geoespacial nao corresponde ao registro")
    for campo in ("status", "schema_version", "algorithm_version"):
        if str(registro.get(campo) or "") != str(payload.get(campo) or ""):
            raise ValueError("metadados geoespaciais divergentes")
    if payload.get("status") not in {"sucesso", "parcial"}:
        raise ValueError("resultado geoespacial indisponivel")

    parametros = payload.get("parametros")
    atributos = payload.get("atributos")
    if not isinstance(parametros, Mapping) or not isinstance(atributos, Mapping):
        raise ValueError("payload geoespacial incompleto")
    if any(
        not _valores_equivalentes(registro.get(campo), parametros.get(campo))
        for campo in PARAMETROS_PERSISTIDOS
    ):
        raise ValueError("parametros geoespaciais divergentes")

    valores_disponiveis = 0
    for campo_registro, campo_payload in ATRIBUTOS_PERSISTIDOS.items():
        atributo = atributos.get(campo_payload)
        if not isinstance(atributo, Mapping) or "valor" not in atributo:
            raise ValueError("atributo geoespacial ausente")
        valor_payload = atributo.get("valor")
        if not _valores_equivalentes(registro.get(campo_registro), valor_payload):
            raise ValueError("atributo geoespacial divergente")
        if valor_payload is not None:
            valores_disponiveis += 1
    if payload.get("status") == "sucesso" and valores_disponiveis != 4:
        raise ValueError("resultado de sucesso exige quatro atributos")
    if payload.get("status") == "parcial" and not 0 < valores_disponiveis < 4:
        raise ValueError("resultado parcial exige disponibilidade parcial")

    for campo in ("fontes", "qualidade", "erros"):
        if registro.get(campo) != payload.get(
            campo, [] if campo != "qualidade" else {}
        ):
            raise ValueError("proveniencia geoespacial divergente")


class ProvedorContextoTerritorialPersistido:
    """Converte o registro local vigente no contrato territorial tipado."""

    def __init__(
        self,
        *,
        buscar_registro: Callable[[str], Mapping[str, Any] | None] = (
            buscar_registro_geoespacial
        ),
        carregador_cache: CarregadorCacheGeoespacialJson | None = None,
    ) -> None:
        self._buscar_registro = buscar_registro
        self._carregador_cache = (
            carregador_cache
            if carregador_cache is not None
            else CarregadorCacheGeoespacialJson()
        )

    def obter(
        self,
        *,
        id_fazenda: str,
        latitude: float,
        longitude: float,
    ) -> AnaliseGeoespacialNormalizada:
        id_normalizado = str(id_fazenda or "").strip()
        if not id_normalizado:
            raise ContextoTerritorialIndisponivel(id_normalizado)
        try:
            registro_encontrado = self._buscar_registro(id_normalizado)
        except Exception as exc:
            raise ContextoTerritorialIndisponivel(id_normalizado, exc) from exc
        if not isinstance(registro_encontrado, Mapping):
            raise ContextoTerritorialIndisponivel(id_normalizado)
        registro = deepcopy(dict(registro_encontrado))

        chave_cache = registro.get("cache_chave")
        payload_encontrado = self._carregador_cache.carregar(chave_cache)
        if not isinstance(payload_encontrado, Mapping):
            # Um arquivo presente e ilegivel continua sendo rejeitado: nesse
            # caso ha evidencia de corrupcao, nao apenas ausencia de artefato.
            if self._carregador_cache.existe(chave_cache):
                raise ContextoTerritorialIndisponivel(id_normalizado)
            try:
                payload_encontrado = _reconstruir_payload_persistido(
                    registro,
                    chave_cache,
                )
            except Exception as exc:
                raise ContextoTerritorialIndisponivel(
                    id_normalizado,
                    exc,
                ) from exc
        payload = deepcopy(dict(payload_encontrado))

        try:
            _validar_vinculo(
                registro,
                payload,
                id_fazenda=id_normalizado,
                latitude=latitude,
                longitude=longitude,
                chave_cache=chave_cache,
            )
            calculado_em_utc = registro.get("calculado_em_utc")
            if not calculado_em_utc:
                raise ValueError("timestamp geoespacial ausente")
            return normalizar_geoespacial(
                payload,
                calculado_em_utc=calculado_em_utc,
            )
        except ContextoTerritorialIncompativel:
            raise
        except Exception as exc:
            raise ContextoTerritorialIndisponivel(id_normalizado, exc) from exc


__all__ = [
    "CarregadorCacheGeoespacialJson",
    "ProvedorContextoTerritorialPersistido",
    "TOLERANCIA_COORDENADA_GRAUS",
]
