from __future__ import annotations

import inspect
import math
import unittest
from datetime import date, datetime, timedelta, timezone

from backend.exposicao import (
    ClassificacaoIndice,
    DIAS_AQUISICAO_DUAS_JANELAS_90D,
    DIAS_CONTEXTO_HIDRICO,
    FeatureDiariaCompartilhada,
    FinalidadeJanela,
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    agrupar_eventos,
    calcular_condicao_hidrica_diaria,
    calcular_features_diarias_compartilhadas,
    criar_politica_agrishield_equip_v1,
    normalizar_precipitacao,
)
from backend.exposicao.perigos_hidricos import (
    calcular_condicao_hidrica_meteorologica as calcular_exposicao_hidrica,
)
from backend.risco.modelos import FonteDado


DATA_REFERENCIA = date(2026, 8, 11)


def feature_hidrica(
    *,
    d0: float | None = 20,
    d1_d3: float | None = 20,
    d4_d7: float | None = 20,
    persistencia: int | None = 1,
) -> FeatureDiariaCompartilhada:
    return FeatureDiariaCompartilhada(
        data=DATA_REFERENCIA,
        precipitacao_d0=d0,
        precipitacao_d1_d3=d1_d3,
        precipitacao_d4_d7=d4_d7,
        dias_consecutivos_com_chuva=persistencia,
    )


def criar_features(
    precipitacoes: list[float | None],
):
    janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, len(precipitacoes))
    registros = tuple(
        RegistroMeteorologicoDiario(
            data=janela.inicio + timedelta(days=indice),
            precipitacao_mm=precipitacao,
            temperatura_media_c=25,
            temperatura_maxima_c=30,
            temperatura_minima_c=20,
            umidade_media_pct=70,
        )
        for indice, precipitacao in enumerate(precipitacoes)
    )
    serie = SerieHistoricaFonte.criar(
        id_fazenda="fazenda-teste",
        fonte=FonteDado.NASA_POWER,
        tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
        dataset="NASA/POWER",
        periodo_solicitado=janela,
        referencia_temporal=ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        ),
        registros=registros,
        coletado_em_utc=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
    )
    return calcular_features_diarias_compartilhadas(serie)


def criar_features_90d(precipitacoes: list[float | None]):
    if len(precipitacoes) != 90:
        raise ValueError("teste exige 90 dias")
    return criar_features(precipitacoes)


class TestCurvaPrecipitacao(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_pontos_exatos_da_curva(self):
        for chuva, esperado in ((0, 0), (20, 25), (50, 50), (100, 100)):
            with self.subTest(chuva=chuva):
                self.assertEqual(
                    normalizar_precipitacao(chuva, self.politica), esperado
                )

    def test_acima_de_cem_satura_em_cem(self):
        self.assertEqual(normalizar_precipitacao(180, self.politica), 100)

    def test_interpolacao_linear_entre_pontos(self):
        self.assertEqual(normalizar_precipitacao(10, self.politica), 12.5)
        self.assertEqual(normalizar_precipitacao(35, self.politica), 37.5)
        self.assertEqual(normalizar_precipitacao(75, self.politica), 75)

    def test_zero_e_valido(self):
        self.assertEqual(normalizar_precipitacao(0.0, self.politica), 0.0)

    def test_none_permanece_indisponivel(self):
        self.assertIsNone(normalizar_precipitacao(None, self.politica))

    def test_valor_invalido_e_rejeitado(self):
        for valor in (-1, math.nan, math.inf, True, "20"):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                normalizar_precipitacao(valor, self.politica)


class TestCondicaoHidrica(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_usa_d1_d3_e_d4_d7_separadamente(self):
        condicao = calcular_condicao_hidrica_diaria(
            feature_hidrica(d0=0, d1_d3=20, d4_d7=50),
            self.politica,
        )
        self.assertEqual(condicao.indice_d1_d3, 25)
        self.assertEqual(condicao.indice_d4_d7, 50)

    def test_antecedente_usa_pesos_70_30(self):
        condicao = calcular_condicao_hidrica_diaria(
            feature_hidrica(d0=0, d1_d3=20, d4_d7=50, persistencia=1),
            self.politica,
        )
        self.assertEqual(condicao.indice_antecedente, 25 * 0.70 + 50 * 0.30)

    def test_persistencia_zero_ou_um_multiplica_por_um(self):
        for persistencia in (0, 1):
            with self.subTest(persistencia=persistencia):
                condicao = calcular_condicao_hidrica_diaria(
                    feature_hidrica(persistencia=persistencia), self.politica
                )
                self.assertEqual(condicao.multiplicador_persistencia, 1.0)

    def test_persistencia_dois_ou_tres_multiplica_por_1_1(self):
        for persistencia in (2, 3):
            with self.subTest(persistencia=persistencia):
                condicao = calcular_condicao_hidrica_diaria(
                    feature_hidrica(persistencia=persistencia), self.politica
                )
                self.assertEqual(condicao.multiplicador_persistencia, 1.1)

    def test_persistencia_quatro_ou_mais_multiplica_por_1_2(self):
        for persistencia in (4, 10):
            with self.subTest(persistencia=persistencia):
                condicao = calcular_condicao_hidrica_diaria(
                    feature_hidrica(persistencia=persistencia), self.politica
                )
                self.assertEqual(condicao.multiplicador_persistencia, 1.2)

    def test_amplificador_satura_antecedente_em_cem(self):
        condicao = calcular_condicao_hidrica_diaria(
            feature_hidrica(d1_d3=100, d4_d7=100, persistencia=10),
            self.politica,
        )
        self.assertEqual(condicao.indice_antecedente, 100)

    def test_indice_hidrico_usa_70_30_atual_antecedente(self):
        condicao = calcular_condicao_hidrica_diaria(
            feature_hidrica(d0=20, d1_d3=20, d4_d7=50, persistencia=1),
            self.politica,
        )
        antecedente = 25 * 0.70 + 50 * 0.30
        self.assertEqual(
            condicao.indice_hidrico_meteorologico, 25 * 0.70 + antecedente * 0.30
        )

    def test_ausencia_em_cada_componente_obrigatorio_indisponibiliza(self):
        casos = (
            feature_hidrica(d0=None),
            feature_hidrica(d1_d3=None),
            feature_hidrica(d4_d7=None),
            feature_hidrica(persistencia=None),
        )
        for feature in casos:
            with self.subTest(feature=feature):
                condicao = calcular_condicao_hidrica_diaria(feature, self.politica)
                self.assertIsNone(condicao.indice_hidrico_meteorologico)

    def test_acumulados_explicativos_nao_entram_no_calculo(self):
        base = feature_hidrica()
        alterada = base.model_copy(update={"acumulado_3d": 999, "acumulado_7d": 999})
        self.assertEqual(
            calcular_condicao_hidrica_diaria(base, self.politica),
            calcular_condicao_hidrica_diaria(alterada, self.politica),
        )


class TestExposicaoHidrica(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_dia_seco_produz_indice_zero_quando_janela_disponivel(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([0] * 90), self.politica
        )
        self.assertEqual(resultado.indices_diarios.indices[-1].indice, 0)
        self.assertEqual(
            resultado.indices_diarios.indices[-1].classificacao,
            ClassificacaoIndice.NORMAL,
        )

    def test_chuva_elevada_produz_indice_maior(self):
        seco = calcular_exposicao_hidrica(criar_features_90d([0] * 90), self.politica)
        chuvoso = calcular_exposicao_hidrica(
            criar_features_90d([100] * 90), self.politica
        )
        self.assertGreater(
            chuvoso.indices_diarios.indices[-1].indice,
            seco.indices_diarios.indices[-1].indice,
        )

    def test_persistencia_aumenta_indice(self):
        um_dia = calcular_condicao_hidrica_diaria(
            feature_hidrica(persistencia=1), self.politica
        )
        quatro_dias = calcular_condicao_hidrica_diaria(
            feature_hidrica(persistencia=4), self.politica
        )
        self.assertGreater(
            quatro_dias.indice_hidrico_meteorologico,
            um_dia.indice_hidrico_meteorologico,
        )

    def test_ausencia_nao_vira_normal(self):
        chuvas = [0] * 90
        chuvas[-1] = None
        resultado = calcular_exposicao_hidrica(
            criar_features_90d(chuvas), self.politica
        )
        ultimo = resultado.indices_diarios.indices[-1]
        self.assertIsNone(ultimo.indice)
        self.assertIsNone(ultimo.classificacao)

    def test_usa_indices_eventos_e_agregacao_comuns(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([100] * 90), self.politica
        )
        eventos = agrupar_eventos(resultado.indices_diarios, self.politica)
        self.assertEqual(resultado.agregacao_90d.eventos, eventos)
        self.assertGreater(len(eventos), 0)
        self.assertEqual(resultado.politica_id, self.politica.id_politica)

    def test_resultado_final_permanece_entre_zero_e_cem(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([100] * 90), self.politica
        )
        self.assertGreaterEqual(resultado.agregacao_90d.indice_agregado, 0)
        self.assertLessEqual(resultado.agregacao_90d.indice_agregado, 100)

    def test_classificacao_usa_politica(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([50] * 90), self.politica
        )
        ultimo = resultado.indices_diarios.indices[-1]
        self.assertEqual(
            ultimo.classificacao, self.politica.classificar_indice(ultimo.indice)
        )

    def test_cobertura_reflete_primeiros_dias_sem_antecedentes(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([0] * 90), self.politica
        )
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 83)
        self.assertAlmostEqual(
            resultado.agregacao_90d.cobertura_percentual, 83 / 90 * 100
        )

    def test_indice_e_explicitamente_meteorologico(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([0] * 90), self.politica
        )
        self.assertFalse(resultado.contexto_territorial_aplicado)
        self.assertIn(
            "não possuem suscetibilidade normalizada", resultado.limitacao_territorial
        )


class TestWarmupEJanelaAlvo(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.janela_alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)

    def test_janela_alvo_com_sete_dias_anteriores_reais(self):
        features = criar_features([0] * 97)
        resultado = calcular_exposicao_hidrica(
            features,
            self.politica,
            janela_alvo=self.janela_alvo,
        )
        self.assertEqual(resultado.periodo_features.dias_esperados, 97)
        self.assertEqual(resultado.janela_analisada, self.janela_alvo)
        self.assertEqual(resultado.dias_contexto_calendario, DIAS_CONTEXTO_HIDRICO)

    def test_primeiro_dia_alvo_usa_d1_a_d7_do_contexto(self):
        features = criar_features(list(range(1, 98)))
        resultado = calcular_exposicao_hidrica(
            features,
            self.politica,
            janela_alvo=self.janela_alvo,
        )
        primeira = resultado.condicoes_hidricas[0]
        self.assertEqual(primeira.data, self.janela_alvo.inicio)
        self.assertEqual(
            primeira.indice_d1_d3,
            normalizar_precipitacao(7 + 6 + 5, self.politica),
        )
        self.assertEqual(
            primeira.indice_d4_d7,
            normalizar_precipitacao(4 + 3 + 2 + 1, self.politica),
        )
        self.assertIsNotNone(primeira.indice_hidrico_meteorologico)

    def test_contexto_nao_aparece_na_serie_final(self):
        features = criar_features([100] * 97)
        resultado = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=self.janela_alvo
        )
        self.assertEqual(len(resultado.indices_diarios.indices), 90)
        self.assertEqual(
            resultado.indices_diarios.indices[0].data, self.janela_alvo.inicio
        )
        self.assertEqual(
            resultado.indices_diarios.indices[-1].data, self.janela_alvo.fim
        )
        self.assertNotIn(
            features.periodo.inicio,
            {item.data for item in resultado.indices_diarios.indices},
        )

    def test_contexto_nao_forma_evento_nem_entra_na_frequencia(self):
        features = criar_features([100] * 97)
        resultado = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=self.janela_alvo
        )
        self.assertEqual(resultado.agregacao_90d.quantidade_dias_relevantes, 90)
        self.assertEqual(resultado.agregacao_90d.quantidade_eventos, 1)
        self.assertEqual(
            resultado.agregacao_90d.eventos[0].inicio, self.janela_alvo.inicio
        )
        self.assertEqual(resultado.agregacao_90d.eventos[0].duracao_dias, 90)

    def test_contexto_nao_entra_na_cobertura_e_permite_cem_por_cento(self):
        resultado = calcular_exposicao_hidrica(
            criar_features([0] * 97),
            self.politica,
            janela_alvo=self.janela_alvo,
        )
        self.assertEqual(resultado.agregacao_90d.dias_esperados, 90)
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 90)
        self.assertEqual(resultado.agregacao_90d.cobertura_percentual, 100)

    def test_sem_contexto_mantem_primeiros_dias_indisponiveis(self):
        resultado = calcular_exposicao_hidrica(
            criar_features_90d([0] * 90), self.politica
        )
        self.assertEqual(resultado.dias_contexto_calendario, 0)
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 83)
        self.assertTrue(
            all(item.indice is None for item in resultado.indices_diarios.indices[:7])
        )

    def test_contexto_ausente_nao_e_imputado(self):
        precipitacoes = [0] * 97
        precipitacoes[0] = None
        resultado = calcular_exposicao_hidrica(
            criar_features(precipitacoes),
            self.politica,
            janela_alvo=self.janela_alvo,
        )
        self.assertIsNone(resultado.indices_diarios.indices[0].indice)
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 89)

    def test_mesma_entrada_e_janela_produzem_mesmo_resultado(self):
        features = criar_features([20] * 97)
        primeiro = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=self.janela_alvo
        )
        segundo = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=self.janela_alvo
        )
        self.assertEqual(primeiro, segundo)

    def test_aquisicao_187_suporta_duas_janelas_sem_criar_comparacao(self):
        self.assertEqual(DIAS_AQUISICAO_DUAS_JANELAS_90D, 7 + 180)
        features = criar_features([0] * DIAS_AQUISICAO_DUAS_JANELAS_90D)
        janela_anterior = JanelaHistorica(
            data_referencia=DATA_REFERENCIA,
            inicio=DATA_REFERENCIA - timedelta(days=179),
            fim=DATA_REFERENCIA - timedelta(days=90),
            dias_esperados=90,
            finalidade=FinalidadeJanela.COMPARACAO_ANTERIOR,
        )
        anterior = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=janela_anterior
        )
        atual = calcular_exposicao_hidrica(
            features, self.politica, janela_alvo=self.janela_alvo
        )
        self.assertEqual(anterior.agregacao_90d.cobertura_percentual, 100)
        self.assertEqual(atual.agregacao_90d.cobertura_percentual, 100)
        self.assertEqual(anterior.janela_analisada, janela_anterior)
        self.assertEqual(atual.janela_analisada, self.janela_alvo)


class TestEscopoEImutabilidade(unittest.TestCase):
    def test_resultado_preserva_parametros_e_versao(self):
        politica = criar_politica_agrishield_equip_v1()
        resultado = calcular_exposicao_hidrica(criar_features_90d([0] * 90), politica)
        self.assertEqual(
            resultado.parametros_condicao_hidrica, politica.parametros_condicao_hidrica
        )
        self.assertTrue(resultado.versao)

    def test_modulo_nao_faz_http_persistencia_ou_score_geral(self):
        from backend.exposicao import perigos_hidricos

        codigo = inspect.getsource(perigos_hidricos).lower()
        for termo in (
            "requests",
            "http://",
            "https://",
            "open(",
            "read_csv",
            "to_csv",
            "fastapi",
            "supabase",
            "score_geral",
            "etapa3",
            "granizo",
            "raios",
            "vento",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_nao_implementa_outros_perigos(self):
        from backend.exposicao import perigos_hidricos

        codigo = inspect.getsource(perigos_hidricos).lower()
        for termo in ("instabilidade", "incendio", "tempestades"):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
