from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from backend.persistencia.insights_ia import buscar_insight_ia, salvar_insight_ia


class TestPersistenciaInsightsIA(unittest.TestCase):
    @patch("backend.persistencia.insights_ia.cliente_supabase")
    def test_busca_por_fazenda_e_hash(self, criar_cliente):
        cliente = Mock()
        cliente.selecionar.return_value = [{"id_fazenda": 3, "insight": {}}]
        criar_cliente.return_value = cliente

        resultado = buscar_insight_ia("3", "a" * 64)

        self.assertEqual(resultado["id_fazenda"], 3)
        self.assertEqual(
            cliente.selecionar.call_args.kwargs["filtros"],
            {"id_fazenda": "eq.3", "contexto_hash": f"eq.{'a' * 64}"},
        )

    @patch("backend.persistencia.insights_ia.cliente_supabase")
    def test_upsert_mantem_um_briefing_por_fazenda(self, criar_cliente):
        cliente = Mock()
        cliente.upsert.return_value = [{"id_fazenda": 3}]
        criar_cliente.return_value = cliente

        salvar_insight_ia(
            "3",
            contexto_hash="b" * 64,
            modelo="gpt-4o-mini",
            insight={"resumo": "teste"},
        )

        chamada = cliente.upsert.call_args
        self.assertEqual(chamada.args[0], "agrishield_insights_ia")
        self.assertEqual(chamada.kwargs["conflito"], "id_fazenda")
        self.assertEqual(chamada.args[1]["id_fazenda"], 3)


if __name__ == "__main__":
    unittest.main()
