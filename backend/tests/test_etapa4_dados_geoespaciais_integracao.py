from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import unittest


ETL = Path(__file__).resolve().parents[1] / "etl"
sys.path.insert(0, str(ETL))

import etapa4_dados_geoespaciais as geo


@unittest.skipUnless(
    os.getenv("EARTH_ENGINE_PROJECT"),
    "EARTH_ENGINE_PROJECT não configurado; integração Earth Engine ignorada",
)
class TestEtapa4IntegracaoEarthEngine(unittest.TestCase):
    FAZENDAS = [
        ("Boa Esperança", -12.5450, -55.7210),
        ("Santa Luzia", -11.8644, -55.5025),
        ("Três Rios", -16.4708, -54.6356),
    ]

    def test_tres_fazendas_com_resultado_completo(self):
        for nome, latitude, longitude in self.FAZENDAS:
            with self.subTest(fazenda=nome):
                resultado = geo.consultar_dados_geoespaciais(latitude, longitude)
                self.assertEqual("sucesso", resultado["status"], resultado["erros"])
                for atributo in resultado["atributos"].values():
                    self.assertTrue(math.isfinite(atributo["valor"]))
                self.assertGreaterEqual(
                    resultado["atributos"]["area_drenagem_montante"]["valor"], 10.0
                )
                json.dumps(resultado, allow_nan=False)

    def test_limiares_e_cache(self):
        _, latitude, longitude = self.FAZENDAS[0]
        chaves = set()
        for limiar in (5, 10, 25, 50):
            with self.subTest(limiar=limiar):
                primeiro = geo.consultar_dados_geoespaciais(
                    latitude, longitude, limiar_drenagem_km2=limiar
                )
                self.assertEqual("sucesso", primeiro["status"], primeiro["erros"])
                self.assertGreaterEqual(
                    primeiro["atributos"]["area_drenagem_montante"]["valor"], limiar
                )
                self.assertLessEqual(
                    primeiro["atributos"]["distancia_drenagem"]["valor"], 50000
                )
                segundo = geo.consultar_dados_geoespaciais(
                    latitude, longitude, limiar_drenagem_km2=limiar
                )
                self.assertTrue(segundo["cache"]["hit"])
                chaves.add(primeiro["cache"]["chave"])
        self.assertEqual(4, len(chaves))

    def test_coordenada_generica_aceita_parcial_explicito(self):
        resultado = geo.consultar_dados_geoespaciais(-15.0, -47.0, usar_cache=False)
        self.assertIn(resultado["status"], {"sucesso", "parcial"})
        if resultado["status"] == "parcial":
            self.assertTrue(resultado["erros"])
            self.assertTrue(
                any(
                    atributo["status"] == "disponivel"
                    for atributo in resultado["atributos"].values()
                )
            )
        json.dumps(resultado, allow_nan=False)


if __name__ == "__main__":
    unittest.main()
