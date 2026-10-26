from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote

from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError
import httpx

from backend import autenticacao_earth_engine as auth
from backend.app import main
from backend.mapbiomas.cliente import ClienteEarthEngineMapBiomas


AMBIENTE_WIF = {
    "EARTH_ENGINE_PROJECT": "sompo-api",
    "GCP_PROJECT_NUMBER": "644279865927",
    "GCP_WORKLOAD_IDENTITY_POOL_ID": "vercel",
    "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID": "vercel",
    "GCP_SERVICE_ACCOUNT_EMAIL": "agrishield-backend@sompo-api.iam.gserviceaccount.com",
}


def resposta_google(dados):
    return Mock(status=200, data=json.dumps(dados).encode(), headers={})


def transporte_google():
    expires = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return Mock(side_effect=[
        resposta_google({
            "access_token": "token-sts-de-teste",
            "expires_in": 3600,
            "token_type": "Bearer",
            "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }),
        resposta_google({"accessToken": "token-google-de-teste", "expireTime": expires}),
    ])


class TestCredenciaisEarthEngine(TestCase):
    def test_sem_federacao_preserva_autenticacao_local(self):
        ee = Mock()
        with patch.dict(os.environ, {}, clear=True):
            auth.inicializar_earth_engine(ee, "local")
        ee.Initialize.assert_called_once_with(project="local")
        ee.Authenticate.assert_not_called()

    def test_configuracao_parcial_nao_faz_fallback_silencioso(self):
        ee = Mock()
        with patch.dict(os.environ, {"GCP_PROJECT_NUMBER": "644279865927"}, clear=True):
            with self.assertRaises(auth.ErroCredenciaisEarthEngine) as erro:
                auth.inicializar_earth_engine(ee, "sompo-api")
        self.assertIn("GCP_SERVICE_ACCOUNT_EMAIL", str(erro.exception))
        ee.Initialize.assert_not_called()

    def test_configuracao_invalida_e_rejeitada_antes_de_usar_token(self):
        for campo, valor in (
            ("GCP_PROJECT_NUMBER", "sompo-api"),
            ("GCP_WORKLOAD_IDENTITY_POOL_ID", "vercel/../../outro"),
            ("GCP_SERVICE_ACCOUNT_EMAIL", "pessoa@example.com"),
        ):
            with self.subTest(campo=campo), patch.dict(
                os.environ, {**AMBIENTE_WIF, campo: valor}, clear=True,
            ):
                with self.assertRaises(auth.ErroCredenciaisEarthEngine):
                    auth.obter_credenciais_earth_engine("sompo-api")

    def test_vercel_exige_token_da_requisicao_e_ignora_token_do_build(self):
        with patch.dict(os.environ, {
            **AMBIENTE_WIF, "VERCEL": "1", "VERCEL_OIDC_TOKEN": "token-build",
        }, clear=True):
            with self.assertRaises(auth.ErroCredenciaisEarthEngine) as erro:
                auth.obter_credenciais_earth_engine("sompo-api")
        self.assertIn("x-vercel-oidc-token", str(erro.exception))
        self.assertNotIn("token-build", str(erro.exception))

    def test_token_local_e_trocado_no_sts_e_na_conta_correta(self):
        transporte = transporte_google()
        with patch.dict(os.environ, {
            **AMBIENTE_WIF, "VERCEL_OIDC_TOKEN": "token-oidc-local",
        }, clear=True):
            credenciais = auth.obter_credenciais_earth_engine("sompo-api")
            credenciais.refresh(transporte)
        self.assertEqual("token-google-de-teste", credenciais.token)
        self.assertEqual(2, transporte.call_count)
        sts, iam = [call.kwargs for call in transporte.call_args_list]
        self.assertEqual("https://sts.googleapis.com/v1/token", sts["url"])
        self.assertEqual("POST", sts["method"])
        corpo = parse_qs(sts["body"].decode())
        self.assertEqual(["token-oidc-local"], corpo["subject_token"])
        self.assertEqual([
            "//iam.googleapis.com/projects/644279865927/locations/global/"
            "workloadIdentityPools/vercel/providers/vercel",
        ], corpo["audience"])
        self.assertEqual(
            "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/"
            "agrishield-backend@sompo-api.iam.gserviceaccount.com:generateAccessToken",
            unquote(iam["url"]),
        )
        self.assertEqual("Bearer token-sts-de-teste", iam["headers"]["authorization"])
        escopos = json.loads(iam["body"])["scope"]
        self.assertIn("https://www.googleapis.com/auth/earthengine", escopos)

    def test_geoespacial_e_mapbiomas_recebem_credenciais_federadas(self):
        geo = importlib.import_module(main.consultar_dados_geoespaciais.__module__)
        for inicializar in (
            lambda ee: geo._inicializar_ee(ee, "sompo-api"),
            lambda ee: ClienteEarthEngineMapBiomas(ee_module=ee)._inicializar(ee),
        ):
            with self.subTest(inicializar=inicializar), patch.dict(os.environ, {
                **AMBIENTE_WIF, "VERCEL_OIDC_TOKEN": "token-local",
            }, clear=True):
                ee = Mock()
                inicializar(ee)
                chamada = ee.Initialize.call_args.kwargs
                self.assertEqual("sompo-api", chamada["project"])
                self.assertEqual(
                    "token-local", chamada["credentials"].retrieve_subject_token(Mock()),
                )
                ee.Authenticate.assert_not_called()

    def test_recalculo_real_da_api_recebe_oidc_no_handler_sincrono(self):
        geo = importlib.import_module(main.consultar_dados_geoespaciais.__module__)
        ee = Mock()
        transporte = transporte_google()
        ee.Initialize.side_effect = lambda **opcoes: opcoes["credentials"].refresh(transporte)
        consultar = main.consultar_dados_geoespaciais
        fazenda = {
            "id_fazenda": "18", "latitude": -12.545, "longitude": -55.721,
            "area_ha": 250,
        }
        srtm = {
            "elevacao_media_m": 410, "elevacao_ponto_m": 417.5,
            "declividade_media_graus": 3.25, "pixels_validos": 3400,
            "pixels_totais": 3500,
        }
        hidro = {
            "encontrada": True, "candidatos": 1,
            "selecionado": {
                "latitude": -12.54, "longitude": -55.72,
                "distancia_m": 725, "upa_km2": 18.5,
            },
        }
        with (
            patch.dict(os.environ, {**AMBIENTE_WIF, "VERCEL": "1"}, clear=True),
            patch.object(main, "_autenticacao_obrigatoria", return_value=False),
            patch.object(main, "buscar_fazenda", return_value=fazenda),
            patch.object(main, "consultar_dados_geoespaciais", side_effect=(
                lambda lat, lon: consultar(lat, lon, usar_cache=False)
            )),
            patch.object(main, "salvar_resultado_geoespacial", side_effect=(
                lambda fazenda, resultado: deepcopy(resultado)
            )),
            patch.object(geo, "_carregar_ee", return_value=ee),
            patch.object(geo, "_consultar_srtm", return_value=srtm),
            patch.object(geo, "_consultar_hidrografia", return_value=hidro),
            TestClient(main.app) as client,
        ):
            resposta = client.post(
                "/api/fazendas/18/geoespacial/recalcular",
                headers={"x-vercel-oidc-token": "token-da-invocacao"},
            )
        self.assertEqual(200, resposta.status_code)
        self.assertEqual("sucesso", resposta.json()["status"])
        self.assertEqual([], resposta.json()["erros"])
        self.assertNotIn("token-da-invocacao", resposta.text)
        corpo_sts = parse_qs(transporte.call_args_list[0].kwargs["body"].decode())
        self.assertEqual(["token-da-invocacao"], corpo_sts["subject_token"])
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            with self.assertRaises(auth.ErroCredenciaisEarthEngine):
                auth._obter_token_oidc()


class TestIsolamentoOidc(IsolatedAsyncioTestCase):
    async def test_tokens_concorrentes_chegam_isolados_aos_workers(self):
        app = FastAPI()
        app.add_middleware(auth.ContextoOidcVercelMiddleware)
        chegaram = 0
        prontos = asyncio.Event()

        @app.get("/teste")
        async def ler():
            nonlocal chegaram
            chegaram += 1
            if chegaram == 2:
                prontos.set()
            await asyncio.wait_for(prontos.wait(), timeout=3)
            token = await asyncio.to_thread(auth._obter_token_oidc)
            return {"token_de_teste": token}

        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://teste",
            ) as client:
                a, b = await asyncio.gather(
                    client.get("/teste", headers={"x-vercel-oidc-token": "token-a"}),
                    client.get("/teste", headers={"x-vercel-oidc-token": "token-b"}),
                )
            self.assertEqual("token-a", a.json()["token_de_teste"])
            self.assertEqual("token-b", b.json()["token_de_teste"])
            with self.assertRaises(auth.ErroCredenciaisEarthEngine):
                auth._obter_token_oidc()

    async def test_contexto_e_removido_mesmo_quando_a_aplicacao_falha(self):
        async def falhar(scope, receive, send):
            self.assertEqual("token-efemero", auth._obter_token_oidc())
            raise RuntimeError("falha controlada")

        middleware = auth.ContextoOidcVercelMiddleware(falhar)
        scope = {"type": "http", "headers": [(b"x-vercel-oidc-token", b"token-efemero")]}
        with patch.dict(os.environ, {"VERCEL": "1"}, clear=True):
            with self.assertRaises(RuntimeError):
                await middleware(scope, None, None)
            with self.assertRaises(RefreshError):
                auth._FornecedorTokenVercel().get_subject_token(None, None)
