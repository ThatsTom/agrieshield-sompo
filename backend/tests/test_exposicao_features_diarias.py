from __future__ import annotations

import inspect
import unittest
from datetime import date, datetime, timedelta, timezone

from pydantic import ValidationError

from backend.exposicao import (
    FeatureDiariaCompartilhada,
    calcular_features_diarias_compartilhadas,
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


def criar_serie(
    precipitacoes: list[float | None],
    *,
    datas_sem_registro: set[date] | None = None,
    fonte: FonteDado = FonteDado.NASA_POWER,
    valores_por_indice=None,
    metadados_origem=None,
) -> SerieHistoricaFonte:
    janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, len(precipitacoes))
    registros = []
    for indice, precipitacao in enumerate(precipitacoes):
        data_registro = janela.inicio + timedelta(days=indice)
        if data_registro in (datas_sem_registro or set()):
            continue
        valores = {
            "temperatura_media_c": 20.0 + indice,
            "temperatura_maxima_c": 30.0 + indice,
            "temperatura_minima_c": 10.0 + indice,
            "umidade_media_pct": 60.0 + indice,
        }
        if valores_por_indice is not None:
            valores.update(valores_por_indice(indice, data_registro) or {})
        registros.append(
            RegistroMeteorologicoDiario(
                data=data_registro,
                precipitacao_mm=precipitacao,
                **valores,
            )
        )
    if fonte == FonteDado.NASA_POWER:
        produto = TipoProdutoHistorico.HISTORICO_REGIONAL
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        )
    else:
        produto = TipoProdutoHistorico.REANALISE_MODELADA
        referencia = ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC)
    return SerieHistoricaFonte.criar(
        id_fazenda="fazenda-teste",
        fonte=fonte,
        tipo_produto=produto,
        dataset="dataset-teste",
        periodo_solicitado=janela,
        referencia_temporal=referencia,
        registros=tuple(registros),
        coletado_em_utc=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        metadados_origem=metadados_origem,
    )


class TestCalendarioEJanelas(unittest.TestCase):
    def setUp(self):
        self.serie = criar_serie([1, 2, 3, 4, 5, 6, 7, 8])
        self.resultado = calcular_features_diarias_compartilhadas(self.serie)
        self.ultimo = self.resultado.dias[-1]

    def test_serie_diaria_simples_sem_gaps(self):
        self.assertEqual(len(self.resultado.dias), 8)
        self.assertTrue(
            all(
                isinstance(dia, FeatureDiariaCompartilhada)
                for dia in self.resultado.dias
            )
        )

    def test_preserva_ordem_cronologica(self):
        self.assertEqual(
            tuple(dia.data for dia in self.resultado.dias),
            tuple(
                self.serie.periodo_solicitado.inicio + timedelta(days=indice)
                for indice in range(8)
            ),
        )

    def test_precipitacao_d0(self):
        self.assertEqual(self.ultimo.precipitacao_d0, 8)

    def test_d1_d3_exclui_d0(self):
        self.assertEqual(self.ultimo.precipitacao_d1_d3, 7 + 6 + 5)

    def test_d4_d7_nao_sobrepoe_d1_d3(self):
        self.assertEqual(self.ultimo.precipitacao_d4_d7, 4 + 3 + 2 + 1)
        self.assertEqual(
            self.ultimo.precipitacao_d1_d3 + self.ultimo.precipitacao_d4_d7,
            sum(range(1, 8)),
        )

    def test_acumulado_3d(self):
        self.assertEqual(self.ultimo.acumulado_3d, 8 + 7 + 6)

    def test_acumulado_7d(self):
        self.assertEqual(self.ultimo.acumulado_7d, 8 + 7 + 6 + 5 + 4 + 3 + 2)

    def test_primeiros_dias_sem_historico_suficiente(self):
        self.assertIsNone(self.resultado.dias[0].acumulado_3d)
        self.assertIsNone(self.resultado.dias[1].acumulado_3d)
        self.assertIsNotNone(self.resultado.dias[2].acumulado_3d)
        self.assertTrue(
            all(
                self.resultado.dias[indice].precipitacao_d1_d3 is None
                for indice in range(3)
            )
        )
        self.assertTrue(
            all(self.resultado.dias[indice].acumulado_7d is None for indice in range(6))
        )
        self.assertIsNotNone(self.resultado.dias[6].acumulado_7d)
        self.assertIsNone(self.resultado.dias[6].precipitacao_d4_d7)
        self.assertIsNotNone(self.resultado.dias[7].precipitacao_d4_d7)

    def test_busca_tipadamente_por_data(self):
        self.assertIs(self.resultado.por_data(self.ultimo.data), self.ultimo)
        with self.assertRaises(KeyError):
            self.resultado.por_data(
                self.serie.periodo_solicitado.inicio - timedelta(days=1)
            )


class TestAusenciaEZero(unittest.TestCase):
    def test_zero_de_chuva_e_valido(self):
        resultado = calcular_features_diarias_compartilhadas(criar_serie([0] * 8))
        ultimo = resultado.dias[-1]
        self.assertEqual(ultimo.precipitacao_d0, 0)
        self.assertEqual(ultimo.precipitacao_d1_d3, 0)
        self.assertEqual(ultimo.precipitacao_d4_d7, 0)
        self.assertEqual(ultimo.acumulado_3d, 0)
        self.assertEqual(ultimo.acumulado_7d, 0)

    def test_gap_em_acumulado_3d(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 1, None, 1])
        )
        self.assertIsNone(resultado.dias[-1].acumulado_3d)

    def test_gap_em_acumulado_7d(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 1, 1, None, 1, 1, 1, 1])
        )
        self.assertIsNone(resultado.dias[-1].acumulado_7d)

    def test_gap_em_d1_d3(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, None, 1, 1])
        )
        self.assertIsNone(resultado.dias[-1].precipitacao_d1_d3)

    def test_gap_em_d4_d7(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 1, None, 1, 1, 1, 1, 1])
        )
        self.assertIsNone(resultado.dias[-1].precipitacao_d4_d7)

    def test_data_sem_registro_aparece_como_gap_explicito(self):
        serie_base = criar_serie([1, 1, 1])
        data_gap = serie_base.periodo_solicitado.inicio + timedelta(days=1)
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 1, 1], datas_sem_registro={data_gap})
        )
        dia_gap = resultado.por_data(data_gap)
        self.assertIsNone(dia_gap.precipitacao_d0)
        self.assertIsNone(dia_gap.temperatura_media)
        self.assertEqual(len(resultado.dias), 3)


class TestSequenciasNeutras(unittest.TestCase):
    def test_dias_consecutivos_com_chuva(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 2, 3, 0, 4])
        )
        self.assertEqual(
            [dia.dias_consecutivos_com_chuva for dia in resultado.dias],
            [1, 2, 3, 0, 1],
        )

    def test_sequencia_com_none_reinicia_conhecimento(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([1, 2, None, 3, 4])
        )
        self.assertEqual(
            [dia.dias_consecutivos_com_chuva for dia in resultado.dias],
            [1, 2, None, 1, 2],
        )

    def test_dias_desde_ultima_chuva(self):
        resultado = calcular_features_diarias_compartilhadas(criar_serie([5, 0, 0, 2]))
        self.assertEqual(
            [dia.dias_desde_ultima_chuva_relevante for dia in resultado.dias],
            [0, 1, 2, 0],
        )

    def test_dias_desde_chuva_com_gap_nao_infere_continuidade(self):
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie([5, 0, None, 0, 2, 0])
        )
        self.assertEqual(
            [dia.dias_desde_ultima_chuva_relevante for dia in resultado.dias],
            [0, 1, None, None, 0, 1],
        )

    def test_sem_chuva_anterior_conhecida_retorna_none(self):
        resultado = calcular_features_diarias_compartilhadas(criar_serie([0, 0, 1]))
        self.assertEqual(
            [dia.dias_desde_ultima_chuva_relevante for dia in resultado.dias],
            [None, None, 0],
        )


class TestMeteorologiaELinhagem(unittest.TestCase):
    def test_velocidade_vento_e_copiada_sem_transformacao(self):
        for valor in (3.75, 0.0, None):
            with self.subTest(valor=valor):

                def vento(_indice, _data, valor=valor):
                    return {"velocidade_vento_media_m_s": valor}

                dia = calcular_features_diarias_compartilhadas(
                    criar_serie([1], valores_por_indice=vento)
                ).dias[0]
                self.assertEqual(dia.velocidade_vento_media_m_s, valor)

    def test_proveniencia_do_vento_atravessa_para_features(self):
        metadados = {
            "parametro_fonte": "WS2M",
            "variavel_canonica": "velocidade_vento_media_m_s",
            "unidade": "m/s",
            "altura_m": 2,
            "agregacao_temporal": "media_diaria",
            "referencia_temporal": "LST",
        }
        resultado = calcular_features_diarias_compartilhadas(
            criar_serie(
                [1],
                valores_por_indice=lambda *_: {"velocidade_vento_media_m_s": 3.5},
                metadados_origem={"vento": metadados},
            )
        )
        self.assertEqual(resultado.metadados_vento, metadados)
        self.assertEqual(resultado.fonte, FonteDado.NASA_POWER)
        self.assertEqual(resultado.natureza.value, "HISTORICO")

    def test_temperaturas_copiadas_sem_alteracao(self):
        resultado = calcular_features_diarias_compartilhadas(criar_serie([1, 1]))
        ultimo = resultado.dias[-1]
        self.assertEqual(ultimo.temperatura_media, 21)
        self.assertEqual(ultimo.temperatura_maxima, 31)
        self.assertEqual(ultimo.temperatura_minima, 11)

    def test_umidade_copiada_sem_alteracao(self):
        ultimo = calcular_features_diarias_compartilhadas(criar_serie([1, 1])).dias[-1]
        self.assertEqual(ultimo.umidade_relativa, 61)

    def test_valores_meteorologicos_none_preservados(self):
        def ausentes(_indice, _data):
            return {
                "temperatura_media_c": None,
                "temperatura_maxima_c": None,
                "temperatura_minima_c": None,
                "umidade_media_pct": None,
            }

        dia = calcular_features_diarias_compartilhadas(
            criar_serie([1], valores_por_indice=ausentes)
        ).dias[0]
        self.assertIsNone(dia.temperatura_media)
        self.assertIsNone(dia.temperatura_maxima)
        self.assertIsNone(dia.temperatura_minima)
        self.assertIsNone(dia.umidade_relativa)

    def test_preserva_fonte_dataset_periodo_e_versao(self):
        serie = criar_serie([1, 2, 3])
        resultado = calcular_features_diarias_compartilhadas(serie)
        self.assertEqual(resultado.fonte, serie.fonte)
        self.assertEqual(resultado.dataset, serie.dataset)
        self.assertEqual(resultado.periodo, serie.periodo_solicitado)
        self.assertEqual(resultado.referencia_temporal, serie.referencia_temporal)
        self.assertTrue(resultado.versao)

    def test_fontes_nao_sao_misturadas(self):
        nasa = calcular_features_diarias_compartilhadas(criar_serie([1, 2, 3]))
        open_meteo = calcular_features_diarias_compartilhadas(
            criar_serie([4, 5, 6], fonte=FonteDado.OPEN_METEO)
        )
        self.assertEqual(nasa.fonte, FonteDado.NASA_POWER)
        self.assertEqual(open_meteo.fonte, FonteDado.OPEN_METEO)
        self.assertNotEqual(
            nasa.dias[-1].precipitacao_d0, open_meteo.dias[-1].precipitacao_d0
        )


class TestPurezaEIsolamento(unittest.TestCase):
    def test_resultado_e_features_sao_imutaveis(self):
        resultado = calcular_features_diarias_compartilhadas(criar_serie([1, 2, 3]))
        with self.assertRaises(ValidationError):
            resultado.dataset = "outro"
        with self.assertRaises(ValidationError):
            resultado.dias[0].precipitacao_d0 = 99

    def test_nao_altera_serie_de_entrada(self):
        serie = criar_serie([1, 2, None, 0])
        antes = serie.model_dump(mode="json")
        calcular_features_diarias_compartilhadas(serie)
        self.assertEqual(serie.model_dump(mode="json"), antes)

    def test_mesma_entrada_produz_mesmo_resultado(self):
        serie = criar_serie([1, 2, None, 0])
        primeiro = calcular_features_diarias_compartilhadas(serie)
        segundo = calcular_features_diarias_compartilhadas(serie)
        self.assertEqual(primeiro, segundo)

    def test_nenhuma_classificacao_de_risco_aparece(self):
        campos = set(FeatureDiariaCompartilhada.model_fields)
        self.assertTrue(
            campos.isdisjoint(
                {"perigo", "evento", "score", "classificacao", "severidade"}
            )
        )

    def test_nenhuma_dependencia_de_politica_http_ou_filesystem(self):
        from backend.exposicao import features_diarias

        codigo = inspect.getsource(features_diarias).lower()
        for termo in (
            "politica",
            "requests",
            "http://",
            "https://",
            "open(",
            "read_csv",
            "to_csv",
            "write_text",
            "fastapi",
            "supabase",
            "score",
            "threshold",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
