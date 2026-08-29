from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "etl"))
sys.path.insert(0, str(BACKEND / "app"))

from app import main
import etapa3_engenharia_variaveis as etapa3
from backend.app.fabrica_servico_avaliacao_exposicao import (
    criar_servico_avaliacao_exposicao,
)
from backend.app.provedor_contexto_territorial_persistido import (
    ProvedorContextoTerritorialPersistido,
)
from backend.app.provedor_pesos_perigos_persistido import (
    ProvedorPesosPerigosPersistido,
)
from backend.app.servico_avaliacao_exposicao import (
    ContextoTerritorialIncompativel,
    ContextoTerritorialIndisponivel,
    CoordenadasIndisponiveis,
    FazendaNaoEncontrada,
    FonteMeteorologicaIndisponivel,
    PeriodoHistoricoInvalido,
    RepositorioFazendasIndisponivel,
    RepositorioFazendasPorFuncao,
)
from backend.etl import etapa4_dados_geoespaciais as etapa4
from backend.exposicao import (
    ResultadoApresentacaoExposicaoMaquinario,
    criar_apresentacao_exposicao_maquinario,
)
from backend.exposicao.clientes import (
    ClienteNasaPowerHistorico,
    ClienteOpenMeteoHistorico,
)
from backend.risco.modelos import FonteDado
from backend.tests.test_exposicao_avaliacao_exposicao import (
    DATA_REFERENCIA,
    criar_serie_avaliacao,
    executar as executar_avaliacao_fixture,
)


ID_FAZENDA = "F001"


def criar_resultado_apresentacao() -> ResultadoApresentacaoExposicaoMaquinario:
    avaliacao = executar_avaliacao_fixture(criar_serie_avaliacao(cenario="aumento"))
    resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
    payload = resultado.model_dump()
    payload["id_fazenda"] = ID_FAZENDA
    return ResultadoApresentacaoExposicaoMaquinario.model_validate(payload)


class ServicoFalso:
    def __init__(self, resultado=None, erro: Exception | None = None):
        self.resultado = (
            resultado if resultado is not None else criar_resultado_apresentacao()
        )
        self.erro = erro
        self.chamadas: list[dict[str, object]] = []

    def avaliar_exposicao_fazenda(
        self,
        id_fazenda: str,
        data_referencia: date,
        *,
        fonte: FonteDado,
    ) -> ResultadoApresentacaoExposicaoMaquinario:
        self.chamadas.append(
            {
                "id_fazenda": id_fazenda,
                "data_referencia": data_referencia,
                "fonte": fonte,
            }
        )
        if self.erro is not None:
            raise self.erro
        return self.resultado


class BaseApiExposicao(unittest.TestCase):
    def setUp(self):
        self.servico = ServicoFalso()
        main.app.dependency_overrides[main.obter_servico_avaliacao_exposicao] = (
            lambda: self.servico
        )
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        main.app.dependency_overrides.clear()
        self.client.close()


class TestRespostaHttp(BaseApiExposicao):
    def test_200_retorna_integralmente_o_dto_de_apresentacao(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()
        esperado = self.servico.resultado.model_dump(mode="json")
        self.assertEqual(payload, esperado)
        self.assertEqual(payload["politica_id"], esperado["politica_id"])
        self.assertEqual(payload["score_atual"], esperado["score_atual"])
        self.assertEqual(
            payload["classificacao_atual"], esperado["classificacao_atual"]
        )
        self.assertEqual(payload["score_anterior"], esperado["score_anterior"])
        self.assertEqual(payload["variacao_pontos"], esperado["variacao_pontos"])
        self.assertEqual(len(payload["perigos"]), 5)
        self.assertEqual(
            set(payload["detalhes_perigos"]),
            {"trafegabilidade", "incendio", "instabilidade", "tempestades"},
        )
        self.assertIn(
            "dia_maior_indice",
            payload["detalhes_perigos"]["incendio"],
        )
        self.assertIn(
            "peso_dia",
            payload["detalhes_perigos"]["trafegabilidade"],
        )
        self.assertIn(
            "limiar_relevancia",
            payload["detalhes_perigos"]["trafegabilidade"],
        )
        self.assertEqual(
            set(payload["detalhes_perigos"]["tempestades"]["agregacao_90d"]).issuperset(
                {
                    "severidade",
                    "frequencia",
                    "duracao",
                    "recorrencia",
                    "indice_agregado",
                }
            ),
            True,
        )
        self.assertEqual(payload["perigo_dominante"], esperado["perigo_dominante"])
        self.assertEqual(payload["timeline_eventos"], esperado["timeline_eventos"])
        self.assertEqual(payload["qualidade_dados"], esperado["qualidade_dados"])
        self.assertEqual(payload["score_publicavel"], esperado["score_publicavel"])
        self.assertEqual(
            payload["avaliacao_publicavel"],
            esperado["avaliacao_publicavel"],
        )

    def test_resposta_nao_publica_score_de_confianca(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 200)
        contrato_serializado = resposta.text.lower()
        for termo_inexistente in (
            "confidence",
            "confianca",
            "confiança",
            "reliability",
            "confiabilidade",
        ):
            with self.subTest(termo=termo_inexistente):
                self.assertNotIn(termo_inexistente, contrato_serializado)

    def test_comparacao_e_entre_janelas_anterior_e_atual_de_90_dias(self):
        avaliacao = executar_avaliacao_fixture(criar_serie_avaliacao(cenario="aumento"))
        self.servico.resultado = criar_apresentacao_exposicao_maquinario(avaliacao)

        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )

        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()
        self.assertEqual(avaliacao.janela_anterior.dias_esperados, 90)
        self.assertEqual(avaliacao.janela_atual.dias_esperados, 90)
        self.assertLess(avaliacao.janela_anterior.fim, avaliacao.janela_atual.inicio)
        self.assertEqual(payload["score_anterior"], avaliacao.comparacao.score_anterior)
        self.assertEqual(payload["score_atual"], avaliacao.comparacao.score_atual)
        self.assertEqual(
            payload["variacao_pontos"],
            avaliacao.comparacao.variacao_pontos,
        )
        self.assertNotIn("score_legado", payload)

    def test_data_explicita_e_repassada_sem_consultar_relogio(self):
        with patch.object(
            main,
            "_data_atual_servidor",
            side_effect=AssertionError("relogio nao deve ser consultado"),
        ):
            resposta = self.client.get(
                f"/api/v1/exposicao/{ID_FAZENDA}",
                params={"data_referencia": "2026-08-14"},
            )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.servico.chamadas[0]["data_referencia"],
            date(2026, 8, 14),
        )

    def test_data_default_e_resolvida_uma_vez_na_camada_http(self):
        esperada = date(2026, 8, 15)
        with patch.object(
            main,
            "_data_atual_servidor",
            return_value=esperada,
        ) as relogio:
            resposta = self.client.get(f"/api/v1/exposicao/{ID_FAZENDA}")
        self.assertEqual(resposta.status_code, 200)
        relogio.assert_called_once_with()
        self.assertEqual(self.servico.chamadas[0]["data_referencia"], esperada)

    def test_fonte_default_e_nasa_power(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(
            self.servico.chamadas[0]["fonte"],
            FonteDado.NASA_POWER,
        )

    def test_open_meteo_e_selecionada_explicitamente_sem_nasa(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={
                "data_referencia": DATA_REFERENCIA.isoformat(),
                "fonte": "OPEN_METEO",
            },
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(len(self.servico.chamadas), 1)
        self.assertEqual(
            self.servico.chamadas[0]["fonte"],
            FonteDado.OPEN_METEO,
        )

    def test_fonte_invalida_retorna_422_sem_chamar_servico(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"fonte": "INMET"},
        )
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(self.servico.chamadas, [])

    def test_data_invalida_retorna_422_sem_chamar_servico(self):
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": "14-08-2026"},
        )
        self.assertEqual(resposta.status_code, 422)
        self.assertEqual(self.servico.chamadas, [])


class TestErrosHttp(BaseApiExposicao):
    def test_erros_tipados_possuem_status_e_payload_estavel(self):
        casos = (
            (FazendaNaoEncontrada(ID_FAZENDA), 404, "FAZENDA_NAO_ENCONTRADA"),
            (CoordenadasIndisponiveis(ID_FAZENDA), 422, "COORDENADAS_INDISPONIVEIS"),
            (
                ContextoTerritorialIndisponivel(ID_FAZENDA),
                422,
                "CONTEXTO_TERRITORIAL_INDISPONIVEL",
            ),
            (
                ContextoTerritorialIncompativel(ID_FAZENDA),
                422,
                "CONTEXTO_TERRITORIAL_INCOMPATIVEL",
            ),
            (
                PeriodoHistoricoInvalido(ID_FAZENDA),
                422,
                "PERIODO_HISTORICO_INVALIDO",
            ),
            (
                FonteMeteorologicaIndisponivel(
                    ID_FAZENDA,
                    FonteDado.NASA_POWER,
                    RuntimeError("payload externo sensivel"),
                ),
                503,
                "FONTE_METEOROLOGICA_INDISPONIVEL",
            ),
            (
                RepositorioFazendasIndisponivel(
                    ID_FAZENDA,
                    RuntimeError("caminho local sensivel"),
                ),
                503,
                "REPOSITORIO_FAZENDAS_INDISPONIVEL",
            ),
        )
        for erro, status, codigo in casos:
            with self.subTest(codigo=codigo):
                self.servico.erro = erro
                resposta = self.client.get(
                    f"/api/v1/exposicao/{ID_FAZENDA}",
                    params={"data_referencia": DATA_REFERENCIA.isoformat()},
                )
                self.assertEqual(resposta.status_code, status)
                self.assertEqual(resposta.json()["detail"]["codigo"], codigo)
                self.assertEqual(
                    set(resposta.json()["detail"]),
                    {"codigo", "mensagem"},
                )
                self.assertNotIn("sensivel", resposta.text)

    def test_erro_nao_mapeado_permanece_500(self):
        self.servico.erro = RuntimeError("erro inesperado")
        resposta = self.client.get(
            f"/api/v1/exposicao/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 500)
        self.assertNotIn("erro inesperado", resposta.text)


class TestFactoryENaoRegressao(BaseApiExposicao):
    def test_endpoint_nao_chama_funcoes_do_score_ou_dashboard_legado(self):
        proibida = AssertionError("fluxo legado nao deve ser chamado")
        with (
            patch.object(main, "_gerar_score", side_effect=proibida) as gerar_score,
            patch.object(
                main,
                "consolidar_para_dashboard",
                side_effect=proibida,
            ) as consolidar,
            patch.object(
                etapa3,
                "_calcular_score",
                side_effect=proibida,
            ) as calcular_score,
        ):
            resposta = self.client.get(
                f"/api/v1/exposicao/{ID_FAZENDA}",
                params={"data_referencia": DATA_REFERENCIA.isoformat()},
            )

        self.assertEqual(resposta.status_code, 200)
        gerar_score.assert_not_called()
        consolidar.assert_not_called()
        calcular_score.assert_not_called()

    def test_factory_compone_componentes_sem_acionar_earth_engine(self):
        with patch.object(
            etapa4,
            "_carregar_ee",
            side_effect=AssertionError("Earth Engine nao deve ser carregado"),
        ) as carregar_ee:
            servico = criar_servico_avaliacao_exposicao()
        carregar_ee.assert_not_called()
        self.assertIsInstance(
            servico._repositorio_fazendas,
            RepositorioFazendasPorFuncao,
        )
        self.assertIsInstance(
            servico._clientes_meteorologicos[FonteDado.NASA_POWER],
            ClienteNasaPowerHistorico,
        )
        self.assertIsInstance(
            servico._clientes_meteorologicos[FonteDado.OPEN_METEO],
            ClienteOpenMeteoHistorico,
        )
        self.assertIsInstance(
            servico._provedor_contexto_territorial,
            ProvedorContextoTerritorialPersistido,
        )
        self.assertIsInstance(
            servico._provedor_pesos_perigos,
            ProvedorPesosPerigosPersistido,
        )

    def test_openapi_documenta_rota_response_model_e_fontes(self):
        schema = main.app.openapi()
        operacao = schema["paths"][f"/api/v1/exposicao/{{id_fazenda}}"]["get"]
        self.assertIn("Score demonstrativo", operacao["description"])
        self.assertIn(
            "ResultadoApresentacaoExposicaoMaquinario",
            str(operacao["responses"]["200"]),
        )
        fonte = next(
            parametro
            for parametro in operacao["parameters"]
            if parametro["name"] == "fonte"
        )
        self.assertEqual(
            schema["components"]["schemas"]["FonteHistoricaExposicao"]["enum"],
            ["NASA_POWER", "OPEN_METEO"],
        )
        self.assertEqual(fonte["schema"]["default"], "NASA_POWER")

    def test_endpoints_legados_permanecem_registrados_e_basicos_respondem(self):
        rotas = {rota.path for rota in main.app.routes}
        for rota in (
            "/api/fazendas",
            "/api/fazendas/{id_fazenda}/score",
            "/api/fazendas/{id_fazenda}/alertas",
            "/api/fazendas/{id_fazenda}/dashboard",
            "/api/fazendas/{id_fazenda}/geoespacial",
            "/api/fazendas/{id_fazenda}/inmet",
            "/api/fazendas/{id_fazenda}/mapbiomas",
        ):
            with self.subTest(rota=rota):
                self.assertIn(rota, rotas)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/api/fazendas").status_code, 200)


if __name__ == "__main__":
    unittest.main()
