from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.exposicao.agregacao_perigos import (
    ValorIndiceDiario,
    agregar_indice_historico,
    criar_indices_diarios,
)
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.scripts.simulacao_hidrico_v2 import (
    ARQUIVOS_SAIDA,
    BASELINE_PADRAO,
    calcular_h2,
    curva_precipitacao_oficial,
    executar_simulacao,
    snapshot_baseline,
)


class TesteCalculoH2(unittest.TestCase):
    def test_g_zero_mantem_h1(self):
        self.assertEqual(calcular_h2(37.0, 0.0, 90.0), (37.0, 0.0, 0.0))

    def test_s_zero_mantem_h1(self):
        self.assertEqual(calcular_h2(37.0, 0.8, 0.0), (37.0, 0.0, 0.0))

    def test_h2_nunca_excede_100(self):
        h2, incremento, percentual = calcular_h2(95.0, 1.0, 100.0)
        self.assertEqual(h2, 100.0)
        self.assertEqual(incremento, 30.0)
        self.assertEqual(percentual, 30.0)

    def test_missing_permanece_missing(self):
        self.assertEqual(calcular_h2(None, 0.5, 50.0), (None, None, None))
        self.assertEqual(calcular_h2(10.0, None, 50.0), (None, None, None))

    def test_incremento_nunca_negativo_e_h2_nao_reduz_h1(self):
        for h1 in (0.0, 5.0, 25.0, 70.0, 100.0):
            for g in (0.0, 0.2, 1.0):
                h2, incremento, _ = calcular_h2(h1, g, 73.5)
                self.assertGreaterEqual(incremento, 0.0)
                self.assertGreaterEqual(h2, h1)

    def test_curva_oficial_nos_pontos_e_interpolacao(self):
        self.assertEqual(curva_precipitacao_oficial(0), 0)
        self.assertEqual(curva_precipitacao_oficial(20), 25)
        self.assertEqual(curva_precipitacao_oficial(50), 50)
        self.assertEqual(curva_precipitacao_oficial(100), 100)
        self.assertEqual(curva_precipitacao_oficial(200), 100)
        self.assertAlmostEqual(curva_precipitacao_oficial(35), 37.5)


@unittest.skipUnless(
    (BASELINE_PADRAO / "01_resumo_fazendas.csv").exists(),
    "baseline histórico não está presente no workspace",
)
class TesteIntegracaoSimulacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hashes_antes = snapshot_baseline(BASELINE_PADRAO)
        cls.temporario = TemporaryDirectory()
        cls.saida = Path(cls.temporario.name)
        cls.resultado = executar_simulacao(BASELINE_PADRAO, cls.saida)

    @classmethod
    def tearDownClass(cls):
        cls.temporario.cleanup()

    def test_agregacao_h1_usa_e_reproduz_logica_oficial(self):
        politica = criar_politica_agrishield_equip_v1()
        periodo = JanelaHistorica.criar_atual(date(2026, 8, 15), dias=90)
        valores = [
            ValorIndiceDiario(
                data=periodo.inicio + timedelta(days=indice),
                indice=30.0 if indice in {0, 1, 5} else 0.0,
            )
            for indice in range(90)
        ]
        agregado = agregar_indice_historico(
            criar_indices_diarios(periodo, valores, politica), politica
        )
        self.assertEqual(agregado.quantidade_eventos, 2)
        self.assertEqual(agregado.quantidade_dias_relevantes, 3)
        self.assertAlmostEqual(agregado.frequencia_score, 20.0)
        self.assertAlmostEqual(agregado.duracao_score, 2 / 7 * 100)
        self.assertAlmostEqual(agregado.recorrencia_score, 40.0)

    def test_trafegabilidade_fora_e_outros_perigos_identicos(self):
        for item in self.resultado["impactos"]:
            self.assertEqual(item["peso_trafegabilidade"], 0.0)
            self.assertGreaterEqual(item["score_experimental"], item["score_v1"])

    def test_baseline_nao_foi_modificado(self):
        self.assertEqual(self.hashes_antes, snapshot_baseline(BASELINE_PADRAO))

    def test_todos_os_artefatos_foram_gerados(self):
        self.assertEqual(
            {item.name for item in self.saida.iterdir()}, set(ARQUIVOS_SAIDA)
        )

    def test_dimensoes_e_invariantes(self):
        self.assertEqual(len(self.resultado["diarios"]), 6 * 180 * 9)
        self.assertEqual(len(self.resultado["agregados"]), 6 * 2 * 9)
        self.assertEqual(len(self.resultado["impactos"]), 6 * 2 * 9)
        for item in self.resultado["diarios"]:
            if item["h2"] is not None:
                self.assertLessEqual(item["h2"], 100.0)
                self.assertGreaterEqual(item["h2"], item["h1"])
                self.assertGreaterEqual(item["incremento_territorial"], 0.0)
                self.assertTrue(math.isfinite(item["h2"]))


if __name__ == "__main__":
    unittest.main()
