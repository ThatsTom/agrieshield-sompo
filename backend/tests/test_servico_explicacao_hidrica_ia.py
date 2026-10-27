from __future__ import annotations

import math
import unittest
from datetime import timedelta
from unittest.mock import patch

from backend.app.servico_explicacao_hidrica_ia import (
    gerar_explicacao_hidrica_ia,
    montar_calculo_hidrico,
)
from backend.exposicao.apresentacao_exposicao import criar_apresentacao_exposicao_maquinario
from backend.exposicao.avaliacao_exposicao import executar_avaliacao_exposicao_maquinario
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.tests.test_exposicao_avaliacao_exposicao import (
    DATA_REFERENCIA,
    criar_serie_avaliacao,
    executar,
)
from backend.tests.test_exposicao_validacao_integrada import criar_geo
from backend.risco.modelos import StatusQualidade


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
        self.assertEqual(calculo["disponibilidade_diaria"], {
            "disponivel": True,
            "data_referencia": DATA_REFERENCIA.isoformat(),
            "data_calculo": DATA_REFERENCIA.isoformat(),
            "dias_defasagem": 0,
            "entradas_ausentes_referencia": [],
            "motivo": "O cálculo diário usa os dados da data de referência.",
        })

    def test_ultimo_dia_calculavel_alinha_operandos_e_preserva_avaliacao(self):
        lacunas = {DATA_REFERENCIA - timedelta(days=dias) for dias in range(3)}
        avaliacao = executar(criar_serie_avaliacao(gaps_precipitacao=lacunas))
        apresentacao = criar_apresentacao_exposicao_maquinario(avaliacao)
        avaliacao_antes = avaliacao.model_dump()
        apresentacao_antes = apresentacao.model_dump()

        calculo = montar_calculo_hidrico(
            apresentacao, avaliacao, criar_politica_agrishield_equip_v1()
        )

        dia_esperado = DATA_REFERENCIA - timedelta(days=3)
        disponibilidade = calculo["disponibilidade_diaria"]
        self.assertTrue(disponibilidade["disponivel"])
        self.assertEqual(disponibilidade["data_calculo"], dia_esperado.isoformat())
        self.assertEqual(disponibilidade["dias_defasagem"], 3)
        self.assertIn("chuva do dia", disponibilidade["entradas_ausentes_referencia"])
        self.assertIn("chuva acumulada em 3 dias", disponibilidade["entradas_ausentes_referencia"])
        self.assertEqual(calculo["data_referencia"], DATA_REFERENCIA.isoformat())
        meteo = calculo["meteorologia_dia"]
        hidrico = avaliacao.validacao_atual.exposicao_hidrica
        condicao = next(item for item in hidrico.condicoes_hidricas_base if item.data == dia_esperado)
        diario = next(item for item in hidrico.detalhes_diarios if item.data == dia_esperado)
        feature = avaliacao.features_compartilhadas.por_data(dia_esperado)
        self.assertEqual(meteo["data"], dia_esperado.isoformat())
        self.assertEqual(meteo["chuva_hoje_mm"], feature.precipitacao_d0)
        self.assertEqual(meteo["chuva_d1_d3_normalizada"], condicao.indice_d1_d3)
        self.assertEqual(meteo["antecedente_normalizado"], condicao.indice_antecedente)
        self.assertEqual(meteo["indice_diario"], diario.indice_exposicao_hidrica)
        self.assertEqual(calculo["janela_90d"]["inicio"], hidrico.agregacao_90d.inicio.isoformat())
        self.assertEqual(calculo["janela_90d"]["fim"], DATA_REFERENCIA.isoformat())
        self.assertEqual(calculo["janela_90d"]["indice"], hidrico.agregacao_90d.indice_agregado)
        self.assertEqual(avaliacao.model_dump(), avaliacao_antes)
        self.assertEqual(apresentacao.model_dump(), apresentacao_antes)

    def test_lacuna_interna_identifica_bloco_antecedente_ausente(self):
        avaliacao = executar(criar_serie_avaliacao(
            gaps_precipitacao={DATA_REFERENCIA - timedelta(days=4)}
        ))
        calculo = montar_calculo_hidrico(
            criar_apresentacao_exposicao_maquinario(avaliacao),
            avaliacao, criar_politica_agrishield_equip_v1(),
        )

        disponibilidade = calculo["disponibilidade_diaria"]
        self.assertEqual(disponibilidade["data_calculo"], (DATA_REFERENCIA - timedelta(days=5)).isoformat())
        self.assertEqual(disponibilidade["dias_defasagem"], 5)
        self.assertEqual(disponibilidade["entradas_ausentes_referencia"], [
            "chuva acumulada entre 4 e 7 dias anteriores",
        ])
        self.assertNotIn("NASA", disponibilidade["motivo"])

    def test_indice_zero_e_chuva_zero_sao_dados_validos(self):
        avaliacao = executar(criar_serie_avaliacao(
            cenario="reducao", gaps_precipitacao={DATA_REFERENCIA}
        ))
        calculo = montar_calculo_hidrico(
            criar_apresentacao_exposicao_maquinario(avaliacao),
            avaliacao, criar_politica_agrishield_equip_v1(),
        )

        disponibilidade = calculo["disponibilidade_diaria"]
        self.assertTrue(disponibilidade["disponivel"])
        self.assertEqual(disponibilidade["data_calculo"], (DATA_REFERENCIA - timedelta(days=1)).isoformat())
        self.assertEqual(disponibilidade["dias_defasagem"], 1)
        for campo in ("chuva_hoje_mm", "chuva_3d_mm", "ativacao_chuva_3d", "base", "indice_diario"):
            self.assertEqual(calculo["meteorologia_dia"][campo], 0.0)

    def test_ausencia_total_nao_inventa_dia_nem_resultado(self):
        serie = criar_serie_avaliacao()
        todas_as_datas = {item.data for item in serie.registros}
        avaliacao = executar(criar_serie_avaliacao(gaps_precipitacao=todas_as_datas))
        calculo = montar_calculo_hidrico(
            criar_apresentacao_exposicao_maquinario(avaliacao),
            avaliacao, criar_politica_agrishield_equip_v1(),
        )

        disponibilidade = calculo["disponibilidade_diaria"]
        self.assertFalse(disponibilidade["disponivel"])
        self.assertIsNone(disponibilidade["data_calculo"])
        self.assertIsNone(disponibilidade["dias_defasagem"])
        self.assertIn("Não há dia", disponibilidade["motivo"])
        self.assertEqual(calculo["meteorologia_dia"]["data"], DATA_REFERENCIA.isoformat())
        for campo in ("chuva_hoje_mm", "chuva_3d_mm", "ativacao_chuva_3d", "base", "indice_diario"):
            self.assertIsNone(calculo["meteorologia_dia"][campo])
        self.assertIsNotNone(calculo["territorio"]["indice"])
        self.assertIsNone(calculo["janela_90d"]["indice"])

    def test_territorio_ausente_preserva_meteorologia_parcial(self):
        geo = criar_geo(20)
        dados_geo = geo.model_dump()
        dados_geo["distancia_drenagem_m"]["valor"] = None
        dados_geo["distancia_drenagem_m"]["qualidade"]["status"] = StatusQualidade.AUSENTE
        geo = type(geo).model_validate(dados_geo)
        avaliacao = executar_avaliacao_exposicao_maquinario(
            criar_serie_avaliacao(), geo, criar_politica_agrishield_equip_v1()
        )
        calculo = montar_calculo_hidrico(
            criar_apresentacao_exposicao_maquinario(avaliacao),
            avaliacao, criar_politica_agrishield_equip_v1(),
        )

        disponibilidade = calculo["disponibilidade_diaria"]
        self.assertFalse(disponibilidade["disponivel"])
        self.assertEqual(disponibilidade["entradas_ausentes_referencia"], ["distância até a drenagem"])
        self.assertIsNone(disponibilidade["data_calculo"])
        self.assertEqual(calculo["meteorologia_dia"]["data"], DATA_REFERENCIA.isoformat())
        self.assertIsNotNone(calculo["meteorologia_dia"]["base"])
        self.assertIsNotNone(calculo["meteorologia_dia"]["chuva_3d_mm"])
        self.assertIsNone(calculo["meteorologia_dia"]["indice_diario"])
        self.assertIsNone(calculo["territorio"]["indice"])

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
