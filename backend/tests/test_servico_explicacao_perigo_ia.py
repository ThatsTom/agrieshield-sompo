from __future__ import annotations

import math
import unittest
from datetime import timedelta
from unittest.mock import patch

from backend.app.servico_explicacao_perigo_ia import (
    PerigoExplicacaoIA,
    gerar_explicacao_perigo_ia,
    montar_calculo_perigo,
)
from backend.exposicao.apresentacao_exposicao import criar_apresentacao_exposicao_maquinario
from backend.exposicao.avaliacao_exposicao import executar_avaliacao_exposicao_maquinario
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.tests.test_exposicao_avaliacao_exposicao import DATA_REFERENCIA, criar_serie_avaliacao
from backend.tests.test_exposicao_validacao_integrada import criar_geo


def calcular(serie=None, politica=None):
    politica = politica or criar_politica_agrishield_equip_v1()
    avaliacao = executar_avaliacao_exposicao_maquinario(
        serie or criar_serie_avaliacao(cenario="aumento"), criar_geo(20), politica
    )
    apresentacao = criar_apresentacao_exposicao_maquinario(avaliacao)
    return apresentacao, avaliacao, politica


class TestExplicacaoPerigoIA(unittest.TestCase):
    def test_quatro_perigos_preservam_operandos_e_agregacao_do_motor(self):
        apresentacao, avaliacao, politica = calcular()
        antes = avaliacao.model_dump()
        for perigo in PerigoExplicacaoIA:
            with self.subTest(perigo=perigo):
                c = montar_calculo_perigo(apresentacao, avaliacao, politica, perigo)
                d = c["operandos"]
                if perigo == PerigoExplicacaoIA.INCENDIO:
                    base = 100 * math.prod((d["componente_temperatura"], d["componente_baixa_umidade"], d["componente_vento"])) ** (1 / 3)
                    diario = min(100, base * d["multiplicador_secura"])
                elif perigo == PerigoExplicacaoIA.INSTABILIDADE:
                    diario = min(100, d["indice_suscetibilidade_topografica"] * d["fator_ativacao_hidrica"])
                elif perigo == PerigoExplicacaoIA.TRAFEGABILIDADE:
                    p = politica.parametros_trafegabilidade
                    diario = min(100, d["componente_dia"] * p.peso_dia + d["componente_acumulado"] * p.peso_acumulado + d["componente_recuperacao"] * p.peso_recuperacao)
                else:
                    diario = min(100, d["indice_vento"] * d["fator_amplificacao_chuva"])
                self.assertAlmostEqual(diario, c["dia"]["indice_diario"], places=10)
                self.assertAlmostEqual(c["etapas"][-1]["resultado"], diario, places=10)
                self.assertEqual(c["disponibilidade_diaria"]["dias_defasagem"], 0)
                self.assertEqual(c["data_referencia"], DATA_REFERENCIA.isoformat())
                janela = c["janela_90d"]
                self.assertAlmostEqual(janela["indice"], sum(janela["pesos"][k] * v for k, v in janela["componentes"].items()), places=10)
                resumo = next(item for item in apresentacao.perigos if item.perigo.value == perigo.value)
                self.assertEqual(janela["indice"], resumo.indice)
        self.assertEqual(avaliacao.model_dump(), antes)

    def test_pesos_e_faixas_vigentes_chegam_as_contas_e_ao_contexto(self):
        politica = criar_politica_agrishield_equip_v1()
        politica = politica.model_copy(update={
            "parametros_tempestade": politica.parametros_tempestade.model_copy(update={"peso_base_vento": .6, "peso_amplificacao_chuva": .4}),
            "parametros_trafegabilidade": politica.parametros_trafegabilidade.model_copy(update={"peso_dia": .2, "peso_acumulado": .5, "peso_recuperacao": .3, "limiar_relevancia": 30}),
            "parametros_propagacao_fogo": politica.parametros_propagacao_fogo.model_copy(update={"faixas_secura_antecedente": tuple(p.model_copy(update={"multiplicador": .8 + i * .1}) for i, p in enumerate(politica.parametros_propagacao_fogo.faixas_secura_antecedente))}),
            "parametros_instabilidade": politica.parametros_instabilidade.model_copy(update={"faixas_ativacao_hidrica": tuple(p.model_copy(update={"fator_ativacao": i * .25}) for i, p in enumerate(politica.parametros_instabilidade.faixas_ativacao_hidrica))}),
        })
        apresentacao, avaliacao, politica = calcular(politica=politica)
        fogo = montar_calculo_perigo(apresentacao, avaliacao, politica, "INCENDIO")
        instabilidade = montar_calculo_perigo(apresentacao, avaliacao, politica, "INSTABILIDADE")
        trafego = montar_calculo_perigo(apresentacao, avaliacao, politica, "TRAFEGABILIDADE")
        tempestade = montar_calculo_perigo(apresentacao, avaliacao, politica, "TEMPESTADES")
        self.assertEqual(fogo["operandos"]["multiplicador_secura"], .8)
        self.assertIn("0,8000", fogo["etapas"][-1]["formula"])
        self.assertEqual(instabilidade["operandos"]["fator_ativacao_hidrica"], .75)
        self.assertEqual(trafego["parametros"]["peso_dia"], .2)
        self.assertEqual(trafego["parametros"]["limiar_relevancia"], 30)
        self.assertIn("0,2000", trafego["etapas"][-1]["formula"])
        self.assertEqual(tempestade["parametros"]["peso_base_vento"], .6)
        self.assertIn("0,6000 + 0,4000", tempestade["etapas"][-2]["formula"])

    def test_lacunas_finais_selecionam_ultimo_dia_calculavel_sem_deslocar_janela(self):
        gaps = {DATA_REFERENCIA - timedelta(days=i) for i in range(3)}
        argumentos = calcular(criar_serie_avaliacao(gaps_precipitacao=gaps, gaps_vento=gaps, gaps_umidade=gaps))
        for perigo in PerigoExplicacaoIA:
            with self.subTest(perigo=perigo):
                c = montar_calculo_perigo(*argumentos, perigo)
                self.assertEqual(c["dia"]["data"], (DATA_REFERENCIA - timedelta(days=3)).isoformat())
                self.assertEqual(c["disponibilidade_diaria"]["dias_defasagem"], 3)
                self.assertEqual(c["janela_90d"]["fim"], DATA_REFERENCIA.isoformat())
                self.assertEqual(c["data_referencia"], DATA_REFERENCIA.isoformat())
                self.assertTrue(c["disponibilidade_diaria"]["entradas_ausentes_referencia"])
                self.assertEqual(c["dia"]["data"], c["operandos"]["data"])

    def test_zero_e_um_indice_diario_valido_para_todos_os_perigos(self):
        argumentos = calcular(criar_serie_avaliacao(cenario="reducao"))
        for perigo in PerigoExplicacaoIA:
            with self.subTest(perigo=perigo):
                c = montar_calculo_perigo(*argumentos, perigo)
                self.assertTrue(c["disponibilidade_diaria"]["disponivel"])
                self.assertEqual(c["dia"]["indice_diario"], 0)
                self.assertEqual(c["dia"]["data"], DATA_REFERENCIA.isoformat())
                self.assertEqual(c["etapas"][-1]["resultado"], 0)

    def test_ausencia_total_conserva_dados_parciais_sem_fabricar_resultado(self):
        datas = {r.data for r in criar_serie_avaliacao().registros}
        argumentos = calcular(criar_serie_avaliacao(gaps_precipitacao=datas, gaps_vento=datas, gaps_umidade=datas))
        for perigo in PerigoExplicacaoIA:
            with self.subTest(perigo=perigo):
                c = montar_calculo_perigo(*argumentos, perigo)
                self.assertFalse(c["disponibilidade_diaria"]["disponivel"])
                self.assertIsNone(c["disponibilidade_diaria"]["data_calculo"])
                self.assertIsNone(c["dia"]["indice_diario"])
                self.assertIsNone(c["janela_90d"]["indice"])
                self.assertTrue(any(d["valor"] is None for d in c["dados_utilizados"]))
                self.assertTrue(all(e["resultado"] is not None and "None" not in e["formula"] for e in c["etapas"]))
                self.assertFalse(any(e["titulo"] == "Índice diário" for e in c["etapas"]))

    def test_fogo_sem_contexto_de_chuva_mantem_base_sem_inventar_multiplicador(self):
        datas = {r.data for r in criar_serie_avaliacao().registros}
        c = montar_calculo_perigo(*calcular(criar_serie_avaliacao(gaps_precipitacao=datas)), "INCENDIO")
        self.assertTrue(c["disponibilidade_diaria"]["disponivel"])
        self.assertIsNone(c["operandos"]["multiplicador_secura"])
        self.assertEqual(c["dia"]["indice_diario"], c["operandos"]["indice_fogo_base"])
        self.assertIn("sem aplicação de multiplicador", c["etapas"][-1]["formula"])
        self.assertIn("contexto opcional", c["disponibilidade_diaria"]["motivo"])

    def test_perigo_hidrico_usa_servico_proprio(self):
        with self.assertRaises(ValueError):
            montar_calculo_perigo(*calcular(), "EXPOSICAO_HIDRICA")

    @patch("backend.app.servico_explicacao_perigo_ia.gerar_resposta_estruturada")
    def test_geracao_reutiliza_resposta_estruturada_com_contexto_intacto(self, gerar):
        gerar.return_value = ({"resumo": "Resumo do perigo."}, {})
        contexto = {"perigo": "INCENDIO", "dia": {"indice_diario": 0}}
        self.assertEqual(gerar_explicacao_perigo_ia(contexto, chave_api="teste"), {"resumo": "Resumo do perigo."})
        self.assertEqual(gerar.call_args.args[0], contexto)
        self.assertEqual(gerar.call_args.kwargs["nome_schema"], "agrishield_explicacao_perigo")
        self.assertEqual(gerar.call_args.kwargs["chave_api"], "teste")


if __name__ == "__main__":
    unittest.main()
