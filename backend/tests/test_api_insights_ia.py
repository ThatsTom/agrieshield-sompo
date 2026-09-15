from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.servico_insights_ia import ResultadoInsightIA


INSIGHT = {
    "resumo_executivo": "Leitura executiva.",
    "nivel_atencao": "moderado",
    "leitura_principal": "Acompanhar as condições.",
    "prioridades": [],
    "perguntas_consultor": [],
    "pontos_positivos": [],
    "limitacoes": ["Dados sujeitos a atualização."],
}


class TestApiInsightsIA(unittest.TestCase):
    def setUp(self):
        main._cache_insights_ia.clear()
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

        patches = [
            patch.object(main, "buscar_fazenda", return_value={"id_fazenda": "7"}),
            patch.object(main, "buscar_registro_geoespacial", return_value=None),
            patch.object(
                main,
                "_normalizar_fazenda",
                return_value={
                    "id": "7",
                    "nome_fazenda": "Fazenda Teste",
                    "cidade": "Sorriso",
                    "uf": "MT",
                    "area_ha": 120,
                    "tipo_operacao": "campo",
                    "proximidade_agua": False,
                    "status_geoespacial": "PENDENTE",
                },
            ),
            patch.object(
                main,
                "get_dashboard",
                return_value={
                    "score": {"score": 72, "condicao_atual": "Atenção"},
                    "alertas": [],
                    "previsao_5d": [],
                },
            ),
            patch.object(
                main,
                "listar_fazendas",
                return_value=[
                    {
                        "id_fazenda": "7",
                        "tipo_operacao": "campo",
                        "proximidade_agua": "False",
                        "arquivada": "False",
                        "uf": "MT",
                    }
                ],
            ),
            patch.object(main, "supabase_configurado", return_value=False),
            patch.object(
                main,
                "gerar_insight_ia",
                return_value=ResultadoInsightIA(insight=INSIGHT, uso={}),
            ),
        ]
        self.mocks = [item.start() for item in patches]
        for item in patches:
            self.addCleanup(item.stop)

    def test_gera_e_depois_reaproveita_cache(self):
        primeira = self.client.post(
            "/api/fazendas/7/insights-ia", json={"forcar": False}
        )
        segunda = self.client.post(
            "/api/fazendas/7/insights-ia", json={"forcar": False}
        )

        self.assertEqual(primeira.status_code, 200)
        self.assertEqual(primeira.json()["origem"], "openai")
        self.assertFalse(primeira.json()["cache"])
        self.assertEqual(segunda.json()["origem"], "cache_memoria")
        self.assertTrue(segunda.json()["cache"])
        self.assertEqual(self.mocks[-1].call_count, 1)

    def test_forcar_ignora_cache(self):
        self.client.post("/api/fazendas/7/insights-ia", json={"forcar": False})
        resposta = self.client.post(
            "/api/fazendas/7/insights-ia", json={"forcar": True}
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["origem"], "openai")
        self.assertEqual(self.mocks[-1].call_count, 2)


if __name__ == "__main__":
    unittest.main()
