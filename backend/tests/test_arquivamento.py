from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.app import main
from backend.persistencia.supabase_rest import ErroSupabase


cadastro = importlib.import_module(main.definir_arquivamento.__module__)


class TestArquivamento(unittest.TestCase):
    def setUp(self):
        self.registro = {
            "id_fazenda": 18,
            "nome_fazenda": "Fazenda Teste",
            "numero_apolice": "AP-018",
            "apolices": ["AP-018", "AP-019"],
            "cep": "78890-000",
            "cidade": "Sorriso",
            "uf": "MT",
            "tipo_operacao": "transporte",
            "proximidade_agua": True,
            "latitude": -12.545,
            "longitude": -55.721,
            "area_ha": 250,
            "poligono": {"type": "Polygon", "coordinates": [[
                [-55.72, -12.54], [-55.71, -12.55],
                [-55.73, -12.56], [-55.72, -12.54],
            ]]},
            "arquivada": False,
        }
        self.original = deepcopy(self.registro)
        self.supabase = Mock()
        self.supabase.atualizar.side_effect = self._atualizar
        for substituicao in (
            patch.object(cadastro, "supabase_configurado", return_value=True),
            patch.object(cadastro, "cliente_supabase", return_value=self.supabase),
            patch.object(main, "_autenticacao_obrigatoria", return_value=False),
            patch.object(main, "buscar_registro_geoespacial", return_value=None),
            patch.object(main, "_carregar_score_preview", return_value=None),
        ):
            substituicao.start()
            self.addCleanup(substituicao.stop)
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.origem = next(
            (origem for origem in main._ORIGENS_PERMITIDAS if origem != "*"),
            "https://agrishield-sompo-frontend.vercel.app",
        )

    def _atualizar(self, tabela, payload, *, filtros):
        if filtros != {"id_fazenda": "eq.18"}:
            return None
        atualizada = {**self.registro, **payload}
        if not all(atualizada.get(campo) for campo in (
            "nome_fazenda", "numero_apolice", "cep",
        )):
            raise ErroSupabase("Atualização viola as constraints do cadastro.")
        self.registro = atualizada
        return deepcopy(atualizada)

    def test_arquivar_e_restaurar_preservam_cadastro_e_cors(self):
        for arquivada in (True, False):
            with self.subTest(arquivada=arquivada):
                resposta = self.client.post(
                    "/api/fazendas/18/arquivamento",
                    json={"arquivada": arquivada},
                    headers={"Origin": self.origem},
                )
                self.assertEqual(resposta.status_code, 200, resposta.text)
                self.assertEqual(resposta.json()["arquivada"], arquivada)
                self.assertEqual(resposta.json()["apolices"], ["AP-018", "AP-019"])
                self.assertEqual(
                    self.registro, {**self.original, "arquivada": arquivada},
                )
                self.assertIn(
                    resposta.headers.get("access-control-allow-origin"),
                    (self.origem, "*"),
                )
                self.supabase.atualizar.assert_called_with(
                    cadastro.TABELA_FAZENDAS,
                    {"arquivada": arquivada},
                    filtros={"id_fazenda": "eq.18"},
                )

    def test_fazenda_inexistente_retorna_404(self):
        resposta = self.client.post(
            "/api/fazendas/999/arquivamento", json={"arquivada": True},
        )
        self.assertEqual(resposta.status_code, 404)
        self.assertEqual(self.registro, self.original)

    def test_arquivamento_local_continua_reversivel(self):
        with tempfile.TemporaryDirectory() as pasta:
            with (
                patch.object(cadastro, "supabase_configurado", return_value=False),
                patch.object(cadastro, "ARQUIVO_FAZENDAS", Path(pasta) / "fazendas.csv"),
            ):
                cadastro.criar_base_se_nao_existir()
                original = cadastro.buscar_fazenda("1")
                for arquivada in (True, False):
                    atualizada = cadastro.definir_arquivamento("1", arquivada)
                    self.assertEqual(atualizada, {
                        **original, "arquivada": str(arquivada),
                        "apolices_json": cadastro._normalizar_apolices_json(original),
                    })


if __name__ == "__main__":
    unittest.main()
