from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import math
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "etl"))
sys.path.insert(0, str(BACKEND / "app"))

from app import main
from mapbiomas.cliente import (
    ASSET_ID,
    ClienteEarthEngineMapBiomas,
    ErroConfiguracaoMapBiomas,
    ErroDadosMapBiomas,
)
from mapbiomas.legenda import (
    CODIGOS_AGRICULTURA,
    CODIGOS_AGUA,
    CODIGOS_NAO_OBSERVADOS,
    CODIGOS_PASTAGEM,
    CODIGOS_VEGETACAO_NATIVA,
    categoria_codigo,
)
from mapbiomas.repositorio import RepositorioMapBiomasMemoria
from mapbiomas.servico import (
    ALGORITHM_VERSION,
    SCHEMA_VERSION,
    ErroDominioMapBiomas,
    ServicoMapBiomas,
    calcular_raio_equivalente_m,
)


def fazenda_teste(**alteracoes):
    fazenda = {
        "id_fazenda": "9",
        "nome_fazenda": "Fazenda de teste",
        "numero_apolice": "123456",
        "cep": "78455000",
        "cidade": "Lucas do Rio Verde",
        "uf": "MT",
        "latitude": "-13.15",
        "longitude": "-56.05",
        "area_ha": "250",
        "tipo_operacao": "campo",
        "proximidade_agua": "False",
    }
    fazenda.update(alteracoes)
    return fazenda


def resposta_cliente(grupos=None, **alteracoes):
    resposta = {
        "asset_id": ASSET_ID,
        "ano": 2024,
        "banda": "classification_2024",
        "area_geometria_m2": 2_501_000.0,
        "area_grade_m2": 2_500_000.0,
        "grupos": (
            grupos
            if grupos is not None
            else [
                {"codigo": 39, "sum": 2_400_000.0},
                {"codigo": 4, "sum": 100_000.0},
            ]
        ),
    }
    resposta.update(alteracoes)
    return resposta


def criar_servico(fazenda=None, resposta=None):
    cliente = Mock()
    cliente.reduzir_territorio.return_value = resposta or resposta_cliente()
    repositorio = RepositorioMapBiomasMemoria()
    relogio = lambda: datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
    servico = ServicoMapBiomas(
        cliente=cliente,
        repositorio=repositorio,
        buscar_fazenda=lambda _: fazenda if fazenda is not None else fazenda_teste(),
        agora_utc=relogio,
    )
    return servico, cliente, repositorio


class TestLegendaMapBiomas(unittest.TestCase):
    def test_codigos_agricultura_pastagem_vegetacao_e_agua(self):
        for codigo in CODIGOS_AGRICULTURA:
            self.assertEqual("agricultura", categoria_codigo(codigo))
        for codigo in CODIGOS_PASTAGEM:
            self.assertEqual("pastagem", categoria_codigo(codigo))
        for codigo in CODIGOS_VEGETACAO_NATIVA:
            self.assertEqual("vegetacao_nativa", categoria_codigo(codigo))
        for codigo in CODIGOS_AGUA:
            self.assertEqual("agua", categoria_codigo(codigo))

    def test_aquicultura_pertence_ao_grupo_agua(self):
        self.assertIn(31, CODIGOS_AGUA)
        self.assertEqual("agua", categoria_codigo(31))

    def test_outros_e_nao_observado(self):
        self.assertEqual("outros", categoria_codigo(21))
        self.assertIn(27, CODIGOS_NAO_OBSERVADOS)
        self.assertIsNone(categoria_codigo(27))


class TestGeometriaEValidacao(unittest.TestCase):
    def test_calculo_raio_equivalente(self):
        self.assertAlmostEqual(
            math.sqrt(250 * 10_000 / math.pi),
            calcular_raio_equivalente_m(250),
        )

    def test_area_ausente_zero_negativa_e_nao_numerica(self):
        for valor in (None, "", 0, -1, "abc"):
            with self.subTest(valor=valor), self.assertRaises(ErroDominioMapBiomas):
                calcular_raio_equivalente_m(valor)

    def test_latitude_e_longitude_invalidas(self):
        for alteracao in ({"latitude": 91}, {"longitude": -181}):
            servico, _, _ = criar_servico(fazenda_teste(**alteracao))
            with self.assertRaises(ErroDominioMapBiomas):
                servico.analisar("9")


class TestServicoMapBiomas(unittest.TestCase):
    def test_resultado_explicavel_e_distribuicao_preservada(self):
        servico, cliente, repositorio = criar_servico()
        resultado = servico.analisar("9")

        chamada = cliente.reduzir_territorio.call_args.kwargs
        self.assertEqual(-13.15, chamada["latitude"])
        self.assertEqual(-56.05, chamada["longitude"])
        self.assertAlmostEqual(
            calcular_raio_equivalente_m(250), chamada["raio_equivalente_m"]
        )
        self.assertEqual("ESTIMADA", resultado["referencia"]["tipo_geometria"])
        self.assertEqual(
            "circulo_equivalente_por_area", resultado["referencia"]["metodo_geometria"]
        )
        self.assertEqual("CEP", resultado["referencia"]["origem_coordenada"])
        self.assertEqual("APROXIMADA", resultado["referencia"]["precisao_espacial"])
        self.assertIn("não representa", resultado["metadados"]["warning_geometria"])
        self.assertEqual(
            [4, 39], [item["codigo"] for item in resultado["distribuicao_bruta"]]
        )
        self.assertEqual(resultado, repositorio.buscar("9"))
        json.dumps(resultado, ensure_ascii=False)

    def test_percentuais_soma_predominante_e_outros(self):
        grupos = [
            {"codigo": 39, "sum": 400.0},
            {"codigo": 15, "sum": 300.0},
            {"codigo": 3, "sum": 200.0},
            {"codigo": 33, "sum": 50.0},
            {"codigo": 21, "sum": 50.0},
        ]
        servico, _, _ = criar_servico(
            resposta=resposta_cliente(
                grupos, area_grade_m2=1000, area_geometria_m2=1000
            )
        )
        resultado = servico.analisar("9")
        cobertura = resultado["cobertura"]
        self.assertEqual(39, cobertura["classe_predominante_codigo"])
        self.assertEqual(40.0, cobertura["agricultura_pct"])
        self.assertEqual(30.0, cobertura["pastagem_pct"])
        self.assertEqual(20.0, cobertura["vegetacao_nativa_pct"])
        self.assertEqual(5.0, cobertura["agua_pct"])
        self.assertEqual(5.0, cobertura["outros_pct"])
        self.assertAlmostEqual(
            100.0, resultado["qualidade"]["soma_percentuais_validos"]
        )

    def test_codigo_27_e_no_data_ficam_fora_do_denominador(self):
        grupos = [
            {"codigo": 39, "sum": 900.0},
            {"codigo": 27, "sum": 100.0},
        ]
        servico, _, _ = criar_servico(
            resposta=resposta_cliente(
                grupos, area_grade_m2=1100, area_geometria_m2=1100
            )
        )
        resultado = servico.analisar("9")
        qualidade = resultado["qualidade"]
        self.assertEqual(900.0, qualidade["area_valida_m2"])
        self.assertEqual(100.0, qualidade["area_codigo_27_m2"])
        self.assertEqual(100.0, qualidade["area_no_data_m2"])
        self.assertEqual(200.0, qualidade["area_nao_observada_m2"])
        self.assertEqual(81.818182, qualidade["cobertura_valida_pct"])
        self.assertEqual(
            [39], [item["codigo"] for item in resultado["distribuicao_bruta"]]
        )
        self.assertEqual(100.0, resultado["cobertura"]["agricultura_pct"])

    def test_empate_da_classe_predominante_usa_menor_codigo(self):
        grupos = [{"codigo": 39, "sum": 500}, {"codigo": 15, "sum": 500}]
        servico, _, _ = criar_servico(
            resposta=resposta_cliente(
                grupos, area_grade_m2=1000, area_geometria_m2=1000
            )
        )
        resultado = servico.analisar("9")
        self.assertEqual(15, resultado["cobertura"]["classe_predominante_codigo"])

    def test_versionamento_e_fingerprint_consideram_ano_e_banda(self):
        servico, cliente, _ = criar_servico()

        def responder(**kwargs):
            return resposta_cliente(
                ano=kwargs["ano"],
                banda=f"classification_{kwargs['ano']}",
            )

        cliente.reduzir_territorio.side_effect = responder
        primeiro = servico.analisar("9", ano=2024)
        segundo = servico.analisar("9", ano=2023)
        self.assertEqual(ALGORITHM_VERSION, primeiro["mapbiomas"]["algorithm_version"])
        self.assertEqual(SCHEMA_VERSION, primeiro["metadados"]["schema_version"])
        self.assertNotEqual(
            primeiro["metadados"]["input_fingerprint"],
            segundo["metadados"]["input_fingerprint"],
        )

    def test_ano_deriva_banda_default_2023_e_limites(self):
        servico, cliente, _ = criar_servico()

        def responder(**kwargs):
            return resposta_cliente(
                ano=kwargs["ano"],
                banda=f"classification_{kwargs['ano']}",
            )

        cliente.reduzir_territorio.side_effect = responder
        for ano in (1985, 2023, 2024):
            with self.subTest(ano=ano):
                if ano == 2024:
                    resultado = servico.analisar("9")
                else:
                    resultado = servico.analisar("9", ano=ano)
                self.assertEqual(ano, resultado["mapbiomas"]["ano_referencia"])
                self.assertEqual(
                    f"classification_{ano}",
                    resultado["mapbiomas"]["banda"],
                )
                chamada = cliente.reduzir_territorio.call_args.kwargs
                self.assertEqual(ano, chamada["ano"])
                self.assertNotIn("banda", chamada)

    def test_anos_fora_do_intervalo_sao_rejeitados(self):
        servico, cliente, _ = criar_servico()
        for ano in (1984, 2025):
            with self.subTest(ano=ano), self.assertRaises(ErroDominioMapBiomas):
                servico.analisar("9", ano=ano)
        cliente.reduzir_territorio.assert_not_called()

    def test_resposta_interna_com_banda_incoerente_e_rejeitada(self):
        servico, _, _ = criar_servico(
            resposta=resposta_cliente(
                ano=2023,
                banda="classification_2024",
            )
        )
        with self.assertRaises(ErroDadosMapBiomas):
            servico.analisar("9", ano=2023)

    def test_repositorio_faz_upsert_e_copia_defensiva(self):
        repositorio = RepositorioMapBiomasMemoria()
        repositorio.salvar("9", {"versao": 1})
        retorno = repositorio.salvar("9", {"versao": 2})
        retorno["versao"] = 3
        self.assertEqual({"versao": 2}, repositorio.buscar("9"))


class TestClienteMapBiomas(unittest.TestCase):
    def test_configuracao_ausente_e_erro_sao_sanitizados_sem_autenticacao(self):
        ee = Mock()
        ee.Initialize.side_effect = RuntimeError("token externo secreto")
        cliente = ClienteEarthEngineMapBiomas(ee_module=ee)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(
            ErroConfiguracaoMapBiomas
        ) as ausente:
            cliente.reduzir_territorio(
                latitude=-13.15,
                longitude=-56.05,
                raio_equivalente_m=100,
            )
        self.assertIn("EARTH_ENGINE_PROJECT", str(ausente.exception))
        ee.Initialize.assert_not_called()

        with patch.dict(
            os.environ, {"EARTH_ENGINE_PROJECT": "projeto"}, clear=True
        ), self.assertRaises(ErroConfiguracaoMapBiomas) as falha:
            cliente.reduzir_territorio(
                latitude=-13.15,
                longitude=-56.05,
                raio_equivalente_m=100,
            )
        self.assertNotIn("secreto", str(falha.exception))
        self.assertFalse(getattr(ee, "Authenticate").called)


class TestApiEIsolamentoMapBiomas(unittest.TestCase):
    def setUp(self):
        self.fazenda = fazenda_teste()

    def test_get_le_somente_repositorio_sem_earth_engine(self):
        servico, cliente, repositorio = criar_servico(self.fazenda)
        repositorio.salvar("9", {"id_fazenda": "9", "fonte": "MAPBIOMAS"})
        with patch.object(main, "_servico_mapbiomas", servico):
            resultado = main.get_mapbiomas("9")
        self.assertEqual("9", resultado["id_fazenda"])
        cliente.reduzir_territorio.assert_not_called()

    def test_endpoint_post_delega_analise_explicita(self):
        servico = Mock()
        servico.analisar.return_value = {"id_fazenda": "9"}
        with patch.object(main, "_servico_mapbiomas", servico):
            resultado = main.analisar_mapbiomas("9", 2024)
        self.assertEqual("9", resultado["id_fazenda"])
        servico.analisar.assert_called_once_with("9", ano=2024)

    def test_endpoint_publico_e_cliente_nao_expoem_banda(self):
        parametros_endpoint = inspect.signature(main.analisar_mapbiomas).parameters
        parametros_cliente = inspect.signature(
            ClienteEarthEngineMapBiomas.reduzir_territorio
        ).parameters
        self.assertEqual({"id_fazenda", "ano"}, set(parametros_endpoint))
        self.assertNotIn("banda", parametros_cliente)

    def test_cadastro_score_dashboard_e_alertas_nao_chamam_mapbiomas(self):
        servico = Mock()
        servico.analisar.side_effect = AssertionError(
            "MapBiomas não deveria ser chamado"
        )
        servico.obter.side_effect = AssertionError("MapBiomas não deveria ser chamado")

        entrada = main.FazendaIn(
            nome_fazenda="Nova",
            numero_apolice="123456",
            cep="78455000",
            area_ha=250,
        )
        with patch.object(main, "_servico_mapbiomas", servico), patch.object(
            main,
            "geocoding_por_cep",
            return_value={
                "latitude": -13.15,
                "longitude": -56.05,
                "logradouro": "",
                "bairro": "",
                "cidade": "Lucas",
                "uf": "MT",
            },
        ), patch.object(
            main, "adicionar_fazenda", return_value=self.fazenda
        ), patch.object(
            main, "_processar_geoespacial"
        ):
            main.post_fazenda(entrada)

        resumo = {"score": 20, "metricas_dia": {}, "fatores_risco": []}
        with patch.object(main, "_servico_mapbiomas", servico), patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(
            main, "coletar_nasa_power", return_value=(Mock(), "teste")
        ), patch.object(
            main, "enriquecer", return_value=Mock()
        ), patch.object(
            main, "salvar_enriquecido_csv"
        ), patch.object(
            main, "consolidar_para_dashboard", return_value=resumo.copy()
        ), patch.object(
            main, "salvar_dashboard_csv"
        ):
            main._cache_score.clear()
            main._gerar_score("9")

        with patch.object(main, "_servico_mapbiomas", servico), patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(main, "_gerar_score", return_value=resumo), patch.object(
            main, "previsao_open_meteo", return_value={"alertas": [], "dias": []}
        ):
            main.get_alertas("9")

        with patch.object(main, "_servico_mapbiomas", servico), patch.object(
            main, "_gerar_score", return_value=resumo
        ), patch.object(
            main, "get_alertas", return_value={"alertas": [], "previsao_5d": []}
        ):
            main.get_dashboard("9")

        servico.analisar.assert_not_called()
        servico.obter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
