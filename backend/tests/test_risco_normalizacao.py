from datetime import datetime, timezone
import sys
from pathlib import Path
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from risco.modelos import (  # noqa: E402
    FonteDado,
    NaturezaDado,
    StatusQualidade,
)
from risco.normalizacao import (  # noqa: E402
    normalizar_cadastro,
    normalizar_geoespacial,
    normalizar_inmet,
    normalizar_mapbiomas,
    normalizar_nasa,
    normalizar_open_meteo,
)


def dataframe_nasa():
    return pd.DataFrame(
        [
            {
                "data": "2026-08-02",
                "temp_media_c": 25.0,
                "temp_maxima_c": 31.0,
                "temp_minima_c": 20.0,
                "precipitacao_mm": 0.0,
                "umidade_relativa_pct": None,
                "radiacao_solar_mj": 18.0,
                "vento_ms": 0.0,
            },
            {
                "data": "2026-08-01",
                "temp_media_c": 24.0,
                "temp_maxima_c": 30.0,
                "temp_minima_c": 19.0,
                "precipitacao_mm": None,
                "umidade_relativa_pct": 70.0,
                "radiacao_solar_mj": 17.0,
                "vento_ms": 2.0,
            },
        ]
    )


def payload_inmet():
    qualidade_var = {
        nome: {
            "horas_esperadas": 24,
            "horas_disponiveis": 1,
            "disponibilidade_pct": 4.17,
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
        "id_fazenda": "1",
        "estacao": {"codigo": "A904", "nome": "Sorriso", "distancia_km": 22.5},
        "periodo": {
            "data_inicio": "2026-01-01",
            "data_fim": "2026-01-01",
            "timezone": "UTC",
        },
        "observacoes": [
            {
                "codigo_estacao": "A904",
                "observado_em_utc": "2026-01-01T00:00:00+00:00",
                "temperatura_c": 25.0,
                "precipitacao_mm": 0.0,
                "umidade_pct": None,
                "vento_m_s": 0.0,
                "rajada_m_s": 1.2,
                "direcao_vento_graus": 0.0,
                "pressao_hpa": 998.0,
                "radiacao_kj_m2": None,
                "fonte": "INMET",
                "ingerido_em_utc": "2026-08-11T10:00:00+00:00",
            }
        ],
        "qualidade": {
            "horas_esperadas": 24,
            "horas_observadas": 1,
            "variaveis": qualidade_var,
        },
        "origem": {"fonte": "INMET"},
    }


def payload_geo(status="parcial"):
    def atributo(valor, unidade, fonte, banda, resolucao):
        return {
            "valor": valor,
            "unidade": unidade,
            "status": "disponivel" if valor is not None else "indisponivel",
            "metodologia": "método",
            "fonte": fonte,
            "banda": banda,
            "resolucao_m": resolucao,
        }

    return {
        "schema_version": "1",
        "algorithm_version": "fase1-v3",
        "status": status,
        "localizacao": {"latitude": -12.5, "longitude": -55.7},
        "parametros": {
            "raio_analise_m": 1000,
            "limiar_drenagem_km2": 10,
            "raio_busca_drenagem_m": 50000,
        },
        "atributos": {
            "declividade_media": atributo(
                3.2, "graus", "USGS/SRTMGL1_003", "elevation→slope", 30
            ),
            "posicao_topografica_relativa": atributo(
                None, "m", "USGS/SRTMGL1_003", "elevation", 30
            ),
            "distancia_drenagem": atributo(
                2001.0, "m", "MERIT/Hydro/v1_0_1", "upa", 92.77
            ),
            "area_drenagem_montante": atributo(
                850.0, "km²", "MERIT/Hydro/v1_0_1", "upa", 92.77
            ),
        },
        "qualidade": {
            "cobertura_srtm_pct": 98.5,
            "pixels_srtm_validos": 3500,
            "pixel_drenagem": {"latitude": -12.49, "longitude": -55.69},
            "candidatos_drenagem": 32,
            "flags": ["FLAG_FONTE"],
        },
        "fontes": [
            {"identificador": "USGS/SRTMGL1_003", "resolucao_m": 30},
            {"identificador": "MERIT/Hydro/v1_0_1", "resolucao_m": 92.77},
        ],
    }


def payload_mapbiomas():
    return {
        "id_fazenda": "1",
        "referencia": {
            "latitude": -12.5,
            "longitude": -55.7,
            "area_ha": 250,
            "raio_equivalente_m": 892.06,
            "tipo_geometria": "ESTIMADA",
            "metodo_geometria": "circulo_equivalente_por_area",
            "origem_coordenada": "CEP",
            "precisao_espacial": "APROXIMADA",
        },
        "mapbiomas": {
            "asset_id": "projects/mapbiomas-public/assets/brazil/lulc/collection10/mapbiomas_brazil_collection10_integration_v2",
            "colecao": "10",
            "asset_version": "2",
            "ano_referencia": 2024,
            "banda": "classification_2024",
            "versao_legenda": "mapbiomas-brasil-colecao10-v1",
            "algorithm_version": "mapbiomas-territorial-v1",
        },
        "cobertura": {
            "classe_predominante_codigo": 15,
            "classe_predominante_nome": "Pastagem",
            "agricultura_pct": 20,
            "pastagem_pct": 50,
            "vegetacao_nativa_pct": 20,
            "agua_pct": 0,
            "outros_pct": 10,
        },
        "qualidade": {
            "area_nominal_m2": 2500000,
            "area_geometria_m2": 2499990,
            "area_grade_analisada_m2": 2500200,
            "area_mapeada_m2": 2490000,
            "area_valida_m2": 2480000,
            "area_nao_observada_m2": 20200,
            "area_codigo_27_m2": 10000,
            "area_no_data_m2": 10200,
            "cobertura_valida_pct": 99.192065,
            "soma_percentuais_validos": 100,
        },
        "distribuicao_bruta": [
            {
                "codigo": 15,
                "nome": "Pastagem",
                "area_m2": 1240000,
                "percentual_area_valida": 50,
            },
            {
                "codigo": 31,
                "nome": "Aquicultura",
                "area_m2": 0,
                "percentual_area_valida": 0,
            },
        ],
        "metadados": {
            "fonte": "MAPBIOMAS",
            "calculado_em_utc": "2026-08-11T12:00:00+00:00",
            "schema_version": "1",
            "input_fingerprint": "abc123",
            "warning_geometria": "Geometria estimada; não representa o polígono real.",
        },
    }


def payload_open_meteo(*, simulado=False):
    fonte = "SIMULADOR_INTERNO" if simulado else "OPEN_METEO"
    flags = ["DADO_SINTETICO"] if simulado else ["VALORES_AUSENTES"]
    return {
        "schema_version": "1",
        "fonte": fonte,
        "natureza": "PREVISTO",
        "simulado": simulado,
        "coletado_em_utc": "2026-08-12T02:30:00+00:00",
        "requisicao": {
            "latitude": -12.5,
            "longitude": -55.7,
            "forecast_days": 2,
            "timezone_solicitado": "America/Cuiaba",
        },
        "resposta": {
            "latitude_grade": -12.5,
            "longitude_grade": -55.7,
            "elevacao_m": 380.0,
            "timezone": "America/Cuiaba",
            "timezone_abbreviation": "-04",
            "utc_offset_seconds": -14400,
            "generationtime_ms": 0.45,
            "unidades": {
                "time": "iso8601",
                "precipitation_sum": "mm",
                "precipitation_probability_max": "%",
                "temperature_2m_max": "\N{DEGREE SIGN}C",
            },
        },
        "dias": [
            {
                "data_local": "2026-08-11",
                "precipitacao_mm": 0.0,
                "prob_precip_pct": 0,
                "temp_max_c": 0.0,
            },
            {
                "data_local": "2026-08-12",
                "precipitacao_mm": None,
                "prob_precip_pct": None,
                "temp_max_c": None,
            },
        ],
        "qualidade": {
            "status": "PARCIAL",
            "dias_esperados": 2,
            "dias_recebidos": 2,
            "variaveis_ausentes": ["precipitacao_mm", "prob_precip_pct", "temp_max_c"],
            "flags": flags,
        },
        "erro_origem": (
            {"categoria": "transporte", "tipo": "Timeout"} if simulado else None
        ),
    }


class NormalizacaoRiscoTests(unittest.TestCase):
    @staticmethod
    def _cadastro(**campos):
        cadastro = {
            "id_fazenda": "1",
            "nome_fazenda": "Boa Esperança",
            "numero_apolice": "AP-1",
            "cep": "00000000",
            "cidade": "Sorriso",
            "uf": "MT",
            "latitude": "-12.5",
            "longitude": "-55.7",
            "area_ha": "",
            "tipo_operacao": "campo",
        }
        cadastro.update(campos)
        return cadastro

    def test_cadastro_legado_sem_area(self):
        cadastro = normalizar_cadastro(self._cadastro(proximidade_agua="True"))
        self.assertIsNone(cadastro.area_ha)
        self.assertTrue(cadastro.proximidade_agua_declarada)

    def test_cadastro_preserva_proximidade_agua_verdadeira(self):
        cadastro = normalizar_cadastro(self._cadastro(proximidade_agua=True))
        self.assertIs(cadastro.proximidade_agua_declarada, True)

    def test_cadastro_preserva_proximidade_agua_falsa(self):
        cadastro = normalizar_cadastro(self._cadastro(proximidade_agua=False))
        self.assertIs(cadastro.proximidade_agua_declarada, False)

    def test_cadastro_sem_proximidade_agua_preserva_ausencia(self):
        cadastro = normalizar_cadastro(self._cadastro())
        self.assertIsNone(cadastro.proximidade_agua_declarada)

    def test_cadastro_proximidade_agua_none_preserva_ausencia(self):
        cadastro = normalizar_cadastro(self._cadastro(proximidade_agua=None))
        self.assertIsNone(cadastro.proximidade_agua_declarada)
        self.assertIsNot(cadastro.proximidade_agua_declarada, False)

    def test_nasa_real_nomes_unidades_ordem_zero_none_e_input_intacto(self):
        entrada = dataframe_nasa()
        original = entrada.copy(deep=True)
        serie = normalizar_nasa(entrada, "nasa_power")
        assert_frame_equal(entrada, original)
        self.assertEqual(serie.fonte, FonteDado.NASA_POWER)
        self.assertFalse(serie.qualidade.simulado)
        datas = [d.referencia_temporal.inicio for d in serie.dados]
        self.assertEqual(datas, sorted(datas))
        chuva = [d for d in serie.dados if d.variavel == "precipitacao_diaria_mm"]
        self.assertIsNone(chuva[0].valor)
        self.assertEqual(chuva[1].valor, 0)
        self.assertEqual(chuva[1].unidade, "mm/dia")
        unidades = {d.variavel: d.unidade for d in serie.dados}
        self.assertEqual(
            unidades,
            {
                "temperatura_media_diaria_c": "°C",
                "temperatura_maxima_diaria_c": "°C",
                "temperatura_minima_diaria_c": "°C",
                "precipitacao_diaria_mm": "mm/dia",
                "umidade_relativa_media_diaria_pct": "%",
                "radiacao_solar_diaria_mj_m2": "MJ/m²/dia",
                "vento_medio_diario_m_s": "m/s",
            },
        )
        self.assertFalse(any(d.qualidade.imputado for d in serie.dados))

    def test_nasa_sintetica_identificada_sem_parecer_nasa_real(self):
        serie = normalizar_nasa(dataframe_nasa(), "simulado")
        self.assertEqual(serie.fonte, FonteDado.SIMULADOR_INTERNO)
        self.assertEqual(serie.natureza, NaturezaDado.HISTORICO)
        self.assertTrue(serie.qualidade.simulado)
        self.assertIn("DADO_SINTETICO", serie.qualidade.flags)
        self.assertTrue(
            all(d.fonte == FonteDado.SIMULADOR_INTERNO for d in serie.dados)
        )

    def test_nasa_origem_desconhecida_rejeitada(self):
        with self.assertRaises(ValueError):
            normalizar_nasa(dataframe_nasa(), "talvez_nasa")

    def test_inmet_preserva_estacao_utc_zero_none_e_disponibilidade(self):
        serie = normalizar_inmet(payload_inmet())
        self.assertEqual(serie.fonte, FonteDado.INMET)
        self.assertEqual(serie.natureza, NaturezaDado.OBSERVADO)
        self.assertEqual(serie.contexto["estacao"]["codigo"], "A904")
        chuva = next(d for d in serie.dados if d.variavel == "precipitacao_horaria_mm")
        direcao = next(d for d in serie.dados if d.variavel == "vento_direcao_graus")
        umidade = next(d for d in serie.dados if d.variavel == "umidade_relativa_pct")
        self.assertEqual(chuva.valor, 0)
        self.assertEqual(direcao.valor, 0)
        self.assertIsNone(umidade.valor)
        self.assertEqual(chuva.referencia_temporal.timezone, "UTC")
        self.assertEqual(chuva.qualidade.cobertura_pct, 4.17)
        self.assertFalse(chuva.qualidade.imputado)
        self.assertEqual(len(serie.dados), 8)

    def test_inmet_rejeita_mistura_de_estacoes(self):
        payload = payload_inmet()
        payload["observacoes"][0]["codigo_estacao"] = "A905"
        with self.assertRaises(ValueError):
            normalizar_inmet(payload)

    def test_open_meteo_real_preserva_proveniencia_zero_none_tempo_e_unidades(self):
        serie = normalizar_open_meteo(payload_open_meteo())

        self.assertEqual(serie.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(serie.natureza, NaturezaDado.PREVISTO)
        self.assertFalse(serie.qualidade.simulado)
        self.assertEqual(serie.qualidade.status, StatusQualidade.PARCIAL)
        self.assertEqual(len(serie.dados), 6)
        self.assertTrue(
            all(
                d.fonte == FonteDado.OPEN_METEO
                and d.nivel_processamento.value == "NORMALIZADO"
                for d in serie.dados
            )
        )
        primeiros = {d.variavel: d for d in serie.dados[:3]}
        segundos = {d.variavel: d for d in serie.dados[3:]}
        self.assertEqual(primeiros["precipitacao_prevista_diaria_mm"].valor, 0)
        self.assertEqual(
            primeiros["probabilidade_precipitacao_maxima_diaria_pct"].valor, 0
        )
        self.assertEqual(primeiros["temperatura_maxima_prevista_diaria_c"].valor, 0)
        self.assertTrue(all(d.valor is None for d in segundos.values()))
        self.assertEqual(primeiros["precipitacao_prevista_diaria_mm"].unidade, "mm")
        self.assertEqual(
            primeiros["precipitacao_prevista_diaria_mm"].referencia_temporal.timezone,
            "America/Cuiaba",
        )
        self.assertEqual(
            primeiros["precipitacao_prevista_diaria_mm"].coletado_em_utc,
            datetime(2026, 8, 12, 2, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(serie.contexto["resposta"]["utc_offset_seconds"], -14400)

    def test_open_meteo_sintetico_fica_inequivocamente_identificado(self):
        serie = normalizar_open_meteo(payload_open_meteo(simulado=True))

        self.assertEqual(serie.fonte, FonteDado.SIMULADOR_INTERNO)
        self.assertEqual(serie.natureza, NaturezaDado.PREVISTO)
        self.assertTrue(serie.qualidade.simulado)
        self.assertIn("DADO_SINTETICO", serie.qualidade.flags)
        self.assertTrue(
            all(
                d.fonte == FonteDado.SIMULADOR_INTERNO
                and d.qualidade.simulado
                and d.nivel_processamento.value == "NORMALIZADO"
                for d in serie.dados
            )
        )

    def test_open_meteo_rejeita_fonte_e_simulacao_incoerentes(self):
        payload = payload_open_meteo()
        payload["simulado"] = True
        with self.assertRaises(ValueError):
            normalizar_open_meteo(payload)

    def test_geoespacial_preserva_srtm_merit_none_parcial_e_contexto(self):
        geo = normalizar_geoespacial(payload_geo())
        self.assertEqual(geo.qualidade.status, StatusQualidade.PARCIAL)
        self.assertEqual(geo.qualidade.cobertura_pct, 98.5)
        self.assertEqual(geo.declividade_media_graus.fonte, FonteDado.SRTM)
        self.assertIsNone(geo.posicao_topografica_relativa_m.valor)
        self.assertEqual(geo.distancia_drenagem_m.fonte, FonteDado.MERIT_HYDRO)
        self.assertEqual(geo.area_drenagem_montante_km2.unidade, "km²")
        self.assertEqual(geo.parametros.limiar_drenagem_km2, 10)
        self.assertEqual(geo.algorithm_version, "fase1-v3")
        self.assertEqual(len(geo.fontes), 2)
        self.assertEqual(geo.qualidade_contexto["candidatos_drenagem"], 32)

    def test_geoespacial_erro_permanece_invalido(self):
        payload = payload_geo(status="erro")
        for atributo in payload["atributos"].values():
            atributo["valor"] = None
            atributo["status"] = "indisponivel"
        geo = normalizar_geoespacial(payload)
        self.assertEqual(geo.qualidade.status, StatusQualidade.INVALIDO)
        self.assertTrue(
            all(
                item.valor is None
                for item in (
                    geo.declividade_media_graus,
                    geo.posicao_topografica_relativa_m,
                    geo.distancia_drenagem_m,
                    geo.area_drenagem_montante_km2,
                )
            )
        )

    def test_mapbiomas_preserva_contexto_qualidade_e_distribuicao(self):
        territorial = normalizar_mapbiomas(payload_mapbiomas())
        self.assertEqual(territorial.ano_referencia, 2024)
        self.assertEqual(territorial.banda, "classification_2024")
        self.assertEqual(territorial.asset_version, "2")
        self.assertEqual(territorial.fingerprint, "abc123")
        self.assertEqual(territorial.classe_predominante_codigo, 15)
        self.assertEqual(territorial.agua_pct, 0)
        self.assertEqual(territorial.distribuicao_bruta[1].codigo, 31)
        self.assertEqual(territorial.qualidade_territorial.area_codigo_27_m2, 10000)
        self.assertEqual(territorial.qualidade_territorial.area_no_data_m2, 10200)
        self.assertEqual(territorial.qualidade.cobertura_pct, 99.192065)
        self.assertEqual(territorial.geometria.tipo_geometria, "ESTIMADA")
        self.assertEqual(territorial.geometria.precisao_espacial, "APROXIMADA")
        self.assertIn("não representa", territorial.geometria.warning)


if __name__ == "__main__":
    unittest.main()
