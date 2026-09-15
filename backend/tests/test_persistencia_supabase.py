import os
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from backend.persistencia.clima import salvar_observacoes_climaticas
from backend.persistencia.supabase_rest import (
    ClienteSupabaseRest,
    diagnostico_supabase,
    supabase_configurado,
)


class TestConfiguracaoSupabase(unittest.TestCase):
    def test_anon_key_do_frontend_nao_habilita_persistencia_privada(self):
        ambiente = {
            "REACT_APP_SUPABASE_URL": "https://projeto.supabase.co",
            "REACT_APP_SUPABASE_KEY": "anon-publica",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            self.assertFalse(supabase_configurado())
            self.assertEqual(diagnostico_supabase()["persistencia"], "csv_local")

    def test_secret_key_do_backend_habilita_supabase_sem_expor_valor(self):
        ambiente = {
            "SUPABASE_URL": "https://projeto.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_ultrassecreta",
        }
        with patch.dict(os.environ, ambiente, clear=True):
            diagnostico = diagnostico_supabase()
            self.assertTrue(supabase_configurado())
            self.assertEqual(diagnostico["persistencia"], "supabase")
            self.assertNotIn("sb_secret_ultrassecreta", repr(diagnostico))


class TestClienteSupabaseRest(unittest.TestCase):
    @patch("backend.persistencia.supabase_rest.requests.request")
    def test_upsert_envia_chave_apenas_em_headers_e_conflito_na_query(self, requisitar):
        resposta = Mock(status_code=200, content=b'[{"id_fazenda":1}]')
        resposta.raise_for_status.return_value = None
        resposta.json.return_value = [{"id_fazenda": 1}]
        requisitar.return_value = resposta
        cliente = ClienteSupabaseRest(
            url="https://projeto.supabase.co", chave="sb_secret_teste"
        )

        resultado = cliente.upsert(
            "agrishield_fazendas",
            {"id_fazenda": 1},
            conflito="id_fazenda",
        )

        self.assertEqual(resultado, [{"id_fazenda": 1}])
        chamada = requisitar.call_args.kwargs
        self.assertEqual(chamada["params"], {"on_conflict": "id_fazenda"})
        self.assertEqual(chamada["headers"]["apikey"], "sb_secret_teste")
        self.assertNotIn("sb_secret_teste", chamada["params"].values())


class TestPersistenciaClimatica(unittest.TestCase):
    @patch("backend.persistencia.clima.cliente_supabase")
    def test_datas_e_valores_ausentes_sao_serializados_para_json(self, criar_cliente):
        cliente = Mock()
        cliente.upsert.return_value = []
        criar_cliente.return_value = cliente
        df = pd.DataFrame(
            [
                {
                    "data": pd.Timestamp("2026-09-09"),
                    "ano": 2026,
                    "mes": 9,
                    "dia": 9,
                    "temp_media_c": float("nan"),
                }
            ]
        )

        salvar_observacoes_climaticas("7", df, "nasa_power")

        chamada = cliente.upsert.call_args
        linha = chamada.args[1][0]
        self.assertEqual(linha["id_fazenda"], 7)
        self.assertEqual(linha["data"], "2026-09-09")
        self.assertIsNone(linha["temp_media_c"])
        self.assertEqual(chamada.kwargs["conflito"], "id_fazenda,data")


if __name__ == "__main__":
    unittest.main()
