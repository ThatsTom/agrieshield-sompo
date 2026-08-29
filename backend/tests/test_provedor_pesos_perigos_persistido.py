from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.provedor_pesos_perigos_persistido import (
    ProvedorPesosPerigosPersistido,
)
from backend.app.servico_parametros_score import OverridesParametrosModelo
from backend.etl import repositorio_parametros_score as repositorio
from backend.exposicao.politica import criar_politica_agrishield_equip_v1


class TestProvedorPesosPerigosPersistido(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        pasta = Path(self.tempdir.name)
        arquivo = pasta / "parametros_score.csv"
        self.patch_pasta = patch.object(repositorio, "PASTA_DADOS", pasta)
        self.patch_arquivo = patch.object(
            repositorio, "ARQUIVO_PARAMETROS_SCORE", arquivo
        )
        self.patch_pasta.start()
        self.patch_arquivo.start()
        self.addCleanup(self.patch_pasta.stop)
        self.addCleanup(self.patch_arquivo.stop)

    def test_obter_retorna_overrides_com_os_defaults(self):
        overrides = ProvedorPesosPerigosPersistido().obter()
        self.assertIsInstance(overrides, OverridesParametrosModelo)
        self.assertEqual(overrides.pesos_perigos.exposicao_hidrica, 0.30)
        self.assertEqual(overrides.pesos_perigos.trafegabilidade, 0.25)
        base = criar_politica_agrishield_equip_v1()
        self.assertEqual(
            overrides.parametros_territoriais_hidricos,
            base.parametros_territoriais_hidricos,
        )
        self.assertEqual(
            overrides.parametros_instabilidade, base.parametros_instabilidade
        )
        self.assertEqual(
            overrides.parametros_propagacao_fogo, base.parametros_propagacao_fogo
        )
        self.assertEqual(overrides.parametros_tempestade, base.parametros_tempestade)
        self.assertEqual(
            overrides.parametros_trafegabilidade, base.parametros_trafegabilidade
        )

    def test_obter_reflete_o_que_foi_persistido(self):
        valores = {
            (g, i, p): padrao
            for g, i, p, padrao, _ in repositorio.PARAMETROS_MODELO_PADRAO
        }
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.50
        valores[("SCORE", "TRAFEGABILIDADE", "peso")] = 0.15
        valores[("SCORE", "INSTABILIDADE", "peso")] = 0.10
        valores[("SCORE", "INCENDIO", "peso")] = 0.05
        valores[("SCORE", "TEMPESTADES", "peso")] = 0.20
        valores[("TEMPESTADES", "VENTO_CHUVA", "base")] = 0.60
        valores[("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva")] = 0.40
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")] = 0.20
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")] = 0.60
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")] = 0.20
        valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")] = 30
        repositorio.salvar_parametros_modelo(valores)

        overrides = ProvedorPesosPerigosPersistido().obter()
        self.assertEqual(overrides.pesos_perigos.exposicao_hidrica, 0.50)
        self.assertEqual(overrides.pesos_perigos.tempestades, 0.20)
        self.assertEqual(overrides.parametros_tempestade.peso_base_vento, 0.60)
        self.assertEqual(overrides.parametros_tempestade.peso_amplificacao_chuva, 0.40)
        self.assertEqual(overrides.parametros_trafegabilidade.peso_dia, 0.20)
        self.assertEqual(overrides.parametros_trafegabilidade.peso_acumulado, 0.60)
        self.assertEqual(overrides.parametros_trafegabilidade.limiar_relevancia, 30)


if __name__ == "__main__":
    unittest.main()
