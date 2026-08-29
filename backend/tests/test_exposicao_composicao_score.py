from __future__ import annotations

import inspect
import math
import unittest

from pydantic import ValidationError

from backend.exposicao import (
    DESCRICAO_COMPOSICAO_SCORE,
    METODOLOGIA_COMPOSICAO_SCORE,
    ConfiguracaoComposicaoPerigo,
    PerigoExposicao,
    PoliticaComposicaoScore,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
)


class TestPoliticaComposicaoV1(unittest.TestCase):
    def setUp(self):
        self.politica_origem = criar_politica_agrishield_equip_v1()
        self.composicao = criar_politica_composicao_score(self.politica_origem)
        self.por_perigo = {
            configuracao.perigo: configuracao
            for configuracao in self.composicao.configuracoes
        }

    def test_contem_exatamente_os_cinco_perigos(self):
        self.assertEqual(
            tuple(
                configuracao.perigo for configuracao in self.composicao.configuracoes
            ),
            tuple(PerigoExposicao),
        )

    def test_pesos_30_25_20_15_10_sao_lidos_da_politica(self):
        esperados = {
            PerigoExposicao.EXPOSICAO_HIDRICA: 0.30,
            PerigoExposicao.TRAFEGABILIDADE: 0.25,
            PerigoExposicao.INSTABILIDADE: 0.20,
            PerigoExposicao.INCENDIO: 0.15,
            PerigoExposicao.TEMPESTADES: 0.10,
        }
        self.assertEqual(
            {perigo: item.peso for perigo, item in self.por_perigo.items()},
            esperados,
        )
        self.assertTrue(math.isclose(self.composicao.soma_pesos, 1.0))

    def test_todos_os_cinco_perigos_participam_do_score(self):
        participantes = {
            perigo
            for perigo, configuracao in self.por_perigo.items()
            if configuracao.participa_score
        }
        self.assertEqual(participantes, set(PerigoExposicao))
        self.assertTrue(
            self.por_perigo[PerigoExposicao.TRAFEGABILIDADE].participa_score
        )
        self.assertEqual(self.por_perigo[PerigoExposicao.TRAFEGABILIDADE].peso, 0.25)

    def test_nao_ha_renormalizacao_o_peso_e_usado_diretamente(self):
        self.assertEqual(self.por_perigo[PerigoExposicao.EXPOSICAO_HIDRICA].peso, 0.30)
        self.assertEqual(self.por_perigo[PerigoExposicao.INSTABILIDADE].peso, 0.20)
        self.assertEqual(self.por_perigo[PerigoExposicao.INCENDIO].peso, 0.15)
        self.assertEqual(self.por_perigo[PerigoExposicao.TEMPESTADES].peso, 0.10)
        self.assertTrue(
            math.isclose(
                self.composicao.soma_pesos,
                1.0,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        )

    def test_metodologia_e_descricao_sao_explicitas(self):
        self.assertEqual(self.composicao.metodologia, METODOLOGIA_COMPOSICAO_SCORE)
        self.assertEqual(self.composicao.descricao, DESCRICAO_COMPOSICAO_SCORE)
        self.assertIn("peso configuravel", self.composicao.descricao)

    def test_determinismo_imutabilidade_e_entrada_nao_mutada(self):
        antes = self.politica_origem.model_dump()
        repetida = criar_politica_composicao_score(self.politica_origem)
        self.assertEqual(self.composicao, repetida)
        self.assertEqual(self.politica_origem.model_dump(), antes)
        with self.assertRaises(ValidationError):
            self.composicao.soma_pesos = 0


class TestValidacoesComposicao(unittest.TestCase):
    def setUp(self):
        self.base = criar_politica_composicao_score(
            criar_politica_agrishield_equip_v1()
        )

    def test_peso_negativo_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            ConfiguracaoComposicaoPerigo(
                perigo=PerigoExposicao.EXPOSICAO_HIDRICA,
                peso=-0.1,
                participa_score=True,
            )

    def test_inativo_exige_peso_zero(self):
        with self.assertRaises(ValidationError):
            ConfiguracaoComposicaoPerigo(
                perigo=PerigoExposicao.TRAFEGABILIDADE,
                peso=0.25,
                participa_score=False,
            )

    def test_soma_invalida_e_rejeitada(self):
        dados = self.base.model_dump()
        dados["configuracoes"][0]["peso"] = 0.31
        with self.assertRaisesRegex(ValidationError, "soma dos pesos"):
            PoliticaComposicaoScore.model_validate(dados)

    def test_soma_declarada_divergente_e_rejeitada(self):
        dados = self.base.model_dump()
        dados["soma_pesos"] = 0.5
        with self.assertRaisesRegex(ValidationError, "soma de pesos declarada"):
            PoliticaComposicaoScore.model_validate(dados)

    def test_cinco_perigos_ausentes_duplicados_ou_fora_de_ordem_sao_rejeitados(self):
        dados = self.base.model_dump()
        dados["configuracoes"][0]["perigo"] = PerigoExposicao.TRAFEGABILIDADE
        with self.assertRaisesRegex(ValidationError, "cinco perigos"):
            PoliticaComposicaoScore.model_validate(dados)

    def test_id_vazio_e_rejeitado(self):
        dados = self.base.model_dump()
        dados["politica_id"] = ""
        with self.assertRaises(ValidationError):
            PoliticaComposicaoScore.model_validate(dados)

    def test_sem_nenhum_participante_e_rejeitado(self):
        dados = self.base.model_dump()
        for configuracao in dados["configuracoes"]:
            configuracao["participa_score"] = False
            configuracao["peso"] = 0
        dados["soma_pesos"] = 0
        with self.assertRaisesRegex(ValidationError, "ao menos um participante"):
            PoliticaComposicaoScore.model_validate(dados)

    def test_composicao_efetiva_da_factory_e_aceita(self):
        self.assertEqual(
            PoliticaComposicaoScore.model_validate(self.base.model_dump()),
            self.base,
        )


class TestSemDependenciaDaValidacaoIntegrada(unittest.TestCase):
    def test_composicao_nao_recebe_nem_conhece_a_validacao_integrada(self):
        assinatura = inspect.signature(criar_politica_composicao_score)
        self.assertEqual(list(assinatura.parameters), ["politica"])

        from backend.exposicao import composicao_score

        codigo = inspect.getsource(composicao_score).lower()
        for termo in (
            "validacao_integrada",
            "conflito",
            "requests",
            "fastapi",
            "supabase",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_nenhum_score_de_fazenda_e_calculado(self):
        campos = set(PoliticaComposicaoScore.model_fields)
        self.assertTrue(
            campos.isdisjoint(
                {
                    "score_final",
                    "indice_composto",
                    "contribuicoes",
                    "id_fazenda",
                    "resultado_fazenda",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
