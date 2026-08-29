from __future__ import annotations

import inspect
import os
import time
import unittest
from datetime import date, datetime, timedelta, timezone

from backend.exposicao.features_historicas import (
    FEATURES_HISTORICAS_VERSION,
    calcular_features_historicas,
    comparar_periodos_90d,
)
from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
)
from backend.risco.modelos import FonteDado


DATA_REFERENCIA = date(2026, 8, 11)
COLETADO_EM = datetime(2026, 8, 12, 12, tzinfo=timezone.utc)


def criar_serie(
    *,
    dias: int = 90,
    fonte: FonteDado = FonteDado.NASA_POWER,
    dataset: str = "dataset-teste",
    valores_por_indice=None,
    datas_sem_registro: set[date] | None = None,
):
    janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    registros = []
    for indice in range(dias):
        data_registro = janela.inicio + timedelta(days=indice)
        if data_registro in (datas_sem_registro or set()):
            continue
        valores = {
            "precipitacao_mm": 1.0,
            "temperatura_media_c": 25.0,
            "temperatura_maxima_c": 31.0,
            "temperatura_minima_c": 19.0,
            "umidade_media_pct": 70.0,
        }
        if valores_por_indice is not None:
            valores.update(valores_por_indice(indice, data_registro) or {})
        registros.append(RegistroMeteorologicoDiario(data=data_registro, **valores))
    tipo = (
        TipoProdutoHistorico.HISTORICO_REGIONAL
        if fonte == FonteDado.NASA_POWER
        else TipoProdutoHistorico.REANALISE_MODELADA
    )
    referencia = (
        ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="referência de teste LST",
        )
        if fonte == FonteDado.NASA_POWER
        else ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.UTC,
            timezone="UTC",
        )
    )
    return SerieHistoricaFonte.criar(
        id_fazenda="MT-01",
        fonte=fonte,
        tipo_produto=tipo,
        dataset=dataset,
        periodo_solicitado=janela,
        referencia_temporal=referencia,
        registros=tuple(registros),
        coletado_em_utc=COLETADO_EM,
    )


class TestFeaturesPrecipitacao(unittest.TestCase):
    def test_precipitacao_acumulada_90d(self):
        features = calcular_features_historicas(criar_serie())
        self.assertEqual(features.precipitacao_acumulada_90d_mm.valor, 90)

    def test_precipitacao_acumulada_30d(self):
        features = calcular_features_historicas(criar_serie())
        self.assertEqual(features.precipitacao_acumulada_30d_mm.valor, 30)

    def test_maior_precipitacao_e_data(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 42 if indice == 15 else 1}

        serie = criar_serie(valores_por_indice=valores)
        feature = calcular_features_historicas(serie).maior_precipitacao_diaria_mm
        self.assertEqual(feature.valor, 42)
        self.assertEqual(
            feature.data_associada, serie.periodo_solicitado.inicio + timedelta(days=15)
        )

    def test_empate_em_maior_precipitacao_escolhe_primeira_data(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 42 if indice in (15, 20) else 1}

        serie = criar_serie(valores_por_indice=valores)
        feature = calcular_features_historicas(serie).maior_precipitacao_diaria_mm
        self.assertEqual(
            feature.data_associada, serie.periodo_solicitado.inicio + timedelta(days=15)
        )

    def test_media_diaria_usa_somente_valores_validos(self):
        def valores(indice, _data):
            return {"precipitacao_mm": None if indice == 0 else 2}

        feature = calcular_features_historicas(
            criar_serie(valores_por_indice=valores)
        ).precipitacao_media_diaria_mm
        self.assertEqual(feature.valor, 2)
        self.assertEqual(feature.dias_disponiveis, 89)

    def test_zero_e_preservado_e_conta_na_cobertura(self):
        def valores(_indice, _data):
            return {"precipitacao_mm": 0.0}

        features = calcular_features_historicas(criar_serie(valores_por_indice=valores))
        self.assertEqual(features.precipitacao_acumulada_90d_mm.valor, 0)
        self.assertEqual(features.precipitacao_media_diaria_mm.valor, 0)
        self.assertEqual(features.precipitacao_acumulada_90d_mm.cobertura_pct, 100)

    def test_none_reduz_cobertura_sem_virar_zero(self):
        def valores(indice, _data):
            return {"precipitacao_mm": None if indice in (0, 89) else 1}

        feature = calcular_features_historicas(
            criar_serie(valores_por_indice=valores)
        ).precipitacao_acumulada_90d_mm
        self.assertEqual(feature.valor, 88)
        self.assertEqual(feature.dias_disponiveis, 88)
        self.assertEqual(feature.cobertura_pct, 97.78)

    def test_ausencia_total_retorna_none(self):
        def valores(_indice, _data):
            return {"precipitacao_mm": None}

        features = calcular_features_historicas(criar_serie(valores_por_indice=valores))
        for feature in (
            features.precipitacao_acumulada_90d_mm,
            features.precipitacao_acumulada_30d_mm,
            features.precipitacao_media_diaria_mm,
            features.maior_precipitacao_diaria_mm,
        ):
            self.assertIsNone(feature.valor)
            self.assertEqual(feature.cobertura_pct, 0)


class TestFeaturesTemperaturaEUmidade(unittest.TestCase):
    def test_temperatura_media(self):
        def valores(indice, _data):
            return {"temperatura_media_c": 20 if indice < 45 else 30}

        feature = calcular_features_historicas(
            criar_serie(valores_por_indice=valores)
        ).temperatura_media_90d_c
        self.assertEqual(feature.valor, 25)

    def test_temperatura_maxima_e_data(self):
        def valores(indice, _data):
            return {"temperatura_maxima_c": 39 if indice == 70 else 30}

        serie = criar_serie(valores_por_indice=valores)
        feature = calcular_features_historicas(serie).temperatura_maxima_90d_c
        self.assertEqual(feature.valor, 39)
        self.assertEqual(
            feature.data_associada, serie.periodo_solicitado.inicio + timedelta(days=70)
        )

    def test_temperatura_minima_e_data(self):
        def valores(indice, _data):
            return {"temperatura_minima_c": 8 if indice == 3 else 19}

        serie = criar_serie(valores_por_indice=valores)
        feature = calcular_features_historicas(serie).temperatura_minima_90d_c
        self.assertEqual(feature.valor, 8)
        self.assertEqual(
            feature.data_associada, serie.periodo_solicitado.inicio + timedelta(days=3)
        )

    def test_umidade_media(self):
        def valores(indice, _data):
            return {"umidade_media_pct": 60 if indice < 45 else 80}

        self.assertEqual(
            calcular_features_historicas(
                criar_serie(valores_por_indice=valores)
            ).umidade_media_90d_pct.valor,
            70,
        )

    def test_umidade_minima(self):
        def valores(indice, _data):
            return {"umidade_media_pct": 35 if indice == 10 else 70}

        self.assertEqual(
            calcular_features_historicas(
                criar_serie(valores_por_indice=valores)
            ).umidade_minima_90d_pct.valor,
            35,
        )

    def test_umidade_maxima(self):
        def valores(indice, _data):
            return {"umidade_media_pct": 95 if indice == 80 else 70}

        self.assertEqual(
            calcular_features_historicas(
                criar_serie(valores_por_indice=valores)
            ).umidade_maxima_90d_pct.valor,
            95,
        )

    def test_variavel_inteira_ausente_retorna_none(self):
        def valores(_indice, _data):
            return {
                "temperatura_media_c": None,
                "temperatura_maxima_c": None,
                "temperatura_minima_c": None,
                "umidade_media_pct": None,
            }

        features = calcular_features_historicas(criar_serie(valores_por_indice=valores))
        for feature in (
            features.temperatura_media_90d_c,
            features.temperatura_maxima_90d_c,
            features.temperatura_minima_90d_c,
            features.umidade_media_90d_pct,
            features.umidade_minima_90d_pct,
            features.umidade_maxima_90d_pct,
        ):
            self.assertIsNone(feature.valor)
            self.assertEqual(feature.cobertura_pct, 0)


class TestJanelasGapsELinhagem(unittest.TestCase):
    def test_periodo_principal_tem_90_dias_exatos(self):
        features = calcular_features_historicas(criar_serie())
        self.assertEqual(features.periodo.dias_esperados, 90)
        self.assertEqual((features.periodo.fim - features.periodo.inicio).days + 1, 90)

    def test_periodo_precipitacao_30d_tem_30_dias_exatos(self):
        periodo = calcular_features_historicas(
            criar_serie()
        ).precipitacao_acumulada_30d_mm.periodo
        self.assertEqual(periodo.dias_esperados, 30)
        self.assertEqual((periodo.fim - periodo.inicio).days + 1, 30)
        self.assertEqual(periodo.fim, DATA_REFERENCIA)

    def test_gap_no_inicio_reduz_cobertura(self):
        serie_base = criar_serie()
        serie = criar_serie(datas_sem_registro={serie_base.periodo_solicitado.inicio})
        feature = calcular_features_historicas(serie).precipitacao_acumulada_90d_mm
        self.assertEqual(feature.dias_disponiveis, 89)
        self.assertEqual(feature.cobertura_pct, 98.89)

    def test_gap_interno_reduz_cobertura(self):
        serie_base = criar_serie()
        ausente = serie_base.periodo_solicitado.inicio + timedelta(days=40)
        feature = calcular_features_historicas(
            criar_serie(datas_sem_registro={ausente})
        ).temperatura_media_90d_c
        self.assertEqual(feature.dias_disponiveis, 89)

    def test_gap_final_nao_desloca_periodo(self):
        feature = calcular_features_historicas(
            criar_serie(datas_sem_registro={DATA_REFERENCIA})
        ).precipitacao_acumulada_90d_mm
        self.assertEqual(feature.periodo.fim, DATA_REFERENCIA)
        self.assertEqual(feature.periodo.inicio, DATA_REFERENCIA - timedelta(days=89))
        self.assertEqual(feature.dias_disponiveis, 89)

    def test_30d_nao_busca_fora_do_periodo(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 1000 if indice < 60 else 1}

        feature = calcular_features_historicas(
            criar_serie(valores_por_indice=valores)
        ).precipitacao_acumulada_30d_mm
        self.assertEqual(feature.valor, 30)

    def test_linhagem_preserva_origem_e_versao(self):
        feature = calcular_features_historicas(criar_serie()).temperatura_media_90d_c
        self.assertEqual(feature.fonte, FonteDado.NASA_POWER)
        self.assertEqual(feature.dataset, "dataset-teste")
        self.assertEqual(feature.versao, FEATURES_HISTORICAS_VERSION)
        self.assertIn(
            "SerieHistoricaFonte.registros.temperatura_media_c", feature.linhagem
        )
        self.assertEqual(feature.dias_esperados, 90)

    def test_janela_fornecida_precisa_ter_90_dias(self):
        serie = criar_serie()
        with self.assertRaises(ValueError):
            calcular_features_historicas(
                serie, JanelaHistorica.criar_atual(DATA_REFERENCIA, 30)
            )


class TestComparacaoPeriodos(unittest.TestCase):
    def test_serie_180_dias_e_dividida_em_periodos_contiguos(self):
        comparacao = comparar_periodos_90d(criar_serie(dias=180))
        anterior = comparacao.periodo_anterior.periodo
        atual = comparacao.periodo_atual.periodo
        self.assertEqual(anterior.dias_esperados, 90)
        self.assertEqual(atual.dias_esperados, 90)
        self.assertEqual(anterior.fim + timedelta(days=1), atual.inicio)

    def test_comparacao_precipitacao(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 1 if indice < 90 else 2}

        comparacao = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        )
        feature = comparacao.buscar("precipitacao_acumulada_90d_mm")
        self.assertEqual(feature.valor_anterior, 90)
        self.assertEqual(feature.valor_atual, 180)
        self.assertEqual(feature.diferenca_absoluta, 90)
        self.assertEqual(feature.variacao_pct, 100)

    def test_comparacao_temperatura_e_neutra(self):
        def valores(indice, _data):
            return {"temperatura_media_c": 20 if indice < 90 else 25}

        feature = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        ).buscar("temperatura_media_90d_c")
        self.assertEqual(feature.diferenca_absoluta, 5)
        self.assertIsNone(feature.variacao_pct)
        self.assertEqual(
            feature.motivo_variacao_indisponivel,
            "VARIACAO_PERCENTUAL_NAO_APLICAVEL",
        )

    def test_comparacao_umidade(self):
        def valores(indice, _data):
            return {"umidade_media_pct": 50 if indice < 90 else 70}

        feature = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        ).buscar("umidade_media_90d_pct")
        self.assertEqual(feature.diferenca_absoluta, 20)
        self.assertEqual(feature.variacao_pct, 40)

    def test_variacao_percentual(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 2 if indice < 90 else 3}

        feature = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        ).buscar("precipitacao_acumulada_90d_mm")
        self.assertEqual(feature.variacao_pct, 50)

    def test_periodo_anterior_zero(self):
        def valores(indice, _data):
            return {"precipitacao_mm": 0 if indice < 90 else 1}

        feature = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        ).buscar("precipitacao_acumulada_90d_mm")
        self.assertEqual(feature.diferenca_absoluta, 90)
        self.assertIsNone(feature.variacao_pct)
        self.assertEqual(feature.motivo_variacao_indisponivel, "PERIODO_ANTERIOR_ZERO")

    def test_ausencia_no_periodo_anterior(self):
        def valores(indice, _data):
            return {"precipitacao_mm": None if indice < 90 else 1}

        feature = comparar_periodos_90d(
            criar_serie(dias=180, valores_por_indice=valores)
        ).buscar("precipitacao_acumulada_90d_mm")
        self.assertIsNone(feature.valor_anterior)
        self.assertIsNone(feature.diferenca_absoluta)
        self.assertIsNone(feature.variacao_pct)
        self.assertEqual(feature.motivo_variacao_indisponivel, "VALOR_AUSENTE")

    def test_serie_de_90_dias_nao_pode_ser_dividida(self):
        with self.assertRaises(ValueError):
            comparar_periodos_90d(criar_serie())


class TestIsolamentoFeatures(unittest.TestCase):
    def test_fontes_permanecem_independentes(self):
        nasa = calcular_features_historicas(criar_serie())
        open_meteo = calcular_features_historicas(
            criar_serie(
                fonte=FonteDado.OPEN_METEO,
                dataset="ERA5-Land",
                valores_por_indice=lambda _i, _d: {"precipitacao_mm": None},
            )
        )
        self.assertEqual(nasa.fonte, FonteDado.NASA_POWER)
        self.assertEqual(open_meteo.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(nasa.precipitacao_acumulada_90d_mm.valor, 90)
        self.assertIsNone(open_meteo.precipitacao_acumulada_90d_mm.valor)

    def test_nao_existe_classificacao_operacional(self):
        from backend.exposicao import features_historicas

        campos = {
            *features_historicas.FeatureHistorica.model_fields,
            *features_historicas.FeaturesHistoricas.model_fields,
            *features_historicas.ComparacaoFeatureHistorica.model_fields,
        }
        proibidos = {"score", "severidade", "classificacao", "evento"}
        self.assertTrue(campos.isdisjoint(proibidos))

    def test_modulo_nao_faz_http_persistencia_ou_score(self):
        from backend.exposicao import features_historicas

        codigo = inspect.getsource(features_historicas).lower()
        for termo in (
            "requests",
            "http://",
            "https://",
            "to_csv",
            "write_text",
            "fastapi",
            "supabase",
            "etapa3",
            "score",
            "alertas",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_calculo_nao_muta_serie(self):
        serie = criar_serie()
        antes = serie.model_dump(mode="json")
        calcular_features_historicas(serie)
        self.assertEqual(serie.model_dump(mode="json"), antes)


@unittest.skipUnless(
    os.getenv("RUN_EXPOSICAO_FEATURES_INTEGRATION") == "1",
    "integração real NASA/features opcional",
)
class TestFeaturesIntegracaoReal(unittest.TestCase):
    def test_mt_nasa_180_dias(self):
        from backend.exposicao.clientes.nasa_power_historico import (
            ClienteNasaPowerHistorico,
            ErroHttpNasaPower,
            ErroTransporteNasaPower,
        )

        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        cliente = ClienteNasaPowerHistorico(timeout=(5, 60))
        inicio = time.monotonic()
        try:
            serie = cliente.consultar(-13.15, -56.05, janela, id_fazenda="MT-POC")
        except (ErroTransporteNasaPower, ErroHttpNasaPower) as exc:
            self.skipTest(f"serviço externo indisponível: {type(exc).__name__}")
        comparacao = comparar_periodos_90d(serie)
        duracao = time.monotonic() - inicio
        atual = comparacao.periodo_atual
        anterior = comparacao.periodo_anterior
        chuva = comparacao.buscar("precipitacao_acumulada_90d_mm")
        diagnostico = {
            "precipitacao_90d_atual_mm": chuva.valor_atual,
            "precipitacao_90d_anterior_mm": chuva.valor_anterior,
            "diferenca_precipitacao_mm": chuva.diferenca_absoluta,
            "variacao_precipitacao_pct": chuva.variacao_pct,
            "precipitacao_30d_mm": atual.precipitacao_acumulada_30d_mm.valor,
            "maior_precipitacao_diaria_mm": atual.maior_precipitacao_diaria_mm.valor,
            "data_maior_precipitacao": (
                atual.maior_precipitacao_diaria_mm.data_associada.isoformat()
                if atual.maior_precipitacao_diaria_mm.data_associada
                else None
            ),
            "temperatura_media_90d_c": atual.temperatura_media_90d_c.valor,
            "temperatura_maxima_90d_c": atual.temperatura_maxima_90d_c.valor,
            "temperatura_minima_90d_c": atual.temperatura_minima_90d_c.valor,
            "umidade_media_90d_pct": atual.umidade_media_90d_pct.valor,
            "umidade_minima_90d_pct": atual.umidade_minima_90d_pct.valor,
            "umidade_maxima_90d_pct": atual.umidade_maxima_90d_pct.valor,
            "cobertura_atual": {
                feature.nome: feature.cobertura_pct for feature in atual.todas()
            },
            "cobertura_anterior": {
                feature.nome: feature.cobertura_pct for feature in anterior.todas()
            },
            "duracao_total_s": round(duracao, 3),
        }
        print(f"Features históricas NASA MT: {diagnostico}")
        self.assertEqual(atual.periodo.dias_esperados, 90)
        self.assertEqual(anterior.periodo.dias_esperados, 90)


if __name__ == "__main__":
    unittest.main()
