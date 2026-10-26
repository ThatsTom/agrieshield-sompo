"""Autenticação Earth Engine local ou por federação OIDC da Vercel.

O token da plataforma fica no contexto da requisição, sem arquivo, variável
global mutável ou gravação em os.environ. O Google valida o token no STS e
aplica o vínculo IAM da conta de serviço antes de emitir o acesso temporário.
"""

from __future__ import annotations

from contextvars import ContextVar
import os
import re
from typing import Any
from urllib.parse import quote

from google.auth import identity_pool
from google.auth.exceptions import RefreshError
from starlette.types import ASGIApp, Receive, Scope, Send


_token_oidc: ContextVar[str | None] = ContextVar("earth_engine_oidc", default=None)
_VARIAVEIS_FEDERACAO = (
    "GCP_PROJECT_NUMBER",
    "GCP_WORKLOAD_IDENTITY_POOL_ID",
    "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID",
    "GCP_SERVICE_ACCOUNT_EMAIL",
)
_ESCOPOS = (
    "https://www.googleapis.com/auth/earthengine",
    "https://www.googleapis.com/auth/cloud-platform",
)


class ErroCredenciaisEarthEngine(RuntimeError):
    """Configuração incompleta ou token da plataforma indisponível."""


class ContextoOidcVercelMiddleware:
    """Propaga o token aos handlers síncronos sem misturar requisições."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        cabecalhos = dict(scope.get("headers", []))
        token = cabecalhos.get(b"x-vercel-oidc-token", b"").decode("latin-1").strip()
        marcador = _token_oidc.set(token or None)
        try:
            await self.app(scope, receive, send)
        finally:
            _token_oidc.reset(marcador)


def _obter_token_oidc() -> str:
    token = _token_oidc.get()
    # Em produção não reutiliza um token estático do build. O token vigente
    # é injetado pela Vercel no cabeçalho de cada invocação da Function.
    if not token and os.getenv("VERCEL") != "1":
        token = os.getenv("VERCEL_OIDC_TOKEN", "").strip()
    if not token:
        raise ErroCredenciaisEarthEngine(
            "Token OIDC da Vercel ausente. Ative OIDC em Settings > Security "
            "do backend e publique novamente; a Function deve receber "
            "x-vercel-oidc-token."
        )
    return token


class _FornecedorTokenVercel(identity_pool.SubjectTokenSupplier):
    def get_subject_token(self, context: Any, request: Any) -> str:
        try:
            return _obter_token_oidc()
        except ErroCredenciaisEarthEngine as exc:
            raise RefreshError(str(exc)) from exc


def obter_credenciais_earth_engine(projeto: str) -> identity_pool.Credentials | None:
    valores = {nome: os.getenv(nome, "").strip() for nome in _VARIAVEIS_FEDERACAO}
    if not any(valores.values()):
        return None
    ausentes = [nome for nome, valor in valores.items() if not valor]
    if ausentes:
        raise ErroCredenciaisEarthEngine(
            "Federação Earth Engine incompleta. Configure: " + ", ".join(ausentes)
        )
    numero = valores["GCP_PROJECT_NUMBER"]
    pool = valores["GCP_WORKLOAD_IDENTITY_POOL_ID"]
    provedor = valores["GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID"]
    email = valores["GCP_SERVICE_ACCOUNT_EMAIL"]
    if not numero.isascii() or not numero.isdigit():
        raise ErroCredenciaisEarthEngine("GCP_PROJECT_NUMBER deve ser o número do projeto.")
    if not all(re.fullmatch(r"[a-z0-9-]+", valor) for valor in (pool, provedor)):
        raise ErroCredenciaisEarthEngine("IDs do pool e do provedor OIDC inválidos.")
    if not re.fullmatch(r"[a-z0-9-]+@[a-z0-9-]+\.iam\.gserviceaccount\.com", email):
        raise ErroCredenciaisEarthEngine("GCP_SERVICE_ACCOUNT_EMAIL inválido.")
    _obter_token_oidc()
    return identity_pool.Credentials(
        audience=(
            f"//iam.googleapis.com/projects/{numero}/locations/global/"
            f"workloadIdentityPools/{pool}/providers/{provedor}"
        ),
        subject_token_type="urn:ietf:params:oauth:token-type:jwt",
        token_url="https://sts.googleapis.com/v1/token",
        subject_token_supplier=_FornecedorTokenVercel(),
        service_account_impersonation_url=(
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            f"{quote(email, safe='')}:generateAccessToken"
        ),
        scopes=_ESCOPOS,
        quota_project_id=projeto,
    )


def inicializar_earth_engine(ee: Any, projeto: str) -> None:
    credenciais = obter_credenciais_earth_engine(projeto)
    if credenciais is None:
        ee.Initialize(project=projeto)
    else:
        ee.Initialize(credentials=credenciais, project=projeto)
