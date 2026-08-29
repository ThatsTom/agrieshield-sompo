from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ETL = Path(__file__).resolve().parents[1] / "etl"
sys.path.insert(0, str(ETL))

import etapa4_dados_geoespaciais as geo


class TestEtapa4DadosGeoespaciais(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.cache_patch = patch.object(geo, "PASTA_CACHE", Path(self.tempdir.name))
        self.cache_patch.start()

    def tearDown(self):
        self.cache_patch.stop()
        self.tempdir.cleanup()

    @staticmethod
    def _srtm():
        return {
            "elevacao_media_m": 410.0,
            "elevacao_ponto_m": 417.5,
            "declividade_media_graus": 3.25,
            "pixels_validos": 3400,
            "pixels_totais": 3500,
        }

    @staticmethod
    def _hidro(upa=18.5):
        return {
            "encontrada": True,
            "selecionado": {
                "latitude": -12.54,
                "longitude": -55.72,
                "distancia_m": 725.0,
                "upa_km2": upa,
            },
            "candidatos": 2,
        }

    def _consultar(self, **kwargs):
        ambiente = {"EARTH_ENGINE_PROJECT": "projeto-teste"}
        with patch.dict(os.environ, ambiente, clear=False), patch.object(
            geo, "_carregar_ee", return_value=Mock()
        ), patch.object(geo, "_inicializar_ee") as inicializar, patch.object(
            geo, "_consultar_srtm", return_value=self._srtm()
        ), patch.object(
            geo, "_consultar_hidrografia", return_value=self._hidro()
        ):
            resultado = geo.consultar_dados_geoespaciais(-12.545, -55.721, **kwargs)
        inicializar.assert_called_once()
        return resultado

    def test_resultado_completo_e_serializavel(self):
        resultado = self._consultar(usar_cache=False)
        self.assertEqual("sucesso", resultado["status"])
        self.assertEqual(3.25, resultado["atributos"]["declividade_media"]["valor"])
        self.assertEqual(
            7.5, resultado["atributos"]["posicao_topografica_relativa"]["valor"]
        )
        self.assertEqual(725.0, resultado["atributos"]["distancia_drenagem"]["valor"])
        self.assertEqual(
            18.5, resultado["atributos"]["area_drenagem_montante"]["valor"]
        )
        self.assertNotIn(
            "classe", resultado["atributos"]["posicao_topografica_relativa"]
        )
        json.dumps(resultado, allow_nan=False)

    def test_cache_persistente_e_hit_sem_earth_engine(self):
        primeiro = self._consultar()
        self.assertFalse(primeiro["cache"]["hit"])
        with patch.dict(os.environ, {}, clear=True), patch.object(
            geo, "_carregar_ee", side_effect=AssertionError("não deveria consultar")
        ):
            segundo = geo.consultar_dados_geoespaciais(-12.545, -55.721)
        self.assertTrue(segundo["cache"]["hit"])
        self.assertEqual(primeiro["cache"]["chave"], segundo["cache"]["chave"])

    def test_cache_corrompido_e_ignorado(self):
        base = geo._resultado_base(-12.545, -55.721, 1000.0, 10.0, 50000.0)
        chave = geo._chave_cache(base)
        Path(self.tempdir.name, f"{chave}.json").write_text(
            "{invalido", encoding="utf-8"
        )
        resultado = self._consultar()
        self.assertEqual("sucesso", resultado["status"])

    def test_limiares_geram_chaves_distintas(self):
        chaves = set()
        for limiar in (5, 10, 25, 50):
            base = geo._resultado_base(-12.545, -55.721, 1000.0, float(limiar), 50000.0)
            chaves.add(geo._chave_cache(base))
        self.assertEqual(4, len(chaves))

    def test_limiar_padrao_e_dez(self):
        resultado = self._consultar(usar_cache=False)
        self.assertEqual(10.0, resultado["parametros"]["limiar_drenagem_km2"])

    def test_selecao_deterministica_preserva_upa_do_mesmo_registro(self):
        candidatos = [
            {
                "distancia_m": 100.0,
                "longitude": -55.0,
                "latitude": -12.0,
                "upa_km2": 80.0,
            },
            {
                "distancia_m": 100.0,
                "longitude": -56.0,
                "latitude": -11.0,
                "upa_km2": 25.0,
            },
            {
                "distancia_m": 120.0,
                "longitude": -57.0,
                "latitude": -10.0,
                "upa_km2": 500.0,
            },
        ]
        selecionado = geo._selecionar_candidato(candidatos)
        self.assertEqual(-56.0, selecionado["longitude"])
        self.assertEqual(25.0, selecionado["upa_km2"])

    def test_aplicacao_hidrologica_rejeita_upa_abaixo_do_limiar(self):
        resultado = geo._resultado_base(-12.0, -55.0, 1000.0, 10.0, 50000.0)
        with self.assertRaises(geo.ErroConsultaGeoespacial):
            geo._aplicar_hidrografia(resultado, self._hidro(upa=9.99), 10.0)

    def test_consulta_hidro_amostra_pixels_e_preserva_upa(self):
        ee = Mock()
        ponto = ee.Geometry.Point.return_value
        upa = ee.Image.return_value.select.return_value
        rede = upa.gte.return_value.selfMask.return_value.rename.return_value
        amostras = upa.updateMask.return_value.sample.return_value
        limitados = amostras.map.return_value.limit.return_value
        limitados.getInfo.return_value = {
            "features": [
                {
                    "geometry": {"coordinates": [-55.72, -12.54]},
                    "properties": {"distancia_geodesica_m": 725.0, "upa": 18.5},
                }
            ]
        }

        resultado = geo._consultar_hidrografia(ee, -12.545, -55.721, 10.0, 50000.0)

        upa.gte.assert_called_once_with(10.0)
        upa.updateMask.assert_called_once_with(rede)
        amostras.map.return_value.limit.assert_called_once_with(
            geo.MAX_CANDIDATOS_DRENAGEM, "distancia_geodesica_m", True
        )
        self.assertEqual(18.5, resultado["selecionado"]["upa_km2"])
        self.assertEqual(725.0, resultado["selecionado"]["distancia_m"])

    def test_diagnostico_preserva_mensagem_e_remove_segredo(self):
        erro = geo._erro(
            "consulta_merit_falhou",
            geo.MERIT_ID,
            RuntimeError("Kernel too large\n token=segredo"),
        )
        self.assertEqual("RuntimeError", erro["tipo"])
        self.assertIn("Kernel too large", erro["detalhe"])
        self.assertNotIn("segredo", erro["detalhe"])

    def test_codigo_especifico_da_consulta_e_preservado(self):
        exc = geo.ErroConsultaGeoespacial(
            "falha na amostragem", "merit_amostragem_pixels_falhou"
        )
        erro = geo._erro("consulta_merit_falhou", geo.MERIT_ID, exc)
        self.assertEqual("merit_amostragem_pixels_falhou", erro["codigo"])

    def test_falha_srtm_produz_parcial(self):
        with patch.dict(os.environ, {"EARTH_ENGINE_PROJECT": "teste"}), patch.object(
            geo, "_carregar_ee", return_value=Mock()
        ), patch.object(geo, "_inicializar_ee"), patch.object(
            geo, "_consultar_srtm", side_effect=RuntimeError("falha")
        ), patch.object(
            geo, "_consultar_hidrografia", return_value=self._hidro()
        ):
            resultado = geo.consultar_dados_geoespaciais(-12, -55, usar_cache=False)
        self.assertEqual("parcial", resultado["status"])
        self.assertEqual(
            2, sum(a["status"] == "disponivel" for a in resultado["atributos"].values())
        )
        self.assertTrue(resultado["erros"])

    def test_sem_drenagem_produz_parcial_com_erro(self):
        with patch.dict(os.environ, {"EARTH_ENGINE_PROJECT": "teste"}), patch.object(
            geo, "_carregar_ee", return_value=Mock()
        ), patch.object(geo, "_inicializar_ee"), patch.object(
            geo, "_consultar_srtm", return_value=self._srtm()
        ), patch.object(
            geo,
            "_consultar_hidrografia",
            return_value={"encontrada": False, "motivo": "fora_do_raio_busca"},
        ):
            resultado = geo.consultar_dados_geoespaciais(-12, -55, usar_cache=False)
        self.assertEqual("parcial", resultado["status"])
        self.assertTrue(resultado["qualidade"]["distancia_limitada_pelo_raio_busca"])
        self.assertEqual("drenagem_fora_raio_busca", resultado["erros"][0]["codigo"])

    def test_configuracao_ausente_e_erro_sem_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            resultado = geo.consultar_dados_geoespaciais(-12, -55, usar_cache=False)
        self.assertEqual("erro", resultado["status"])
        self.assertTrue(resultado["erros"])
        self.assertNotIn("simulado", json.dumps(resultado).lower())

    def test_modo_estrito_propaga_configuracao(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(geo.ErroConfiguracaoGeoespacial):
                geo.consultar_dados_geoespaciais(
                    -12, -55, usar_cache=False, strict=True
                )

    def test_validacao_de_entradas(self):
        invalidos = [
            ((91, 0), {}),
            ((0, 181), {}),
            ((0, 0), {"raio_analise_m": 0}),
            ((0, 0), {"limiar_drenagem_km2": -1}),
            ((0, 0), {"limiar_drenagem_km2": float("nan")}),
            ((True, 0), {}),
        ]
        for argumentos, kwargs in invalidos:
            with self.subTest(argumentos=argumentos, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    geo.consultar_dados_geoespaciais(
                        *argumentos, usar_cache=False, **kwargs
                    )


if __name__ == "__main__":
    unittest.main()
