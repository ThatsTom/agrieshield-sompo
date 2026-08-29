from __future__ import annotations

import inspect
import json
import math
import unittest
from datetime import timedelta

from pydantic import ValidationError

from backend.exposicao import (
    DISCLAIMER_COMPARACAO_SCORE,
    METODOLOGIA_COMPARACAO_SCORE,
    DirecaoVariacaoScore,
    FinalidadeJanela,
    JanelaHistorica,
    MotivoIndisponibilidadeScore,
    MotivoIndisponibilidadeComparacao,
    MotivoPercentualIndisponivel,
    PerigoExposicao,
    PesosPerigos,
    ResultadoComparacaoScoreExposicao90d,
    calcular_score_exposicao_maquinario,
    comparar_scores_exposicao_90d,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
    validar_cinco_perigos,
)
from backend.tests.test_exposicao_score_exposicao import (
    _com_indices,
    _com_perigo_insuficiente,
)
from backend.tests.test_exposicao_validacao_integrada import (
    criar_features,
    criar_geo,
)


def _valores(valor: float) -> dict[PerigoExposicao, float]:
    return {perigo: valor for perigo in PerigoExposicao}


class BaseComparacaoScore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.politica = criar_politica_agrishield_equip_v1()
        cls.composicao = criar_politica_composicao_score(cls.politica)
        features = criar_features("seco_calmo", dias=180)
        cls.janela_anterior, cls.janela_atual = (
            features.periodo.dividir_em_periodos_90()
        )
        geo = criar_geo(0)
        cls.validacao_anterior = validar_cinco_perigos(
            features,
            geo,
            cls.politica,
            janela_alvo=cls.janela_anterior,
        )
        cls.validacao_atual = validar_cinco_perigos(
            features,
            geo,
            cls.politica,
            janela_alvo=cls.janela_atual,
        )

    def criar_score(self, *, anterior: bool, valor: float, insuficiente=None):
        validacao = self.validacao_anterior if anterior else self.validacao_atual
        validacao = _com_indices(validacao, _valores(valor))
        if insuficiente is not None:
            validacao = _com_perigo_insuficiente(validacao, insuficiente)
        return calcular_score_exposicao_maquinario(
            validacao,
            self.composicao,
            self.politica,
        )

    def comparar(self, anterior=55.0, atual=65.0):
        return comparar_scores_exposicao_90d(
            self.criar_score(anterior=True, valor=anterior),
            self.criar_score(anterior=False, valor=atual),
        )

    def janela_anterior_customizada(self, fim, dias=90):
        return JanelaHistorica(
            data_referencia=self.janela_atual.data_referencia,
            inicio=fim - timedelta(days=dias - 1),
            fim=fim,
            dias_esperados=dias,
            finalidade=FinalidadeJanela.COMPARACAO_ANTERIOR,
        )


class TestJanelasECompatibilidade(BaseComparacaoScore):
    def test_duas_janelas_de_90_dias_consecutivas_e_sem_sobreposicao(self):
        resultado = self.comparar()
        self.assertEqual(resultado.janela_anterior.dias_esperados, 90)
        self.assertEqual(resultado.janela_atual.dias_esperados, 90)
        self.assertEqual(
            resultado.janela_anterior.fim + timedelta(days=1),
            resultado.janela_atual.inicio,
        )
        self.assertLess(
            resultado.janela_anterior.fim,
            resultado.janela_atual.inicio,
        )

    def test_politica_metodologia_e_composicao_iguais_sao_aceitas(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(anterior=False, valor=65)
        resultado = comparar_scores_exposicao_90d(anterior, atual)
        self.assertEqual(resultado.politica_id, anterior.politica_id)
        self.assertEqual(resultado.politica_versao, anterior.politica_versao)
        self.assertEqual(resultado.metodologia_score, anterior.metodologia)
        self.assertEqual(anterior.soma_pesos, atual.soma_pesos)

    def test_politica_id_diferente_e_rejeitado(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(anterior=False, valor=65).model_copy(
            update={"politica_id": "outra-politica"}
        )
        with self.assertRaisesRegex(ValueError, "politica_id"):
            comparar_scores_exposicao_90d(anterior, atual)

    def test_metodologia_incompativel_e_rejeitada(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(anterior=False, valor=65).model_copy(
            update={"metodologia": "OUTRA_METODOLOGIA"}
        )
        with self.assertRaisesRegex(ValueError, "metodologia"):
            comparar_scores_exposicao_90d(anterior, atual)

    def test_composicao_incompativel_e_rejeitada(self):
        anterior = self.criar_score(anterior=True, valor=55)
        politica_alternativa = self.politica.model_copy(
            update={
                "pesos_perigos": PesosPerigos(
                    exposicao_hidrica=0.50,
                    trafegabilidade=0.20,
                    instabilidade=0.15,
                    incendio=0.10,
                    tempestades=0.05,
                )
            }
        )
        composicao_alternativa = criar_politica_composicao_score(politica_alternativa)
        validacao_atual = _com_indices(self.validacao_atual, _valores(65.0))
        atual = calcular_score_exposicao_maquinario(
            validacao_atual, composicao_alternativa, politica_alternativa
        )
        with self.assertRaisesRegex(ValueError, "composicao"):
            comparar_scores_exposicao_90d(anterior, atual)

    def test_fazendas_diferentes_sao_rejeitadas(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(anterior=False, valor=65).model_copy(
            update={"id_fazenda": "outra-fazenda"}
        )
        with self.assertRaisesRegex(ValueError, "mesma fazenda"):
            comparar_scores_exposicao_90d(anterior, atual)

    def test_janela_com_duracao_diferente_e_rejeitada(self):
        anterior = self.criar_score(anterior=True, valor=55)
        fim = self.janela_atual.inicio - timedelta(days=1)
        anterior = anterior.model_copy(
            update={"janela": self.janela_anterior_customizada(fim, dias=89)}
        )
        with self.assertRaisesRegex(ValueError, "90 dias"):
            comparar_scores_exposicao_90d(
                anterior,
                self.criar_score(anterior=False, valor=65),
            )

    def test_janelas_sobrepostas_sao_rejeitadas(self):
        anterior = self.criar_score(anterior=True, valor=55).model_copy(
            update={
                "janela": self.janela_anterior_customizada(self.janela_atual.inicio)
            }
        )
        with self.assertRaisesRegex(ValueError, "sobrepor"):
            comparar_scores_exposicao_90d(
                anterior,
                self.criar_score(anterior=False, valor=65),
            )

    def test_gap_entre_janelas_e_rejeitado(self):
        anterior = self.criar_score(anterior=True, valor=55).model_copy(
            update={
                "janela": self.janela_anterior_customizada(
                    self.janela_atual.inicio - timedelta(days=2)
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "gap"):
            comparar_scores_exposicao_90d(
                anterior,
                self.criar_score(anterior=False, valor=65),
            )

    def test_ordem_invertida_e_rejeitada(self):
        anterior = self.criar_score(anterior=True, valor=55).model_copy(
            update={"janela": self.janela_anterior_customizada(self.janela_atual.fim)}
        )
        with self.assertRaisesRegex(ValueError, "preceder"):
            comparar_scores_exposicao_90d(
                anterior,
                self.criar_score(anterior=False, valor=65),
            )


class TestVariacaoScore(BaseComparacaoScore):
    def test_55_para_65_e_aumento_de_dez_pontos(self):
        resultado = self.comparar(55, 65)
        self.assertTrue(math.isclose(resultado.variacao_pontos, 10, abs_tol=1e-12))
        self.assertEqual(resultado.direcao, DirecaoVariacaoScore.AUMENTO)
        self.assertTrue(
            math.isclose(
                resultado.variacao_percentual,
                10 / 55 * 100,
                abs_tol=1e-12,
            )
        )

    def test_60_para_45_e_reducao_de_quinze_pontos(self):
        resultado = self.comparar(60, 45)
        self.assertTrue(math.isclose(resultado.variacao_pontos, -15, abs_tol=1e-12))
        self.assertEqual(resultado.direcao, DirecaoVariacaoScore.REDUCAO)
        self.assertTrue(
            math.isclose(
                resultado.variacao_percentual,
                -15 / 60 * 100,
                abs_tol=1e-12,
            )
        )

    def test_scores_iguais_sao_estaveis(self):
        resultado = self.comparar(55, 55)
        self.assertEqual(resultado.variacao_pontos, 0)
        self.assertEqual(resultado.variacao_percentual, 0)
        self.assertEqual(resultado.direcao, DirecaoVariacaoScore.ESTAVEL)

    def test_zero_para_zero_tem_percentual_zero(self):
        resultado = self.comparar(0, 0)
        self.assertEqual(resultado.variacao_pontos, 0)
        self.assertEqual(resultado.variacao_percentual, 0)
        self.assertEqual(resultado.direcao, DirecaoVariacaoScore.ESTAVEL)
        self.assertIsNone(resultado.motivo_percentual_indisponivel)

    def test_zero_para_positivo_nao_inventa_percentual(self):
        resultado = self.comparar(0, 25)
        self.assertEqual(resultado.variacao_pontos, 25)
        self.assertIsNone(resultado.variacao_percentual)
        self.assertEqual(
            resultado.motivo_percentual_indisponivel,
            MotivoPercentualIndisponivel.BASE_ANTERIOR_ZERO,
        )
        self.assertFalse(
            isinstance(resultado.variacao_percentual, float)
            and math.isinf(resultado.variacao_percentual)
        )

    def test_classificacoes_sao_preservadas_e_mudanca_detectada(self):
        anterior = self.criar_score(anterior=True, valor=20)
        atual = self.criar_score(anterior=False, valor=60)
        resultado = comparar_scores_exposicao_90d(anterior, atual)
        self.assertEqual(resultado.classificacao_anterior, anterior.classificacao)
        self.assertEqual(resultado.classificacao_atual, atual.classificacao)
        self.assertTrue(resultado.classificacao_mudou)

    def test_classificacao_igual_nao_mudou(self):
        resultado = self.comparar(55, 60)
        self.assertFalse(resultado.classificacao_mudou)


class TestPublicabilidadeComparacao(BaseComparacaoScore):
    def test_anterior_nao_publicavel_bloqueia_comparacao(self):
        anterior = self.criar_score(
            anterior=True,
            valor=55,
            insuficiente=PerigoExposicao.INCENDIO,
        )
        atual = self.criar_score(anterior=False, valor=65)
        resultado = comparar_scores_exposicao_90d(anterior, atual)
        self.assertFalse(resultado.comparacao_publicavel)
        self.assertIsNone(resultado.variacao_pontos)
        self.assertIsNone(resultado.variacao_percentual)
        self.assertIsNone(resultado.direcao)
        self.assertEqual(
            resultado.motivo_indisponibilidade,
            MotivoIndisponibilidadeComparacao.SCORE_ANTERIOR_NAO_PUBLICAVEL,
        )
        self.assertEqual(
            resultado.perigos_indisponiveis_anterior,
            (PerigoExposicao.INCENDIO,),
        )
        self.assertIn(
            MotivoIndisponibilidadeScore.QUALIDADE_INSUFICIENTE,
            resultado.detalhes_indisponibilidade_anterior[0].motivos,
        )

    def test_atual_nao_publicavel_bloqueia_comparacao(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(
            anterior=False,
            valor=65,
            insuficiente=PerigoExposicao.TEMPESTADES,
        )
        resultado = comparar_scores_exposicao_90d(anterior, atual)
        self.assertFalse(resultado.comparacao_publicavel)
        self.assertIsNone(resultado.variacao_pontos)
        self.assertIsNone(resultado.classificacao_mudou)
        self.assertEqual(
            resultado.motivo_indisponibilidade,
            MotivoIndisponibilidadeComparacao.SCORE_ATUAL_NAO_PUBLICAVEL,
        )
        self.assertEqual(
            resultado.motivo_percentual_indisponivel,
            MotivoPercentualIndisponivel.COMPARACAO_NAO_PUBLICAVEL,
        )

    def test_ambos_nao_publicaveis_preservam_os_dois_estados(self):
        anterior = self.criar_score(
            anterior=True,
            valor=55,
            insuficiente=PerigoExposicao.INSTABILIDADE,
        )
        atual = self.criar_score(
            anterior=False,
            valor=65,
            insuficiente=PerigoExposicao.EXPOSICAO_HIDRICA,
        )
        resultado = comparar_scores_exposicao_90d(anterior, atual)
        self.assertEqual(
            resultado.motivo_indisponibilidade,
            MotivoIndisponibilidadeComparacao.AMBOS_SCORES_NAO_PUBLICAVEIS,
        )
        self.assertEqual(
            resultado.perigos_indisponiveis_anterior,
            (PerigoExposicao.INSTABILIDADE,),
        )
        self.assertEqual(
            resultado.perigos_indisponiveis_atual,
            (PerigoExposicao.EXPOSICAO_HIDRICA,),
        )


class TestContratoComparacao(BaseComparacaoScore):
    def test_metodologia_disclaimer_e_semantica_sao_explicitos(self):
        resultado = self.comparar()
        self.assertEqual(resultado.metodologia, METODOLOGIA_COMPARACAO_SCORE)
        self.assertEqual(resultado.disclaimer, DISCLAIMER_COMPARACAO_SCORE)
        self.assertIn("Score de Exposicao", resultado.disclaimer)
        self.assertIn("Nao representa", resultado.disclaimer)
        self.assertNotIn("risco aumentou", resultado.disclaimer.lower())

    def test_determinismo_inputs_nao_mutados_e_imutabilidade(self):
        anterior = self.criar_score(anterior=True, valor=55)
        atual = self.criar_score(anterior=False, valor=65)
        antes = (anterior.model_dump(), atual.model_dump())
        primeiro = comparar_scores_exposicao_90d(anterior, atual)
        segundo = comparar_scores_exposicao_90d(anterior, atual)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(antes, (anterior.model_dump(), atual.model_dump()))
        with self.assertRaises(ValidationError):
            primeiro.variacao_pontos = 99

    def test_serializacao_e_estrutura_coerentes(self):
        resultado = self.comparar()
        serializado = resultado.model_dump(mode="json")
        json.dumps(serializado)
        self.assertEqual(
            ResultadoComparacaoScoreExposicao90d.model_validate(serializado),
            resultado,
        )

    def test_nao_recalcula_perigo_score_classificacao_ou_threshold(self):
        from backend.exposicao import comparacao_score

        codigo = inspect.getsource(comparacao_score)
        for termo in (
            "calcular_score_exposicao_maquinario",
            "validar_cinco_perigos",
            "calcular_exposicao_hidrica",
            "classificar_indice",
            "inicio_atencao",
            "inicio_alerta",
            "inicio_critico",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
