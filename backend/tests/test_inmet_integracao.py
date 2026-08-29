from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
import unittest


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from inmet.cliente import ClienteCatalogoInmet, ClienteHistoricoInmet
from inmet.normalizacao import parsear_zip_historico


@unittest.skipUnless(
    os.getenv("RUN_INMET_INTEGRATION") == "1",
    "Defina RUN_INMET_INTEGRATION=1 para consultar as fontes oficiais do INMET",
)
class TestIntegracaoRealInmet(unittest.TestCase):
    def test_catalogo_e_historico_a904_2026(self):
        estacoes = ClienteCatalogoInmet().obter_estacoes()
        a904 = next((item for item in estacoes if item["codigo"] == "A904"), None)
        self.assertIsNotNone(a904)
        self.assertEqual("Operante", a904["situacao"])

        conteudo = ClienteHistoricoInmet().baixar_ano(2026)
        resultado = parsear_zip_historico(
            conteudo,
            "A904",
            data_inicio=date(2026, 7, 30),
            data_fim=date(2026, 7, 31),
        )
        observacoes = resultado["observacoes"]
        self.assertGreater(len(observacoes), 0)
        self.assertTrue(all(item["codigo_estacao"] == "A904" for item in observacoes))
        self.assertTrue(
            all(item["observado_em_utc"].endswith("+00:00") for item in observacoes)
        )


if __name__ == "__main__":
    unittest.main()
