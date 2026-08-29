from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "etl"))
sys.path.insert(0, str(BACKEND / "app"))

from app import main
from backend.etl import repositorio_parametros_score as repositorio


def _payload_padrao():
    return {
        "parametros": [
            {"grupo": g, "indicador": i, "parametro": p, "valor": padrao}
            for g, i, p, padrao, _ in repositorio.PARAMETROS_MODELO_PADRAO
        ]
    }


class BaseApiParametrosScore(unittest.TestCase):
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
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)


class TestGetParametrosScore(BaseApiParametrosScore):
    def test_retorna_os_22_parametros_com_defaults_na_primeira_consulta(self):
        resposta = self.client.get("/api/v1/parametros-score")
        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()["parametros"]
        self.assertEqual(len(payload), 22)
        valores = {
            (item["grupo"], item["indicador"], item["parametro"]): item["valor_atual"]
            for item in payload
        }
        self.assertEqual(valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.30)
        self.assertEqual(
            valores[("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem")], 0.40
        )
        self.assertEqual(valores[("INSTABILIDADE", "ATIVACAO", "critico")], 1.00)
        self.assertEqual(valores[("INCENDIO", "SECURA", "7_mais_dias")], 1.10)
        self.assertEqual(
            valores[("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva")], 0.25
        )
        self.assertEqual(valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")], 0.35)
        self.assertEqual(
            valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")], 0.45
        )
        self.assertEqual(
            valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")], 0.20
        )
        self.assertEqual(
            valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")], 25
        )

    def test_resposta_inclui_o_valor_padrao_ao_lado_de_cada_atual(self):
        resposta = self.client.get("/api/v1/parametros-score")
        payload = resposta.json()["parametros"]
        for item in payload:
            self.assertIn("valor_padrao", item)
            self.assertIn("tipo", item)
            self.assertIn("atualizado_em", item)

    def test_resposta_nao_expoe_peso_nominal_ou_efetivo(self):
        resposta = self.client.get("/api/v1/parametros-score")
        corpo = resposta.text.lower()
        self.assertNotIn("peso_nominal", corpo)
        self.assertNotIn("peso_efetivo", corpo)


class TestPutParametrosScore(BaseApiParametrosScore):
    def test_salva_e_retorna_a_configuracao_atualizada(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "SCORE" and item["indicador"] == "EXPOSICAO_HIDRICA":
                item["valor"] = 0.40
            if item["grupo"] == "SCORE" and item["indicador"] == "TRAFEGABILIDADE":
                item["valor"] = 0.15

        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 200)
        valores = {
            (item["grupo"], item["indicador"], item["parametro"]): item["valor_atual"]
            for item in resposta.json()["parametros"]
        }
        self.assertEqual(valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.40)
        self.assertEqual(valores[("SCORE", "TRAFEGABILIDADE", "peso")], 0.15)

        confirmacao = self.client.get("/api/v1/parametros-score")
        valores_confirmados = {
            (item["grupo"], item["indicador"], item["parametro"]): item["valor_atual"]
            for item in confirmacao.json()["parametros"]
        }
        self.assertEqual(valores_confirmados, valores)

    def test_soma_do_score_diferente_de_100_retorna_422_com_mensagem_do_grupo(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "SCORE" and item["indicador"] == "EXPOSICAO_HIDRICA":
                item["valor"] = 0.31
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)
        detalhe = resposta.json()["detail"]
        self.assertEqual(len(detalhe), 1)
        self.assertEqual(detalhe[0]["grupo"], "SCORE")
        self.assertEqual(
            detalhe[0]["mensagem"], "Os pesos do índice devem totalizar 100%."
        )

    def test_soma_hidrica_diferente_de_100_retorna_422(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if (
                item["grupo"] == "EXPOSICAO_HIDRICA"
                and item["parametro"] == "proximidade_drenagem"
            ):
                item["valor"] = 0.50
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json()["detail"][0]["grupo"], "EXPOSICAO_HIDRICA")

    def test_tempestades_base_mais_influencia_diferente_de_um_retorna_422(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "TEMPESTADES" and item["parametro"] == "base":
                item["valor"] = 0.90
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json()["detail"][0]["grupo"], "TEMPESTADES")

    def test_fator_negativo_retorna_422(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "INCENDIO" and item["parametro"] == "2_3_dias":
                item["valor"] = -0.5
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)

    def test_soma_interna_de_trafegabilidade_diferente_de_100_retorna_422(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "TRAFEGABILIDADE" and item["parametro"] == "peso_dia":
                item["valor"] = 0.60
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json()["detail"][0]["grupo"], "TRAFEGABILIDADE")

    def test_limiar_de_relevancia_fora_de_0_100_retorna_422(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if (
                item["grupo"] == "TRAFEGABILIDADE"
                and item["parametro"] == "limiar_relevancia"
            ):
                item["valor"] = 150
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(resposta.json()["detail"][0]["grupo"], "TRAFEGABILIDADE")

    def test_alterar_trafegabilidade_e_confirmado_na_releitura(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if (
                item["grupo"] == "TRAFEGABILIDADE"
                and item["parametro"] == "limiar_relevancia"
            ):
                item["valor"] = 20
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 200)
        confirmacao = self.client.get("/api/v1/parametros-score")
        valores = {
            (item["grupo"], item["indicador"], item["parametro"]): item["valor_atual"]
            for item in confirmacao.json()["parametros"]
        }
        self.assertEqual(
            valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")], 20
        )

    def test_soma_invalida_nao_altera_a_configuracao_persistida(self):
        payload = _payload_padrao()
        for item in payload["parametros"]:
            if item["grupo"] == "SCORE" and item["indicador"] == "EXPOSICAO_HIDRICA":
                item["valor"] = 0.31
        self.client.put("/api/v1/parametros-score", json=payload)
        confirmacao = self.client.get("/api/v1/parametros-score")
        valores = {
            (item["grupo"], item["indicador"], item["parametro"]): item["valor_atual"]
            for item in confirmacao.json()["parametros"]
        }
        self.assertEqual(valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.30)

    def test_menos_de_22_parametros_retorna_422(self):
        payload = _payload_padrao()
        payload["parametros"].pop()
        resposta = self.client.put("/api/v1/parametros-score", json=payload)
        self.assertEqual(resposta.status_code, 422)


if __name__ == "__main__":
    unittest.main()
