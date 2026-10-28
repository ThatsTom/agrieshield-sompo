from __future__ import annotations

from datetime import date, timedelta
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app import main
from backend.app.maquinarios import (
    CABECALHO_CSV_MAQUINARIOS,
    MaquinarioIn,
    modelo_csv_maquinarios,
    resumo_maquinarios,
    validar_csv_maquinarios,
)


def entrada_valida(**mudancas):
    base = {
        "tipo_equipamento": "TRATOR",
        "marca": "JOHN_DEERE",
        "modelo": "7230J",
        "ano_fabricacao": 2022,
        "chassi": " demo-01 ",
        "apelido": "Trator 1",
        "horimetro_atual": 1250.5,
        "hodometro_atual": None,
        "media_horas_dia": 8,
        "possui_seguro": True,
        "seguradora": "OUTRA",
        "seguradora_outro": "Seguradora demonstrativa",
        "vencimento_apolice": "2027-11-15",
    }
    base.update(mudancas)
    return base


class TestModeloMaquinario(unittest.TestCase):
    def test_normaliza_chassi_e_aceita_equipamento_motorizado(self):
        modelo = MaquinarioIn.model_validate(entrada_valida())

        self.assertEqual("DEMO-01", modelo.chassi)
        self.assertEqual(date(2027, 11, 15), modelo.vencimento_apolice)

    def test_equipamento_passivo_nao_exige_horimetro(self):
        modelo = MaquinarioIn.model_validate(
            entrada_valida(
                tipo_equipamento="PLANTADEIRA",
                marca="STARA",
                horimetro_atual=None,
                possui_seguro=False,
                seguradora=None,
                vencimento_apolice=None,
            )
        )
        self.assertIsNone(modelo.horimetro_atual)

    def test_seguro_ativo_exige_seguradora_e_vencimento(self):
        with self.assertRaises(ValidationError):
            MaquinarioIn.model_validate(
                entrada_valida(seguradora=None, vencimento_apolice=None)
            )

    def test_outros_exige_nome_real(self):
        with self.assertRaises(ValidationError):
            MaquinarioIn.model_validate(entrada_valida(marca="OUTROS"))

    def test_campos_livres_respeitam_o_minimo_do_banco(self):
        for mudanca in (
            {"chassi": "X"},
            {"marca": "OUTROS", "marca_outro": "X"},
            {"seguradora": "OUTRA", "seguradora_outro": "X"},
        ):
            with self.subTest(mudanca=mudanca), self.assertRaises(ValidationError):
                MaquinarioIn.model_validate(entrada_valida(**mudanca))


class TestCsvMaquinarios(unittest.TestCase):
    def test_modelo_tem_bom_cabecalho_e_ponto_e_virgula(self):
        conteudo = modelo_csv_maquinarios()
        texto = conteudo.decode("utf-8-sig")

        self.assertTrue(conteudo.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(";".join(CABECALHO_CSV_MAQUINARIOS), texto.strip())

    def test_valida_decimal_brasileiro_e_booleano(self):
        cabecalho = ";".join(CABECALHO_CSV_MAQUINARIOS)
        linha = ";".join(
            [
                "TRATOR",
                "JOHN DEERE",
                "",
                "7230J",
                "2022",
                "CSV-01",
                "Trator",
                "1.250,5",
                "",
                "8,0",
                "SIM",
                "OUTRA",
                "Seguradora demonstrativa",
                "2027-11-15",
            ]
        )

        registros, erros = validar_csv_maquinarios(f"{cabecalho}\n{linha}\n")

        self.assertEqual([], erros)
        self.assertEqual(1, len(registros))
        self.assertEqual(1250.5, registros[0].horimetro_atual)

    def test_rejeita_arquivo_inteiro_quando_ha_chassi_duplicado(self):
        cabecalho = ";".join(CABECALHO_CSV_MAQUINARIOS)
        linha = ";".join(
            [
                "PLANTADEIRA", "STARA", "", "Estrela", "2022", "DUP-1",
                "", "", "", "", "NAO", "", "", "",
            ]
        )
        registros, erros = validar_csv_maquinarios(
            f"{cabecalho}\n{linha}\n{linha}\n"
        )

        self.assertEqual(1, len(registros))
        self.assertEqual("chassi", erros[0]["campo"])


class TestResumoMaquinarios(unittest.TestCase):
    def test_agrega_seguro_uso_e_composicao(self):
        resumo = resumo_maquinarios(
            [
                {
                    "tipo_equipamento": "TRATOR",
                    "ano_fabricacao": 2022,
                    "horimetro_atual": 100,
                    "media_horas_dia": 8,
                    "possui_seguro": True,
                    "vencimento_apolice": "2026-11-15",
                },
                {
                    "tipo_equipamento": "PLANTADEIRA",
                    "ano_fabricacao": 2020,
                    "possui_seguro": False,
                },
            ],
            referencia=date(2026, 9, 28),
        )

        self.assertEqual(2, resumo["total"])
        self.assertEqual(1, resumo["segurados"])
        self.assertEqual(1, resumo["seguros_vigentes"])
        self.assertEqual(0, resumo["vencendo_30_dias"])
        self.assertEqual(1, resumo["vencendo_60_dias"])
        self.assertEqual(1, resumo["vencendo_90_dias"])
        self.assertEqual(8, resumo["horas_dia_estimadas"])
        self.assertEqual(1, resumo["horas_dia_informadas"])
        self.assertEqual(1, resumo["horimetros_informados"])
        self.assertEqual({"PLANTADEIRA": 1, "TRATOR": 1}, resumo["por_tipo"])

    def test_separa_seguro_vigente_vencido_e_janelas_de_renovacao(self):
        referencia = date(2026, 9, 28)
        vencimentos = [
            referencia - timedelta(days=1),
            referencia,
            referencia + timedelta(days=30),
            referencia + timedelta(days=31),
            referencia + timedelta(days=61),
        ]
        resumo = resumo_maquinarios(
            [
                {
                    "tipo_equipamento": "TRATOR",
                    "possui_seguro": True,
                    "vencimento_apolice": vencimento.isoformat(),
                }
                for vencimento in vencimentos
            ],
            referencia=referencia,
        )

        self.assertEqual(5, resumo["segurados"])
        self.assertEqual(4, resumo["seguros_vigentes"])
        self.assertEqual(1, resumo["seguros_vencidos"])
        self.assertEqual(2, resumo["vencendo_30_dias"])
        self.assertEqual(3, resumo["vencendo_60_dias"])
        self.assertEqual(4, resumo["vencendo_90_dias"])
        self.assertEqual(80, resumo["percentual_seguro_vigente"])


class TestApiMaquinarios(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)
        self.fazenda = {"id_fazenda": "5", "arquivada": "False"}

    @patch.object(main, "cadastrar_maquinario")
    @patch.object(main, "chassis_existentes", return_value=set())
    @patch.object(main, "buscar_fazenda")
    def test_cadastro_individual_vincula_id_da_rota(
        self, buscar, _chassis, cadastrar
    ):
        buscar.return_value = self.fazenda
        cadastrar.return_value = {"id_maquinario": 10, "id_fazenda": 5}

        resposta = self.client.post(
            "/api/fazendas/5/maquinarios", json=entrada_valida()
        )

        self.assertEqual(201, resposta.status_code)
        self.assertEqual("5", cadastrar.call_args.args[0])
        self.assertEqual("manual", cadastrar.call_args.args[1]["origem_cadastro"])

    def test_download_do_modelo_csv(self):
        resposta = self.client.get("/api/maquinarios/modelo.csv")

        self.assertEqual(200, resposta.status_code)
        self.assertTrue(resposta.content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("modelo-maquinarios", resposta.headers["content-disposition"])

    @patch.object(main, "cadastrar_maquinarios")
    @patch.object(main, "chassis_existentes", return_value=set())
    @patch.object(main, "buscar_fazenda")
    def test_csv_invalido_nao_grava_nenhuma_linha(
        self, buscar, _chassis, cadastrar
    ):
        buscar.return_value = self.fazenda
        cabecalho = ";".join(CABECALHO_CSV_MAQUINARIOS)
        resposta = self.client.post(
            "/api/fazendas/5/maquinarios/importacoes",
            json={"conteudo_csv": f"{cabecalho}\nTRATOR;INVALIDO\n"},
        )

        self.assertEqual(422, resposta.status_code)
        cadastrar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
