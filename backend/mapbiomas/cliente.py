"""Cliente Earth Engine para análise territorial MapBiomas."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


ASSET_ID = (
    "projects/mapbiomas-public/assets/brazil/lulc/collection10_1/"
    "mapbiomas_brazil_collection10_1_coverage_v1"
)
COLECAO = "10.1"
ASSET_VERSION = "v1"
ANO_DEFAULT = 2024
BANDA_DEFAULT = "classification_2024"
RESOLUCAO_NOMINAL_M = 30
ANO_INICIAL = 1985
ANO_FINAL = 2024


class ErroMapBiomas(RuntimeError):
    """Erro controlado do subsistema MapBiomas."""


class ErroConfiguracaoMapBiomas(ErroMapBiomas):
    """Configuração local ausente ou inválida."""


class ErroConsultaMapBiomas(ErroMapBiomas):
    """Falha sanitizada de comunicação ou processamento no Earth Engine."""


class ErroDadosMapBiomas(ErroMapBiomas):
    """Resposta externa ausente ou incompatível com o contrato esperado."""


def banda_para_ano(ano: int) -> str:
    return f"classification_{int(ano)}"


class ClienteEarthEngineMapBiomas:
    """Executa somente operações Earth Engine; não conhece API ou persistência."""

    def __init__(
        self,
        *,
        ee_module: Any = None,
        projeto: Optional[str] = None,
        asset_id: str = ASSET_ID,
    ) -> None:
        self._ee_module = ee_module
        self._projeto = projeto
        self._asset_id = asset_id

    def _ee(self) -> Any:
        if self._ee_module is not None:
            return self._ee_module
        try:
            import ee  # type: ignore
        except ImportError as exc:
            raise ErroConfiguracaoMapBiomas(
                "A dependência earthengine-api não está instalada"
            ) from exc
        return ee

    def _inicializar(self, ee: Any) -> str:
        projeto = (self._projeto or os.getenv("EARTH_ENGINE_PROJECT", "")).strip()
        if not projeto:
            raise ErroConfiguracaoMapBiomas("EARTH_ENGINE_PROJECT não está configurado")
        try:
            # Autenticação é responsabilidade explícita do ambiente. Este módulo
            # nunca chama ee.Authenticate().
            ee.Initialize(project=projeto)
        except Exception as exc:
            raise ErroConfiguracaoMapBiomas(
                "Não foi possível inicializar o Google Earth Engine"
            ) from exc
        return projeto

    def reduzir_territorio(
        self,
        *,
        latitude: float,
        longitude: float,
        raio_equivalente_m: float,
        ano: int = ANO_DEFAULT,
    ) -> Dict[str, Any]:
        """Soma área por classe dentro do círculo estimado da propriedade."""
        ee = self._ee()
        self._inicializar(ee)
        banda_solicitada = banda_para_ano(ano)

        try:
            imagem_asset = ee.Image(self._asset_id)
            bandas = imagem_asset.bandNames().getInfo()
            if not isinstance(bandas, list):
                raise ErroDadosMapBiomas(
                    "O Earth Engine não retornou a lista de bandas do MapBiomas"
                )
            if banda_solicitada not in bandas:
                raise ErroDadosMapBiomas(
                    f"Banda MapBiomas indisponível: {banda_solicitada}"
                )

            classificacao = imagem_asset.select(banda_solicitada).rename("classe")
            projecao = classificacao.projection()
            ponto = ee.Geometry.Point([float(longitude), float(latitude)])
            geometria = ponto.buffer(float(raio_equivalente_m), maxError=1)
            area_pixel = ee.Image.pixelArea().rename("area_m2")
            area_classificada = area_pixel.addBands(classificacao)

            resposta = ee.Dictionary(
                {
                    "area_geometria_m2": geometria.area(maxError=1),
                    "area_grade_m2": area_pixel.reduceRegion(
                        reducer=ee.Reducer.sum(),
                        geometry=geometria,
                        scale=RESOLUCAO_NOMINAL_M,
                        crs=projecao,
                        maxPixels=10_000_000,
                        tileScale=2,
                    ).get("area_m2"),
                    "grupos": area_classificada.reduceRegion(
                        reducer=ee.Reducer.sum().group(
                            groupField=1,
                            groupName="codigo",
                        ),
                        geometry=geometria,
                        scale=RESOLUCAO_NOMINAL_M,
                        crs=projecao,
                        maxPixels=10_000_000,
                        tileScale=2,
                    ).get("groups"),
                }
            ).getInfo()
        except ErroMapBiomas:
            raise
        except Exception as exc:
            raise ErroConsultaMapBiomas(
                "Falha ao consultar a cobertura territorial no Google Earth Engine"
            ) from exc

        if not isinstance(resposta, dict):
            raise ErroDadosMapBiomas("Resposta territorial MapBiomas inválida")
        return {
            "asset_id": self._asset_id,
            "ano": int(ano),
            "banda": banda_solicitada,
            "area_geometria_m2": resposta.get("area_geometria_m2"),
            "area_grade_m2": resposta.get("area_grade_m2"),
            "grupos": resposta.get("grupos"),
        }


__all__ = [
    "ANO_DEFAULT",
    "ANO_FINAL",
    "ANO_INICIAL",
    "ASSET_ID",
    "ASSET_VERSION",
    "BANDA_DEFAULT",
    "COLECAO",
    "ClienteEarthEngineMapBiomas",
    "ErroConfiguracaoMapBiomas",
    "ErroConsultaMapBiomas",
    "ErroDadosMapBiomas",
    "ErroMapBiomas",
    "RESOLUCAO_NOMINAL_M",
    "banda_para_ano",
]
