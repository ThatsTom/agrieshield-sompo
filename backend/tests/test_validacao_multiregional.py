from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

from backend.validacao import (
    CenarioValidacao,
    DependenciasValidacao,
    ExecutorValidacaoMultiregional,
    carregar_cenarios,
    salvar_relatorios,
)
from backend.validacao.relatorio import para_json_compativel, resumir_cenario


AGORA = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)
DATA_REFERENCIA = date(2026, 8, 10)


def cenario_coordenada(*, proximidade_agua=False):
    return CenarioValidacao.model_validate(
        {
            "id_cenario": "MT_TESTE_01",
            "nome": "Ponto rural de validação",
            "modo": "COORDENADA",
            "classificacao": "PONTO_RURAL_DE_VALIDACAO",
            "uf": "MT",
            "regiao": "Centro-Oeste",
            "latitude": -13.15,
            "longitude": -56.05,
            "area_ha": 250,
            "tipo_operacao": "campo",
            "proximidade_agua_declarada": proximidade_agua,
            "observacao": "Não representa propriedade real.",
        }
    )


def cenario_cep():
    return CenarioValidacao.model_validate(
        {
            "id_cenario": "CEP_TESTE_01",
            "nome": "Cenário CEP de validação",
            "modo": "CEP",
            "classificacao": "CENARIO_CEP_DE_VALIDACAO",
            "uf": "MT",
            "regiao": "Centro-Oeste",
            "cep": "78890000",
            "area_ha": 100,
        }
    )


def dataframe_nasa(*, incluir_none=False):
    linhas = []
    for indice in range(7):
        dia = DATA_REFERENCIA - timedelta(days=6 - indice)
        linhas.append(
            {
                "data": pd.Timestamp(dia),
                "ano": dia.year,
                "mes": dia.month,
                "dia": dia.day,
                "temp_media_c": 25.0,
                "temp_maxima_c": 31.0,
                "temp_minima_c": 20.0,
                "precipitacao_mm": 0.0 if indice == 6 else 2.0,
                "umidade_relativa_pct": None if incluir_none and indice == 5 else 70.0,
                "radiacao_solar_mj": 18.0,
                "vento_ms": 0.0,
            }
        )
    return pd.DataFrame(linhas)


def openmeteo(*, simulado=False):
    dias = []
    for indice in range(5):
        dias.append(
            {
                "data_local": (DATA_REFERENCIA + timedelta(days=indice)).isoformat(),
                "precipitacao_mm": [0.0, 2.0, 3.0, 4.0, 5.0][indice],
                "prob_precip_pct": [0, 20, 30, 40, 50][indice],
                "temp_max_c": [30.0, 31.0, 32.0, 33.0, 34.0][indice],
            }
        )
    return {
        "schema_version": "1",
        "fonte": "SIMULADOR_INTERNO" if simulado else "OPEN_METEO",
        "natureza": "PREVISTO",
        "simulado": simulado,
        "coletado_em_utc": AGORA.isoformat(),
        "requisicao": {
            "latitude": -13.15,
            "longitude": -56.05,
            "forecast_days": 5,
            "timezone_solicitado": "America/Cuiaba",
        },
        "resposta": {
            "latitude_grade": -13.1,
            "longitude_grade": -56.0,
            "elevacao_m": 400.0,
            "timezone": "America/Cuiaba",
            "timezone_abbreviation": "-04",
            "utc_offset_seconds": -14400,
            "generationtime_ms": 0.5,
            "unidades": {
                "time": "iso8601",
                "precipitation_sum": "mm",
                "precipitation_probability_max": "%",
                "temperature_2m_max": "°C",
            },
        },
        "dias": dias,
        "qualidade": {
            "status": "PARCIAL" if simulado else "DISPONIVEL",
            "dias_esperados": 5,
            "dias_recebidos": 5,
            "variaveis_ausentes": [],
            "flags": ["DADO_SINTETICO"] if simulado else [],
        },
        "erro_origem": (
            {"categoria": "transporte", "tipo": "Timeout"} if simulado else None
        ),
    }


def inmet(*, observacoes=True):
    lista = []
    if observacoes:
        inicio = datetime(2026, 8, 4, tzinfo=timezone.utc)
        lista = [
            {
                "codigo_estacao": "A904",
                "observado_em_utc": (inicio + timedelta(hours=indice)).isoformat(),
                "temperatura_c": 25.0,
                "precipitacao_mm": 0.0,
                "umidade_pct": 70.0,
                "vento_m_s": 0.0,
                "rajada_m_s": 1.0,
                "direcao_vento_graus": 0.0,
                "pressao_hpa": 998.0,
                "radiacao_kj_m2": 0.0,
                "fonte": "INMET",
                "ingerido_em_utc": AGORA.isoformat(),
            }
            for indice in range(168)
        ]
    variaveis = {
        nome: {
            "horas_esperadas": 168,
            "horas_disponiveis": len(lista),
            "disponibilidade_pct": round(len(lista) * 100 / 168, 2),
        }
        for nome in (
            "temperatura_c",
            "precipitacao_mm",
            "umidade_pct",
            "vento_m_s",
            "rajada_m_s",
            "direcao_vento_graus",
            "pressao_hpa",
            "radiacao_kj_m2",
        )
    }
    return {
        "id_fazenda": "MT_TESTE_01",
        "estacao": {
            "codigo": "A904",
            "nome": "Estação teste",
            "uf": "MT",
            "latitude": -12.5,
            "longitude": -55.7,
            "altitude_m": 380.0,
            "distancia_km": 22.5,
        },
        "periodo": {
            "data_inicio": "2026-08-04",
            "data_fim": "2026-08-10",
            "timezone": "UTC",
        },
        "observacoes": lista,
        "qualidade": {
            "horas_esperadas": 168,
            "horas_observadas": len(lista),
            "variaveis": variaveis,
        },
        "origem": {"fonte": "INMET", "arquivo": "A904.CSV"},
    }


def inmet_com_defasagem(defasagem_dias):
    payload = inmet(observacoes=False)
    if defasagem_dias is None:
        return payload
    observacao = inmet()["observacoes"][0]
    dia = DATA_REFERENCIA - timedelta(days=defasagem_dias)
    observacao["observado_em_utc"] = datetime(
        dia.year, dia.month, dia.day, 12, tzinfo=timezone.utc
    ).isoformat()
    payload["observacoes"] = [observacao]
    payload["qualidade"]["horas_observadas"] = 1
    for qualidade in payload["qualidade"]["variaveis"].values():
        qualidade["horas_disponiveis"] = 1
        qualidade["disponibilidade_pct"] = round(100 / 168, 2)
    return payload


def geoespacial():
    def atributo(valor, unidade, fonte, banda, resolucao):
        return {
            "valor": valor,
            "unidade": unidade,
            "status": "disponivel",
            "metodologia": "metodo existente",
            "fonte": fonte,
            "banda": banda,
            "resolucao_m": resolucao,
        }

    return {
        "schema_version": "1",
        "algorithm_version": "fase1-v3",
        "status": "sucesso",
        "localizacao": {"latitude": -13.15, "longitude": -56.05},
        "parametros": {
            "raio_analise_m": 1000,
            "limiar_drenagem_km2": 10,
            "raio_busca_drenagem_m": 50000,
        },
        "atributos": {
            "declividade_media": atributo(
                0.0, "graus", "USGS/SRTMGL1_003", "slope", 30
            ),
            "posicao_topografica_relativa": atributo(
                -1.2, "m", "USGS/SRTMGL1_003", "elevation", 30
            ),
            "distancia_drenagem": atributo(
                2000.0, "m", "MERIT/Hydro/v1_0_1", "upa", 92.77
            ),
            "area_drenagem_montante": atributo(
                850.0, "km²", "MERIT/Hydro/v1_0_1", "upa", 92.77
            ),
        },
        "qualidade": {
            "cobertura_srtm_pct": 100.0,
            "pixels_srtm_validos": 3500,
            "flags": [],
        },
        "fontes": [
            {"identificador": "USGS/SRTMGL1_003", "resolucao_m": 30},
            {"identificador": "MERIT/Hydro/v1_0_1", "resolucao_m": 92.77},
        ],
        "erros": [],
    }


def mapbiomas():
    return {
        "id_fazenda": "MT_TESTE_01",
        "referencia": {
            "latitude": -13.15,
            "longitude": -56.05,
            "area_ha": 250,
            "raio_equivalente_m": math.sqrt(250 * 10000 / math.pi),
            "tipo_geometria": "ESTIMADA",
            "metodo_geometria": "circulo_equivalente_por_area",
            "origem_coordenada": "COORDENADA_INFORMADA",
            "precisao_espacial": "APROXIMADA",
        },
        "mapbiomas": {
            "asset_id": "asset",
            "colecao": "10.1",
            "asset_version": "v1",
            "ano_referencia": 2024,
            "banda": "classification_2024",
            "versao_legenda": "legenda-v1",
            "algorithm_version": "map-v1",
        },
        "cobertura": {
            "classe_predominante_codigo": 39,
            "classe_predominante_nome": "Soja",
            "agricultura_pct": 80.0,
            "pastagem_pct": 5.0,
            "vegetacao_nativa_pct": 10.0,
            "agua_pct": 0.0,
            "outros_pct": 5.0,
        },
        "qualidade": {
            "area_nominal_m2": 2500000,
            "area_geometria_m2": 2500000,
            "area_grade_analisada_m2": 2500000,
            "area_mapeada_m2": 2500000,
            "area_valida_m2": 2500000,
            "area_nao_observada_m2": 0,
            "area_codigo_27_m2": 0,
            "area_no_data_m2": 0,
            "cobertura_valida_pct": 100.0,
            "soma_percentuais_validos": 100.0,
        },
        "distribuicao_bruta": [
            {
                "codigo": 39,
                "nome": "Soja",
                "area_m2": 2000000,
                "percentual_area_valida": 80.0,
            }
        ],
        "metadados": {
            "fonte": "MAPBIOMAS",
            "calculado_em_utc": AGORA.isoformat(),
            "schema_version": "1",
            "input_fingerprint": "fingerprint",
            "warning_geometria": "Não representa polígono real.",
        },
    }


def dependencias(**substituicoes):
    padrao = {
        "geocodificar": Mock(
            return_value={
                "latitude": -12.545,
                "longitude": -55.721,
                "origem": "base_estatica_demo",
            }
        ),
        "nasa": Mock(return_value=(dataframe_nasa(), "nasa_power")),
        "openmeteo": Mock(return_value=openmeteo()),
        "inmet": Mock(return_value=inmet()),
        "geoespacial": Mock(return_value=geoespacial()),
        "mapbiomas": Mock(return_value=mapbiomas()),
    }
    padrao.update(substituicoes)
    return DependenciasValidacao(**padrao)


def executor(deps):
    return ExecutorValidacaoMultiregional(deps, agora_utc=lambda: AGORA)


class ValidacaoMultiregionalTests(unittest.TestCase):
    def test_fixtures_versionaveis_reusam_tres_pontos_poc(self):
        caminho = (
            Path(__file__).resolve().parents[1]
            / "validacao"
            / "cenarios_multiregionais.json"
        )
        cenarios = carregar_cenarios(caminho)
        pontos = {(item.latitude, item.longitude, item.area_ha) for item in cenarios}
        self.assertEqual(6, len(cenarios))
        self.assertIn((-13.15, -56.05, 250.0), pontos)
        self.assertIn((-20.2, -55.55, 500.0), pontos)
        self.assertIn((-7.75, -55.25, 1000.0), pontos)
        self.assertTrue(
            all(
                "real" in item.observacao.lower() or item.modo.value == "CEP"
                for item in cenarios
            )
        )

    def test_cenario_completo_mockado_e_sequencial(self):
        ordem = []
        deps = dependencias(
            nasa=Mock(
                side_effect=lambda *args: (
                    ordem.append("nasa") or dataframe_nasa(),
                    "nasa_power",
                )
            ),
            openmeteo=Mock(
                side_effect=lambda *args: ordem.append("openmeteo") or openmeteo()
            ),
            inmet=Mock(side_effect=lambda *args: ordem.append("inmet") or inmet()),
            geoespacial=Mock(
                side_effect=lambda *args: ordem.append("geoespacial") or geoespacial()
            ),
            mapbiomas=Mock(
                side_effect=lambda *args: ordem.append("mapbiomas") or mapbiomas()
            ),
        )
        resultado = executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )

        self.assertEqual(
            ["nasa", "openmeteo", "inmet", "geoespacial", "mapbiomas"], ordem
        )
        self.assertEqual("SUCESSO", resultado["status_execucao"])
        self.assertTrue(
            all(item["status"] == "SUCESSO" for item in resultado["fontes"].values())
        )
        self.assertEqual("LEGADO", resultado["score_legado"]["score_tipo"])
        self.assertEqual("EXECUTADO", resultado["score_legado"]["status"])
        self.assertEqual(
            "COORDENADA_INFORMADA", resultado["referencia"]["origem_coordenada"]
        )
        self.assertEqual("ESTIMADA", resultado["referencia"]["tipo_geometria"])
        self.assertIn("não representa", resultado["referencia"]["warning"])
        self.assertIn("climaticas", resultado["camada_canonica"])
        deps.geocodificar.assert_not_called()

    def test_cenario_cep_usa_geocodificacao_sem_persistir_cadastro(self):
        deps = dependencias()
        resultado = executor(deps).executar_cenario(
            cenario_cep(), data_referencia=DATA_REFERENCIA
        )

        deps.geocodificar.assert_called_once_with("78890000")
        chamada_nasa = deps.nasa.call_args.args
        self.assertEqual((-12.545, -55.721), chamada_nasa[:2])
        self.assertEqual("CEP", resultado["referencia"]["origem_coordenada"])
        self.assertEqual(
            "base_estatica_demo", resultado["referencia"]["origem_coordenada_detalhada"]
        )

    def test_falha_de_uma_fonte_nao_aborta_as_demais_e_sanitiza_erro(self):
        deps = dependencias(
            inmet=Mock(side_effect=RuntimeError("token=segredo falha externa"))
        )
        resultado = executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )

        self.assertEqual("ERRO", resultado["fontes"]["INMET"]["status"])
        self.assertEqual("SUCESSO", resultado["fontes"]["MAPBIOMAS"]["status"])
        self.assertEqual("PARCIAL", resultado["status_execucao"])
        self.assertNotIn("segredo", resultado["fontes"]["INMET"]["erro"]["mensagem"])
        deps.mapbiomas.assert_called_once()

    def test_fonte_ausente_e_resultado_parcial(self):
        deps = dependencias(inmet=Mock(return_value=inmet(observacoes=False)))
        resultado = executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )

        self.assertEqual("AUSENTE", resultado["fontes"]["INMET"]["status"])
        self.assertEqual("PARCIAL", resultado["status_execucao"])

    def test_freshness_inmet_e_distancia_nao_alteram_score(self):
        expectativas = {
            0: "ATUAL",
            1: "ATUAL",
            2: "DEFASADO",
            3: "DEFASADO",
            4: "DESATUALIZADO",
            None: "AUSENTE",
        }
        scores = []
        for defasagem, freshness in expectativas.items():
            with self.subTest(defasagem=defasagem):
                deps = dependencias(
                    inmet=Mock(return_value=inmet_com_defasagem(defasagem))
                )
                resultado = executor(deps).executar_cenario(
                    cenario_coordenada(proximidade_agua=False),
                    data_referencia=DATA_REFERENCIA,
                )
                diagnostico = resultado["fontes"]["INMET"]["dados"][
                    "diagnostico_temporal"
                ]
                self.assertEqual(freshness, diagnostico["freshness_status"])
                self.assertEqual(defasagem, diagnostico["defasagem_dias"])
                self.assertEqual(22.5, diagnostico["distancia_estacao_km"])
                self.assertEqual(14, diagnostico["lookback_diagnostico_dias"])
                scores.append(resultado["score_legado"]["score"])

        self.assertTrue(all(score == scores[0] for score in scores))

    def test_harness_solicita_lookback_inmet_de_ate_14_dias(self):
        deps = dependencias()
        executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )
        _, inicio, fim = deps.inmet.call_args.args
        self.assertEqual(DATA_REFERENCIA - timedelta(days=13), inicio)
        self.assertEqual(DATA_REFERENCIA, fim)

    def test_freshness_inmet_ignora_linha_sem_variavel_meteorologica(self):
        payload = inmet_com_defasagem(2)
        vazia = dict(payload["observacoes"][0])
        vazia["observado_em_utc"] = datetime(
            DATA_REFERENCIA.year,
            DATA_REFERENCIA.month,
            DATA_REFERENCIA.day,
            23,
            tzinfo=timezone.utc,
        ).isoformat()
        for campo in (
            "temperatura_c",
            "precipitacao_mm",
            "umidade_pct",
            "vento_m_s",
            "rajada_m_s",
            "direcao_vento_graus",
            "pressao_hpa",
            "radiacao_kj_m2",
        ):
            vazia[campo] = None
        payload["observacoes"].append(vazia)
        resultado = executor(
            dependencias(inmet=Mock(return_value=payload))
        ).executar_cenario(cenario_coordenada(), data_referencia=DATA_REFERENCIA)
        diagnostico = resultado["fontes"]["INMET"]["dados"]["diagnostico_temporal"]
        self.assertEqual(2, diagnostico["defasagem_dias"])
        self.assertEqual("DEFASADO", diagnostico["freshness_status"])

    def test_disponibilidade_inmet_separa_dados_somente_no_lookback(self):
        resultado = executor(
            dependencias(inmet=Mock(return_value=inmet_com_defasagem(11)))
        ).executar_cenario(cenario_coordenada(), data_referencia=DATA_REFERENCIA)
        diagnostico = resultado["fontes"]["INMET"]["dados"]["diagnostico_temporal"]
        periodo = diagnostico["janela_operacional"]
        lookback = diagnostico["janela_lookback"]
        self.assertEqual(
            (DATA_REFERENCIA - timedelta(days=6)).isoformat(), periodo["inicio"]
        )
        self.assertEqual(
            (DATA_REFERENCIA - timedelta(days=13)).isoformat(), lookback["inicio"]
        )
        self.assertEqual(0.0, periodo["disponibilidade_precipitacao_pct"])
        self.assertGreater(lookback["disponibilidade_precipitacao_pct"], 0.0)

    def test_disponibilidade_inmet_no_periodo_operacional(self):
        resultado = executor(
            dependencias(inmet=Mock(return_value=inmet_com_defasagem(2)))
        ).executar_cenario(cenario_coordenada(), data_referencia=DATA_REFERENCIA)
        diagnostico = resultado["fontes"]["INMET"]["dados"]["diagnostico_temporal"]
        self.assertGreater(
            diagnostico["janela_operacional"]["disponibilidade_precipitacao_pct"],
            0.0,
        )
        self.assertGreater(
            diagnostico["janela_lookback"]["disponibilidade_precipitacao_pct"],
            0.0,
        )

    def test_disponibilidade_inmet_sem_observacoes_e_zero(self):
        sem_dados = executor(
            dependencias(inmet=Mock(return_value=inmet_com_defasagem(None)))
        ).executar_cenario(cenario_coordenada(), data_referencia=DATA_REFERENCIA)
        diagnostico = sem_dados["fontes"]["INMET"]["dados"]["diagnostico_temporal"]
        self.assertEqual(
            0.0, diagnostico["janela_operacional"]["disponibilidade_precipitacao_pct"]
        )
        self.assertEqual(
            0.0, diagnostico["janela_lookback"]["disponibilidade_precipitacao_pct"]
        )
        self.assertEqual("AUSENTE", diagnostico["freshness_status"])

        chuva_zero = inmet_com_defasagem(0)
        for campo in (
            "temperatura_c",
            "umidade_pct",
            "vento_m_s",
            "rajada_m_s",
            "direcao_vento_graus",
            "pressao_hpa",
            "radiacao_kj_m2",
        ):
            chuva_zero["observacoes"][0][campo] = None
        chuva_zero["observacoes"][0]["precipitacao_mm"] = 0.0
        com_zero = executor(
            dependencias(inmet=Mock(return_value=chuva_zero))
        ).executar_cenario(cenario_coordenada(), data_referencia=DATA_REFERENCIA)
        diagnostico_zero = com_zero["fontes"]["INMET"]["dados"]["diagnostico_temporal"]
        self.assertEqual(
            1, diagnostico_zero["janela_operacional"]["horas_disponiveis_precipitacao"]
        )
        self.assertGreater(
            diagnostico_zero["janela_operacional"]["disponibilidade_precipitacao_pct"],
            0.0,
        )
        self.assertEqual("ATUAL", diagnostico_zero["freshness_status"])

    def test_zero_none_e_openmeteo_sintetico_permanecem_explicitos(self):
        aberto = openmeteo(simulado=True)
        aberto["dias"][0]["precipitacao_mm"] = None
        deps = dependencias(
            nasa=Mock(return_value=(dataframe_nasa(incluir_none=True), "nasa_power")),
            openmeteo=Mock(return_value=aberto),
        )
        resultado = executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )

        fonte = resultado["fontes"]["OPEN_METEO"]
        self.assertEqual("PARCIAL", fonte["status"])
        self.assertFalse(fonte["dados"]["evidencia_meteorologica_real"])
        self.assertTrue(fonte["dados"]["bruto"]["simulado"])
        self.assertIsNone(fonte["dados"]["bruto"]["dias"][0]["precipitacao_mm"])
        registros = resultado["fontes"]["NASA_POWER"]["dados"]["registros"]
        self.assertEqual(0.0, registros[-1]["precipitacao_mm"])
        self.assertIsNone(registros[-2]["umidade_relativa_pct"])
        self.assertEqual("nasa_power", resultado["score_legado"]["origem_nasa"])

    def test_score_legado_nao_executado_quando_nasa_falha(self):
        deps = dependencias(nasa=Mock(side_effect=RuntimeError("NASA indisponível")))
        resultado = executor(deps).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )

        self.assertEqual("NAO_EXECUTADO", resultado["score_legado"]["status"])
        self.assertIsNone(resultado["score_legado"]["score"])
        self.assertEqual("SUCESSO", resultado["fontes"]["MAPBIOMAS"]["status"])

    def test_score_legado_nao_executa_com_nasa_sintetica(self):
        for proximidade_agua in (True, False):
            with self.subTest(proximidade_agua=proximidade_agua):
                deps = dependencias(
                    nasa=Mock(return_value=(dataframe_nasa(), "simulado"))
                )
                resultado = executor(deps).executar_cenario(
                    cenario_coordenada(proximidade_agua=proximidade_agua),
                    data_referencia=DATA_REFERENCIA,
                )

                self.assertEqual("PARCIAL", resultado["fontes"]["NASA_POWER"]["status"])
                self.assertTrue(
                    resultado["fontes"]["NASA_POWER"]["dados"]["normalizado"][
                        "qualidade"
                    ]["simulado"]
                )
                self.assertEqual("NAO_EXECUTADO", resultado["score_legado"]["status"])
                self.assertEqual("LEGADO", resultado["score_legado"]["score_tipo"])
                self.assertEqual(
                    "serie_nasa_sintetica", resultado["score_legado"]["motivo"]
                )
                self.assertEqual("simulado", resultado["score_legado"]["origem_nasa"])
                self.assertIsNone(resultado["score_legado"]["score"])

    def test_score_legado_continua_executando_com_nasa_real(self):
        for proximidade_agua in (True, False):
            with self.subTest(proximidade_agua=proximidade_agua):
                deps = dependencias(
                    nasa=Mock(return_value=(dataframe_nasa(), "nasa_power"))
                )
                resultado = executor(deps).executar_cenario(
                    cenario_coordenada(proximidade_agua=proximidade_agua),
                    data_referencia=DATA_REFERENCIA,
                )

                self.assertEqual("EXECUTADO", resultado["score_legado"]["status"])
                self.assertEqual("LEGADO", resultado["score_legado"]["score_tipo"])
                self.assertEqual("nasa_power", resultado["score_legado"]["origem_nasa"])
                self.assertIsNotNone(resultado["score_legado"]["score"])

    def test_score_legado_nao_inventa_proximidade_agua_ausente(self):
        resultado = executor(dependencias()).executar_cenario(
            cenario_coordenada(proximidade_agua=None),
            data_referencia=DATA_REFERENCIA,
        )
        self.assertEqual("NAO_EXECUTADO", resultado["score_legado"]["status"])
        self.assertEqual(
            "proximidade_agua_declarada_ausente",
            resultado["score_legado"]["motivo"],
        )

    def test_json_csv_resumo_e_comparativo_sem_nan(self):
        deps = dependencias()
        execucao = executor(deps).executar(
            [cenario_coordenada()], data_referencia=DATA_REFERENCIA
        )
        execucao["diagnostico_nao_finito"] = [float("nan"), float("inf")]
        with tempfile.TemporaryDirectory() as temporario:
            json_path, csv_path = salvar_relatorios(execucao, temporario)
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            csv_texto = csv_path.read_text(encoding="utf-8-sig")

        self.assertEqual([None, None], payload["diagnostico_nao_finito"])
        self.assertIn("id_cenario;uf;modo", csv_texto)
        self.assertIn("MT_TESTE_01", csv_texto)
        self.assertIn("nasa_data_efetiva_chuva", csv_texto)
        self.assertIn("inmet_ultima_observacao", csv_texto)
        self.assertIn("inmet_disponibilidade_chuva_periodo_pct", csv_texto)
        self.assertIn("inmet_disponibilidade_chuva_lookback_pct", csv_texto)
        self.assertNotIn("inmet_disponibilidade_chuva_pct;", csv_texto)
        resumo = resumir_cenario(payload["resultados"][0])
        self.assertEqual("ATUAL", resumo["nasa_freshness_chuva"])
        self.assertEqual("ATUAL", resumo["inmet_freshness"])
        self.assertIn("chuva_7d_mm", payload["comparativo"])
        self.assertIn("freshness_por_cenario", payload["comparativo"])
        json.dumps(payload, allow_nan=False)

    def test_resumo_nao_forca_ausencia_para_zero(self):
        resultado = executor(dependencias()).executar_cenario(
            cenario_coordenada(), data_referencia=DATA_REFERENCIA
        )
        resultado["fontes"]["MAPBIOMAS"]["dados"]["bruto"]["cobertura"][
            "agua_pct"
        ] = None
        resumo = resumir_cenario(resultado)
        self.assertIsNone(resumo["agua_pct"])
        self.assertEqual(0.0, resumo["declividade_graus"])

    def test_referencia_invalida_impede_fontes_sem_abortar_relatorio(self):
        deps = dependencias(geocodificar=Mock(side_effect=ValueError("CEP inválido")))
        resultado = executor(deps).executar_cenario(
            cenario_cep(), data_referencia=DATA_REFERENCIA
        )
        self.assertEqual("ERRO", resultado["status_execucao"])
        self.assertTrue(
            all(
                item["status"] == "NAO_EXECUTADO"
                for item in resultado["fontes"].values()
            )
        )
        self.assertEqual("NAO_EXECUTADO", resultado["score_legado"]["status"])
        deps.nasa.assert_not_called()

    def test_serializador_converte_datetime_enum_numpy_e_nao_finitos(self):
        payload = para_json_compativel(
            {
                "quando": AGORA,
                "numero": pd.Series([1]).iloc[0],
                "nan": float("nan"),
                "infinito": float("inf"),
                "pandas_ausente": pd.NA,
            }
        )
        self.assertEqual(AGORA.isoformat(), payload["quando"])
        self.assertEqual(1, payload["numero"])
        self.assertIsNone(payload["nan"])
        self.assertIsNone(payload["infinito"])
        self.assertIsNone(payload["pandas_ausente"])


if __name__ == "__main__":
    unittest.main()
