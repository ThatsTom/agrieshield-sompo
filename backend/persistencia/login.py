"""Perfis e aprovação de acesso específicos do AgriShield."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from backend.app.autenticacao import ADMIN_EMAIL, UsuarioAutenticado
from backend.persistencia.supabase_rest import cliente_supabase


TABELA_LOGIN = "agrishield_login"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto(valor: Any, limite: int) -> str:
    return str(valor or "").strip()[:limite]


def buscar_perfil(usuario_id: str) -> dict[str, Any] | None:
    registros = cliente_supabase().selecionar(
        TABELA_LOGIN,
        filtros={"usuario_id": f"eq.{usuario_id}"},
        limite=1,
    )
    return registros[0] if registros else None


def obter_ou_criar_perfil(usuario: UsuarioAutenticado) -> dict[str, Any]:
    existente = buscar_perfil(usuario.id)
    agora = _agora()
    if existente:
        mudancas: dict[str, Any] = {
            "ultimo_acesso_em": agora,
            "email_confirmado_em": usuario.email_confirmado_em,
        }
        if str(existente.get("email") or "").lower() != usuario.email:
            mudancas["email"] = usuario.email
        atualizado = cliente_supabase().atualizar(
            TABELA_LOGIN,
            mudancas,
            filtros={"usuario_id": f"eq.{usuario.id}"},
        )
        return atualizado or {**existente, **mudancas}

    metadados = usuario.metadados
    nome = _texto(
        metadados.get("nome_completo")
        or metadados.get("full_name")
        or usuario.email.split("@", 1)[0],
        120,
    )
    funcao = _texto(metadados.get("funcao") or "Consultor", 80)
    administrador = usuario.email == ADMIN_EMAIL
    payload = {
        "usuario_id": usuario.id,
        "email": usuario.email,
        "nome_completo": nome,
        "funcao": "Administrador" if administrador else funcao,
        "telefone": "",
        "papel": "administrador" if administrador else "usuario",
        "status_acesso": "aprovado" if administrador else "pendente",
        "email_confirmado_em": usuario.email_confirmado_em,
        "ultimo_acesso_em": agora,
        "aprovado_por": usuario.id if administrador else None,
        "aprovado_em": agora if administrador else None,
        "motivo_rejeicao": "",
    }
    salvos = cliente_supabase().upsert(
        TABELA_LOGIN,
        payload,
        conflito="usuario_id",
    )
    return salvos[0] if salvos else payload


def atualizar_perfil(
    usuario_id: str,
    *,
    nome_completo: str,
    funcao: str,
    telefone: str,
) -> dict[str, Any]:
    atualizado = cliente_supabase().atualizar(
        TABELA_LOGIN,
        {
            "nome_completo": _texto(nome_completo, 120),
            "funcao": _texto(funcao, 80),
            "telefone": _texto(telefone, 30),
        },
        filtros={"usuario_id": f"eq.{usuario_id}"},
    )
    if not atualizado:
        raise LookupError("Perfil do usuário não encontrado")
    return atualizado


def listar_perfis() -> list[dict[str, Any]]:
    return cliente_supabase().selecionar(
        TABELA_LOGIN,
        ordem="created_at.desc",
    )


def atualizar_acesso(
    usuario_id: str,
    *,
    administrador_id: str,
    status_acesso: str,
    funcao: str | None = None,
    motivo_rejeicao: str = "",
) -> dict[str, Any]:
    agora = _agora()
    mudancas: dict[str, Any] = {
        "status_acesso": status_acesso,
        "motivo_rejeicao": (
            _texto(motivo_rejeicao, 500)
            if status_acesso == "rejeitado"
            else ""
        ),
        "aprovado_por": administrador_id,
        "aprovado_em": agora if status_acesso == "aprovado" else None,
    }
    if funcao is not None:
        mudancas["funcao"] = _texto(funcao, 80)
    atualizado = cliente_supabase().atualizar(
        TABELA_LOGIN,
        mudancas,
        filtros={"usuario_id": f"eq.{usuario_id}"},
    )
    if not atualizado:
        raise LookupError("Usuário não encontrado")
    return atualizado


def perfil_publico(perfil: Mapping[str, Any]) -> dict[str, Any]:
    campos = (
        "usuario_id",
        "email",
        "nome_completo",
        "funcao",
        "telefone",
        "papel",
        "status_acesso",
        "email_confirmado_em",
        "ultimo_acesso_em",
        "aprovado_por",
        "aprovado_em",
        "motivo_rejeicao",
        "created_at",
        "updated_at",
    )
    return {campo: perfil.get(campo) for campo in campos}


__all__ = [
    "atualizar_acesso",
    "atualizar_perfil",
    "buscar_perfil",
    "listar_perfis",
    "obter_ou_criar_perfil",
    "perfil_publico",
]
