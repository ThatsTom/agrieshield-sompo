from __future__ import annotations

import inspect
import re
import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from backend.exposicao import (
    ClassificacaoIndice,
    EstadoDisponibilidade,
    FaixasClassificacaoIndice,
    IndiceDiarioPerigo,
    JanelaHistorica,
    ValorIndiceDiario,
    agregar_indice_historico,
    agrupar_eventos,
    criar_indices_diarios,
    criar_politica_agrishield_equip_v1,
)


DATA_REFERENCIA = date(2026, 8, 11)


def criar_serie_indices(
    valores: list[float | None],
    *,
    posicoes: list[int] | None = None,
    fora_de_ordem: bool = False,
):
    politica = criar_politica_agrishield_equip_v1()
    janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
    posicoes_usadas = posicoes if posicoes is not None else list(range(len(valores)))
    informados = [
        ValorIndiceDiario(
            data=janela.inicio + timedelta(days=posicao),
            indice=valor,
        )
        for posicao, valor in zip(posicoes_usadas, valores, strict=True)
    ]
    if fora_de_ordem:
        informados.reverse()
    return criar_indices_diarios(janela, informados, politica), politica


def resultado_com_dias_relevantes(quantidade: int):
    valores = [25.0] * quantidade + [0.0] * (90 - quantidade)
    serie, politica = criar_serie_indices(valores)
    return agregar_indice_historico(serie, politica)


def resultado_com_eventos(quantidade: int):
    valores = [0.0] * 90
    for indice in range(quantidade):
        valores[indice * 2] = 25.0
    serie, politica = criar_serie_indices(valores)
    return agregar_indice_historico(serie, politica)


class TestIndicesDiarios(unittest.TestCase):
    def test_limites_classificados_pela_politica(self):
        valores = [0, 24.999, 25, 50, 75, 100]
        serie, _ = criar_serie_indices(valores)
        self.assertEqual(
            [item.classificacao for item in serie.indices[:6]],
            [
                ClassificacaoIndice.NORMAL,
                ClassificacaoIndice.NORMAL,
                ClassificacaoIndice.ATENCAO,
                ClassificacaoIndice.ALERTA,
                ClassificacaoIndice.CRITICO,
                ClassificacaoIndice.CRITICO,
            ],
        )

    def test_indice_invalido_rejeitado(self):
        for valor in (-0.01, 100.01):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                ValorIndiceDiario(data=DATA_REFERENCIA, indice=valor)

    def test_classificacao_usa_thresholds_da_politica(self):
        politica_base = criar_politica_agrishield_equip_v1()
        politica = politica_base.model_copy(
            update={
                "faixas_classificacao": FaixasClassificacaoIndice(
                    inicio_atencao=10,
                    inicio_alerta=20,
                    inicio_critico=30,
                )
            }
        )
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        serie = criar_indices_diarios(
            janela,
            [ValorIndiceDiario(data=janela.inicio, indice=15)],
            politica,
        )
        self.assertEqual(serie.indices[0].classificacao, ClassificacaoIndice.ATENCAO)

    def test_ausencia_e_indisponivel_sem_classificacao(self):
        serie, _ = criar_serie_indices([None])
        primeiro = serie.indices[0]
        self.assertEqual(primeiro.disponibilidade, EstadoDisponibilidade.INDISPONIVEL)
        self.assertIsNone(primeiro.indice)
        self.assertIsNone(primeiro.classificacao)


class TestEventos(unittest.TestCase):
    def test_sequencia_continua_de_atencao(self):
        serie, politica = criar_serie_indices([25, 25, 25, 0])
        eventos = agrupar_eventos(serie, politica)
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0].duracao_dias, 3)

    def test_atencao_alerta_critico_formam_um_evento(self):
        serie, politica = criar_serie_indices([25, 50, 75, 0])
        evento = agrupar_eventos(serie, politica)[0]
        self.assertEqual(evento.duracao_dias, 3)
        self.assertEqual(evento.classificacao_maxima, ClassificacaoIndice.CRITICO)
        self.assertEqual(evento.indice_maximo, 75)
        self.assertEqual(evento.indice_medio, 50)

    def test_normal_encerra_evento(self):
        serie, politica = criar_serie_indices([50, 0, 50])
        eventos = agrupar_eventos(serie, politica)
        self.assertEqual(len(eventos), 2)
        self.assertEqual([evento.duracao_dias for evento in eventos], [1, 1])

    def test_gap_encerra_evento(self):
        serie, politica = criar_serie_indices([50, None, 50])
        eventos = agrupar_eventos(serie, politica)
        self.assertEqual(len(eventos), 2)

    def test_dois_eventos_separados(self):
        serie, politica = criar_serie_indices([25, 25, 0, 50, 50, 0])
        eventos = agrupar_eventos(serie, politica)
        self.assertEqual(len(eventos), 2)
        self.assertEqual([evento.duracao_dias for evento in eventos], [2, 2])

    def test_evento_no_primeiro_dia(self):
        serie, politica = criar_serie_indices([25, 0])
        evento = agrupar_eventos(serie, politica)[0]
        self.assertEqual(evento.inicio, serie.periodo.inicio)

    def test_evento_terminando_no_ultimo_dia(self):
        serie, politica = criar_serie_indices([25, 25], posicoes=[88, 89])
        evento = agrupar_eventos(serie, politica)[0]
        self.assertEqual(evento.fim, serie.periodo.fim)
        self.assertEqual(evento.duracao_dias, 2)

    def test_duracao_usa_dias_calendario(self):
        serie, politica = criar_serie_indices([25, 25, 25, 25])
        evento = agrupar_eventos(serie, politica)[0]
        self.assertEqual((evento.fim - evento.inicio).days + 1, 4)
        self.assertEqual(evento.quantidade_dias_relevantes, 4)


class TestSeveridade(unittest.TestCase):
    def test_evento_somente_atencao_tem_severidade_33(self):
        serie, politica = criar_serie_indices([25, 25, 0])
        self.assertEqual(agrupar_eventos(serie, politica)[0].severidade_evento, 33)

    def test_evento_com_alerta_tem_severidade_67(self):
        serie, politica = criar_serie_indices([25, 50, 25, 0])
        self.assertEqual(agrupar_eventos(serie, politica)[0].severidade_evento, 67)

    def test_evento_com_critico_tem_severidade_100(self):
        serie, politica = criar_serie_indices([50, 75, 50, 0])
        self.assertEqual(agrupar_eventos(serie, politica)[0].severidade_evento, 100)

    def test_media_de_severidade_de_multiplos_eventos(self):
        serie, politica = criar_serie_indices([25, 0, 75, 0])
        resultado = agregar_indice_historico(serie, politica)
        self.assertEqual(resultado.severidade_score, (33 + 100) / 2)

    def test_sem_eventos_tem_severidade_zero(self):
        serie, politica = criar_serie_indices([0] * 90)
        self.assertEqual(agregar_indice_historico(serie, politica).severidade_score, 0)


class TestComponentesNormalizados(unittest.TestCase):
    def test_frequencia_zero(self):
        self.assertEqual(resultado_com_dias_relevantes(0).frequencia_score, 0)

    def test_frequencia_intermediaria(self):
        self.assertEqual(resultado_com_dias_relevantes(3).frequencia_score, 20)

    def test_frequencia_15_dias_satura(self):
        self.assertEqual(resultado_com_dias_relevantes(15).frequencia_score, 100)

    def test_frequencia_acima_de_15_permanece_100(self):
        self.assertEqual(resultado_com_dias_relevantes(20).frequencia_score, 100)

    def test_duracao_zero(self):
        self.assertEqual(resultado_com_dias_relevantes(0).duracao_score, 0)

    def test_duracao_intermediaria(self):
        self.assertAlmostEqual(
            resultado_com_dias_relevantes(3).duracao_score, 3 / 7 * 100
        )

    def test_duracao_7_dias_satura(self):
        self.assertEqual(resultado_com_dias_relevantes(7).duracao_score, 100)

    def test_duracao_acima_de_7_permanece_100(self):
        self.assertEqual(resultado_com_dias_relevantes(8).duracao_score, 100)

    def test_recorrencia_zero(self):
        self.assertEqual(resultado_com_eventos(0).recorrencia_score, 0)

    def test_recorrencia_intermediaria(self):
        self.assertEqual(resultado_com_eventos(2).recorrencia_score, 40)

    def test_recorrencia_5_eventos_satura(self):
        self.assertEqual(resultado_com_eventos(5).recorrencia_score, 100)

    def test_recorrencia_acima_de_5_permanece_100(self):
        self.assertEqual(resultado_com_eventos(6).recorrencia_score, 100)


class TestAgregacao(unittest.TestCase):
    def test_formula_40_30_20_10(self):
        serie, politica = criar_serie_indices([75] + [0] * 89)
        resultado = agregar_indice_historico(serie, politica)
        esperado = 100 * 0.40 + (100 / 15) * 0.30 + (100 / 7) * 0.20 + 20 * 0.10
        self.assertAlmostEqual(resultado.indice_agregado, esperado)

    def test_nao_arredonda_componentes_antes_da_soma(self):
        serie, politica = criar_serie_indices([25] + [0] * 89)
        resultado = agregar_indice_historico(serie, politica)
        esperado = 33 * 0.40 + (100 / 15) * 0.30 + (100 / 7) * 0.20 + 20 * 0.10
        self.assertAlmostEqual(resultado.indice_agregado, esperado)
        self.assertNotEqual(resultado.indice_agregado, round(esperado, 2))

    def test_indice_final_permanece_entre_zero_e_cem(self):
        for quantidade in (0, 1, 15, 90):
            with self.subTest(quantidade=quantidade):
                indice = resultado_com_dias_relevantes(quantidade).indice_agregado
                self.assertGreaterEqual(indice, 0)
                self.assertLessEqual(indice, 100)

    def test_classificacao_final_usa_politica(self):
        serie, politica = criar_serie_indices([75] * 90)
        resultado = agregar_indice_historico(serie, politica)
        self.assertEqual(
            resultado.classificacao_agregada,
            politica.classificar_indice(resultado.indice_agregado),
        )


class TestCobertura(unittest.TestCase):
    def test_cobertura_cem_por_cento(self):
        resultado = resultado_com_dias_relevantes(0)
        self.assertEqual(resultado.dias_disponiveis, 90)
        self.assertEqual(resultado.cobertura_percentual, 100)
        self.assertTrue(resultado.qualidade_suficiente)

    def test_cobertura_parcial(self):
        serie, politica = criar_serie_indices([0] * 45)
        resultado = agregar_indice_historico(serie, politica)
        self.assertEqual(resultado.dias_disponiveis, 45)
        self.assertEqual(resultado.cobertura_percentual, 50)

    def test_abaixo_de_80_marca_qualidade_insuficiente(self):
        serie, politica = criar_serie_indices([0] * 71)
        resultado = agregar_indice_historico(serie, politica)
        self.assertLess(resultado.cobertura_percentual, 80)
        self.assertFalse(resultado.qualidade_suficiente)

    def test_oitenta_por_cento_e_suficiente(self):
        serie, politica = criar_serie_indices([0] * 72)
        self.assertTrue(agregar_indice_historico(serie, politica).qualidade_suficiente)

    def test_cobertura_nao_reduz_indice(self):
        completa, politica = criar_serie_indices([75] + [0] * 89)
        parcial, _ = criar_serie_indices([75] + [0] * 44)
        resultado_completo = agregar_indice_historico(completa, politica)
        resultado_parcial = agregar_indice_historico(parcial, politica)
        self.assertEqual(
            resultado_completo.indice_agregado, resultado_parcial.indice_agregado
        )
        self.assertNotEqual(
            resultado_completo.qualidade_suficiente,
            resultado_parcial.qualidade_suficiente,
        )

    def test_ausencia_total_nao_vira_normal(self):
        serie, politica = criar_serie_indices([])
        resultado = agregar_indice_historico(serie, politica)
        self.assertEqual(resultado.dias_disponiveis, 0)
        self.assertIsNone(resultado.indice_agregado)
        self.assertIsNone(resultado.classificacao_agregada)

    def test_gap_nao_e_relevante_e_separa_eventos(self):
        serie, politica = criar_serie_indices([50, None, 50])
        resultado = agregar_indice_historico(serie, politica)
        self.assertEqual(resultado.quantidade_dias_relevantes, 2)
        self.assertEqual(resultado.quantidade_eventos, 2)


class TestRobustezEIsolamento(unittest.TestCase):
    def test_entrada_fora_de_ordem_e_ordenada_pelo_calendario(self):
        serie, _ = criar_serie_indices([0, 25, 50], fora_de_ordem=True)
        self.assertEqual(
            [item.indice for item in serie.indices[:3]],
            [0, 25, 50],
        )

    def test_datas_duplicadas_rejeitadas(self):
        politica = criar_politica_agrishield_equip_v1()
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        duplicados = [
            ValorIndiceDiario(data=janela.inicio, indice=0),
            ValorIndiceDiario(data=janela.inicio, indice=25),
        ]
        with self.assertRaises(ValueError):
            criar_indices_diarios(janela, duplicados, politica)

    def test_janela_deve_corresponder_a_politica(self):
        politica = criar_politica_agrishield_equip_v1()
        with self.assertRaises(ValueError):
            criar_indices_diarios(
                JanelaHistorica.criar_atual(DATA_REFERENCIA, 30),
                [],
                politica,
            )

    def test_classificacao_manual_incoerente_e_rejeitada(self):
        serie, politica = criar_serie_indices([25])
        incoerente = IndiceDiarioPerigo(
            data=serie.periodo.inicio,
            indice=25,
            classificacao=ClassificacaoIndice.NORMAL,
            disponibilidade=EstadoDisponibilidade.DISPONIVEL,
        )
        serie_incoerente = serie.model_copy(
            update={"indices": (incoerente, *serie.indices[1:])}
        )
        with self.assertRaises(ValueError):
            agregar_indice_historico(serie_incoerente, politica)

    def test_funcoes_nao_mutam_entrada(self):
        politica = criar_politica_agrishield_equip_v1()
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        valores = [ValorIndiceDiario(data=janela.inicio, indice=25)]
        antes = list(valores)
        serie = criar_indices_diarios(janela, valores, politica)
        agregar_indice_historico(serie, politica)
        self.assertEqual(valores, antes)

    def test_mesma_entrada_produz_mesmo_resultado(self):
        serie, politica = criar_serie_indices([25, 0, 50, None, 75])
        self.assertEqual(
            agregar_indice_historico(serie, politica),
            agregar_indice_historico(serie, politica),
        )

    def test_resultados_sao_imutaveis(self):
        serie, politica = criar_serie_indices([25, 0])
        resultado = agregar_indice_historico(serie, politica)
        with self.assertRaises(ValidationError):
            resultado.indice_agregado = 100
        with self.assertRaises(ValidationError):
            resultado.eventos[0].duracao_dias = 99

    def test_sem_dependencias_proibidas_ou_perigos_especificos(self):
        from backend.exposicao import agregacao_perigos

        codigo = inspect.getsource(agregacao_perigos).lower()
        for termo in (
            "precipitacao",
            "temperatura",
            "umidade",
            "vento",
            "exposicao_hidrica",
            "trafegabilidade",
            "instabilidade",
            "incendio",
            "tempestades",
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
        ):
            with self.subTest(termo=termo):
                if termo == "vento":
                    self.assertIsNone(re.search(r"\bvento\b", codigo))
                else:
                    self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
