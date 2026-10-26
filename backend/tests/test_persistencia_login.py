from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from backend.app.autenticacao import UsuarioAutenticado
from backend.persistencia.login import obter_ou_criar_perfil


def usuario(email: str) -> UsuarioAutenticado:
    return UsuarioAutenticado(
        id="fdd19411-2aca-4b45-a99c-eae69a182a39",
        email=email,
        email_confirmado_em="2026-09-23T12:00:00Z",
        metadados={"nome_completo": "Pessoa Teste", "funcao": "Consultor"},
    )


class TestPersistenciaLogin(unittest.TestCase):
    @patch("backend.persistencia.login.cliente_supabase")
    def test_nova_conta_comeca_pendente(self, criar_cliente):
        cliente = Mock()
        cliente.selecionar.return_value = []
        cliente.upsert.side_effect = lambda _tabela, payload, **_kwargs: [payload]
        criar_cliente.return_value = cliente

        perfil = obter_ou_criar_perfil(usuario("pessoa@empresa.com"))

        self.assertEqual(perfil["status_acesso"], "pendente")
        self.assertEqual(perfil["papel"], "usuario")
        self.assertIsNone(perfil["aprovado_por"])

    @patch("backend.persistencia.login.cliente_supabase")
    def test_email_principal_recebe_administrador_aprovado(self, criar_cliente):
        cliente = Mock()
        cliente.selecionar.return_value = []
        cliente.upsert.side_effect = lambda _tabela, payload, **_kwargs: [payload]
        criar_cliente.return_value = cliente

        perfil = obter_ou_criar_perfil(usuario("tomholanda300@gmail.com"))

        self.assertEqual(perfil["status_acesso"], "aprovado")
        self.assertEqual(perfil["papel"], "administrador")
        self.assertEqual(perfil["funcao"], "Administrador")


if __name__ == "__main__":
    unittest.main()
