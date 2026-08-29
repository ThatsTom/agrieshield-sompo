from datetime import date, timedelta
import sys
from pathlib import Path
import unittest

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from risco.features import calcular_features_climaticas  # noqa: E402
from risco.modelos import FreshnessStatus, FonteDado, StatusQualidade  # noqa: E402
from risco.normalizacao import normalizar_nasa  # noqa: E402


def dataframe_climatico():
    inicio = date(2026, 8, 1)
    precipitacoes = [5.0, 1.0, 2.0, 3.0, 2.0, 0.0, 0.0, 0.0]
    return pd.DataFrame(
        [
            {
                "data": inicio + timedelta(days=i),
                "temp_media_c": 24.0 + i,
                "temp_maxima_c": 30.0 + i,
                "temp_minima_c": 19.0 + i,
                "precipitacao_mm": precipitacoes[i],
                "umidade_relativa_pct": 60.0 + i,
                "radiacao_solar_mj": 18.0,
                "vento_ms": 2.0,
            }
            for i in range(8)
        ]
    )


def dataframe_freshness():
    inicio = date(2026, 8, 1)
    return pd.DataFrame(
        [
            {
                "data": inicio + timedelta(days=i),
                "temp_media_c": 24.0 + i,
                "temp_maxima_c": 30.0 + i,
                "temp_minima_c": 19.0 + i,
                "precipitacao_mm": 0.0,
                "umidade_relativa_pct": 60.0 + i,
                "radiacao_solar_mj": 18.0,
                "vento_ms": 2.0,
            }
            for i in range(11)
        ]
    )


def por_nome(grupo):
    return {feature.nome: feature for feature in grupo.features}


class FeaturesRiscoTests(unittest.TestCase):
    def test_janelas_completas_usam_intervalo_calendario(self):
        grupo = calcular_features_climaticas(
            normalizar_nasa(dataframe_climatico(), "nasa_power")
        )
        features = por_nome(grupo)
        chuva7 = features["chuva_acumulada_7_dias_mm"]
        self.assertEqual(chuva7.valor, 8.0)
        self.assertEqual(chuva7.metadados["dias_esperados"], 7)
        self.assertEqual(chuva7.metadados["dias_disponiveis"], 7)
        self.assertEqual(chuva7.qualidade.cobertura_pct, 100)
        self.assertEqual(chuva7.qualidade.status, StatusQualidade.DISPONIVEL)
        self.assertEqual(chuva7.referencia_temporal.inicio, date(2026, 8, 2))
        self.assertEqual(chuva7.referencia_temporal.fim, date(2026, 8, 8))
        self.assertEqual(
            chuva7.contexto_temporal.freshness_status, FreshnessStatus.ATUAL
        )
        self.assertEqual(chuva7.contexto_temporal.defasagem_dias, 0)

    def test_dados_fora_de_ordem_produzem_mesmo_resultado(self):
        df = dataframe_climatico()
        normal = calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        inverso = calcular_features_climaticas(
            normalizar_nasa(df.iloc[::-1].reset_index(drop=True), "nasa_power")
        )
        self.assertEqual(
            [f.valor for f in normal.features],
            [f.valor for f in inverso.features],
        )

    def test_dia_ausente_retorna_parcial_sem_inventar_valor(self):
        df = dataframe_climatico()
        df = df[df["data"] != date(2026, 8, 4)]
        features = por_nome(
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        )
        chuva7 = features["chuva_acumulada_7_dias_mm"]
        self.assertEqual(chuva7.valor, 5.0)
        self.assertEqual(chuva7.qualidade.status, StatusQualidade.PARCIAL)
        self.assertEqual(chuva7.metadados["dias_disponiveis"], 6)
        self.assertAlmostEqual(chuva7.qualidade.cobertura_pct, 6 / 7 * 100)
        self.assertFalse(chuva7.qualidade.imputado)

    def test_data_duplicada_rejeitada(self):
        df = dataframe_climatico()
        df = pd.concat([df, df.iloc[[3]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "data duplicada"):
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))

    def test_zero_de_chuva_e_acumulados_preservados(self):
        df = dataframe_climatico()
        df.loc[:, "precipitacao_mm"] = 0.0
        features = por_nome(
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        )
        self.assertEqual(features["chuva_acumulada_3_dias_mm"].valor, 0)
        self.assertEqual(features["chuva_acumulada_7_dias_mm"].valor, 0)
        self.assertEqual(
            features["chuva_acumulada_7_dias_mm"].qualidade.status,
            StatusQualidade.DISPONIVEL,
        )

    def test_umidade_media_e_temperatura_referencia(self):
        features = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(dataframe_climatico(), "nasa_power")
            )
        )
        self.assertEqual(features["umidade_relativa_media_3_dias_pct"].valor, 66.0)
        self.assertEqual(features["temperatura_maxima_dia_referencia_c"].valor, 37.0)

    def test_dias_sem_chuva_consecutivos(self):
        features = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(dataframe_climatico(), "nasa_power")
            )
        )
        seca = features["dias_sem_chuva_consecutivos"]
        self.assertEqual(seca.valor, 3)
        self.assertEqual(seca.qualidade.status, StatusQualidade.DISPONIVEL)
        self.assertEqual(seca.metadados["limiar_definicao_feature_mm_dia"], 1.0)

    def test_sequencia_sem_chuva_interrompida_por_lacuna(self):
        df = dataframe_climatico()
        df = df[df["data"] != date(2026, 8, 6)]
        seca = por_nome(
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        )["dias_sem_chuva_consecutivos"]
        self.assertEqual(seca.valor, 2)
        self.assertEqual(seca.qualidade.status, StatusQualidade.PARCIAL)
        self.assertIn("SEQUENCIA_INTERROMPIDA_POR_LACUNA", seca.qualidade.flags)

    def test_none_na_janela_nao_vira_zero_nem_e_imputado(self):
        df = dataframe_climatico()
        df.loc[df["data"] == date(2026, 8, 7), "precipitacao_mm"] = None
        chuva3 = por_nome(
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        )["chuva_acumulada_3_dias_mm"]
        self.assertEqual(chuva3.valor, 0.0)
        self.assertEqual(chuva3.qualidade.status, StatusQualidade.PARCIAL)
        self.assertEqual(chuva3.metadados["dias_disponiveis"], 2)
        self.assertFalse(chuva3.qualidade.imputado)

    def test_dia_referencia_sem_precipitacao_busca_dia_anterior(self):
        df = dataframe_climatico()
        df.loc[df["data"] == date(2026, 8, 8), "precipitacao_mm"] = None
        seca = por_nome(
            calcular_features_climaticas(normalizar_nasa(df, "nasa_power"))
        )["dias_sem_chuva_consecutivos"]
        self.assertEqual(seca.valor, 2)
        self.assertEqual(seca.qualidade.status, StatusQualidade.DISPONIVEL)
        self.assertEqual(
            seca.contexto_temporal.data_referencia_efetiva, date(2026, 8, 7)
        )
        self.assertEqual(
            seca.contexto_temporal.freshness_status, FreshnessStatus.DEFASADO
        )

    def test_fonte_e_linhagem_preservadas(self):
        features = calcular_features_climaticas(
            normalizar_nasa(dataframe_climatico(), "simulado")
        ).features
        self.assertTrue(all(f.fonte == FonteDado.SIMULADOR_INTERNO for f in features))
        self.assertTrue(all(f.qualidade.simulado for f in features))
        self.assertTrue(all(f.linhagem.versao == "risk-features-v2" for f in features))
        self.assertTrue(
            all(
                f.contexto_temporal.freshness_status == FreshnessStatus.AUSENTE
                for f in features
            )
        )
        self.assertTrue(
            all(f.contexto_temporal.data_referencia_efetiva is None for f in features)
        )

    def test_freshness_nasa_atual_e_defasada_entre_um_e_tres_dias(self):
        referencia = date(2026, 8, 11)
        for defasagem, esperado in (
            (0, FreshnessStatus.ATUAL),
            (1, FreshnessStatus.DEFASADO),
            (2, FreshnessStatus.DEFASADO),
            (3, FreshnessStatus.DEFASADO),
        ):
            with self.subTest(defasagem=defasagem):
                df = dataframe_freshness()
                if defasagem:
                    df.loc[
                        df["data"] > referencia - timedelta(days=defasagem),
                        "precipitacao_mm",
                    ] = None
                chuva = por_nome(
                    calcular_features_climaticas(
                        normalizar_nasa(df, "nasa_power"),
                        data_referencia=referencia,
                    )
                )["chuva_acumulada_3_dias_mm"]
                self.assertEqual(chuva.contexto_temporal.freshness_status, esperado)
                self.assertEqual(chuva.contexto_temporal.defasagem_dias, defasagem)
                self.assertEqual(
                    chuva.contexto_temporal.data_referencia_efetiva,
                    referencia - timedelta(days=defasagem),
                )

    def test_nasa_desatualizada_nao_produz_feature_automatica(self):
        referencia = date(2026, 8, 11)
        df = dataframe_freshness()
        df.loc[df["data"] > date(2026, 8, 7), "precipitacao_mm"] = None
        chuva = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(df, "nasa_power"),
                data_referencia=referencia,
            )
        )["chuva_acumulada_7_dias_mm"]

        self.assertIsNone(chuva.valor)
        self.assertIsNone(chuva.referencia_temporal)
        self.assertEqual(chuva.qualidade.status, StatusQualidade.AUSENTE)
        self.assertEqual(
            chuva.contexto_temporal.freshness_status,
            FreshnessStatus.DESATUALIZADO,
        )
        self.assertEqual(
            chuva.contexto_temporal.data_referencia_efetiva, date(2026, 8, 7)
        )
        self.assertEqual(chuva.contexto_temporal.defasagem_dias, 4)
        self.assertIsNone(chuva.contexto_temporal.cobertura_pct)

    def test_nasa_sem_observacao_tem_freshness_ausente(self):
        df = dataframe_freshness()
        df["precipitacao_mm"] = float("nan")
        chuva = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(df, "nasa_power"),
                data_referencia=date(2026, 8, 11),
            )
        )["chuva_acumulada_3_dias_mm"]

        self.assertIsNone(chuva.valor)
        self.assertEqual(
            chuva.contexto_temporal.freshness_status, FreshnessStatus.AUSENTE
        )
        self.assertIsNone(chuva.contexto_temporal.data_referencia_efetiva)
        self.assertIsNone(chuva.contexto_temporal.defasagem_dias)

    def test_zero_no_ultimo_dia_e_observacao_valida_atual(self):
        chuva = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(dataframe_freshness(), "nasa_power"),
                data_referencia=date(2026, 8, 11),
            )
        )["chuva_acumulada_3_dias_mm"]

        self.assertEqual(chuva.valor, 0.0)
        self.assertEqual(
            chuva.contexto_temporal.freshness_status, FreshnessStatus.ATUAL
        )
        self.assertEqual(
            chuva.contexto_temporal.data_referencia_efetiva, date(2026, 8, 11)
        )

    def test_chuva_7d_reposicionada_preserva_cobertura_e_gap_interno(self):
        referencia = date(2026, 8, 11)
        completa = dataframe_freshness()
        completa.loc[completa["data"] >= date(2026, 8, 10), "precipitacao_mm"] = None
        chuva_completa = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(completa, "nasa_power"),
                data_referencia=referencia,
            )
        )["chuva_acumulada_7_dias_mm"]
        self.assertEqual(
            chuva_completa.contexto_temporal.janela_inicio, date(2026, 8, 3)
        )
        self.assertEqual(chuva_completa.contexto_temporal.janela_fim, date(2026, 8, 9))
        self.assertEqual(chuva_completa.contexto_temporal.dias_disponiveis, 7)
        self.assertEqual(chuva_completa.qualidade.cobertura_pct, 100.0)
        self.assertEqual(chuva_completa.qualidade.status, StatusQualidade.DISPONIVEL)
        self.assertEqual(
            chuva_completa.contexto_temporal.freshness_status, FreshnessStatus.DEFASADO
        )

        parcial = completa.copy()
        parcial.loc[parcial["data"] == date(2026, 8, 5), "precipitacao_mm"] = None
        chuva_parcial = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(parcial, "nasa_power"),
                data_referencia=referencia,
            )
        )["chuva_acumulada_7_dias_mm"]
        self.assertEqual(chuva_parcial.contexto_temporal.dias_disponiveis, 6)
        self.assertAlmostEqual(chuva_parcial.qualidade.cobertura_pct, 6 / 7 * 100)
        self.assertEqual(chuva_parcial.qualidade.status, StatusQualidade.PARCIAL)
        self.assertEqual(
            chuva_parcial.contexto_temporal.freshness_status, FreshnessStatus.DEFASADO
        )

    def test_data_efetiva_e_independente_por_variavel_e_ignora_futuro(self):
        referencia = date(2026, 8, 11)
        df = dataframe_freshness()
        df.loc[df["data"] >= date(2026, 8, 10), "precipitacao_mm"] = None
        df.loc[df["data"] >= date(2026, 8, 9), "umidade_relativa_pct"] = None
        df.loc[df["data"] == referencia, "temp_maxima_c"] = None
        futuro = df.iloc[[-1]].copy()
        futuro.loc[:, "data"] = date(2026, 8, 12)
        futuro.loc[:, "precipitacao_mm"] = 999.0
        df = pd.concat([futuro, df.iloc[::-1]], ignore_index=True)

        features = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(df, "nasa_power"),
                data_referencia=referencia,
            )
        )
        chuva = features["chuva_acumulada_7_dias_mm"]
        umidade = features["umidade_relativa_media_3_dias_pct"]
        temperatura = features["temperatura_maxima_dia_referencia_c"]
        self.assertEqual(
            chuva.contexto_temporal.data_referencia_efetiva, date(2026, 8, 9)
        )
        self.assertEqual(
            umidade.contexto_temporal.data_referencia_efetiva, date(2026, 8, 8)
        )
        self.assertEqual(
            temperatura.contexto_temporal.data_referencia_efetiva, date(2026, 8, 10)
        )
        self.assertEqual(temperatura.valor, 39.0)

    def test_dias_sem_chuva_ancoram_na_referencia_efetiva(self):
        referencia = date(2026, 8, 11)
        df = dataframe_freshness()
        df.loc[df["data"] >= date(2026, 8, 10), "precipitacao_mm"] = None
        df.loc[df["data"] == date(2026, 8, 7), "precipitacao_mm"] = 5.0
        seca = por_nome(
            calcular_features_climaticas(
                normalizar_nasa(df, "nasa_power"),
                data_referencia=referencia,
            )
        )["dias_sem_chuva_consecutivos"]

        self.assertEqual(seca.valor, 2)
        self.assertEqual(seca.referencia_temporal.fim, date(2026, 8, 9))
        self.assertEqual(
            seca.contexto_temporal.data_referencia_efetiva, date(2026, 8, 9)
        )
        self.assertEqual(seca.contexto_temporal.defasagem_dias, 2)
        self.assertEqual(
            seca.contexto_temporal.freshness_status, FreshnessStatus.DEFASADO
        )

    def test_mistura_de_fontes_rejeitada(self):
        serie = normalizar_nasa(dataframe_climatico(), "nasa_power")
        misturado = serie.dados[0].model_copy(update={"fonte": FonteDado.INMET})
        serie = serie.model_copy(update={"dados": (misturado, *serie.dados[1:])})
        with self.assertRaisesRegex(ValueError, "misturar fontes"):
            calcular_features_climaticas(serie)


if __name__ == "__main__":
    unittest.main()
