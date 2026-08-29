from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "etl"))
sys.path.insert(0, str(BACKEND / "app"))

from app import main
import etapa1_cadastro_fazendas as cadastro
import etapa4_dados_geoespaciais as geo
import repositorio_fazendas_geoespaciais as repositorio


def resultado_geo(status="sucesso"):
    disponivel = status == "sucesso"
    valor = lambda numero: {"valor": numero if disponivel else None}
    return {
        "schema_version": "1",
        "algorithm_version": "fase1-v3",
        "status": status,
        "parametros": {
            "raio_analise_m": 1000,
            "limiar_drenagem_km2": 10,
            "raio_busca_drenagem_m": 50000,
        },
        "atributos": {
            "declividade_media": valor(3.2),
            "posicao_topografica_relativa": valor(7.1),
            "distancia_drenagem": valor(800.0),
            "area_drenagem_montante": valor(18.0),
        },
        "fontes": [{"identificador": "SRTM"}, {"identificador": "MERIT"}],
        "qualidade": {"teste": True},
        "erros": [] if disponivel else [{"codigo": "indisponivel"}],
        "cache": {"chave": "abc"},
    }


def registro_geo(status="sucesso", latitude=-12.5, longitude=-55.7):
    return {
        "id_fazenda": "9",
        "status": status,
        "latitude_referencia": latitude,
        "longitude_referencia": longitude,
    }


class TestCadastroArea(unittest.TestCase):
    def test_repositorio_atualiza_sem_trocar_id_e_preserva_outros_registros(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "fazendas.csv"
            with patch.object(cadastro, "ARQUIVO_FAZENDAS", arquivo):
                cadastro.criar_base_se_nao_existir()
                antes = cadastro.listar_fazendas()
                atualizada = cadastro.atualizar_fazenda(
                    "1", {"nome_fazenda": "Nome editado", "area_ha": 321}
                )
                depois = cadastro.listar_fazendas()

        self.assertEqual("1", atualizada["id_fazenda"])
        self.assertEqual("Nome editado", atualizada["nome_fazenda"])
        self.assertEqual("321", str(atualizada["area_ha"]))
        self.assertEqual(len(antes), len(depois))
        self.assertEqual(antes[1]["nome_fazenda"], depois[1]["nome_fazenda"])

    def test_csv_antigo_e_migrado_com_area_vazia(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "fazendas.csv"
            arquivo.write_text(
                "id_fazenda;nome_fazenda;numero_apolice;cep;logradouro;bairro;cidade;uf;tipo_operacao;proximidade_agua;latitude;longitude\n"
                "1;Legada;123;00000000;;;;MT;campo;False;-12;-55\n",
                encoding="utf-8-sig",
            )
            with patch.object(cadastro, "ARQUIVO_FAZENDAS", arquivo):
                cadastro.criar_base_se_nao_existir()
                linhas = cadastro.listar_fazendas()
                with arquivo.open(encoding="utf-8-sig") as f:
                    cabecalho = next(csv.reader(f, delimiter=";"))
            self.assertIn("area_ha", cabecalho)
            self.assertEqual("", linhas[0]["area_ha"])

    def test_novo_payload_exige_area_positiva(self):
        dados = dict(nome_fazenda="Nova", numero_apolice="123", cep="78890000")
        self.assertEqual(250.0, main.FazendaIn(**dados, area_ha=250).area_ha)
        for valor in (0, -1, "abc", None):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                main.FazendaIn(**dados, area_ha=valor)

    def test_normalizacao_legada_retorna_area_nula(self):
        normalizada = main._normalizar_fazenda(
            {
                "id_fazenda": "1",
                "proximidade_agua": "False",
                "latitude": "-12",
                "longitude": "-55",
                "area_ha": "",
            }
        )
        self.assertIsNone(normalizada["area_ha"])

    def test_coordenadas_manuais_devem_formar_par_valido(self):
        base = dict(
            nome_fazenda="Nova", numero_apolice="123", cep="78890000", area_ha=100
        )
        invalidas = (
            {"latitude": -12.5},
            {"longitude": -55.7},
            {"latitude": -91, "longitude": -55.7},
            {"latitude": -12.5, "longitude": 181},
            {"latitude": 0, "longitude": 0},
        )
        for coordenadas in invalidas:
            with self.subTest(coordenadas=coordenadas), self.assertRaises(
                ValidationError
            ):
                main.FazendaIn(**base, **coordenadas)
        entrada = main.FazendaIn(**base, latitude=-12.5, longitude=-55.7)
        self.assertEqual((-12.5, -55.7), (entrada.latitude, entrada.longitude))

    def test_novos_campos_rurais_sao_opcionais_para_registros_antigos(self):
        entrada = main.FazendaIn(
            nome_fazenda="Legada", numero_apolice="123", cep="78890000", area_ha=10
        )
        self.assertEqual("", entrada.numero_km)
        self.assertEqual("", entrada.complemento)
        self.assertEqual("", entrada.referencia_acesso)


class TestRepositorioGeoespacial(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.arquivo = Path(self.tempdir.name) / "fazendas_geoespaciais.csv"
        self.patch_arquivo = patch.object(
            repositorio, "ARQUIVO_FAZENDAS_GEOESPACIAIS", self.arquivo
        )
        self.patch_pasta = patch.object(
            repositorio, "PASTA_DADOS", Path(self.tempdir.name)
        )
        self.patch_arquivo.start()
        self.patch_pasta.start()
        self.fazenda = {
            "id_fazenda": "7",
            "latitude": "-12.5",
            "longitude": "-55.7",
            "area_ha": "100",
        }

    def tearDown(self):
        self.patch_pasta.stop()
        self.patch_arquivo.stop()
        self.tempdir.cleanup()

    def test_raio_equivalente_e_metodo(self):
        registro = repositorio.montar_registro_geoespacial(
            self.fazenda, resultado_geo()
        )
        esperado = math.sqrt(100 * 10000 / math.pi)
        self.assertAlmostEqual(esperado, float(registro["raio_equivalente_m"]))
        self.assertEqual("circulo_equivalente_por_area", registro["metodo_geometria"])
        self.assertEqual("1000", registro["raio_analise_m"])

    def test_area_legada_vazia_nao_inventa_geometria(self):
        fazenda = {**self.fazenda, "area_ha": ""}
        registro = repositorio.montar_registro_geoespacial(fazenda, resultado_geo())
        self.assertEqual("", registro["raio_equivalente_m"])
        self.assertEqual("", registro["metodo_geometria"])

    def test_persiste_sucesso_parcial_e_erro(self):
        for status in ("sucesso", "parcial", "erro"):
            with self.subTest(status=status):
                salvo = repositorio.salvar_resultado_geoespacial(
                    self.fazenda, resultado_geo(status)
                )
                self.assertEqual(status, salvo["status"])
                self.assertEqual("fase1-v3", salvo["algorithm_version"])
                self.assertTrue(salvo["input_fingerprint"])
                self.assertTrue(salvo["calculado_em_utc"])

    def test_upsert_nao_duplica_fazenda(self):
        repositorio.salvar_resultado_geoespacial(self.fazenda, resultado_geo("parcial"))
        repositorio.salvar_resultado_geoespacial(self.fazenda, resultado_geo("sucesso"))
        linhas = repositorio.listar_registros_geoespaciais()
        self.assertEqual(1, len(linhas))
        self.assertEqual("sucesso", linhas[0]["status"])

    def test_busca_normaliza_json_e_numeros(self):
        repositorio.salvar_resultado_geoespacial(self.fazenda, resultado_geo())
        encontrado = repositorio.buscar_registro_geoespacial("7")
        self.assertEqual(100.0, encontrado["area_ha_referencia"])
        self.assertEqual({"teste": True}, encontrado["qualidade"])
        self.assertEqual(2, len(encontrado["fontes"]))


class TestOrquestracaoApi(unittest.TestCase):
    def setUp(self):
        self.fazenda = {
            "id_fazenda": "9",
            "nome_fazenda": "Nova",
            "numero_apolice": "123",
            "cep": "78890000",
            "logradouro": "",
            "bairro": "",
            "cidade": "Sorriso",
            "uf": "MT",
            "tipo_operacao": "campo",
            "proximidade_agua": "False",
            "latitude": "-12.5",
            "longitude": "-55.7",
            "area_ha": "100",
        }

    def test_cadastro_enriquece_e_mantem_raio_padrao(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova", numero_apolice="123", cep="78890000", area_ha=100
        )
        with patch.object(
            main,
            "geocoding_por_cep",
            return_value={
                "latitude": -12.5,
                "longitude": -55.7,
                "cidade": "Sorriso",
                "uf": "MT",
            },
        ), patch.object(
            main, "adicionar_fazenda", return_value=self.fazenda
        ), patch.object(
            main, "consultar_dados_geoespaciais", return_value=resultado_geo()
        ) as consultar, patch.object(
            main, "salvar_resultado_geoespacial", return_value=registro_geo()
        ):
            resposta = main.post_fazenda(entrada)
        consultar.assert_called_once_with(-12.5, -55.7)
        self.assertEqual(100.0, resposta["area_ha"])
        self.assertEqual("SUCESSO", resposta["status_geoespacial"])

    def test_edicao_persiste_campos_e_mantem_contexto_quando_coordenadas_iguais(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova editada",
            numero_apolice="456",
            cep="78890000",
            area_ha=150,
            cidade="Sorriso",
            uf="MT",
            latitude=-12.5,
            longitude=-55.7,
        )
        atualizar = Mock(
            return_value={
                **self.fazenda,
                **entrada.model_dump(),
                "id_fazenda": "9",
                "latitude": "-12.5",
                "longitude": "-55.7",
            }
        )
        with patch.object(main, "buscar_fazenda", return_value=self.fazenda), patch.object(
            main, "atualizar_fazenda", atualizar
        ), patch.object(
            main, "buscar_registro_geoespacial", return_value=registro_geo()
        ), patch.object(main, "_processar_geoespacial") as processar, patch.object(
            main, "_carregar_score_preview", return_value=None
        ):
            resposta = main.put_fazenda("9", entrada)

        processar.assert_not_called()
        self.assertEqual("Nova editada", atualizar.call_args.args[1]["nome_fazenda"])
        self.assertEqual("Nova editada", resposta["nome_fazenda"])
        self.assertEqual("SUCESSO", resposta["status_geoespacial"])

    def test_listagem_inclui_condicao_persistida_sem_disparar_nasa(self):
        with tempfile.TemporaryDirectory() as pasta:
            base = Path(pasta)
            (base / "data").mkdir()
            (base / "data" / "dashboard_indicadores_9.csv").write_text(
                "id_fazenda;data_referencia;score;condicao_atual\n"
                "9;2026-08-26;56;ATENÇÃO\n",
                encoding="utf-8-sig",
            )
            with patch.object(main, "BASE", base), patch.object(
                main, "listar_fazendas", return_value=[self.fazenda]
            ), patch.object(
                main, "buscar_registro_geoespacial", return_value=registro_geo()
            ), patch.object(main, "coletar_nasa_power") as nasa:
                resposta = main.get_fazendas()

        nasa.assert_not_called()
        self.assertEqual(56, resposta[0]["score_preview"]["score"])
        self.assertEqual("ATENÇÃO", resposta[0]["score_preview"]["condicao_atual"])

    def test_coordenadas_manuais_tem_prioridade_sobre_geocodificacao(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova",
            numero_apolice="123",
            cep="78890000",
            area_ha=100,
            latitude=-23.5505,
            longitude=-46.6333,
        )
        adicionar = Mock(
            return_value={
                **self.fazenda,
                "latitude": "-23.5505",
                "longitude": "-46.6333",
            }
        )
        with patch.object(main, "geocoding_por_cep") as geocodificar, patch.object(
            main, "adicionar_fazenda", adicionar
        ), patch.object(main, "_processar_geoespacial"):
            resposta = main.post_fazenda(entrada)
        geocodificar.assert_not_called()
        dados = adicionar.call_args.args[0]
        self.assertEqual("-23.5505", dados["latitude"])
        self.assertEqual("-46.6333", dados["longitude"])
        self.assertEqual(-23.5505, resposta["latitude"])

    def test_campos_de_endereco_rural_sao_encaminhados_para_persistencia(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova",
            numero_apolice="123",
            cep="78890000",
            area_ha=321.5,
            logradouro="Rodovia Carlos João Strass",
            numero_km="km 14",
            complemento="Distrito de Warta",
            cidade="Londrina",
            uf="PR",
            referencia_acesso="Entrada pela estrada municipal",
            latitude=-23.2,
            longitude=-51.2,
        )
        adicionar = Mock(
            return_value={**self.fazenda, **entrada.model_dump(), "id_fazenda": "9"}
        )
        with patch.object(main, "adicionar_fazenda", adicionar), patch.object(
            main, "_processar_geoespacial"
        ):
            main.post_fazenda(entrada)
        dados = adicionar.call_args.args[0]
        self.assertEqual("Rodovia Carlos João Strass", dados["logradouro"])
        self.assertEqual("km 14", dados["numero_km"])
        self.assertEqual("Distrito de Warta", dados["complemento"])
        self.assertEqual("Entrada pela estrada municipal", dados["referencia_acesso"])
        self.assertEqual(321.5, dados["area_ha"])

    def test_cadastro_reutiliza_cache_sem_inicializar_earth_engine(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova", numero_apolice="123", cep="78890000", area_ha=100
        )
        with tempfile.TemporaryDirectory() as pasta:
            cache = Path(pasta)
            base = geo._resultado_base(-12.5, -55.7, 1000.0, 10.0, 50000.0)
            chave = geo._chave_cache(base)
            payload = resultado_geo()
            (cache / f"{chave}.json").write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(
                main,
                "geocoding_por_cep",
                return_value={"latitude": -12.5, "longitude": -55.7},
            ), patch.object(
                main, "adicionar_fazenda", return_value=self.fazenda
            ), patch.object(
                geo, "PASTA_CACHE", cache
            ), patch.object(
                geo,
                "_carregar_ee",
                side_effect=AssertionError(
                    "Earth Engine nao deve ser inicializado em cache hit"
                ),
            ) as carregar_ee, patch.object(
                main, "salvar_resultado_geoespacial", return_value={"status": "sucesso"}
            ) as salvar:
                main.post_fazenda(entrada)
        carregar_ee.assert_not_called()
        self.assertTrue(salvar.call_args.args[1]["cache"]["hit"])
        self.assertEqual(chave, salvar.call_args.args[1]["cache"]["chave"])

    def test_cadastro_permanece_salvo_quando_earth_engine_falha(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova", numero_apolice="123", cep="78890000", area_ha=100
        )
        adicionar = Mock(return_value=self.fazenda)
        salvar_geo = Mock(return_value=registro_geo("erro"))
        with patch.object(
            main,
            "geocoding_por_cep",
            return_value={"latitude": -12.5, "longitude": -55.7},
        ), patch.object(main, "adicionar_fazenda", adicionar), patch.object(
            main, "consultar_dados_geoespaciais", side_effect=RuntimeError("EE")
        ), patch.object(
            main, "salvar_resultado_geoespacial", salvar_geo
        ):
            resposta = main.post_fazenda(entrada)
        adicionar.assert_called_once()
        self.assertEqual("erro", salvar_geo.call_args.args[1]["status"])
        self.assertEqual("9", resposta["id"])
        self.assertEqual("ERRO", resposta["status_geoespacial"])

    def test_cadastro_sem_coordenadas_utilizaveis_nao_dispara_enriquecimento(self):
        entrada = main.FazendaIn(
            nome_fazenda="Nova", numero_apolice="123", cep="78890000", area_ha=100
        )
        for latitude, longitude in ((None, None), ("", ""), (0, 0)):
            with self.subTest(latitude=latitude, longitude=longitude):
                fazenda = {**self.fazenda, "latitude": latitude, "longitude": longitude}
                with patch.object(
                    main,
                    "geocoding_por_cep",
                    return_value={"latitude": latitude, "longitude": longitude},
                ), patch.object(
                    main, "adicionar_fazenda", return_value=fazenda
                ), patch.object(
                    main, "_processar_geoespacial"
                ) as processar:
                    resposta = main.post_fazenda(entrada)
                processar.assert_not_called()
                self.assertEqual("9", resposta["id"])
                self.assertEqual("PENDENTE", resposta["status_geoespacial"])

    def test_listagem_expoe_status_territorial_minimo(self):
        with patch.object(
            main, "listar_fazendas", return_value=[self.fazenda]
        ), patch.object(
            main, "buscar_registro_geoespacial", return_value=registro_geo()
        ):
            resposta = main.get_fazendas()
        self.assertEqual("SUCESSO", resposta[0]["status_geoespacial"])
        self.assertNotIn("declividade_media_graus", resposta[0])

    def test_contexto_antigo_fica_pendente_quando_coordenadas_mudam(self):
        registro_antigo = registro_geo("sucesso", latitude=-12.4, longitude=-55.6)
        self.assertEqual(
            "PENDENTE", main._status_geoespacial(self.fazenda, registro_antigo)
        )

    def test_status_persistidos_sao_traduzidos_sem_inventar_contexto(self):
        self.assertEqual("PENDENTE", main._status_geoespacial(self.fazenda, None))
        self.assertEqual(
            "SUCESSO", main._status_geoespacial(self.fazenda, registro_geo())
        )
        for status in ("erro", "parcial"):
            with self.subTest(status=status):
                self.assertEqual(
                    "ERRO",
                    main._status_geoespacial(self.fazenda, registro_geo(status)),
                )

    def test_validacao_rejeita_coordenadas_invalidas_sem_inventar_valores(self):
        invalidas = (
            {"latitude": "nan", "longitude": "-55"},
            {"latitude": "-91", "longitude": "-55"},
            {"latitude": "-12", "longitude": "181"},
            {"latitude": None, "longitude": None},
            {"latitude": 0, "longitude": 0},
        )
        for fazenda in invalidas:
            with self.subTest(fazenda=fazenda):
                self.assertFalse(main._coordenadas_utilizaveis(fazenda))
        self.assertTrue(
            main._coordenadas_utilizaveis({"latitude": -12.5, "longitude": -55.7})
        )

    def test_endpoint_consulta(self):
        esperado = {"id_fazenda": "9", "status": "sucesso"}
        with patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(main, "buscar_registro_geoespacial", return_value=esperado):
            self.assertEqual(esperado, main.get_geoespacial("9"))

    def test_endpoint_reprocessamento_explicito(self):
        esperado = {"id_fazenda": "9", "status": "sucesso"}
        with patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(
            main, "_processar_geoespacial", return_value=esperado
        ) as processar:
            self.assertEqual(esperado, main.recalcular_geoespacial("9"))
        processar.assert_called_once_with(self.fazenda)

    def test_retry_manual_pode_recuperar_status_de_erro(self):
        processar = Mock(side_effect=[registro_geo("erro"), registro_geo("sucesso")])
        with patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(main, "_processar_geoespacial", processar):
            primeira = main.recalcular_geoespacial("9")
            segunda = main.recalcular_geoespacial("9")
        self.assertEqual("erro", primeira["status"])
        self.assertEqual("sucesso", segunda["status"])
        self.assertEqual(2, processar.call_count)

    def test_smoke_cadastro_status_provider_e_endpoint_v1_sem_rede(self):
        from backend.app.provedor_contexto_territorial_persistido import (
            CarregadorCacheGeoespacialJson,
            ProvedorContextoTerritorialPersistido,
        )
        from backend.app.servico_avaliacao_exposicao import (
            RepositorioFazendasPorFuncao,
            ServicoAvaliacaoExposicao,
        )
        from backend.exposicao import ResultadoApresentacaoExposicaoMaquinario
        from backend.risco.modelos import FonteDado
        from backend.tests.test_provedor_contexto_territorial_persistido import (
            payload_geoespacial,
        )
        from backend.tests.test_servico_avaliacao_exposicao import (
            ClienteFalso,
            DATA_REFERENCIA,
        )
        from backend.tests.test_exposicao_avaliacao_exposicao import (
            criar_serie_avaliacao,
        )

        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            arquivo_fazendas = raiz / "fazendas.csv"
            arquivo_coordenadas = raiz / "coordenadas.csv"
            arquivo_geoespacial = raiz / "fazendas_geoespaciais.csv"
            diretorio_cache = raiz / "cache"
            diretorio_cache.mkdir()
            with arquivo_fazendas.open("w", newline="", encoding="utf-8-sig") as f:
                csv.DictWriter(
                    f, fieldnames=cadastro.COLUNAS_FAZENDAS, delimiter=";"
                ).writeheader()

            base_cache = geo._resultado_base(-12.545, -55.721, 1000.0, 10.0, 50000.0)
            chave_cache = geo._chave_cache(base_cache)
            payload_cache = payload_geoespacial()
            payload_cache["cache"] = {"hit": False, "chave": chave_cache}
            (diretorio_cache / f"{chave_cache}.json").write_text(
                json.dumps(payload_cache, ensure_ascii=False), encoding="utf-8"
            )

            entrada = main.FazendaIn(
                nome_fazenda="Fazenda Smoke",
                numero_apolice="SMOKE-001",
                cep="78890000",
                area_ha=250,
                latitude=-12.545,
                longitude=-55.721,
            )
            with patch.object(cadastro, "PASTA_DADOS", raiz), patch.object(
                cadastro, "ARQUIVO_FAZENDAS", arquivo_fazendas
            ), patch.object(
                cadastro, "ARQUIVO_COORDENADAS", arquivo_coordenadas
            ), patch.object(
                repositorio, "PASTA_DADOS", raiz
            ), patch.object(
                repositorio,
                "ARQUIVO_FAZENDAS_GEOESPACIAIS",
                arquivo_geoespacial,
            ), patch.object(
                geo, "PASTA_CACHE", diretorio_cache
            ), patch.object(
                geo,
                "_carregar_ee",
                side_effect=AssertionError("cache hit nao deve carregar Earth Engine"),
            ) as carregar_ee:
                cadastrada = main.post_fazenda(entrada)
                listada = main.get_fazendas()[0]
                registro = repositorio.buscar_registro_geoespacial("1")
                provider = ProvedorContextoTerritorialPersistido(
                    buscar_registro=repositorio.buscar_registro_geoespacial,
                    carregador_cache=CarregadorCacheGeoespacialJson(diretorio_cache),
                )
                contexto = provider.obter(
                    id_fazenda="1", latitude=-12.545, longitude=-55.721
                )
                servico = ServicoAvaliacaoExposicao(
                    repositorio_fazendas=RepositorioFazendasPorFuncao(
                        cadastro.buscar_fazenda
                    ),
                    clientes_meteorologicos={
                        FonteDado.NASA_POWER: ClienteFalso(
                            serie=criar_serie_avaliacao().model_copy(
                                update={"id_fazenda": "1"}
                            )
                        )
                    },
                    provedor_contexto_territorial=provider,
                )
                resposta_v1 = main.get_exposicao_v1(
                    "1",
                    servico,
                    DATA_REFERENCIA,
                    main.FonteHistoricaExposicao.NASA_POWER,
                )

            carregar_ee.assert_not_called()
            self.assertEqual("SUCESSO", cadastrada["status_geoespacial"])
            self.assertEqual("SUCESSO", listada["status_geoespacial"])
            self.assertEqual(chave_cache, registro["cache_chave"])
            self.assertAlmostEqual(3.2, contexto.declividade_media_graus.valor)
            self.assertIsInstance(resposta_v1, ResultadoApresentacaoExposicaoMaquinario)
            self.assertEqual("1", resposta_v1.id_fazenda)
            self.assertEqual(5, len(resposta_v1.perigos))

    def test_score_e_dashboard_nao_consultam_etapa4(self):
        consulta_geo = Mock(
            side_effect=AssertionError("Etapa 4 não deveria ser chamada")
        )
        resumo = {"score": 20, "metricas_dia": {}, "fatores_risco": []}
        with patch.object(
            main, "consultar_dados_geoespaciais", consulta_geo
        ), patch.object(
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
        with patch.object(
            main, "consultar_dados_geoespaciais", consulta_geo
        ), patch.object(main, "_gerar_score", return_value=resumo), patch.object(
            main, "get_alertas", return_value={"alertas": [], "previsao_5d": []}
        ):
            main.get_dashboard("9")
        consulta_geo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
