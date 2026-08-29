from __future__ import annotations

import inspect
import unittest
from datetime import date, datetime, timedelta, timezone

from backend.exposicao import (
    AVISO_METODOLOGIA_TRAFEGABILIDADE,
    DIAS_CONTEXTO_TRAFEGABILIDADE,
    FeatureDiariaCompartilhada,
    JanelaHistorica,
    ParametrosTrafegabilidade,
    PerigoExposicao,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    ResultadoTrafegabilidade,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    agrupar_eventos,
    calcular_features_diarias_compartilhadas,
    calcular_recuperacao_trafegabilidade,
    calcular_trafegabilidade_desfavoravel,
    calcular_trafegabilidade_diaria,
    criar_politica_agrishield_equip_v1,
    curva_precipitacao_trafegabilidade,
)
from backend.risco.modelos import FonteDado


DATA_REFERENCIA = date(2026, 8, 11)


def feature(
    *,
    d0: float | None = 20,
    a3: float | None = 20,
    dias_secos: int | None = 0,
    data: date = DATA_REFERENCIA,
) -> FeatureDiariaCompartilhada:
    return FeatureDiariaCompartilhada(
        data=data,
        precipitacao_d0=d0,
        acumulado_3d=a3,
        dias_desde_ultima_chuva_relevante=dias_secos,
    )


def criar_features(precipitacoes: list[float | None]):
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


class TestCurvaPrecipitacaoTrafegabilidade(unittest.TestCase):
    def test_zero_e_zero(self):
        self.assertEqual(curva_precipitacao_trafegabilidade(0), 0)

    def test_none_permanece_indisponivel(self):
        self.assertIsNone(curva_precipitacao_trafegabilidade(None))

    def test_80mm_produz_cem(self):
        self.assertAlmostEqual(curva_precipitacao_trafegabilidade(80), 100.0)

    def test_acima_de_80_satura_em_cem(self):
        self.assertEqual(curva_precipitacao_trafegabilidade(200), 100.0)

    def test_formula_exata_min_100_p_sobre_80_elevado_1_4(self):
        for p in (10, 30, 45, 60):
            with self.subTest(p=p):
                esperado = min(100 * (p / 80) ** 1.4, 100.0)
                self.assertAlmostEqual(curva_precipitacao_trafegabilidade(p), esperado)

    def test_nao_e_a_curva_do_nucleo_hidrico(self):
        # A curva do núcleo hídrico daria índice 25 para 20mm; a curva própria
        # de Trafegabilidade (alta exigência) dá um valor bem menor.
        self.assertLess(curva_precipitacao_trafegabilidade(20), 15)

    def test_valor_invalido_e_rejeitado(self):
        for valor in (-1, True, "20"):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                curva_precipitacao_trafegabilidade(valor)


class TestRecuperacaoTrafegabilidade(unittest.TestCase):
    def test_zero_dias_secos_preserva_componente_acumulado(self):
        self.assertEqual(calcular_recuperacao_trafegabilidade(80.0, 0), 80.0)

    def test_quatro_dias_secos_zera_recuperacao(self):
        self.assertEqual(calcular_recuperacao_trafegabilidade(80.0, 4), 0.0)

    def test_mais_de_quatro_dias_secos_permanece_zero(self):
        self.assertEqual(calcular_recuperacao_trafegabilidade(80.0, 10), 0.0)

    def test_decaimento_linear_em_dois_dias(self):
        self.assertAlmostEqual(calcular_recuperacao_trafegabilidade(80.0, 2), 40.0)

    def test_ausencia_de_qualquer_entrada_indisponibiliza(self):
        self.assertIsNone(calcular_recuperacao_trafegabilidade(None, 2))
        self.assertIsNone(calcular_recuperacao_trafegabilidade(80.0, None))


class TestCalculoDiario(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_dia_totalmente_seco_e_zero(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=0, a3=0, dias_secos=30), self.politica
        )
        self.assertEqual(resultado.indice_trafegabilidade, 0)

    def test_ausencia_de_precipitacao_do_dia_indisponibiliza(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=None, a3=20, dias_secos=0), self.politica
        )
        self.assertIsNone(resultado.indice_trafegabilidade)

    def test_ausencia_de_acumulado_indisponibiliza(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=20, a3=None, dias_secos=0), self.politica
        )
        self.assertIsNone(resultado.indice_trafegabilidade)

    def test_ausencia_de_dias_secos_indisponibiliza(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=20, a3=20, dias_secos=None), self.politica
        )
        self.assertIsNone(resultado.indice_trafegabilidade)

    def test_formula_exata_com_pesos_padrao(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=40, a3=60, dias_secos=1), self.politica
        )
        dia = curva_precipitacao_trafegabilidade(40)
        acumulado = curva_precipitacao_trafegabilidade(60)
        recuperacao = calcular_recuperacao_trafegabilidade(acumulado, 1)
        esperado = min(0.35 * dia + 0.45 * acumulado + 0.20 * recuperacao, 100.0)
        self.assertAlmostEqual(resultado.indice_trafegabilidade, esperado)

    def test_resultado_satura_em_cem(self):
        resultado = calcular_trafegabilidade_diaria(
            feature(d0=500, a3=500, dias_secos=0), self.politica
        )
        self.assertEqual(resultado.indice_trafegabilidade, 100.0)

    def test_alterar_peso_dia_muda_o_resultado(self):
        base = self.politica
        alterado = base.model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=0.60,
                    peso_acumulado=0.20,
                    peso_recuperacao=0.20,
                    limiar_relevancia=25,
                )
            }
        )
        f = feature(d0=60, a3=10, dias_secos=0)
        resultado_base = calcular_trafegabilidade_diaria(f, base)
        resultado_alterado = calcular_trafegabilidade_diaria(f, alterado)
        self.assertNotEqual(
            resultado_base.indice_trafegabilidade,
            resultado_alterado.indice_trafegabilidade,
        )

    def test_alterar_peso_acumulado_muda_o_resultado(self):
        base = self.politica
        alterado = base.model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=0.20,
                    peso_acumulado=0.60,
                    peso_recuperacao=0.20,
                    limiar_relevancia=25,
                )
            }
        )
        f = feature(d0=10, a3=60, dias_secos=0)
        resultado_base = calcular_trafegabilidade_diaria(f, base)
        resultado_alterado = calcular_trafegabilidade_diaria(f, alterado)
        self.assertNotEqual(
            resultado_base.indice_trafegabilidade,
            resultado_alterado.indice_trafegabilidade,
        )

    def test_alterar_peso_recuperacao_muda_o_resultado(self):
        base = self.politica
        alterado = base.model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=0.20,
                    peso_acumulado=0.20,
                    peso_recuperacao=0.60,
                    limiar_relevancia=25,
                )
            }
        )
        f = feature(d0=5, a3=60, dias_secos=2)
        resultado_base = calcular_trafegabilidade_diaria(f, base)
        resultado_alterado = calcular_trafegabilidade_diaria(f, alterado)
        self.assertNotEqual(
            resultado_base.indice_trafegabilidade,
            resultado_alterado.indice_trafegabilidade,
        )

    def test_nao_usa_persistencia_nem_d1_d3_d4_d7(self):
        codigo = inspect.getsource(calcular_trafegabilidade_diaria)
        for termo in ("d1_d3", "d4_d7", "persistencia", "multiplicador"):
            self.assertNotIn(termo, codigo)


class TestCenariosSinteticos(unittest.TestCase):
    """Seção 17 da tarefa: A-F, valores calculados numericamente."""

    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def _indice(self, **kwargs):
        return calcular_trafegabilidade_diaria(
            feature(**kwargs), self.politica
        ).indice_trafegabilidade

    def test_a_periodo_seco_e_zero(self):
        self.assertEqual(self._indice(d0=0, a3=0, dias_secos=30), 0.0)

    def test_b_chuva_forte_apos_seca_reage(self):
        indice = self._indice(d0=45, a3=45, dias_secos=20)
        self.assertGreater(indice, 25)

    def test_c_chuva_moderada_persistente_reflete_acumulado(self):
        indice = self._indice(d0=15, a3=40, dias_secos=0)
        acumulado = curva_precipitacao_trafegabilidade(40)
        # componente de acumulado pesa 45%, mais que os 35% do dia
        self.assertGreater(
            0.45 * acumulado, 0.35 * curva_precipitacao_trafegabilidade(15)
        )
        self.assertGreater(indice, 0)

    def test_d_chuva_antiga_seguida_de_dias_secos_mostra_recuperacao(self):
        recente = self._indice(d0=0, a3=55, dias_secos=0)
        um_dia_seco = self._indice(d0=0, a3=55, dias_secos=1)
        tres_dias_secos = self._indice(d0=0, a3=55, dias_secos=3)
        totalmente_seco = self._indice(d0=0, a3=55, dias_secos=10)
        self.assertGreater(recente, um_dia_seco)
        self.assertGreater(um_dia_seco, tres_dias_secos)
        self.assertGreater(tres_dias_secos, totalmente_seco)
        self.assertEqual(
            totalmente_seco,
            min(
                0.35 * 0 + 0.45 * curva_precipitacao_trafegabilidade(55) + 0.20 * 0,
                100.0,
            ),
        )

    def test_e_chuva_leve_isolada_permanece_baixa(self):
        indice = self._indice(d0=3, a3=3, dias_secos=10)
        self.assertLess(indice, 5)

    def test_f_acumulado_relevante_sem_pico_extremo_segue_curva_alta_exigencia(self):
        indice_com_pico = self._indice(d0=60, a3=60, dias_secos=0)
        indice_sem_pico = self._indice(d0=8, a3=35, dias_secos=0)
        self.assertGreater(indice_com_pico, indice_sem_pico)


class TestResultadoTrafegabilidade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_dia_seco_apos_chuva_antiga_produz_indice_zero(self):
        # Um único dia de chuva no início estabelece "dias desde a última
        # chuva relevante"; sem nenhuma chuva alguma vez, esse campo permanece
        # None (indisponível), não zero — comportamento correto e preexistente
        # de calcular_features_diarias_compartilhadas, não específico desta
        # tarefa.
        resultado = calcular_trafegabilidade_desfavoravel(
            criar_features_90d([50] + [0] * 89), self.politica
        )
        ultimo = resultado.indices_diarios.indices[-1]
        self.assertIsNotNone(ultimo.indice)
        self.assertEqual(ultimo.indice, 0)

    def test_gap_fica_indisponivel(self):
        chuvas = [20] * 90
        chuvas[-1] = None
        resultado = calcular_trafegabilidade_desfavoravel(
            criar_features_90d(chuvas), self.politica
        )
        self.assertIsNone(resultado.indices_diarios.indices[-1].indice)

    def test_indice_classificacao_eventos_agregacao_e_cobertura(self):
        resultado = calcular_trafegabilidade_desfavoravel(
            criar_features_90d([80] * 90), self.politica
        )
        ultimo = resultado.indices_diarios.indices[-1]
        self.assertGreaterEqual(ultimo.indice, 0)
        self.assertLessEqual(ultimo.indice, 100)
        self.assertEqual(
            ultimo.classificacao, self.politica.classificar_indice(ultimo.indice)
        )
        self.assertEqual(
            resultado.agregacao_90d.eventos,
            agrupar_eventos(resultado.indices_diarios, self.politica),
        )

    def test_perigo_e_metodologia_propria(self):
        resultado = calcular_trafegabilidade_desfavoravel(
            criar_features_90d([20] * 90), self.politica
        )
        self.assertEqual(resultado.perigo, PerigoExposicao.TRAFEGABILIDADE)
        self.assertEqual(
            resultado.parametros_trafegabilidade,
            self.politica.parametros_trafegabilidade,
        )
        self.assertEqual(resultado.aviso_metodologia, AVISO_METODOLOGIA_TRAFEGABILIDADE)

    def test_nao_reutiliza_o_nucleo_hidrico(self):
        # ResultadoTrafegabilidade não tem mais o campo condicoes_hidricas do
        # núcleo hídrico compartilhado — a metodologia é própria.
        self.assertNotIn("condicoes_hidricas", ResultadoTrafegabilidade.model_fields)

    def test_janela_alvo_e_respeitada(self):
        janela_alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        features = criar_features([0] * 97)
        resultado = calcular_trafegabilidade_desfavoravel(
            features, self.politica, janela_alvo=janela_alvo
        )
        self.assertEqual(resultado.agregacao_90d.inicio, janela_alvo.inicio)
        self.assertEqual(resultado.agregacao_90d.fim, janela_alvo.fim)
        self.assertEqual(resultado.indices_diarios.periodo, janela_alvo)
        self.assertEqual(
            resultado.dias_contexto_calendario, DIAS_CONTEXTO_TRAFEGABILIDADE
        )

    def test_mesma_entrada_produz_mesmo_resultado(self):
        features = criar_features_90d([30] * 90)
        primeiro = calcular_trafegabilidade_desfavoravel(features, self.politica)
        segundo = calcular_trafegabilidade_desfavoravel(features, self.politica)
        self.assertEqual(primeiro, segundo)


class TestLimiarDeRelevancia(unittest.TestCase):
    """O limiar próprio de Trafegabilidade afeta agregação, não classificação diária."""

    def setUp(self):
        self.politica_padrao = criar_politica_agrishield_equip_v1()

    def test_default_25_mantem_relevancia_igual_a_classificacao(self):
        # Com o limiar padrão (25) = faixa global de ATENCAO, o comportamento
        # deve ficar idêntico a usar apenas a classificação.
        resultado = calcular_trafegabilidade_desfavoravel(
            criar_features_90d([40] * 90), self.politica_padrao
        )
        for indice in resultado.indices_diarios.indices:
            if indice.indice is not None:
                self.assertEqual(indice.relevante, indice.indice >= 25)
                self.assertEqual(
                    indice.relevante,
                    indice.classificacao.value != "NORMAL",
                )

    def test_limiar_mais_baixo_marca_dia_relevante_mesmo_com_classificacao_normal(self):
        politica_limiar_baixo = self.politica_padrao.model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=0.35,
                    peso_acumulado=0.45,
                    peso_recuperacao=0.20,
                    limiar_relevancia=10,
                )
            }
        )
        # precipitacao moderada que produz indice entre 10 e 25 (NORMAL na
        # classificacao global, mas relevante para agregacao com limiar=10)
        precipitacoes = [12] * 90
        resultado_padrao = calcular_trafegabilidade_desfavoravel(
            criar_features_90d(precipitacoes), self.politica_padrao
        )
        resultado_limiar_baixo = calcular_trafegabilidade_desfavoravel(
            criar_features_90d(precipitacoes), politica_limiar_baixo
        )
        indice_dia = resultado_padrao.indices_diarios.indices[-1]
        self.assertIsNotNone(indice_dia.indice)
        self.assertLess(indice_dia.indice, 25)
        self.assertEqual(indice_dia.classificacao.value, "NORMAL")
        self.assertFalse(indice_dia.relevante)

        indice_dia_limiar_baixo = resultado_limiar_baixo.indices_diarios.indices[-1]
        self.assertEqual(indice_dia_limiar_baixo.classificacao.value, "NORMAL")
        if (
            indice_dia_limiar_baixo.indice is not None
            and indice_dia_limiar_baixo.indice >= 10
        ):
            self.assertTrue(indice_dia_limiar_baixo.relevante)

    def test_limiar_altera_apenas_agregacao_nao_classificacao_diaria(self):
        politica_limiar_baixo = self.politica_padrao.model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=0.35,
                    peso_acumulado=0.45,
                    peso_recuperacao=0.20,
                    limiar_relevancia=5,
                )
            }
        )
        precipitacoes = [12] * 90
        resultado_padrao = calcular_trafegabilidade_desfavoravel(
            criar_features_90d(precipitacoes), self.politica_padrao
        )
        resultado_limiar_baixo = calcular_trafegabilidade_desfavoravel(
            criar_features_90d(precipitacoes), politica_limiar_baixo
        )
        # Classificações diárias e valores continuam idênticos.
        classes_padrao = [
            i.classificacao for i in resultado_padrao.indices_diarios.indices
        ]
        classes_limiar = [
            i.classificacao for i in resultado_limiar_baixo.indices_diarios.indices
        ]
        self.assertEqual(classes_padrao, classes_limiar)
        valores_padrao = [i.indice for i in resultado_padrao.indices_diarios.indices]
        valores_limiar = [
            i.indice for i in resultado_limiar_baixo.indices_diarios.indices
        ]
        self.assertEqual(valores_padrao, valores_limiar)
        # Mas a agregação (dias relevantes/eventos) muda.
        self.assertNotEqual(
            resultado_padrao.agregacao_90d.quantidade_dias_relevantes,
            resultado_limiar_baixo.agregacao_90d.quantidade_dias_relevantes,
        )

    def test_limiar_invalido_e_rejeitado(self):
        for limiar in (-1, 101):
            with self.subTest(limiar=limiar), self.assertRaises(Exception):
                ParametrosTrafegabilidade(
                    peso_dia=0.35,
                    peso_acumulado=0.45,
                    peso_recuperacao=0.20,
                    limiar_relevancia=limiar,
                )


class TestParametrosTrafegabilidade(unittest.TestCase):
    def test_defaults_sao_35_45_20_25(self):
        politica = criar_politica_agrishield_equip_v1()
        p = politica.parametros_trafegabilidade
        self.assertEqual(p.peso_dia, 0.35)
        self.assertEqual(p.peso_acumulado, 0.45)
        self.assertEqual(p.peso_recuperacao, 0.20)
        self.assertEqual(p.limiar_relevancia, 25.0)

    def test_pesos_devem_somar_1(self):
        with self.assertRaises(Exception):
            ParametrosTrafegabilidade(
                peso_dia=0.5,
                peso_acumulado=0.5,
                peso_recuperacao=0.5,
                limiar_relevancia=25,
            )

    def test_peso_negativo_e_rejeitado(self):
        with self.assertRaises(Exception):
            ParametrosTrafegabilidade(
                peso_dia=-0.1,
                peso_acumulado=0.9,
                peso_recuperacao=0.2,
                limiar_relevancia=25,
            )

    def test_expoente_normalizador_e_horizonte_nao_sao_configuraveis(self):
        campos = set(ParametrosTrafegabilidade.model_fields)
        self.assertEqual(
            campos,
            {"peso_dia", "peso_acumulado", "peso_recuperacao", "limiar_relevancia"},
        )


class TestEscopoENaoDependencia(unittest.TestCase):
    def test_nao_recebe_nem_usa_evidencia_geoespacial(self):
        # Nenhuma função pública recebe AnaliseGeoespacialNormalizada
        # (SRTM/MERIT), diferente de calcular_exposicao_hidrica/instabilidade.
        assinatura_diaria = inspect.signature(calcular_trafegabilidade_diaria)
        assinatura_resultado = inspect.signature(calcular_trafegabilidade_desfavoravel)
        for assinatura in (assinatura_diaria, assinatura_resultado):
            for nome in assinatura.parameters:
                self.assertNotIn("geo", nome.lower())

    def test_nao_importa_tipos_geoespaciais(self):
        import backend.exposicao.perigo_trafegabilidade as modulo

        codigo = inspect.getsource(modulo)
        for termo in ("AnaliseGeoespacialNormalizada", "AtributoGeoespacial"):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_nao_importa_o_nucleo_hidrico(self):
        import backend.exposicao.perigo_trafegabilidade as modulo

        self.assertNotIn("perigos_hidricos", modulo.__dict__)
        self.assertFalse(any("condicao_hidrica" in nome for nome in modulo.__dict__))
        codigo_sem_docstring = inspect.getsource(modulo).split('"""', 2)[-1]
        self.assertNotIn("perigos_hidricos", codigo_sem_docstring)
        self.assertNotIn("calcular_condicao_hidrica", codigo_sem_docstring)


if __name__ == "__main__":
    unittest.main()
