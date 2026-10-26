from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.autenticacao import ErroAutenticacao, UsuarioAutenticado


ADMIN = UsuarioAutenticado(
    id="fdd19411-2aca-4b45-a99c-eae69a182a39",
    email="tomholanda300@gmail.com",
    email_confirmado_em="2026-09-23T12:00:00Z",
    metadados={},
)
PERFIL_ADMIN = {
    "usuario_id": ADMIN.id,
    "email": ADMIN.email,
    "nome_completo": "Tom Holanda",
    "funcao": "Administrador",
    "papel": "administrador",
    "status_acesso": "aprovado",
}


class TestApiAuth(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def test_me_exige_sessao(self):
        with patch.object(
            main,
            "autenticar_usuario",
            side_effect=ErroAutenticacao("Sessão ausente."),
        ):
            resposta = self.client.get("/api/auth/me")
        self.assertEqual(resposta.status_code, 401)

    def test_me_retorna_perfil_confirmado(self):
        with (
            patch.object(main, "autenticar_usuario", return_value=ADMIN),
            patch.object(main, "obter_ou_criar_perfil", return_value=PERFIL_ADMIN),
        ):
            resposta = self.client.get(
                "/api/auth/me", headers={"Authorization": "Bearer token"}
            )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json()["perfil"]["papel"], "administrador")
        self.assertEqual(resposta.json()["sessao"]["inatividade_minutos"], 15)

    def test_usuario_pendente_nao_acessa_dados(self):
        perfil = {**PERFIL_ADMIN, "papel": "usuario", "status_acesso": "pendente"}
        with (
            patch.object(main, "_autenticacao_obrigatoria", return_value=True),
            patch.object(main, "autenticar_usuario", return_value=ADMIN),
            patch.object(main, "obter_ou_criar_perfil", return_value=perfil),
        ):
            resposta = self.client.get(
                "/api/fazendas", headers={"Authorization": "Bearer token"}
            )
        self.assertEqual(resposta.status_code, 403)

    def test_apenas_admin_lista_acessos(self):
        usuario_comum = UsuarioAutenticado(
            id=ADMIN.id,
            email="pessoa@empresa.com",
            email_confirmado_em=ADMIN.email_confirmado_em,
            metadados={},
        )
        perfil = {**PERFIL_ADMIN, "email": usuario_comum.email, "papel": "usuario"}
        with (
            patch.object(main, "autenticar_usuario", return_value=usuario_comum),
            patch.object(main, "obter_ou_criar_perfil", return_value=perfil),
        ):
            resposta = self.client.get(
                "/api/auth/usuarios", headers={"Authorization": "Bearer token"}
            )
        self.assertEqual(resposta.status_code, 403)

        with (
            patch.object(main, "autenticar_usuario", return_value=ADMIN),
            patch.object(main, "obter_ou_criar_perfil", return_value=PERFIL_ADMIN),
            patch.object(main, "listar_perfis_login", return_value=[PERFIL_ADMIN]),
        ):
            resposta = self.client.get(
                "/api/auth/usuarios", headers={"Authorization": "Bearer token"}
            )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(resposta.json()["usuarios"]), 1)


if __name__ == "__main__":
    unittest.main()
