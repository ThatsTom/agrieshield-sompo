from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from pypdf import PdfReader


BACKEND = Path(__file__).resolve().parents[1]
for pasta in (BACKEND, BACKEND / "app", BACKEND / "etl"):
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))

from app import main  # noqa: E402
from app.relatorio_pdf import gerar_relatorio_pdf  # noqa: E402
import etapa1_cadastro_fazendas as cadastro  # noqa: E402


def entrada_completa(**mudancas):
    dados = {
        "nome_fazenda": "Fazenda Teste",
        "numero_apolice": "AP-001",
        "apolices": ["AP-001", "AP-002", "AP-002"],
        "cep": "78890000",
        "cidade": "Sorriso",
        "uf": "MT",
        "area_ha": 120,
        "latitude": -12.545,
        "longitude": -55.721,
        "poligono": [
            [-55.721, -12.545],
            [-55.710, -12.550],
            [-55.725, -12.560],
        ],
    }
    dados.update(mudancas)
    return main.FazendaIn(**dados)


class PortfolioFeaturesTests(unittest.TestCase):
    def test_multiplas_apolices_sao_deduplicadas_e_poligono_vira_geojson(self):
        entrada = entrada_completa()
        self.assertEqual(["AP-001", "AP-002"], entrada.apolices)
        persistencia = main._dados_persistencia_fazenda(entrada)
        normalizada = main._normalizar_fazenda(
            {
                **persistencia,
                "id_fazenda": "42",
                "arquivada": "False",
            }
        )
        self.assertEqual(["AP-001", "AP-002"], normalizada["apolices"])
        self.assertEqual(3, len(normalizada["poligono"]))
        self.assertEqual([-55.721, -12.545], normalizada["poligono"][0])

    def test_poligono_exige_tres_vertices_validos(self):
        with self.assertRaises(ValidationError):
            entrada_completa(poligono=[[-55.7, -12.5], [-55.8, -12.6]])
        with self.assertRaises(ValidationError):
            entrada_completa(
                poligono=[[-200, -12.5], [-55.8, -12.6], [-55.9, -12.7]]
            )

    def test_arquivamento_e_reversivel_no_csv(self):
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / "fazendas.csv"
            with patch.object(cadastro, "ARQUIVO_FAZENDAS", arquivo):
                cadastro.criar_base_se_nao_existir()
                arquivada = cadastro.definir_arquivamento("1", True)
                restaurada = cadastro.definir_arquivamento("1", False)
        self.assertEqual("True", arquivada["arquivada"])
        self.assertEqual("False", restaurada["arquivada"])

    def test_job_climatico_publica_progresso_e_resultado(self):
        id_fazenda = "job-teste"
        main._jobs_climaticos.pop(id_fazenda, None)

        def gerar(_id, *, forcar, progresso):
            self.assertTrue(forcar)
            progresso(25, "Consultando NASA POWER")
            progresso(85, "Persistindo resumo climático")
            return {
                "score": 44,
                "condicao_atual": "ATENÇÃO",
                "data_referencia": "2026-08-26",
                "origem_dados": "nasa_power",
            }

        with patch.object(main, "_gerar_score", side_effect=gerar):
            main._executar_job_climatico(id_fazenda, "abc")
        job = main._jobs_climaticos[id_fazenda]
        self.assertEqual("concluido", job["status"])
        self.assertEqual(100, job["progresso"])
        self.assertEqual("nasa_power", job["score_preview"]["origem_dados"])

    def test_relatorio_pdf_tem_conteudo_e_uma_pagina_legivel(self):
        fazenda = {
            "id": "42",
            "id_fazenda": "42",
            "nome_fazenda": "Fazenda Teste",
            "apolices": ["AP-001", "AP-002"],
            "numero_apolice": "AP-001",
            "cidade": "Sorriso",
            "uf": "MT",
            "cep": "78890-000",
            "logradouro": "Rodovia MT-242",
            "area_ha": 120,
            "tipo_operacao": "campo",
            "latitude": -12.545,
            "longitude": -55.721,
            "poligono": [[-55.7, -12.5], [-55.8, -12.6], [-55.9, -12.5]],
        }
        resumo = {
            "score": 44,
            "condicao_atual": "ATENÇÃO",
            "data_referencia": "2026-08-26",
            "origem_dados": "nasa_power",
        }
        pdf = gerar_relatorio_pdf(fazenda, resumo, "AP-002")
        self.assertTrue(pdf.startswith(b"%PDF"))
        leitor = PdfReader(BytesIO(pdf))
        self.assertEqual(1, len(leitor.pages))
        texto = leitor.pages[0].extract_text()
        self.assertIn("Fazenda Teste", texto)
        self.assertIn("AP-002", texto)
        self.assertIn("NASA POWER", texto)


if __name__ == "__main__":
    unittest.main()
