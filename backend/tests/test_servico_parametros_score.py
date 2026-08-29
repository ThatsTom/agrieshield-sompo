from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app import servico_parametros_score as servico
from backend.etl import repositorio_parametros_score as repositorio
from backend.exposicao.politica import criar_politica_agrishield_equip_v1


def _valores_padrao():
    return {
        (g, i, p): padrao for g, i, p, padrao, _ in repositorio.PARAMETROS_MODELO_PADRAO
    }


class BaseServicoParametrosScore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        pasta = Path(self.tempdir.name)
        arquivo = pasta / "parametros_score.csv"
        self.patch_pasta = patch.object(repositorio, "PASTA_DADOS", pasta)
        self.patch_arquivo = patch.object(
            repositorio, "ARQUIVO_PARAMETROS_SCORE", arquivo
        )
        self.patch_pasta.start()
        self.patch_arquivo.start()
        self.addCleanup(self.patch_pasta.stop)
        self.addCleanup(self.patch_arquivo.stop)


class TestObterConfiguracao(BaseServicoParametrosScore):
    def test_defaults_sao_retornados_na_primeira_leitura(self):
        configuracao = servico.obter_configuracao_parametros_modelo()
        self.assertEqual(len(configuracao.parametros), 22)
        item = next(
            p
            for p in configuracao.parametros
            if (p.grupo, p.indicador, p.parametro)
            == ("SCORE", "EXPOSICAO_HIDRICA", "peso")
        )
        self.assertEqual(item.valor_atual, 0.30)
        self.assertEqual(item.valor_padrao, 0.30)
        self.assertEqual(item.tipo, "percentual")

    def test_ordem_e_sempre_a_ordem_oficial(self):
        configuracao = servico.obter_configuracao_parametros_modelo()
        chaves = tuple(
            (p.grupo, p.indicador, p.parametro) for p in configuracao.parametros
        )
        self.assertEqual(chaves, repositorio.CHAVES_ESPERADAS)

    def test_valor_padrao_nunca_muda_mesmo_apos_customizar(self):
        valores = _valores_padrao()
        valores[("INSTABILIDADE", "ATIVACAO", "atencao")] = 0.40
        servico.salvar_configuracao_parametros_modelo(valores)
        configuracao = servico.obter_configuracao_parametros_modelo()
        item = next(
            p
            for p in configuracao.parametros
            if (p.grupo, p.indicador, p.parametro)
            == ("INSTABILIDADE", "ATIVACAO", "atencao")
        )
        self.assertEqual(item.valor_atual, 0.40)
        self.assertEqual(item.valor_padrao, 0.35)


class TestCarregarOverrides(BaseServicoParametrosScore):
    def test_overrides_com_defaults_reproduz_a_politica_oficial(self):
        overrides = servico.carregar_overrides_parametros_modelo()
        base = criar_politica_agrishield_equip_v1()
        self.assertEqual(overrides.pesos_perigos, base.pesos_perigos)
        self.assertEqual(
            overrides.parametros_territoriais_hidricos,
            base.parametros_territoriais_hidricos,
        )
        self.assertEqual(
            overrides.parametros_instabilidade, base.parametros_instabilidade
        )
        self.assertEqual(
            overrides.parametros_propagacao_fogo, base.parametros_propagacao_fogo
        )
        self.assertEqual(overrides.parametros_tempestade, base.parametros_tempestade)
        self.assertEqual(
            overrides.parametros_trafegabilidade, base.parametros_trafegabilidade
        )

    def test_overrides_customizados_preservam_curvas_e_thresholds_originais(self):
        valores = _valores_padrao()
        valores[("INSTABILIDADE", "ATIVACAO", "atencao")] = 0.50
        valores[("INCENDIO", "SECURA", "7_mais_dias")] = 1.20
        servico.salvar_configuracao_parametros_modelo(valores)

        overrides = servico.carregar_overrides_parametros_modelo()
        base = criar_politica_agrishield_equip_v1()

        # thresholds (inicio_indice_hidrico / inicio_dias) continuam intactos
        self.assertEqual(
            tuple(
                faixa.inicio_indice_hidrico
                for faixa in overrides.parametros_instabilidade.faixas_ativacao_hidrica
            ),
            tuple(
                faixa.inicio_indice_hidrico
                for faixa in base.parametros_instabilidade.faixas_ativacao_hidrica
            ),
        )
        self.assertEqual(
            tuple(
                faixa.inicio_dias
                for faixa in overrides.parametros_propagacao_fogo.faixas_secura_antecedente
            ),
            tuple(
                faixa.inicio_dias
                for faixa in base.parametros_propagacao_fogo.faixas_secura_antecedente
            ),
        )
        # curva de declividade / temperatura / umidade / vento continuam intactas
        self.assertEqual(
            overrides.parametros_instabilidade.curva_declividade,
            base.parametros_instabilidade.curva_declividade,
        )
        self.assertEqual(
            overrides.parametros_propagacao_fogo.curva_temperatura_maxima,
            base.parametros_propagacao_fogo.curva_temperatura_maxima,
        )
        # apenas os fatores configurados mudaram
        fatores = [
            faixa.fator_ativacao
            for faixa in overrides.parametros_instabilidade.faixas_ativacao_hidrica
        ]
        self.assertEqual(fatores, [0.00, 0.50, 0.65, 1.00])
        multiplicadores = [
            faixa.multiplicador
            for faixa in overrides.parametros_propagacao_fogo.faixas_secura_antecedente
        ]
        self.assertEqual(multiplicadores, [0.90, 1.00, 1.05, 1.20])

    def test_arquivo_corrompido_nao_vira_defaults_silenciosos(self):
        repositorio.criar_base_parametros_score_se_nao_existir()
        with open(repositorio.ARQUIVO_PARAMETROS_SCORE, "w", encoding="utf-8-sig") as f:
            f.write("colunas;erradas\nx;y\n")
        with self.assertRaises(servico.ErroParametrosScorePersistidosInvalidos):
            servico.carregar_overrides_parametros_modelo()


class TestSalvarConfiguracao(BaseServicoParametrosScore):
    def test_salva_e_devolve_a_configuracao_persistida(self):
        valores = _valores_padrao()
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.40
        valores[("SCORE", "TRAFEGABILIDADE", "peso")] = 0.15
        configuracao = servico.salvar_configuracao_parametros_modelo(valores)
        item = next(
            p
            for p in configuracao.parametros
            if (p.grupo, p.indicador, p.parametro)
            == ("SCORE", "EXPOSICAO_HIDRICA", "peso")
        )
        self.assertEqual(item.valor_atual, 0.40)

        relida = servico.obter_configuracao_parametros_modelo()
        item_relido = next(
            p
            for p in relida.parametros
            if (p.grupo, p.indicador, p.parametro)
            == ("SCORE", "EXPOSICAO_HIDRICA", "peso")
        )
        self.assertEqual(item_relido.valor_atual, 0.40)

    def test_soma_do_score_diferente_de_100_e_rejeitada(self):
        valores = _valores_padrao()
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.31
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["SCORE"])
        self.assertIn(servico.MENSAGEM_SOMA_PESOS_INVALIDA, ctx.exception.erros[0][1])

    def test_soma_hidrica_diferente_de_100_e_rejeitada(self):
        valores = _valores_padrao()
        valores[("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem")] = 0.50
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["EXPOSICAO_HIDRICA"])
        self.assertEqual(
            ctx.exception.erros[0][1], servico.MENSAGEM_SOMA_HIDRICO_INVALIDA
        )

    def test_fator_de_instabilidade_fora_do_dominio_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("INSTABILIDADE", "ATIVACAO", "atencao")] = 1.5
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["INSTABILIDADE"])

    def test_fator_de_instabilidade_decrescente_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("INSTABILIDADE", "ATIVACAO", "atencao")] = 0.90  # > alerta (0.65)
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["INSTABILIDADE"])

    def test_multiplicador_de_fogo_negativo_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("INCENDIO", "SECURA", "2_3_dias")] = -1.0
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["INCENDIO"])

    def test_tempestades_base_mais_influencia_diferente_de_um_e_rejeitada(self):
        valores = _valores_padrao()
        valores[("TEMPESTADES", "VENTO_CHUVA", "base")] = 0.90
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["TEMPESTADES"])
        self.assertEqual(
            ctx.exception.erros[0][1], servico.MENSAGEM_TEMPESTADES_INVALIDA
        )

    def test_soma_dos_pesos_internos_de_trafegabilidade_diferente_de_100_e_rejeitada(
        self,
    ):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")] = 0.50
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["TRAFEGABILIDADE"])
        self.assertEqual(
            ctx.exception.erros[0][1], servico.MENSAGEM_TRAFEGABILIDADE_INVALIDA
        )

    def test_peso_negativo_de_trafegabilidade_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")] = -0.10
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")] = 0.90
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["TRAFEGABILIDADE"])

    def test_limiar_de_relevancia_negativo_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")] = -1
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["TRAFEGABILIDADE"])

    def test_limiar_de_relevancia_acima_de_cem_e_rejeitado(self):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")] = 101
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        self.assertEqual([g for g, _ in ctx.exception.erros], ["TRAFEGABILIDADE"])

    def test_alterar_limiar_de_relevancia_nao_afeta_outros_grupos(self):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")] = 40
        configuracao = servico.salvar_configuracao_parametros_modelo(valores)
        for item in configuracao.parametros:
            if (item.grupo, item.indicador, item.parametro) == (
                "TRAFEGABILIDADE",
                "AGREGACAO",
                "limiar_relevancia",
            ):
                self.assertEqual(item.valor_atual, 40)
            elif item.grupo != "TRAFEGABILIDADE":
                self.assertEqual(item.valor_atual, item.valor_padrao)

    def test_restaurar_padrao_de_trafegabilidade_volta_para_35_45_20_25(self):
        valores = _valores_padrao()
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")] = 0.10
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")] = 0.10
        valores[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")] = 0.80
        valores[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")] = 50
        servico.salvar_configuracao_parametros_modelo(valores)

        restaurados = _valores_padrao()
        configuracao = servico.salvar_configuracao_parametros_modelo(restaurados)
        item_por_chave = {
            (p.grupo, p.indicador, p.parametro): p.valor_atual
            for p in configuracao.parametros
        }
        self.assertEqual(
            item_por_chave[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")], 0.35
        )
        self.assertEqual(
            item_por_chave[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")], 0.45
        )
        self.assertEqual(
            item_por_chave[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")], 0.20
        )
        self.assertEqual(
            item_por_chave[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")], 25
        )

    def test_multiplos_grupos_invalidos_reportam_todos_sem_mascarar(self):
        valores = _valores_padrao()
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.31
        valores[("TEMPESTADES", "VENTO_CHUVA", "base")] = 0.90
        with self.assertRaises(servico.ErroParametrosScoreInvalidos) as ctx:
            servico.salvar_configuracao_parametros_modelo(valores)
        grupos = {g for g, _ in ctx.exception.erros}
        self.assertEqual(grupos, {"SCORE", "TEMPESTADES"})

    def test_pesos_nao_sao_normalizados_automaticamente(self):
        valores = _valores_padrao()
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.31
        with self.assertRaises(servico.ErroParametrosScoreInvalidos):
            servico.salvar_configuracao_parametros_modelo(valores)
        configuracao = servico.obter_configuracao_parametros_modelo()
        item = next(
            p
            for p in configuracao.parametros
            if (p.grupo, p.indicador, p.parametro)
            == ("SCORE", "EXPOSICAO_HIDRICA", "peso")
        )
        self.assertEqual(item.valor_atual, 0.30)

    def test_chave_faltando_e_rejeitada(self):
        incompleto = _valores_padrao()
        del incompleto[("TEMPESTADES", "VENTO_CHUVA", "base")]
        with self.assertRaises(servico.ErroParametrosScoreInvalidos):
            servico.salvar_configuracao_parametros_modelo(incompleto)

    def test_reinicio_e_releitura_mantem_configuracao(self):
        valores = _valores_padrao()
        valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.45
        valores[("SCORE", "TRAFEGABILIDADE", "peso")] = 0.20
        valores[("SCORE", "INSTABILIDADE", "peso")] = 0.10
        servico.salvar_configuracao_parametros_modelo(valores)

        # "reinicio": nova leitura do zero, sem estado em memoria
        overrides = servico.carregar_overrides_parametros_modelo()
        self.assertEqual(overrides.pesos_perigos.exposicao_hidrica, 0.45)
        self.assertEqual(overrides.pesos_perigos.instabilidade, 0.10)


if __name__ == "__main__":
    unittest.main()
