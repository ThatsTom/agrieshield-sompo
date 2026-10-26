from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import requests

from backend.app.autenticacao import (
    ErroAutenticacao,
    _extrair_token,
    autenticar_usuario,
)


class TestAutenticacao(unittest.TestCase):
    def test_exige_bearer_token(self):
        with self.assertRaises(ErroAutenticacao):
            _extrair_token(None)
        with self.assertRaises(ErroAutenticacao):
            _extrair_token("Basic segredo")

    @patch("backend.app.autenticacao.requests.get")
    @patch("backend.app.autenticacao.cliente_supabase")
    def test_valida_usuario_confirmado_no_supabase(self, criar_cliente, get):
        criar_cliente.return_value = Mock(
            url="https://projeto.supabase.co", chave="segredo-backend"
        )
        resposta = Mock()
        resposta.raise_for_status.return_value = None
        resposta.json.return_value = {
            "id": "fdd19411-2aca-4b45-a99c-eae69a182a39",
            "email": "Pessoa@Empresa.com",
            "email_confirmed_at": "2026-09-23T12:00:00Z",
            "user_metadata": {"nome_completo": "Pessoa Teste"},
        }
        get.return_value = resposta

        usuario = autenticar_usuario("Bearer token-de-acesso")

        self.assertEqual(usuario.email, "pessoa@empresa.com")
        self.assertEqual(usuario.metadados["nome_completo"], "Pessoa Teste")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"],
            "Bearer token-de-acesso",
        )

    @patch("backend.app.autenticacao.requests.get")
    @patch("backend.app.autenticacao.cliente_supabase")
    def test_recusa_email_nao_confirmado(self, criar_cliente, get):
        criar_cliente.return_value = Mock(url="https://projeto.supabase.co", chave="x")
        resposta = Mock()
        resposta.raise_for_status.return_value = None
        resposta.json.return_value = {
            "id": "fdd19411-2aca-4b45-a99c-eae69a182a39",
            "email": "pessoa@empresa.com",
            "email_confirmed_at": None,
        }
        get.return_value = resposta

        with self.assertRaisesRegex(ErroAutenticacao, "Confirme"):
            autenticar_usuario("Bearer token")

    @patch("backend.app.autenticacao.requests.get")
    @patch("backend.app.autenticacao.cliente_supabase")
    def test_token_expirado_retorna_erro_seguro(self, criar_cliente, get):
        criar_cliente.return_value = Mock(url="https://projeto.supabase.co", chave="x")
        resposta = Mock(status_code=401)
        erro = requests.HTTPError(response=resposta)
        get.side_effect = erro

        with self.assertRaisesRegex(ErroAutenticacao, "expirou") as contexto:
            autenticar_usuario("Bearer token-secreto")
        self.assertNotIn("token-secreto", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
