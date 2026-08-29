from __future__ import annotations

import unittest

from backend.exposicao import (
    PerigoExposicao,
    calcular_exposicao_hidrica,
    calcular_score_exposicao_maquinario,
    criar_apresentacao_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
    validar_cinco_perigos,
)
from backend.exposicao.avaliacao_exposicao import (
    executar_avaliacao_exposicao_maquinario,
)
from backend.tests.test_exposicao_avaliacao_exposicao import criar_serie_avaliacao
from backend.tests.test_exposicao_validacao_integrada import criar_features, criar_geo


class TestExposicaoHidricaOficial(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.geo = criar_geo(8)

    def test_preserva_formula_e_parametros_promovidos(self):
        features = criar_features(
            "seco_calmo",
            alterar=lambda _indice, _data: {
                "chuva": 20.0,
                "d1_d3": 20.0,
                "d4_d7": 20.0,
            },
        )
        resultado = calcular_exposicao_hidrica(features, self.geo, self.politica)
        ultimo = resultado.detalhes_diarios[-1]
        esperado = min(
            100.0,
            ultimo.condicao_meteorologica_base
            + 0.30 * ultimo.ativacao_chuva_3d * ultimo.suscetibilidade_territorial,
        )
        self.assertAlmostEqual(ultimo.indice_exposicao_hidrica, esperado)
        self.assertEqual(resultado.parametros_territoriais.fator_incremento, 0.30)
        self.assertEqual(
            (
                resultado.parametros_territoriais.peso_proximidade_drenagem,
                resultado.parametros_territoriais.peso_area_montante,
                resultado.parametros_territoriais.peso_posicao_topografica,
            ),
            (0.40, 0.35, 0.25),
        )

    def test_missing_territorial_nunca_vira_zero_nem_fallback(self):
        posicao_ausente = self.geo.posicao_topografica_relativa_m.model_copy(
            update={"valor": None}
        )
        geo_sem_posicao = self.geo.model_copy(
            update={"posicao_topografica_relativa_m": posicao_ausente}
        )
        resultado = calcular_exposicao_hidrica(
            criar_features("chuva_persistente"),
            geo_sem_posicao,
            self.politica,
        )
        self.assertIsNone(resultado.suscetibilidade_territorial.indice)
        self.assertTrue(
            any(
                item.condicao_meteorologica_base is not None
                for item in resultado.detalhes_diarios
            )
        )
        self.assertTrue(
            all(
                item.indice_exposicao_hidrica is None
                for item in resultado.detalhes_diarios
            )
        )
        self.assertIsNone(resultado.agregacao_90d.indice_agregado)
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 0)

    def test_instabilidade_usa_somente_nucleo_meteorologico_e_trafegabilidade_e_independente(
        self,
    ):
        validacao = validar_cinco_perigos(
            criar_features(
                "seco_calmo",
                alterar=lambda _indice, _data: {
                    "chuva": 20.0,
                    "d1_d3": 20.0,
                    "d4_d7": 20.0,
                },
            ),
            self.geo,
            self.politica,
        )
        base = tuple(
            item.indice_hidrico_meteorologico
            for item in validacao.exposicao_hidrica.condicoes_hidricas_base
        )
        trafegabilidade = tuple(
            item.indice for item in validacao.trafegabilidade.indices_diarios.indices
        )
        ativacao_instabilidade = tuple(
            item.indice_condicao_hidrica
            for item in validacao.instabilidade.instabilidades_diarias
        )
        oficial = tuple(
            item.indice for item in validacao.exposicao_hidrica.indices_diarios.indices
        )
        # Instabilidade continua ativada pelo núcleo hídrico meteorológico.
        self.assertEqual(ativacao_instabilidade, base)
        self.assertNotEqual(oficial, base)
        # Trafegabilidade tem metodologia própria: não é mais igual ao núcleo.
        self.assertNotEqual(trafegabilidade, base)
        self.assertNotIn(
            "condicoes_hidricas", type(validacao.trafegabilidade).model_fields
        )

    def test_score_card_e_timeline_derivam_da_mesma_agregacao(self):
        avaliacao = executar_avaliacao_exposicao_maquinario(
            criar_serie_avaliacao(), self.geo, self.politica
        )
        validacao = avaliacao.validacao_atual
        agregado = validacao.exposicao_hidrica.agregacao_90d
        score = calcular_score_exposicao_maquinario(
            validacao,
            criar_politica_composicao_score(self.politica),
            self.politica,
        )
        apresentacao = criar_apresentacao_exposicao_maquinario(avaliacao)
        contribuicao = next(
            item
            for item in score.contribuicoes
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        card = next(
            item
            for item in apresentacao.perigos
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        eventos = tuple(
            item
            for item in apresentacao.timeline_eventos
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        self.assertEqual(contribuicao.indice_perigo, agregado.indice_agregado)
        self.assertEqual(card.indice, agregado.indice_agregado)
        self.assertEqual(
            apresentacao.exposicao_hidrica.janela_atual.indice,
            agregado.indice_agregado,
        )
        self.assertEqual(len(eventos), agregado.quantidade_eventos)
        self.assertEqual(
            tuple((item.inicio, item.fim) for item in eventos),
            tuple((item.inicio, item.fim) for item in agregado.eventos),
        )


if __name__ == "__main__":
    unittest.main()
