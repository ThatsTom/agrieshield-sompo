from __future__ import annotations

import json
import os
import unittest
from unittest.mock import Mock, patch

import requests

from backend.app.servico_insights_ia import (
    ErroConfiguracaoOpenAI,
    ErroServicoOpenAI,
    MODELO_OPENAI_INSIGHTS,
    gerar_hash_contexto,
    gerar_insight_ia,
)


def _insight_valido():
    return {
        "resumo_executivo": "A operação pede acompanhamento preventivo.",
        "nivel_atencao": "moderado",
        "leitura_principal": "O score está estável, mas há chuva prevista.",
        "prioridades": [
            {
                "titulo": "Confirmar acesso",
                "prioridade": "hoje",
                "motivo": "A chuva pode afetar a operação.",
                "acao_recomendada": "Validar as rotas com o responsável local.",
                "dado_base": "Previsão de chuva para amanhã.",
            }
        ],
        "perguntas_consultor": ["Há rota alternativa disponível?"],
        "pontos_positivos": ["O contexto territorial está disponível."],
        "limitacoes": ["A previsão pode mudar."],
    }


class TestServicoInsightsIA(unittest.TestCase):
    def test_exige_chave_somente_no_backend(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ErroConfiguracaoOpenAI):
                gerar_insight_ia({"score": 70})

    @patch("backend.app.servico_insights_ia.requests.post")
    def test_usa_gpt_4o_mini_responses_e_json_schema(self, post):
        resposta = Mock()
        resposta.raise_for_status.return_value = None
        resposta.json.return_value = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": json.dumps(_insight_valido())}
                    ]
                }
            ],
            "usage": {"input_tokens": 120, "output_tokens": 200},
        }
        post.return_value = resposta

        resultado = gerar_insight_ia(
            {"score": 70, "valor_ausente": float("nan")},
            chave_api="sk-chave-de-teste",
        )

        self.assertEqual(resultado.insight["nivel_atencao"], "moderado")
        chamada = post.call_args.kwargs
        self.assertEqual(chamada["json"]["model"], MODELO_OPENAI_INSIGHTS)
        self.assertFalse(chamada["json"]["store"])
        self.assertEqual(
            chamada["json"]["text"]["format"]["type"], "json_schema"
        )
        self.assertNotIn("sk-chave-de-teste", repr(chamada["json"]))
        self.assertIn("sk-chave-de-teste", chamada["headers"]["Authorization"])
        self.assertIn('"valor_ausente": null', chamada["json"]["input"][0]["content"][0]["text"])

    @patch("backend.app.servico_insights_ia.requests.post")
    def test_falha_da_api_nao_expoe_a_chave(self, post):
        resposta = Mock(status_code=401)
        post.side_effect = requests.HTTPError(response=resposta)

        with self.assertRaises(ErroServicoOpenAI) as contexto:
            gerar_insight_ia({"score": 70}, chave_api="sk-nao-pode-vazar")

        self.assertNotIn("sk-nao-pode-vazar", str(contexto.exception))
        self.assertIn("não foi aceita", str(contexto.exception))

    @patch("backend.app.servico_insights_ia.time.sleep")
    @patch("backend.app.servico_insights_ia.requests.post")
    def test_repete_uma_vez_quando_a_falha_e_temporaria(self, post, sleep):
        falha = requests.HTTPError(response=Mock(status_code=500))
        sucesso = Mock()
        sucesso.raise_for_status.return_value = None
        sucesso.json.return_value = {"output_text": json.dumps(_insight_valido())}
        post.side_effect = [falha, sucesso]

        resultado = gerar_insight_ia({"score": 70}, chave_api="sk-teste")

        self.assertEqual(resultado.insight["nivel_atencao"], "moderado")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(0.6)

    def test_hash_muda_quando_o_contexto_muda(self):
        primeiro = gerar_hash_contexto({"score": 70})
        repetido = gerar_hash_contexto({"score": 70})
        alterado = gerar_hash_contexto({"score": 71})
        self.assertEqual(primeiro, repetido)
        self.assertNotEqual(primeiro, alterado)
        self.assertEqual(len(primeiro), 64)


if __name__ == "__main__":
    unittest.main()
