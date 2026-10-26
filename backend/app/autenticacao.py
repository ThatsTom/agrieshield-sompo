"""Validação server-side de sessões emitidas pelo Supabase Auth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from backend.persistencia.supabase_rest import cliente_supabase


ADMIN_EMAIL = "tomholanda300@gmail.com"


class ErroAutenticacao(RuntimeError):
    def __init__(self, mensagem: str, status_code: int = 401):
        super().__init__(mensagem)
        self.status_code = status_code


@dataclass(frozen=True)
class UsuarioAutenticado:
    id: str
    email: str
    email_confirmado_em: str | None
    metadados: dict[str, Any]


def _extrair_token(cabecalho: str | None) -> str:
    partes = str(cabecalho or "").strip().split(" ", 1)
    if len(partes) != 2 or partes[0].lower() != "bearer" or not partes[1].strip():
        raise ErroAutenticacao("Sessão ausente. Entre novamente para continuar.")
    return partes[1].strip()


def autenticar_usuario(cabecalho_authorization: str | None) -> UsuarioAutenticado:
    token = _extrair_token(cabecalho_authorization)
    cliente = cliente_supabase()
    try:
        resposta = requests.get(
            f"{cliente.url}/auth/v1/user",
            headers={
                "apikey": cliente.chave,
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=(5, 20),
        )
        resposta.raise_for_status()
        payload = resposta.json()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {401, 403}:
            raise ErroAutenticacao(
                "Sua sessão expirou. Entre novamente para continuar."
            ) from exc
        raise ErroAutenticacao(
            "Não foi possível validar sua sessão neste momento.", status_code=503
        ) from exc
    except ValueError as exc:
        raise ErroAutenticacao(
            "O serviço de autenticação retornou uma resposta inválida.",
            status_code=503,
        ) from exc

    usuario_id = str(payload.get("id") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    confirmado = payload.get("email_confirmed_at")
    if not usuario_id or not email:
        raise ErroAutenticacao("A sessão não identifica um usuário válido.")
    if not confirmado:
        raise ErroAutenticacao("Confirme seu e-mail antes de acessar o AgriShield.")
    metadados = payload.get("user_metadata")
    return UsuarioAutenticado(
        id=usuario_id,
        email=email,
        email_confirmado_em=str(confirmado),
        metadados=dict(metadados) if isinstance(metadados, dict) else {},
    )


__all__ = [
    "ADMIN_EMAIL",
    "ErroAutenticacao",
    "UsuarioAutenticado",
    "autenticar_usuario",
]
