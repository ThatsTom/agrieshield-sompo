from __future__ import annotations

import inspect
import json
import math
import unittest
from datetime import date

from pydantic import ValidationError

from backend.exposicao import (
    DISCLAIMER_SCORE_EXPOSICAO,
    METODOLOGIA_SCORE_EXPOSICAO,
    ContribuicaoPerigoScore,
    JanelaHistorica,
    MotivoIndisponibilidadeScore,
    PerigoExposicao,
    PoliticaComposicaoScore,
    ResultadoScoreExposicaoMaquinario,
    ResultadoValidacaoIntegradaPerigos,
    TipoNaoContribuicaoScore,
    calcular_score_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
)
from backend.tests.test_exposicao_validacao_integrada import executar


VALORES_EXEMPLO = {
    PerigoExposicao.EXPOSICAO_HIDRICA: 75.0,
    PerigoExposicao.TRAFEGABILIDADE: 58.0,
    PerigoExposicao.INSTABILIDADE: 88.0,
    PerigoExposicao.INCENDIO: 32.0,
    PerigoExposicao.TEMPESTADES: 52.0,
}

CAMPO_RESULTADO = {
    PerigoExposicao.EXPOSICAO_HIDRICA: "exposicao_hidrica",
    PerigoExposicao.TRAFEGABILIDADE: "trafegabilidade",
    PerigoExposicao.INSTABILIDADE: "instabilidade",
    PerigoExposicao.INCENDIO: "propagacao_fogo",
    PerigoExposicao.TEMPESTADES: "tempestade",
}


def _com_indices(
    validacao: ResultadoValidacaoIntegradaPerigos,
    valores: dict[PerigoExposicao, float],
) -> ResultadoValidacaoIntegradaPerigos:
    politica = criar_politica_agrishield_equip_v1()
    alteracoes = {}
    for perigo, campo in CAMPO_RESULTADO.items():
        resultado = getattr(validacao, campo)
        valor = valores[perigo]
        agregado = resultado.agregacao_90d.model_copy(
            update={
                "indice_agregado": valor,
                "classificacao_agregada": politica.classificar_indice(valor),
            }
        )
        alteracoes[campo] = resultado.model_copy(update={"agregacao_90d": agregado})
    return ResultadoValidacaoIntegradaPerigos.model_validate(
        validacao.model_copy(update=alteracoes).model_dump()
    )


def _com_perigo_insuficiente(
    validacao: ResultadoValidacaoIntegradaPerigos,
    perigo: PerigoExposicao,
    *,
    indice_ausente: bool = False,
) -> ResultadoValidacaoIntegradaPerigos:
    campo = CAMPO_RESULTADO[perigo]
    resultado = getattr(validacao, campo)
    dias = 0 if indice_ausente else 70
    cobertura = 100.0 * dias / resultado.agregacao_90d.dias_esperados
    agregado = resultado.agregacao_90d.model_copy(
        update={
            "dias_disponiveis": dias,
            "cobertura_percentual": cobertura,
            "qualidade_suficiente": False,
            "indice_agregado": (
                None if indice_ausente else resultado.agregacao_90d.indice_agregado
            ),
            "classificacao_agregada": (
                None
                if indice_ausente
                else resultado.agregacao_90d.classificacao_agregada
            ),
        }
    )
    resultado = resultado.model_copy(update={"agregacao_90d": agregado})
    coberturas = tuple(
        (
            item.model_copy(
                update={
                    "dias_disponiveis": dias,
                    "cobertura_percentual": cobertura,
                    "qualidade_suficiente": False,
                }
            )
            if item.perigo == perigo
            else item
        )
        for item in validacao.coberturas
    )
    return ResultadoValidacaoIntegradaPerigos.model_validate(
        validacao.model_copy(
            update={campo: resultado, "coberturas": coberturas}
        ).model_dump()
    )


class BaseScoreExposicao(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.composicao = criar_politica_composicao_score(self.politica)
        self.validacao = _com_indices(executar("seco_calmo"), VALORES_EXEMPLO)

    def calcular(self, validacao=None, composicao=None, politica=None):
        return calcular_score_exposicao_maquinario(
            validacao or self.validacao,
            composicao or self.composicao,
            politica or self.politica,
        )


class TestContribuicoesScore(BaseScoreExposicao):
    def test_participacao_e_pesos_sao_lidos_da_politica(self):
        resultado = self.calcular()
        esperados = {
            PerigoExposicao.EXPOSICAO_HIDRICA: (True, 0.30),
            PerigoExposicao.TRAFEGABILIDADE: (True, 0.25),
            PerigoExposicao.INSTABILIDADE: (True, 0.20),
            PerigoExposicao.INCENDIO: (True, 0.15),
            PerigoExposicao.TEMPESTADES: (True, 0.10),
        }
        for perigo, esperado in esperados.items():
            with self.subTest(perigo=perigo):
                item = resultado.contribuicao_de(perigo)
                self.assertEqual((item.participa_score, item.peso), esperado)

    def test_contribuicoes_participantes_sao_matematicamente_corretas(self):
        resultado = self.calcular()
        for perigo in PerigoExposicao:
            with self.subTest(perigo=perigo):
                item = resultado.contribuicao_de(perigo)
                self.assertEqual(
                    item.contribuicao,
                    VALORES_EXEMPLO[perigo] * item.peso,
                )

    def test_trafegabilidade_participa_normalmente_do_score(self):
        item = self.calcular().contribuicao_de(PerigoExposicao.TRAFEGABILIDADE)
        self.assertEqual(item.indice_perigo, 58)
        self.assertTrue(item.participa_score)
        self.assertTrue(item.elegivel)
        self.assertEqual(item.peso, 0.25)
        self.assertEqual(item.contribuicao, 58 * 0.25)
        self.assertIsNone(item.tipo_nao_contribuicao)

    def test_indice_de_trafegabilidade_altera_o_score(self):
        primeiro = self.calcular()
        valores = dict(VALORES_EXEMPLO)
        valores[PerigoExposicao.TRAFEGABILIDADE] = 100
        segundo = self.calcular(_com_indices(self.validacao, valores))
        self.assertNotEqual(primeiro.score, segundo.score)
        self.assertEqual(segundo.score - primeiro.score, (100 - 58) * 0.25)

    def test_exemplo_explicavel(self):
        resultado = self.calcular()
        esperado = math.fsum(
            (
                75 * 0.30,
                58 * 0.25,
                88 * 0.20,
                32 * 0.15,
                52 * 0.10,
            )
        )
        self.assertEqual(resultado.score, esperado)
        self.assertEqual(
            resultado.score,
            math.fsum(
                item.contribuicao
                for item in resultado.contribuicoes
                if item.participa_score
            ),
        )


class TestCalculoScore(BaseScoreExposicao):
    def test_score_e_soma_das_cinco_contribuicoes_sem_arredondamento(self):
        resultado = self.calcular()
        esperada = math.fsum(
            VALORES_EXEMPLO[item.perigo] * item.peso
            for item in resultado.contribuicoes
            if item.participa_score
        )
        self.assertEqual(resultado.score, esperada)
        contribuicao_instabilidade = resultado.contribuicao_de(
            PerigoExposicao.INSTABILIDADE
        ).contribuicao
        self.assertEqual(contribuicao_instabilidade, 88 * 0.20)

    def test_score_permanece_no_dominio_e_classificacao_vem_da_politica(self):
        resultado = self.calcular()
        self.assertGreaterEqual(resultado.score, 0)
        self.assertLessEqual(resultado.score, 100)
        self.assertEqual(
            resultado.classificacao,
            self.politica.classificar_indice(resultado.score),
        )
        from backend.exposicao import score_exposicao

        codigo = inspect.getsource(score_exposicao)
        self.assertIn("politica.classificar_indice(score)", codigo)
        self.assertNotIn("inicio_atencao", codigo)

    def test_todos_zero_produzem_zero(self):
        valores = {perigo: 0.0 for perigo in PerigoExposicao}
        resultado = self.calcular(_com_indices(self.validacao, valores))
        self.assertEqual(resultado.score, 0)
        self.assertEqual(resultado.classificacao, self.politica.classificar_indice(0))

    def test_todos_cem_produzem_cem(self):
        valores = {perigo: 100.0 for perigo in PerigoExposicao}
        resultado = self.calcular(_com_indices(self.validacao, valores))
        self.assertTrue(math.isclose(resultado.score, 100, abs_tol=1e-12))
        self.assertEqual(resultado.classificacao, self.politica.classificar_indice(100))

    def test_determinismo_e_inputs_nao_mutados(self):
        antes = (
            self.validacao.model_dump(),
            self.composicao.model_dump(),
            self.politica.model_dump(),
        )
        primeiro = self.calcular()
        segundo = self.calcular()
        self.assertEqual(primeiro, segundo)
        self.assertEqual(
            antes,
            (
                self.validacao.model_dump(),
                self.composicao.model_dump(),
                self.politica.model_dump(),
            ),
        )


class TestQualidadeScore(BaseScoreExposicao):
    def test_todos_participantes_elegiveis_produzem_score_publicavel(self):
        resultado = self.calcular()
        self.assertTrue(resultado.qualidade_suficiente)
        self.assertTrue(resultado.score_publicavel)
        self.assertIsNotNone(resultado.score)
        self.assertEqual(resultado.perigos_indisponiveis, ())

    def test_cada_participante_insuficiente_bloqueia_score(self):
        for perigo in PerigoExposicao:
            with self.subTest(perigo=perigo):
                resultado = self.calcular(
                    _com_perigo_insuficiente(self.validacao, perigo)
                )
                item = resultado.contribuicao_de(perigo)
                self.assertIsNone(resultado.score)
                self.assertIsNone(resultado.classificacao)
                self.assertFalse(resultado.qualidade_suficiente)
                self.assertFalse(resultado.score_publicavel)
                self.assertEqual(resultado.perigos_indisponiveis, (perigo,))
                self.assertIsNone(item.contribuicao)
                self.assertEqual(
                    item.tipo_nao_contribuicao,
                    TipoNaoContribuicaoScore.DADO_INSUFICIENTE,
                )
                self.assertIn(
                    MotivoIndisponibilidadeScore.QUALIDADE_INSUFICIENTE,
                    item.motivos_indisponibilidade,
                )

    def test_ausencia_nao_redistribui_pesos_e_score_parcial_nao_e_publicado(self):
        resultado = self.calcular(
            _com_perigo_insuficiente(
                self.validacao,
                PerigoExposicao.INSTABILIDADE,
            )
        )
        self.assertEqual(
            tuple(item.peso for item in resultado.contribuicoes),
            tuple(item.peso for item in self.composicao.configuracoes),
        )
        self.assertEqual(resultado.soma_pesos, 1)
        self.assertIsNone(resultado.score)
        self.assertFalse(resultado.score_publicavel)

    def test_indice_ausente_em_participante_bloqueia_score_e_preserva_motivos(self):
        resultado = self.calcular(
            _com_perigo_insuficiente(
                self.validacao,
                PerigoExposicao.INCENDIO,
                indice_ausente=True,
            )
        )
        item = resultado.contribuicao_de(PerigoExposicao.INCENDIO)
        self.assertIsNone(resultado.score)
        self.assertIsNone(item.indice_perigo)
        self.assertIn(
            MotivoIndisponibilidadeScore.INDICE_AGREGADO_AUSENTE,
            item.motivos_indisponibilidade,
        )
        self.assertIn(
            MotivoIndisponibilidadeScore.CLASSIFICACAO_AGREGADA_AUSENTE,
            item.motivos_indisponibilidade,
        )


class TestCompatibilidadeScore(BaseScoreExposicao):
    def test_politica_id_divergente_e_rejeitada(self):
        divergente = self.composicao.model_copy(update={"politica_id": "outra"})
        with self.assertRaisesRegex(ValueError, "diverge"):
            self.calcular(composicao=divergente)

    def test_janela_divergente_e_rejeitada(self):
        janela = JanelaHistorica.criar_atual(date(2026, 8, 10), 90)
        divergente = self.validacao.model_copy(update={"janela": janela})
        with self.assertRaises((ValueError, ValidationError)):
            self.calcular(validacao=divergente)

    def test_peso_divergente_da_politica_e_rejeitado(self):
        dados = self.composicao.model_dump()
        dados["configuracoes"][0]["peso"] += 0.01
        dados["configuracoes"][2]["peso"] -= 0.01
        dados["soma_pesos"] = math.fsum(item["peso"] for item in dados["configuracoes"])
        divergente = PoliticaComposicaoScore.model_validate(dados)
        with self.assertRaisesRegex(ValueError, "peso diverge"):
            self.calcular(composicao=divergente)

    def test_soma_de_pesos_e_unitaria(self):
        resultado = self.calcular()
        self.assertTrue(math.isclose(resultado.soma_pesos, 1, abs_tol=1e-12))

    def test_limiar_de_cobertura_divergente_da_politica_e_rejeitado(self):
        resultado = self.validacao.propagacao_fogo
        agregado = resultado.agregacao_90d.model_copy(
            update={"cobertura_minima_percentual": 70.0}
        )
        divergente = self.validacao.model_copy(
            update={
                "propagacao_fogo": resultado.model_copy(
                    update={"agregacao_90d": agregado}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "cobertura minima"):
            self.calcular(validacao=divergente)

    def test_classificacao_individual_divergente_da_politica_e_rejeitada(self):
        resultado = self.validacao.propagacao_fogo
        agregado = resultado.agregacao_90d.model_copy(
            update={"classificacao_agregada": self.politica.classificar_indice(100)}
        )
        divergente = self.validacao.model_copy(
            update={
                "propagacao_fogo": resultado.model_copy(
                    update={"agregacao_90d": agregado}
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "classificacao do perigo"):
            self.calcular(validacao=divergente)


class TestContratoScore(BaseScoreExposicao):
    def test_cinco_contribuicoes_listas_e_pesos_preservados(self):
        resultado = self.calcular()
        self.assertEqual(
            tuple(item.perigo for item in resultado.contribuicoes),
            tuple(PerigoExposicao),
        )
        self.assertEqual(resultado.perigos_participantes, tuple(PerigoExposicao))
        self.assertEqual(resultado.perigos_excluidos, ())
        self.assertEqual(
            tuple(item.peso for item in resultado.contribuicoes),
            tuple(item.peso for item in self.composicao.configuracoes),
        )

    def test_metodologia_disclaimer_e_politica_sao_explicitos(self):
        resultado = self.calcular()
        self.assertEqual(resultado.metodologia, METODOLOGIA_SCORE_EXPOSICAO)
        self.assertEqual(resultado.disclaimer, DISCLAIMER_SCORE_EXPOSICAO)
        self.assertIn("Nao representa probabilidade atuarial", resultado.disclaimer)
        self.assertIn("Sompo", resultado.disclaimer)
        self.assertEqual(resultado.politica_id, self.politica.id_politica)
        self.assertEqual(resultado.politica_versao, self.politica.versao)

    def test_contratos_sao_imutaveis(self):
        resultado = self.calcular()
        with self.assertRaises(ValidationError):
            resultado.score = 10
        with self.assertRaises(ValidationError):
            resultado.contribuicoes[0].contribuicao = 10

    def test_serializacao_json_e_estrutura_coerente(self):
        resultado = self.calcular()
        serializado = resultado.model_dump(mode="json")
        json.dumps(serializado)
        reconstruido = ResultadoScoreExposicaoMaquinario.model_validate(serializado)
        self.assertEqual(reconstruido, resultado)

    def test_modelos_rejeitam_contribuicao_incoerente(self):
        item = self.calcular().contribuicao_de(PerigoExposicao.EXPOSICAO_HIDRICA)
        dados = item.model_dump()
        dados["contribuicao"] += 1
        with self.assertRaisesRegex(ValidationError, "contribuicao diverge"):
            ContribuicaoPerigoScore.model_validate(dados)

    def test_dto_nao_expoe_mais_peso_nominal_ou_efetivo(self):
        item = self.calcular().contribuicao_de(PerigoExposicao.EXPOSICAO_HIDRICA)
        campos = set(item.model_fields)
        self.assertIn("peso", campos)
        self.assertTrue(campos.isdisjoint({"peso_nominal", "peso_efetivo"}))
        campos_resultado = set(ResultadoScoreExposicaoMaquinario.model_fields)
        self.assertIn("soma_pesos", campos_resultado)
        self.assertTrue(
            campos_resultado.isdisjoint({"soma_pesos_nominais", "soma_pesos_efetivos"})
        )


if __name__ == "__main__":
    unittest.main()
