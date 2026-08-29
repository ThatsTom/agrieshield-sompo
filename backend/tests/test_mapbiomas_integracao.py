"""Integração real opcional com o asset oficial MapBiomas no Earth Engine."""

from __future__ import annotations

import math
import os
from pathlib import Path
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from mapbiomas import (
    ASSET_ID,
    BANDA_DEFAULT,
    ClienteEarthEngineMapBiomas,
    ErroMapBiomas,
    RepositorioMapBiomasMemoria,
    ServicoMapBiomas,
)


# Coordenadas territoriais reais e áreas sintéticas exclusivamente técnicas.
# Não representam propriedades ou limites fundiários reais.
CENARIOS = {
    "A": {
        "id_fazenda": "poc-a",
        "latitude": -13.15,
        "longitude": -56.05,
        "area_ha": 250,
        "categoria": "agricultura_pct",
    },
    "B": {
        "id_fazenda": "poc-b",
        "latitude": -20.20,
        "longitude": -55.55,
        "area_ha": 500,
        "categoria": "pastagem_pct",
    },
    "C": {
        "id_fazenda": "poc-c",
        "latitude": -7.75,
        "longitude": -55.25,
        "area_ha": 1000,
        "categoria": "vegetacao_nativa_pct",
    },
}


@unittest.skipUnless(
    os.getenv("EARTH_ENGINE_PROJECT"),
    "EARTH_ENGINE_PROJECT não configurado; integração MapBiomas é opcional",
)
class TestMapBiomasIntegracaoReal(unittest.TestCase):
    def test_tres_contextos_da_poc(self):
        cliente = ClienteEarthEngineMapBiomas()
        fazendas = {item["id_fazenda"]: item for item in CENARIOS.values()}
        servico = ServicoMapBiomas(
            cliente=cliente,
            repositorio=RepositorioMapBiomasMemoria(),
            buscar_fazenda=lambda id_fazenda: fazendas.get(id_fazenda),
        )

        resultados = {}
        try:
            for nome, cenario in CENARIOS.items():
                resultados[nome] = servico.analisar(cenario["id_fazenda"])
        except ErroMapBiomas as exc:
            self.skipTest(f"Earth Engine temporariamente indisponível: {exc}")

        for nome, cenario in CENARIOS.items():
            with self.subTest(cenario=nome):
                resultado = resultados[nome]
                self.assertEqual(ASSET_ID, resultado["mapbiomas"]["asset_id"])
                self.assertEqual(BANDA_DEFAULT, resultado["mapbiomas"]["banda"])
                percentuais = [
                    resultado["cobertura"][campo]
                    for campo in (
                        "agricultura_pct",
                        "pastagem_pct",
                        "vegetacao_nativa_pct",
                        "agua_pct",
                        "outros_pct",
                    )
                ]
                self.assertTrue(all(math.isfinite(valor) for valor in percentuais))
                self.assertAlmostEqual(100.0, sum(percentuais), places=4)
                self.assertGreater(resultado["qualidade"]["cobertura_valida_pct"], 0)
                self.assertGreater(resultado["cobertura"][cenario["categoria"]], 50)
                self.assertTrue(resultado["distribuicao_bruta"])


if __name__ == "__main__":
    unittest.main()
