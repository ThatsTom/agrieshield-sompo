"""Teste de nao regressao obrigatorio (secao 16 da tarefa de migracao de
Trafegabilidade): a nova metodologia de Trafegabilidade nao pode alterar
Exposicao Hidrica, Instabilidade, Incendio/Propagacao de Fogo ou Tempestades
Severas.

Estrategia: executar validar_cinco_perigos() duas vezes com o MESMO cenario e
MESMOS dados de entrada, variando SOMENTE politica.parametros_trafegabilidade
(defaults vs. uma configuracao bem diferente). Os outros quatro perigos nao
leem esse campo, entao devem produzir resultados byte-a-byte identicos nas
duas execucoes - para qualquer valor de parametros_trafegabilidade, nao so
para um "antes/depois" especifico.
"""

from __future__ import annotations

import unittest

from backend.exposicao import (
    ParametrosTrafegabilidade,
    calcular_score_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
    validar_cinco_perigos,
)
from backend.tests.test_exposicao_validacao_integrada import (
    CENARIOS,
    criar_features,
    criar_geo,
)


PARAMETROS_ALTERNATIVOS = ParametrosTrafegabilidade(
    peso_dia=0.10,
    peso_acumulado=0.20,
    peso_recuperacao=0.70,
    limiar_relevancia=60.0,
)


class TestTrafegabilidadeNaoAfetaOutrosPerigos(unittest.TestCase):
    def setUp(self):
        self.politica_padrao = criar_politica_agrishield_equip_v1()
        self.politica_alternativa = self.politica_padrao.model_copy(
            update={"parametros_trafegabilidade": PARAMETROS_ALTERNATIVOS}
        )
        self.assertNotEqual(
            self.politica_padrao.parametros_trafegabilidade,
            self.politica_alternativa.parametros_trafegabilidade,
        )

    def test_quatro_perigos_identicos_para_qualquer_parametro_de_trafegabilidade(self):
        for nome_cenario, definicao in CENARIOS.items():
            with self.subTest(cenario=nome_cenario):
                features = criar_features(nome_cenario)
                geo = criar_geo(definicao["declividade"])

                resultado_padrao = validar_cinco_perigos(
                    features, geo, self.politica_padrao
                )
                resultado_alternativo = validar_cinco_perigos(
                    features, geo, self.politica_alternativa
                )

                self.assertEqual(
                    resultado_padrao.exposicao_hidrica,
                    resultado_alternativo.exposicao_hidrica,
                )
                self.assertEqual(
                    resultado_padrao.instabilidade,
                    resultado_alternativo.instabilidade,
                )
                self.assertEqual(
                    resultado_padrao.propagacao_fogo,
                    resultado_alternativo.propagacao_fogo,
                )
                self.assertEqual(
                    resultado_padrao.tempestade,
                    resultado_alternativo.tempestade,
                )

    def test_score_dos_quatro_outros_perigos_nao_muda(self):
        for nome_cenario, definicao in CENARIOS.items():
            with self.subTest(cenario=nome_cenario):
                features = criar_features(nome_cenario)
                geo = criar_geo(definicao["declividade"])

                resultado_padrao = validar_cinco_perigos(
                    features, geo, self.politica_padrao
                )
                resultado_alternativo = validar_cinco_perigos(
                    features, geo, self.politica_alternativa
                )

                composicao_padrao = criar_politica_composicao_score(
                    self.politica_padrao
                )
                composicao_alternativa = criar_politica_composicao_score(
                    self.politica_alternativa
                )
                score_padrao = calcular_score_exposicao_maquinario(
                    resultado_padrao, composicao_padrao, self.politica_padrao
                )
                score_alternativo = calcular_score_exposicao_maquinario(
                    resultado_alternativo,
                    composicao_alternativa,
                    self.politica_alternativa,
                )

                contrib_padrao = {c.perigo: c for c in score_padrao.contribuicoes}
                contrib_alternativa = {
                    c.perigo: c for c in score_alternativo.contribuicoes
                }
                for perigo in contrib_padrao:
                    if perigo.value == "TRAFEGABILIDADE":
                        continue
                    with self.subTest(perigo=perigo):
                        self.assertEqual(
                            contrib_padrao[perigo], contrib_alternativa[perigo]
                        )

    def test_trafegabilidade_de_fato_muda_com_parametros_diferentes(self):
        # Confirma que o teste acima nao passa trivialmente. Os 5 CENARIOS
        # padrao usam chuva constante (sempre saturada ou sempre zero), o que
        # torna o resultado invariante ao peso escolhido; aqui construimos um
        # dia com componentes deliberadamente distintos entre si (chuva baixa
        # hoje, acumulado alto, poucos dias secos) para que o peso realmente
        # importe.
        def variar_primeiro_dia(indice, _data):
            if indice != 0:
                return {}
            return {"chuva": 5.0, "dias_secura": 2}

        features = criar_features("seco_calmo", alterar=variar_primeiro_dia)
        geo = criar_geo(CENARIOS["seco_calmo"]["declividade"])
        resultado_padrao = validar_cinco_perigos(features, geo, self.politica_padrao)
        resultado_alternativo = validar_cinco_perigos(
            features, geo, self.politica_alternativa
        )
        self.assertNotEqual(
            resultado_padrao.trafegabilidade.indices_diarios.indices[0].indice,
            resultado_alternativo.trafegabilidade.indices_diarios.indices[0].indice,
        )


if __name__ == "__main__":
    unittest.main()
