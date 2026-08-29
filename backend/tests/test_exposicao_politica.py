from __future__ import annotations

import inspect
import math
import unittest

from pydantic import ValidationError

from backend.exposicao import (
    POLITICA_AGRISHIELD_EQUIP_V1_ID,
    ClassificacaoIndice,
    EstadoDisponibilidade,
    FaixasClassificacaoIndice,
    ParametrosCondicaoHidrica,
    ParametrosNormalizacao90d,
    PerigoExposicao,
    PesosAgregacao90d,
    PesosPerigos,
    PontoCurvaPrecipitacao,
    criar_politica_agrishield_equip_v1,
)


class TestPoliticaDefault(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_politica_default(self):
        self.assertTrue(self.politica.demonstrativa)
        self.assertEqual(self.politica.versao, "1.0")
        self.assertEqual(self.politica.janela_historica_dias, 90)
        self.assertEqual(self.politica.comparacao_anterior_dias, 90)

    def test_id_exato(self):
        self.assertEqual(
            self.politica.id_politica,
            "AGRISHIELD-EQUIP-v1.0",
        )
        self.assertEqual(self.politica.id_politica, POLITICA_AGRISHIELD_EQUIP_V1_ID)

    def test_descricao_explicita_carater_demonstrativo(self):
        descricao = self.politica.descricao.lower()
        self.assertIn("demonstrativa", descricao)
        self.assertIn("não atuarial", descricao)
        self.assertIn("fabricante", descricao)

    def test_pesos_dos_cinco_perigos(self):
        pesos = self.politica.pesos_perigos
        esperados = {
            PerigoExposicao.EXPOSICAO_HIDRICA: 0.30,
            PerigoExposicao.TRAFEGABILIDADE: 0.25,
            PerigoExposicao.INSTABILIDADE: 0.20,
            PerigoExposicao.INCENDIO: 0.15,
            PerigoExposicao.TEMPESTADES: 0.10,
        }
        self.assertEqual(
            {perigo: pesos.peso(perigo) for perigo in PerigoExposicao}, esperados
        )

    def test_soma_pesos_perigos(self):
        pesos = self.politica.pesos_perigos
        self.assertTrue(
            math.isclose(
                math.fsum(pesos.peso(perigo) for perigo in PerigoExposicao),
                1.0,
            )
        )

    def test_pesos_agregacao_90d(self):
        pesos = self.politica.pesos_agregacao_90d
        self.assertEqual(
            (pesos.severidade, pesos.frequencia, pesos.duracao, pesos.recorrencia),
            (0.40, 0.30, 0.20, 0.10),
        )
        self.assertTrue(
            math.isclose(
                math.fsum(
                    (
                        pesos.severidade,
                        pesos.frequencia,
                        pesos.duracao,
                        pesos.recorrencia,
                    )
                ),
                1.0,
            )
        )

    def test_severidades_representativas(self):
        severidades = self.politica.severidades_representativas
        self.assertEqual(severidades.valor(ClassificacaoIndice.NORMAL), 0)
        self.assertEqual(severidades.valor(ClassificacaoIndice.ATENCAO), 33)
        self.assertEqual(severidades.valor(ClassificacaoIndice.ALERTA), 67)
        self.assertEqual(severidades.valor(ClassificacaoIndice.CRITICO), 100)

    def test_parametros_normalizacao(self):
        parametros = self.politica.parametros_normalizacao_90d
        self.assertEqual(parametros.frequencia_saturacao_dias, 15)
        self.assertEqual(parametros.duracao_saturacao_dias, 7)
        self.assertEqual(parametros.recorrencia_saturacao_eventos, 5)
        self.assertEqual(parametros.cobertura_minima_percentual, 80.0)

    def test_parametros_demonstrativos_da_condicao_hidrica(self):
        parametros = self.politica.parametros_condicao_hidrica
        self.assertEqual(
            tuple(
                (ponto.precipitacao_mm, ponto.indice)
                for ponto in parametros.curva_precipitacao
            ),
            ((0, 0), (20, 25), (50, 50), (100, 100)),
        )
        self.assertEqual(
            (parametros.peso_antecedente_d1_d3, parametros.peso_antecedente_d4_d7),
            (0.70, 0.30),
        )
        self.assertEqual(
            (parametros.peso_chuva_atual, parametros.peso_chuva_antecedente),
            (0.70, 0.30),
        )
        self.assertEqual(
            (
                parametros.multiplicador_persistencia_0_1_dia,
                parametros.multiplicador_persistencia_2_3_dias,
                parametros.multiplicador_persistencia_4_mais_dias,
            ),
            (1.0, 1.1, 1.2),
        )

    def test_politica_e_imutavel(self):
        with self.assertRaises(ValidationError):
            self.politica.janela_historica_dias = 30
        with self.assertRaises(ValidationError):
            self.politica.pesos_perigos.exposicao_hidrica = 1.0

    def test_rejeita_identificador_versao_ou_descricao_vazios(self):
        for campo in ("id_politica", "versao", "descricao"):
            dados = self.politica.model_dump()
            dados[campo] = "   "
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                type(self.politica)(**dados)


class TestValidacoesPesos(unittest.TestCase):
    def test_rejeita_soma_invalida_dos_perigos(self):
        with self.assertRaises(ValidationError):
            PesosPerigos(
                exposicao_hidrica=0.30,
                trafegabilidade=0.25,
                instabilidade=0.20,
                incendio=0.15,
                tempestades=0.11,
            )

    def test_rejeita_peso_negativo(self):
        with self.assertRaises(ValidationError):
            PesosPerigos(
                exposicao_hidrica=-0.01,
                trafegabilidade=0.31,
                instabilidade=0.20,
                incendio=0.25,
                tempestades=0.25,
            )

    def test_rejeita_peso_maior_que_um(self):
        with self.assertRaises(ValidationError):
            PesosPerigos(
                exposicao_hidrica=1.01,
                trafegabilidade=0,
                instabilidade=0,
                incendio=0,
                tempestades=0,
            )

    def test_rejeita_soma_invalida_da_agregacao(self):
        with self.assertRaises(ValidationError):
            PesosAgregacao90d(
                severidade=0.40,
                frequencia=0.30,
                duracao=0.20,
                recorrencia=0.11,
            )

    def test_aceita_ruido_de_ponto_flutuante_dentro_da_tolerancia(self):
        pesos = PesosAgregacao90d(
            severidade=0.4,
            frequencia=0.3,
            duracao=0.2,
            recorrencia=0.1000000001,
        )
        self.assertAlmostEqual(
            math.fsum(
                (pesos.severidade, pesos.frequencia, pesos.duracao, pesos.recorrencia)
            ),
            1.0,
        )


class TestClassificacaoIndice(unittest.TestCase):
    def setUp(self):
        self.classificar = criar_politica_agrishield_equip_v1().classificar_indice

    def test_limites_de_classificacao(self):
        casos = (
            (0, ClassificacaoIndice.NORMAL),
            (24.999, ClassificacaoIndice.NORMAL),
            (25, ClassificacaoIndice.ATENCAO),
            (49.999, ClassificacaoIndice.ATENCAO),
            (50, ClassificacaoIndice.ALERTA),
            (74.999, ClassificacaoIndice.ALERTA),
            (75, ClassificacaoIndice.CRITICO),
            (100, ClassificacaoIndice.CRITICO),
        )
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(self.classificar(valor), esperado)

    def test_rejeita_indice_menor_que_zero(self):
        with self.assertRaises(ValueError):
            self.classificar(-0.001)

    def test_rejeita_indice_maior_que_cem(self):
        with self.assertRaises(ValueError):
            self.classificar(100.001)

    def test_rejeita_nan_infinito_booleano_e_texto(self):
        for valor in (math.nan, math.inf, -math.inf, True, "25"):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                self.classificar(valor)

    def test_rejeita_thresholds_desordenados(self):
        with self.assertRaises(ValidationError):
            FaixasClassificacaoIndice(
                inicio_atencao=50,
                inicio_alerta=25,
                inicio_critico=75,
            )


class TestParametrosEDisponibilidade(unittest.TestCase):
    def test_rejeita_curva_hidrica_desordenada(self):
        politica = criar_politica_agrishield_equip_v1()
        dados = politica.parametros_condicao_hidrica.model_dump()
        dados["curva_precipitacao"] = (
            PontoCurvaPrecipitacao(precipitacao_mm=20, indice=25),
            PontoCurvaPrecipitacao(precipitacao_mm=10, indice=50),
        )
        with self.assertRaises(ValidationError):
            ParametrosCondicaoHidrica(**dados)

    def test_rejeita_pesos_hidricos_sem_soma_unitaria(self):
        politica = criar_politica_agrishield_equip_v1()
        dados = politica.parametros_condicao_hidrica.model_dump()
        dados["peso_chuva_atual"] = 0.8
        with self.assertRaises(ValidationError):
            ParametrosCondicaoHidrica(**dados)

    def test_rejeita_cobertura_invalida(self):
        for cobertura in (-0.01, 100.01):
            with self.subTest(cobertura=cobertura), self.assertRaises(ValidationError):
                ParametrosNormalizacao90d(
                    frequencia_saturacao_dias=15,
                    duracao_saturacao_dias=7,
                    recorrencia_saturacao_eventos=5,
                    cobertura_minima_percentual=cobertura,
                )

    def test_rejeita_saturacoes_nao_positivas(self):
        campos = (
            "frequencia_saturacao_dias",
            "duracao_saturacao_dias",
            "recorrencia_saturacao_eventos",
        )
        for campo in campos:
            dados = {
                "frequencia_saturacao_dias": 15,
                "duracao_saturacao_dias": 7,
                "recorrencia_saturacao_eventos": 5,
                "cobertura_minima_percentual": 80,
            }
            dados[campo] = 0
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                ParametrosNormalizacao90d(**dados)

    def test_estados_de_disponibilidade(self):
        self.assertEqual(
            {estado.value for estado in EstadoDisponibilidade},
            {"DISPONIVEL", "INDISPONIVEL", "NAO_APLICAVEL"},
        )


class TestEscopoDaFase(unittest.TestCase):
    def test_nao_introduz_calculo_de_perigo_evento_ou_fazenda(self):
        from backend.exposicao import politica

        codigo = inspect.getsource(politica).lower()
        proibidos = (
            "requests",
            "http://",
            "https://",
            "fastapi",
            "supabase",
            "to_csv",
            "calcular_perigo",
            "detectar_evento",
            "score_fazenda",
            "etapa3",
        )
        for termo in proibidos:
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
