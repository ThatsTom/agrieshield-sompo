"""Cliente REST minimo do Supabase para o backend serverless.

O frontend nunca importa este modulo. A credencial aceita aqui precisa ser uma
chave secreta moderna (``sb_secret_...``) ou a ``service_role`` legada, ambas
mantidas somente no ambiente do backend.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Iterable, Mapping
from urllib.parse import quote

import requests


class ErroSupabase(RuntimeError):
    """Falha segura ao acessar a Data API do Supabase."""


def _primeira_variavel(*nomes: str) -> str:
    for nome in nomes:
        valor = str(os.getenv(nome) or "").strip()
        if valor:
            return valor
    return ""


def _url_configurada() -> str:
    # O alias REACT_APP e aceito apenas para facilitar a transicao do .env
    # atual. Ele contem uma URL publica, nunca uma credencial.
    return _primeira_variavel("SUPABASE_URL", "REACT_APP_SUPABASE_URL").rstrip("/")


def _chave_secreta_configurada() -> str:
    return _primeira_variavel("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")


def supabase_configurado() -> bool:
    return bool(_url_configurada() and _chave_secreta_configurada())


def diagnostico_supabase() -> dict[str, Any]:
    url = _url_configurada()
    chave = _chave_secreta_configurada()
    return {
        "configurado": bool(url and chave),
        "url_configurada": bool(url),
        "chave_backend_configurada": bool(chave),
        "persistencia": "supabase" if url and chave else "csv_local",
    }


@dataclass(frozen=True)
class ClienteSupabaseRest:
    url: str
    chave: str
    timeout: tuple[int, int] = (5, 30)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.chave,
            "Authorization": f"Bearer {self.chave}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _requisitar(
        self,
        metodo: str,
        tabela: str,
        *,
        params: Mapping[str, Any] | None = None,
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = self._headers
        if prefer:
            headers["Prefer"] = prefer
        try:
            resposta = requests.request(
                metodo,
                f"{self.url}/rest/v1/{quote(tabela, safe='')}",
                headers=headers,
                params=dict(params or {}),
                json=payload,
                timeout=self.timeout,
            )
            resposta.raise_for_status()
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detalhe = ""
            resposta_erro = getattr(exc, "response", None)
            if resposta_erro is not None:
                try:
                    corpo = resposta_erro.json()
                    detalhe = str(corpo.get("message") or corpo.get("hint") or "")
                except (TypeError, ValueError):
                    detalhe = ""
            sufixo = f" ({status})" if status else ""
            if detalhe:
                sufixo += f": {detalhe[:240]}"
            raise ErroSupabase(f"Falha ao acessar {tabela} no Supabase{sufixo}") from exc

        if resposta.status_code == 204 or not resposta.content:
            return None
        try:
            return resposta.json()
        except ValueError as exc:
            raise ErroSupabase(
                f"Resposta invalida da tabela {tabela} no Supabase"
            ) from exc

    def selecionar(
        self,
        tabela: str,
        *,
        colunas: str = "*",
        filtros: Mapping[str, str] | None = None,
        ordem: str | None = None,
        limite: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": colunas}
        params.update(dict(filtros or {}))
        if ordem:
            params["order"] = ordem
        if limite is not None:
            params["limit"] = limite
        resultado = self._requisitar("GET", tabela, params=params)
        return list(resultado or [])

    def inserir(self, tabela: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        resultado = self._requisitar(
            "POST",
            tabela,
            payload=dict(payload),
            prefer="return=representation",
        )
        if not resultado:
            raise ErroSupabase(f"O Supabase nao retornou o registro de {tabela}")
        return dict(resultado[0])

    def atualizar(
        self,
        tabela: str,
        payload: Mapping[str, Any],
        *,
        filtros: Mapping[str, str],
    ) -> dict[str, Any] | None:
        resultado = self._requisitar(
            "PATCH",
            tabela,
            params=filtros,
            payload=dict(payload),
            prefer="return=representation",
        )
        return dict(resultado[0]) if resultado else None

    def upsert(
        self,
        tabela: str,
        payload: Mapping[str, Any] | Iterable[Mapping[str, Any]],
        *,
        conflito: str,
        retornar: bool = True,
    ) -> list[dict[str, Any]]:
        if isinstance(payload, Mapping):
            corpo: Any = dict(payload)
        else:
            corpo = [dict(item) for item in payload]
        prefer = "resolution=merge-duplicates"
        prefer += ",return=representation" if retornar else ",return=minimal"
        resultado = self._requisitar(
            "POST",
            tabela,
            params={"on_conflict": conflito},
            payload=corpo,
            prefer=prefer,
        )
        return [dict(item) for item in (resultado or [])]


def cliente_supabase() -> ClienteSupabaseRest:
    url = _url_configurada()
    chave = _chave_secreta_configurada()
    if not url or not chave:
        raise ErroSupabase(
            "Configure SUPABASE_URL e SUPABASE_SECRET_KEY no ambiente do backend"
        )
    return ClienteSupabaseRest(url=url, chave=chave)


__all__ = [
    "ClienteSupabaseRest",
    "ErroSupabase",
    "cliente_supabase",
    "diagnostico_supabase",
    "supabase_configurado",
]
