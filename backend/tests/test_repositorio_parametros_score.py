from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.etl import repositorio_parametros_score as repositorio


class BaseRepositorioParametrosScore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        pasta = Path(self.tempdir.name)
        self.arquivo = pasta / "parametros_score.csv"
        self.patch_pasta = patch.object(repositorio, "PASTA_DADOS", pasta)
        self.patch_arquivo = patch.object(
            repositorio, "ARQUIVO_PARAMETROS_SCORE", self.arquivo
        )
        self.patch_pasta.start()
        self.patch_arquivo.start()
        self.addCleanup(self.patch_pasta.stop)
        self.addCleanup(self.patch_arquivo.stop)


class TestInicializacao(BaseRepositorioParametrosScore):
    def test_arquivo_e_criado_com_defaults_na_primeira_leitura(self):
        self.assertFalse(self.arquivo.exists())
        linhas = repositorio.carregar_linhas_parametros_modelo()
        self.assertTrue(self.arquivo.exists())
        self.assertEqual(len(linhas), len(repositorio.CHAVES_ESPERADAS))
        for linha, (grupo, indicador, parametro, padrao, tipo) in zip(
            linhas, repositorio.PARAMETROS_MODELO_PADRAO
        ):
            self.assertEqual(linha["grupo"], grupo)
            self.assertEqual(linha["indicador"], indicador)
            self.assertEqual(linha["parametro"], parametro)
            self.assertEqual(linha["valor_atual"], padrao)
            self.assertEqual(linha["valor_padrao"], padrao)
            self.assertEqual(linha["tipo"], tipo)

    def test_defaults_batem_com_score_hidrico_instabilidade_fogo_tempestade_trafegabilidade(
        self,
    ):
        linhas = {
            (l["grupo"], l["indicador"], l["parametro"]): l["valor_padrao"]
            for l in repositorio.carregar_linhas_parametros_modelo()
        }
        self.assertEqual(linhas[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.30)
        self.assertEqual(linhas[("SCORE", "TRAFEGABILIDADE", "peso")], 0.25)
        self.assertEqual(linhas[("SCORE", "INSTABILIDADE", "peso")], 0.20)
        self.assertEqual(linhas[("SCORE", "INCENDIO", "peso")], 0.15)
        self.assertEqual(linhas[("SCORE", "TEMPESTADES", "peso")], 0.10)
        self.assertEqual(
            linhas[("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem")], 0.40
        )
        self.assertEqual(
            linhas[("EXPOSICAO_HIDRICA", "T3", "relevancia_area_montante")], 0.35
        )
        self.assertEqual(
            linhas[("EXPOSICAO_HIDRICA", "T3", "posicao_topografica")], 0.25
        )
        self.assertEqual(linhas[("INSTABILIDADE", "ATIVACAO", "normal")], 0.00)
        self.assertEqual(linhas[("INSTABILIDADE", "ATIVACAO", "atencao")], 0.35)
        self.assertEqual(linhas[("INSTABILIDADE", "ATIVACAO", "alerta")], 0.65)
        self.assertEqual(linhas[("INSTABILIDADE", "ATIVACAO", "critico")], 1.00)
        self.assertEqual(linhas[("INCENDIO", "SECURA", "0_1_dia")], 0.90)
        self.assertEqual(linhas[("INCENDIO", "SECURA", "2_3_dias")], 1.00)
        self.assertEqual(linhas[("INCENDIO", "SECURA", "4_6_dias")], 1.05)
        self.assertEqual(linhas[("INCENDIO", "SECURA", "7_mais_dias")], 1.10)
        self.assertEqual(linhas[("TEMPESTADES", "VENTO_CHUVA", "base")], 0.75)
        self.assertEqual(
            linhas[("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva")], 0.25
        )
        self.assertEqual(linhas[("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia")], 0.35)
        self.assertEqual(
            linhas[("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado")], 0.45
        )
        self.assertEqual(
            linhas[("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao")], 0.20
        )
        self.assertEqual(
            linhas[("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia")], 25
        )

    def test_colunas_sao_exatamente_o_schema_generico(self):
        repositorio.carregar_linhas_parametros_modelo()
        with open(self.arquivo, encoding="utf-8-sig", newline="") as f:
            leitor = csv.DictReader(f, delimiter=";")
            self.assertEqual(
                leitor.fieldnames,
                [
                    "grupo",
                    "indicador",
                    "parametro",
                    "valor_atual",
                    "valor_padrao",
                    "tipo",
                    "atualizado_em",
                ],
            )

    def test_leitura_repetida_nao_recria_o_arquivo(self):
        repositorio.carregar_linhas_parametros_modelo()
        modificado_em = self.arquivo.stat().st_mtime_ns
        repositorio.carregar_linhas_parametros_modelo()
        self.assertEqual(self.arquivo.stat().st_mtime_ns, modificado_em)


class TestSalvar(BaseRepositorioParametrosScore):
    def _valores_padrao(self):
        return {
            (g, i, p): padrao
            for g, i, p, padrao, _ in repositorio.PARAMETROS_MODELO_PADRAO
        }

    def test_salvar_substitui_todos_os_valores_atomicamente(self):
        novos = self._valores_padrao()
        novos[("SCORE", "EXPOSICAO_HIDRICA", "peso")] = 0.40
        novos[("SCORE", "TRAFEGABILIDADE", "peso")] = 0.15
        linhas = repositorio.salvar_parametros_modelo(novos)
        valores = {
            (l["grupo"], l["indicador"], l["parametro"]): l["valor_atual"]
            for l in linhas
        }
        self.assertEqual(valores[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.40)
        self.assertEqual(valores[("SCORE", "TRAFEGABILIDADE", "peso")], 0.15)
        # valor_padrao nunca muda, mesmo quando valor_atual e customizado
        padroes = {
            (l["grupo"], l["indicador"], l["parametro"]): l["valor_padrao"]
            for l in linhas
        }
        self.assertEqual(padroes[("SCORE", "EXPOSICAO_HIDRICA", "peso")], 0.30)

    def test_salvar_atualiza_o_timestamp(self):
        repositorio.carregar_linhas_parametros_modelo()
        antes = {
            (l["grupo"], l["indicador"], l["parametro"]): l["atualizado_em"]
            for l in repositorio.carregar_linhas_parametros_modelo()
        }
        depois = repositorio.salvar_parametros_modelo(self._valores_padrao())
        for linha in depois:
            chave = (linha["grupo"], linha["indicador"], linha["parametro"])
            self.assertNotEqual(linha["atualizado_em"], antes[chave])

    def test_salvar_com_chave_faltando_e_rejeitado(self):
        incompleto = self._valores_padrao()
        del incompleto[("TEMPESTADES", "VENTO_CHUVA", "base")]
        with self.assertRaises(ValueError):
            repositorio.salvar_parametros_modelo(incompleto)

    def test_salvar_com_chave_desconhecida_e_rejeitado(self):
        invalido = self._valores_padrao()
        del invalido[("TEMPESTADES", "VENTO_CHUVA", "base")]
        invalido[("TEMPESTADES", "VENTO_CHUVA", "chave_inventada")] = 1.0
        with self.assertRaises(ValueError):
            repositorio.salvar_parametros_modelo(invalido)

    def test_nao_deixa_arquivo_temporario_para_tras(self):
        repositorio.salvar_parametros_modelo(self._valores_padrao())
        arquivos = list(self.arquivo.parent.iterdir())
        self.assertEqual(arquivos, [self.arquivo])


class TestArquivoCorrompido(BaseRepositorioParametrosScore):
    def _escrever_csv_bruto(self, linhas):
        with open(self.arquivo, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f, fieldnames=repositorio.COLUNAS_PARAMETROS_MODELO, delimiter=";"
            )
            writer.writeheader()
            writer.writerows(linhas)

    def test_arquivo_com_linha_faltando_e_rejeitado_sem_virar_default_silencioso(self):
        linhas = [
            {
                "grupo": g,
                "indicador": i,
                "parametro": p,
                "valor_atual": str(padrao),
                "valor_padrao": str(padrao),
                "tipo": tipo,
                "atualizado_em": "2026-01-01T00:00:00+00:00",
            }
            for g, i, p, padrao, tipo in repositorio.PARAMETROS_MODELO_PADRAO[:-1]
        ]
        self._escrever_csv_bruto(linhas)
        with self.assertRaises(repositorio.ErroRepositorioParametrosModeloCorrompido):
            repositorio.carregar_linhas_parametros_modelo()

    def test_arquivo_com_valor_nao_numerico_e_rejeitado(self):
        linhas = [
            {
                "grupo": g,
                "indicador": i,
                "parametro": p,
                "valor_atual": (
                    "abc"
                    if (g, i, p) == ("SCORE", "EXPOSICAO_HIDRICA", "peso")
                    else str(padrao)
                ),
                "valor_padrao": str(padrao),
                "tipo": tipo,
                "atualizado_em": "2026-01-01T00:00:00+00:00",
            }
            for g, i, p, padrao, tipo in repositorio.PARAMETROS_MODELO_PADRAO
        ]
        self._escrever_csv_bruto(linhas)
        with self.assertRaises(repositorio.ErroRepositorioParametrosModeloCorrompido):
            repositorio.carregar_linhas_parametros_modelo()

    def test_arquivo_com_chave_duplicada_e_rejeitado(self):
        linhas = [
            {
                "grupo": g,
                "indicador": i,
                "parametro": p,
                "valor_atual": str(padrao),
                "valor_padrao": str(padrao),
                "tipo": tipo,
                "atualizado_em": "2026-01-01T00:00:00+00:00",
            }
            for g, i, p, padrao, tipo in repositorio.PARAMETROS_MODELO_PADRAO
        ]
        linhas.append(dict(linhas[0]))
        self._escrever_csv_bruto(linhas)
        with self.assertRaises(repositorio.ErroRepositorioParametrosModeloCorrompido):
            repositorio.carregar_linhas_parametros_modelo()

    def test_erro_de_corrupcao_e_logado(self):
        linhas = [
            {
                "grupo": g,
                "indicador": i,
                "parametro": p,
                "valor_atual": str(padrao),
                "valor_padrao": str(padrao),
                "tipo": tipo,
                "atualizado_em": "2026-01-01T00:00:00+00:00",
            }
            for g, i, p, padrao, tipo in repositorio.PARAMETROS_MODELO_PADRAO[:-1]
        ]
        self._escrever_csv_bruto(linhas)
        with self.assertLogs(repositorio.logger, level="ERROR"):
            with self.assertRaises(
                repositorio.ErroRepositorioParametrosModeloCorrompido
            ):
                repositorio.carregar_linhas_parametros_modelo()


if __name__ == "__main__":
    unittest.main()
