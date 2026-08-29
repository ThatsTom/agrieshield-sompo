"""AgriShield — Etapa 4: atributos geoespaciais da Fase 1.

O módulo consulta SRTM e MERIT Hydro no Google Earth Engine para um ponto.
Ele não autentica interativamente, não simula dados e não participa do score.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4


SRTM_ID = "USGS/SRTMGL1_003"
MERIT_ID = "MERIT/Hydro/v1_0_1"
SRTM_RESOLUCAO_M = 30.0
MERIT_RESOLUCAO_M = 92.77
SCHEMA_VERSION = "1"
ALGORITHM_VERSION = "fase1-v3"
MAX_CANDIDATOS_DRENAGEM = 32

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
PASTA_CACHE = PASTA_DADOS / "cache" / "geoespacial"


class ErroGeoespacial(RuntimeError):
    """Erro base para consultas geoespaciais em modo estrito."""


class ErroConfiguracaoGeoespacial(ErroGeoespacial):
    """Configuração ou dependência necessária está ausente."""


class ErroConsultaGeoespacial(ErroGeoespacial):
    """O Earth Engine não conseguiu concluir a consulta."""

    def __init__(self, mensagem: str, codigo: str = "consulta_falhou") -> None:
        super().__init__(mensagem)
        self.codigo = codigo


def _numero_finito(nome: str, valor: Any) -> float:
    if isinstance(valor, bool):
        raise ValueError(f"{nome} deve ser numérico")
    try:
        numero = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{nome} deve ser numérico") from exc
    if not math.isfinite(numero):
        raise ValueError(f"{nome} deve ser finito")
    return numero


def _validar_parametros(
    latitude: Any,
    longitude: Any,
    raio_analise_m: Any,
    limiar_drenagem_km2: Any,
    raio_busca_drenagem_m: Any,
) -> tuple[float, float, float, float, float]:
    lat = _numero_finito("latitude", latitude)
    lon = _numero_finito("longitude", longitude)
    raio = _numero_finito("raio_analise_m", raio_analise_m)
    limiar = _numero_finito("limiar_drenagem_km2", limiar_drenagem_km2)
    raio_busca = _numero_finito("raio_busca_drenagem_m", raio_busca_drenagem_m)
    if not -90 <= lat <= 90:
        raise ValueError("latitude deve estar entre -90 e 90")
    if not -180 <= lon <= 180:
        raise ValueError("longitude deve estar entre -180 e 180")
    if raio <= 0 or limiar <= 0 or raio_busca <= 0:
        raise ValueError("raios e limiar de drenagem devem ser maiores que zero")
    return lat, lon, raio, limiar, raio_busca


def _fonte(identificador: str, banda: str, resolucao_m: float) -> Dict[str, Any]:
    return {
        "identificador": identificador,
        "banda": banda,
        "resolucao_m": resolucao_m,
    }


def _atributo(
    valor: Optional[float],
    unidade: str,
    metodologia: str,
    fonte: str,
    banda: str,
    resolucao_m: float,
) -> Dict[str, Any]:
    return {
        "valor": valor,
        "unidade": unidade,
        "status": "disponivel" if valor is not None else "indisponivel",
        "metodologia": metodologia,
        "fonte": fonte,
        "banda": banda,
        "resolucao_m": resolucao_m,
    }


def _resultado_base(
    latitude: float,
    longitude: float,
    raio_analise_m: float,
    limiar_drenagem_km2: float,
    raio_busca_drenagem_m: float,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "status": "erro",
        "localizacao": {"latitude": latitude, "longitude": longitude},
        "parametros": {
            "raio_analise_m": raio_analise_m,
            "limiar_drenagem_km2": limiar_drenagem_km2,
            "raio_busca_drenagem_m": raio_busca_drenagem_m,
        },
        "atributos": {
            "declividade_media": _atributo(
                None,
                "graus",
                "Média da declividade no buffer de análise",
                SRTM_ID,
                "elevation→slope",
                SRTM_RESOLUCAO_M,
            ),
            "distancia_drenagem": _atributo(
                None,
                "m",
                "Distância geodésica ao centro do pixel MERIT mais próximo que atende ao limiar de upa",
                MERIT_ID,
                "upa",
                MERIT_RESOLUCAO_M,
            ),
            "posicao_topografica_relativa": _atributo(
                None,
                "m",
                "Elevação no ponto menos a elevação média no buffer de análise",
                SRTM_ID,
                "elevation",
                SRTM_RESOLUCAO_M,
            ),
            "area_drenagem_montante": _atributo(
                None,
                "km²",
                "Valor upa do mesmo pixel MERIT selecionado para a distância",
                MERIT_ID,
                "upa",
                MERIT_RESOLUCAO_M,
            ),
        },
        "qualidade": {
            "cobertura_srtm_pct": None,
            "pixels_srtm_validos": None,
            "drenagem_encontrada": False,
            "pixel_drenagem": None,
            "candidatos_drenagem": 0,
            "distancia_geodesica_final_m": None,
            "upa_atende_limiar": None,
            "distancia_limitada_pelo_raio_busca": False,
            "representatividade": "entorno_de_ponto",
            "flags": ["coordenada_pontual_nao_representa_poligono_da_fazenda"],
        },
        "fontes": [
            _fonte(SRTM_ID, "elevation", SRTM_RESOLUCAO_M),
            _fonte(MERIT_ID, "upa", MERIT_RESOLUCAO_M),
        ],
        "cache": {"hit": False, "chave": None},
        "erros": [],
    }


def _chave_cache(resultado: Dict[str, Any]) -> str:
    payload = {
        "schema": SCHEMA_VERSION,
        "algoritmo": ALGORITHM_VERSION,
        "datasets": [SRTM_ID, MERIT_ID],
        "latitude": round(resultado["localizacao"]["latitude"], 6),
        "longitude": round(resultado["localizacao"]["longitude"], 6),
        **resultado["parametros"],
    }
    bruto = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _ler_cache(chave: str) -> Optional[Dict[str, Any]]:
    caminho = PASTA_CACHE / f"{chave}.json"
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        if (
            dados.get("schema_version") != SCHEMA_VERSION
            or dados.get("algorithm_version") != ALGORITHM_VERSION
            or dados.get("status") not in {"sucesso", "parcial"}
        ):
            return None
        return dados
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _salvar_cache(chave: str, resultado: Dict[str, Any]) -> None:
    PASTA_CACHE.mkdir(parents=True, exist_ok=True)
    destino = PASTA_CACHE / f"{chave}.json"
    temporario = PASTA_CACHE / f".{chave}.{uuid4().hex}.tmp"
    try:
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(resultado, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
        temporario.replace(destino)
    finally:
        if temporario.exists():
            temporario.unlink()


def _erro(codigo: str, fonte: str, exc: Any) -> Dict[str, str]:
    if isinstance(exc, BaseException):
        tipo = type(exc).__name__
        codigo = getattr(exc, "codigo", codigo)
        detalhe = _sanitizar_mensagem_erro(str(exc)) or tipo
    else:
        tipo = "Erro"
        detalhe = _sanitizar_mensagem_erro(str(exc))
    return {
        "codigo": codigo,
        "fonte": fonte,
        "tipo": tipo,
        "detalhe": detalhe,
    }


def _sanitizar_mensagem_erro(mensagem: str) -> str:
    """Preserva o diagnóstico do EE removendo quebras e possíveis segredos."""
    texto = " ".join(str(mensagem).split())
    texto = re.sub(
        r"(?i)\b(token|authorization|credential|api[_ -]?key)\b(\s*[:=]\s*)\S+",
        r"\1\2[redacted]",
        texto,
    )
    return texto[:500]


def _carregar_ee() -> Any:
    try:
        import ee  # type: ignore
    except ImportError as exc:
        raise ErroConfiguracaoGeoespacial("earthengine-api não está instalado") from exc
    return ee


def _inicializar_ee(ee: Any, projeto: str) -> None:
    """Inicializa credenciais existentes; deliberadamente não chama ee.Authenticate."""
    try:
        ee.Initialize(project=projeto)
    except Exception as exc:
        raise ErroConfiguracaoGeoespacial(
            "não foi possível inicializar o Earth Engine"
        ) from exc


def _consultar_srtm(
    ee: Any, latitude: float, longitude: float, raio_m: float
) -> Dict[str, Any]:
    ponto = ee.Geometry.Point([longitude, latitude])
    regiao = ponto.buffer(raio_m)
    dem = ee.Image(SRTM_ID).select("elevation")
    declividade = ee.Terrain.slope(dem).rename("slope")
    opcoes = {
        "geometry": regiao,
        "scale": SRTM_RESOLUCAO_M,
        "maxPixels": 1_000_000,
        "bestEffort": False,
    }
    elevacao_media = dem.reduceRegion(reducer=ee.Reducer.mean(), **opcoes).get(
        "elevation"
    )
    declividade_media = declividade.reduceRegion(
        reducer=ee.Reducer.mean(), **opcoes
    ).get("slope")
    pixels_validos = dem.reduceRegion(reducer=ee.Reducer.count(), **opcoes).get(
        "elevation"
    )
    # Mantém a projeção SRTM e remove sua máscara para contar a grade esperada.
    grade_total = dem.multiply(0).unmask(0).add(1).rename("total")
    pixels_totais = grade_total.reduceRegion(reducer=ee.Reducer.count(), **opcoes).get(
        "total"
    )
    elevacao_ponto = dem.reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=ponto,
        scale=SRTM_RESOLUCAO_M,
        maxPixels=10,
    ).get("elevation")
    return ee.Dictionary(
        {
            "elevacao_media_m": elevacao_media,
            "elevacao_ponto_m": elevacao_ponto,
            "declividade_media_graus": declividade_media,
            "pixels_validos": pixels_validos,
            "pixels_totais": pixels_totais,
        }
    ).getInfo()


def _extrair_candidatos(collection_info: Dict[str, Any]) -> List[Dict[str, float]]:
    candidatos: List[Dict[str, float]] = []
    for feature in collection_info.get("features", []):
        props = feature.get("properties") or {}
        geometria = feature.get("geometry") or {}
        coords = geometria.get("coordinates") or []
        if len(coords) < 2:
            continue
        try:
            candidato = {
                "longitude": float(coords[0]),
                "latitude": float(coords[1]),
                "distancia_m": float(props["distancia_geodesica_m"]),
                "upa_km2": float(props["upa"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        if all(math.isfinite(v) for v in candidato.values()):
            candidatos.append(candidato)
    return candidatos


def _selecionar_candidato(
    candidatos: Iterable[Dict[str, float]]
) -> Optional[Dict[str, float]]:
    """Ordena deterministicamente; distância e upa permanecem no mesmo registro."""
    validos = list(candidatos)
    if not validos:
        return None
    return min(validos, key=lambda c: (c["distancia_m"], c["longitude"], c["latitude"]))


def _consultar_hidrografia(
    ee: Any,
    latitude: float,
    longitude: float,
    limiar_km2: float,
    raio_busca_m: float,
) -> Dict[str, Any]:
    ponto = ee.Geometry.Point([longitude, latitude])
    upa = ee.Image(MERIT_ID).select("upa")
    rede = upa.gte(limiar_km2).selfMask().rename("drenagem")
    # Cada amostra é o centro de um pixel da rede e conserva a propriedade upa
    # desse exato pixel. A distância é anexada à mesma Feature antes de a
    # coleção ser limitada e materializada.
    try:
        amostras = upa.updateMask(rede).sample(
            region=ponto.buffer(raio_busca_m),
            projection=upa.projection(),
            scale=MERIT_RESOLUCAO_M,
            geometries=True,
            dropNulls=True,
            tileScale=4,
        )

        def adicionar_distancia(feature: Any) -> Any:
            return feature.set(
                "distancia_geodesica_m", ponto.distance(feature.geometry(), 1)
            )

        proximos = amostras.map(adicionar_distancia).limit(
            MAX_CANDIDATOS_DRENAGEM, "distancia_geodesica_m", True
        )
        candidatos = _extrair_candidatos(proximos.getInfo())
    except Exception as exc:
        raise ErroConsultaGeoespacial(
            f"falha ao amostrar e ordenar pixels MERIT: {exc}",
            "merit_amostragem_pixels_falhou",
        ) from exc

    selecionado = _selecionar_candidato(candidatos)
    if selecionado is None:
        return {
            "encontrada": False,
            "motivo": "fora_do_raio_busca",
        }
    return {
        "encontrada": True,
        "selecionado": selecionado,
        "candidatos": len(candidatos),
        "metodo": "amostragem_pixels_no_raio",
    }


def _aplicar_srtm(resultado: Dict[str, Any], dados: Dict[str, Any]) -> None:
    campos = ("declividade_media_graus", "elevacao_ponto_m", "elevacao_media_m")
    if any(dados.get(campo) is None for campo in campos):
        raise ErroConsultaGeoespacial(
            "SRTM não retornou pixels válidos", "srtm_sem_pixels"
        )
    declividade = float(dados["declividade_media_graus"])
    posicao = float(dados["elevacao_ponto_m"]) - float(dados["elevacao_media_m"])
    if (
        not math.isfinite(declividade)
        or not math.isfinite(posicao)
        or not 0 <= declividade <= 90
    ):
        raise ErroConsultaGeoespacial(
            "SRTM retornou valores fora do domínio", "srtm_valor_invalido"
        )
    resultado["atributos"]["declividade_media"]["valor"] = declividade
    resultado["atributos"]["declividade_media"]["status"] = "disponivel"
    resultado["atributos"]["posicao_topografica_relativa"]["valor"] = posicao
    resultado["atributos"]["posicao_topografica_relativa"]["status"] = "disponivel"
    validos = int(dados.get("pixels_validos") or 0)
    totais = int(dados.get("pixels_totais") or 0)
    resultado["qualidade"]["pixels_srtm_validos"] = validos
    resultado["qualidade"]["cobertura_srtm_pct"] = (
        round(validos / totais * 100, 2) if totais else None
    )


def _aplicar_hidrografia(
    resultado: Dict[str, Any], dados: Dict[str, Any], limiar: float
) -> None:
    qualidade = resultado["qualidade"]
    if not dados.get("encontrada"):
        motivo = dados.get("motivo", "drenagem_indisponivel")
        if motivo == "fora_do_raio_busca":
            qualidade["distancia_limitada_pelo_raio_busca"] = True
            raise ErroConsultaGeoespacial(
                "nenhuma drenagem encontrada dentro do raio de busca",
                "drenagem_fora_raio_busca",
            )
        raise ErroConsultaGeoespacial(
            "não foi possível associar distância e upa ao mesmo pixel",
            "associacao_pixel_drenagem_falhou",
        )
    selecionado = dados["selecionado"]
    distancia = float(selecionado["distancia_m"])
    upa = float(selecionado["upa_km2"])
    if (
        not math.isfinite(distancia)
        or not math.isfinite(upa)
        or distancia < 0
        or upa < limiar
    ):
        raise ErroConsultaGeoespacial(
            "MERIT retornou valores fora do domínio", "merit_valor_invalido"
        )
    resultado["atributos"]["distancia_drenagem"]["valor"] = distancia
    resultado["atributos"]["distancia_drenagem"]["status"] = "disponivel"
    resultado["atributos"]["area_drenagem_montante"]["valor"] = upa
    resultado["atributos"]["area_drenagem_montante"]["status"] = "disponivel"
    qualidade.update(
        {
            "drenagem_encontrada": True,
            "pixel_drenagem": {
                "latitude": selecionado["latitude"],
                "longitude": selecionado["longitude"],
            },
            "candidatos_drenagem": int(dados.get("candidatos", 0)),
            "distancia_geodesica_final_m": distancia,
            "upa_atende_limiar": upa >= limiar,
        }
    )
    qualidade["flags"].append("distancia_geodesica_calculada_do_centro_do_pixel_merit")


def _atualizar_status(resultado: Dict[str, Any]) -> None:
    disponiveis = sum(
        atributo["status"] == "disponivel"
        for atributo in resultado["atributos"].values()
    )
    resultado["status"] = (
        "sucesso" if disponiveis == 4 else "parcial" if disponiveis else "erro"
    )


def consultar_dados_geoespaciais(
    latitude: float,
    longitude: float,
    *,
    raio_analise_m: int = 1000,
    limiar_drenagem_km2: float = 10.0,
    raio_busca_drenagem_m: int = 50000,
    usar_cache: bool = True,
    strict: bool = False,
) -> Dict[str, Any]:
    """Consulta os quatro atributos geoespaciais da Fase 1 para um ponto."""
    lat, lon, raio, limiar, raio_busca = _validar_parametros(
        latitude, longitude, raio_analise_m, limiar_drenagem_km2, raio_busca_drenagem_m
    )
    resultado = _resultado_base(lat, lon, raio, limiar, raio_busca)
    chave = _chave_cache(resultado)
    resultado["cache"]["chave"] = chave
    if usar_cache:
        armazenado = _ler_cache(chave)
        if armazenado is not None:
            armazenado["cache"] = {"hit": True, "chave": chave}
            return armazenado

    projeto = os.getenv("EARTH_ENGINE_PROJECT", "").strip()
    if not projeto:
        exc = ErroConfiguracaoGeoespacial("EARTH_ENGINE_PROJECT não configurado")
        if strict:
            raise exc
        resultado["erros"].append(_erro("configuracao_ausente", "earth_engine", exc))
        return resultado
    try:
        ee = _carregar_ee()
        _inicializar_ee(ee, projeto)
    except ErroConfiguracaoGeoespacial as exc:
        if strict:
            raise
        resultado["erros"].append(_erro("inicializacao_falhou", "earth_engine", exc))
        return resultado

    try:
        _aplicar_srtm(resultado, _consultar_srtm(ee, lat, lon, raio))
    except Exception as exc:
        resultado["erros"].append(_erro("consulta_srtm_falhou", SRTM_ID, exc))
        if strict:
            raise ErroConsultaGeoespacial("consulta SRTM falhou") from exc
    try:
        dados_hidro = _consultar_hidrografia(ee, lat, lon, limiar, raio_busca)
        _aplicar_hidrografia(resultado, dados_hidro, limiar)
    except Exception as exc:
        resultado["erros"].append(_erro("consulta_merit_falhou", MERIT_ID, exc))
        if strict:
            raise ErroConsultaGeoespacial("consulta MERIT Hydro falhou") from exc

    _atualizar_status(resultado)
    if usar_cache and resultado["status"] in {"sucesso", "parcial"}:
        try:
            _salvar_cache(chave, resultado)
        except OSError as exc:
            resultado["qualidade"]["flags"].append("cache_escrita_falhou")
            resultado["erros"].append(_erro("cache_escrita_falhou", "cache", exc))
    return resultado


__all__ = [
    "ErroConfiguracaoGeoespacial",
    "ErroConsultaGeoespacial",
    "ErroGeoespacial",
    "consultar_dados_geoespaciais",
]
