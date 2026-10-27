from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from backend.app.servico_explicacao_hidrica_ia import (
    gerar_explicacao_hidrica_ia,
    montar_calculo_hidrico,
)
from backend.exposicao.apresentacao_exposicao import criar_apresentacao_exposicao_maquinario
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.tests.test_exposicao_avaliacao_exposicao import (
    criar_serie_avaliacao,
    executar,
)


class TestExplicacaoHidricaIA(unittest.TestCase):
    def test_operandos_reconstroem_resultado_diario_e_agregado(self):
        avaliacao = executar(criar_serie_avaliacao(cenario="aumento"))
        apresentacao = criar_apresentacao_exposicao_maquinario(avaliacao)
        calculo = montar_calculo_hidrico(
            apresentacao, avaliacao, criar_politica_agrishield_equip_v1()
        )
        territorio = calculo["territorio"]
        meteo = calculo["meteorologia_dia"]
        janela = calculo["janela_90d"]

        self.assertTrue(math.isclose(
            sum(territorio["contribuicoes"].values()),
            territorio["indice"], abs_tol=1e-9,
        ))
        self.assertTrue(math.isclose(
            min(100, meteo["base"] + meteo["incremento_territorial"]),
            meteo["indice_diario"], abs_tol=1e-9,
        ))
        self.assertTrue(math.isclose(
            min(100, sum(janela["pesos"][chave] * janela["componentes"][chave]
                for chave in janela["pesos"])),
            janela["indice"], abs_tol=1e-9,
        ))
        self.assertEqual(janela["indice"], apresentacao.exposicao_hidrica.janela_atual.indice)

    @patch("backend.app.servico_explicacao_hidrica_ia.gerar_resposta_estruturada")
    def test_usa_resposta_estruturada_sem_alterar_os_numeros(self, gerar):
        gerar.return_value = ({
            "resumo": "Leitura simples.",
            "leitura_territorial": "Território baixo.",
            "leitura_meteorologica": "Chuva recente.",
            "leitura_janela": "Histórico de 90 dias.",
            "limitacoes": "Conferir o cadastro.",
        }, {})
        contexto = {"territorio": {"indice": 37.9}}

        resposta = gerar_explicacao_hidrica_ia(contexto, chave_api="teste")

        self.assertEqual(resposta["resumo"], "Leitura simples.")
        self.assertEqual(gerar.call_args.args[0], contexto)
        self.assertEqual(gerar.call_args.kwargs["nome_schema"], "agrishield_explicacao_hidrica")


if __name__ == "__main__":
    unittest.main()
