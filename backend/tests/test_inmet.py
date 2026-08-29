from __future__ import annotations

from datetime import date, datetime, timezone
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import zipfile

import requests


BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "etl"))
sys.path.insert(0, str(BACKEND / "app"))

from app import main
from inmet.cliente import ClienteCatalogoInmet, ErroClienteInmet
from inmet.normalizacao import (
    calcular_qualidade,
    distancia_haversine_km,
    normalizar_catalogo,
    parsear_zip_historico,
    rankear_estacoes,
)
from inmet.repositorio import RepositorioInmetMemoria
from inmet.servico import ServicoInmet


CABECALHO_INMET = (
    "Data;Hora UTC;PRECIPITAÇÃO TOTAL, HORÁRIO (mm);"
    "PRESSAO ATMOSFERICA AO NIVEL DA ESTACAO, HORARIA (mB);"
    "PRESSÃO ATMOSFERICA MAX.NA HORA ANT. (AUT) (mB);"
    "PRESSÃO ATMOSFERICA MIN. NA HORA ANT. (AUT) (mB);"
    "RADIACAO GLOBAL (Kj/m²);"
    "TEMPERATURA DO AR - BULBO SECO, HORARIA (°C);"
    "TEMPERATURA DO PONTO DE ORVALHO (°C);"
    "TEMPERATURA MÁXIMA NA HORA ANT. (AUT) (°C);"
    "TEMPERATURA MÍNIMA NA HORA ANT. (AUT) (°C);"
    "TEMPERATURA ORVALHO MAX. NA HORA ANT. (AUT) (°C);"
    "TEMPERATURA ORVALHO MIN. NA HORA ANT. (AUT) (°C);"
    "UMIDADE REL. MAX. NA HORA ANT. (AUT) (%);"
    "UMIDADE REL. MIN. NA HORA ANT. (AUT) (%);"
    "UMIDADE RELATIVA DO AR, HORARIA (%);"
    "VENTO, DIREÇÃO HORARIA (gr) (° (gr));"
    "VENTO, RAJADA MAXIMA (m/s);"
    "VENTO, VELOCIDADE HORARIA (m/s);"
)


def criar_zip_teste(codigo: str = "A904") -> bytes:
    linhas = [
        "REGIAO:;CO",
        "UF:;MT",
        "ESTACAO:;SORRISO",
        f"CODIGO (WMO):;{codigo}",
        "LATITUDE:;-12,555",
        "LONGITUDE:;-55,72277777",
        "ALTITUDE:;379,31",
        "DATA DE FUNDACAO:;16/12/02",
        CABECALHO_INMET,
        "2026/07/30;0000 UTC;0;970,8;971;970;;28,1;19;29;27;20;18;60;50;58;;;1,2;",
        "2026/07/30;0100 UTC;;971,0;972;970;12,5;27,4;18;28;27;19;17;61;51;59;180;4,2;;",
    ]
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"INMET_CO_MT_{codigo}_SORRISO_01-01-2026_A_31-07-2026.CSV",
            "\n".join(linhas).encode("latin-1"),
        )
    return memoria.getvalue()


def item_catalogo(
    codigo="A904", latitude="-12.555", longitude="-55.72277777", **outros
):
    item = {
        "CD_ESTACAO": codigo,
        "DC_NOME": "SORRISO",
        "SG_ESTADO": "MT",
        "VL_LATITUDE": latitude,
        "VL_LONGITUDE": longitude,
        "VL_ALTITUDE": "379.31",
        "TP_ESTACAO": "Automatica",
        "SG_ENTIDADE": "INMET",
        "CD_SITUACAO": "Operante",
        "DT_INICIO_OPERACAO": "2002-12-16",
        "DT_FIM_OPERACAO": None,
    }
    item.update(outros)
    return item


class TestCatalogoInmet(unittest.TestCase):
    def test_normaliza_e_filtra_catalogo(self):
        payload = [
            item_catalogo(),
            item_catalogo("A002", TP_ESTACAO="Convencional"),
            item_catalogo("A003", SG_ENTIDADE="PARCEIRO"),
            item_catalogo("A004", CD_SITUACAO="Inoperante"),
            item_catalogo("A005", latitude="sem-coordenada"),
        ]
        estacoes = normalizar_catalogo(payload)
        self.assertEqual(1, len(estacoes))
        self.assertEqual("A904", estacoes[0]["codigo"])
        self.assertEqual(379.31, estacoes[0]["altitude_m"])

    def test_cliente_trata_timeout_e_resposta_invalida(self):
        sessao_timeout = Mock()
        sessao_timeout.get.side_effect = requests.Timeout()
        with self.assertRaises(ErroClienteInmet):
            ClienteCatalogoInmet(sessao=sessao_timeout).obter_estacoes()

        resposta = Mock()
        resposta.raise_for_status.return_value = None
        resposta.json.return_value = {"nao": "e uma lista"}
        sessao_invalida = Mock()
        sessao_invalida.get.return_value = resposta
        with self.assertRaises(ErroClienteInmet):
            ClienteCatalogoInmet(sessao=sessao_invalida).obter_estacoes()


class TestSelecaoEstacao(unittest.TestCase):
    def test_haversine_e_ranking_top_5_sem_distancia_maxima(self):
        self.assertAlmostEqual(0.0, distancia_haversine_km(-12, -55, -12, -55))
        estacoes = [
            {
                "codigo": f"A{codigo}",
                "latitude": -12.0 + deslocamento,
                "longitude": -55.0,
            }
            for codigo, deslocamento in (
                (6, 0.6),
                (1, 0.1),
                (5, 0.5),
                (2, 0.2),
                (4, 0.4),
                (3, 0.3),
            )
        ]
        ranking = rankear_estacoes(-12, -55, estacoes)
        self.assertEqual(["A1", "A2", "A3", "A4", "A5"], [e["codigo"] for e in ranking])
        self.assertGreater(ranking[-1]["distancia_km"], 0)

    def test_desempate_deterministico_por_codigo(self):
        estacoes = [
            {"codigo": "A002", "latitude": -12.0, "longitude": -55.0},
            {"codigo": "A001", "latitude": -12.0, "longitude": -55.0},
        ]
        ranking = rankear_estacoes(-12, -55, estacoes, limite=None)
        self.assertEqual(["A001", "A002"], [e["codigo"] for e in ranking])


class TestHistoricoInmet(unittest.TestCase):
    def setUp(self):
        self.ingerido = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)
        self.resultado = parsear_zip_historico(
            criar_zip_teste(),
            "A904",
            data_inicio=date(2026, 7, 30),
            data_fim=date(2026, 7, 30),
            ingerido_em_utc=self.ingerido,
        )

    def test_parser_timestamp_utc_e_codigo_unico(self):
        observacoes = self.resultado["observacoes"]
        self.assertEqual(2, len(observacoes))
        self.assertEqual(
            "2026-07-30T00:00:00+00:00", observacoes[0]["observado_em_utc"]
        )
        self.assertEqual({"A904"}, {item["codigo_estacao"] for item in observacoes})
        self.assertEqual("INMET", observacoes[0]["fonte"])

    def test_preserva_chuva_zero_e_converte_ausencia_em_null(self):
        primeira, segunda = self.resultado["observacoes"]
        self.assertEqual(0.0, primeira["precipitacao_mm"])
        self.assertIsNone(primeira["radiacao_kj_m2"])
        self.assertIsNone(primeira["rajada_m_s"])
        self.assertIsNone(segunda["precipitacao_mm"])
        self.assertIsNone(segunda["vento_m_s"])
        self.assertEqual(180.0, segunda["direcao_vento_graus"])

    def test_remove_coluna_final_vazia_e_normaliza_decimais(self):
        primeira = self.resultado["observacoes"][0]
        self.assertNotIn("", primeira)
        self.assertEqual(28.1, primeira["temperatura_c"])
        self.assertEqual(970.8, primeira["pressao_hpa"])
        self.assertEqual(1.2, primeira["vento_m_s"])

    def test_qualidade_por_variavel_sem_classificacao(self):
        qualidade = calcular_qualidade(
            self.resultado["observacoes"], date(2026, 7, 30), date(2026, 7, 30)
        )
        self.assertEqual(24, qualidade["horas_esperadas"])
        self.assertEqual(2, qualidade["horas_observadas"])
        self.assertEqual(
            2, qualidade["variaveis"]["temperatura_c"]["horas_disponiveis"]
        )
        self.assertEqual(
            1, qualidade["variaveis"]["precipitacao_mm"]["horas_disponiveis"]
        )
        self.assertEqual(
            4.17, qualidade["variaveis"]["precipitacao_mm"]["disponibilidade_pct"]
        )
        self.assertNotIn("classificacao", qualidade)


class TestServicoEApiInmet(unittest.TestCase):
    def setUp(self):
        self.fazenda = {
            "id_fazenda": "9",
            "nome_fazenda": "Nova",
            "numero_apolice": "123456",
            "cep": "78890000",
            "cidade": "Sorriso",
            "uf": "MT",
            "latitude": "-12.545",
            "longitude": "-55.721",
            "tipo_operacao": "campo",
            "proximidade_agua": "False",
        }

    def test_servico_coleta_uma_unica_estacao_e_faz_upsert(self):
        catalogo = Mock()
        catalogo.obter_estacoes.return_value = normalizar_catalogo(
            [
                item_catalogo("A904"),
                item_catalogo("A955", latitude="-13.075", longitude="-55.911"),
            ]
        )
        historico = Mock()
        historico.baixar_ano.return_value = criar_zip_teste()
        repositorio = RepositorioInmetMemoria()
        servico = ServicoInmet(
            cliente_catalogo=catalogo,
            cliente_historico=historico,
            repositorio=repositorio,
            buscar_fazenda=lambda _: self.fazenda,
        )
        primeiro = servico.coletar(
            "9", data_inicio=date(2026, 7, 30), data_fim=date(2026, 7, 30)
        )
        segundo = servico.coletar(
            "9", data_inicio=date(2026, 7, 30), data_fim=date(2026, 7, 30)
        )
        self.assertEqual("A904", primeiro["estacao"]["codigo"])
        self.assertTrue(
            all(item["codigo_estacao"] == "A904" for item in primeiro["observacoes"])
        )
        self.assertFalse(primeiro["diagnostico"]["estacoes_misturadas"])
        self.assertEqual(segundo, repositorio.buscar("9"))

    def test_get_le_repositorio_sem_chamada_externa(self):
        catalogo = Mock()
        historico = Mock()
        repositorio = RepositorioInmetMemoria()
        repositorio.salvar("9", {"id_fazenda": "9", "observacoes": []})
        servico = ServicoInmet(
            cliente_catalogo=catalogo,
            cliente_historico=historico,
            repositorio=repositorio,
            buscar_fazenda=lambda _: self.fazenda,
        )
        with patch.object(main, "_servico_inmet", servico):
            resposta = main.get_inmet("9")
        self.assertEqual("9", resposta["id_fazenda"])
        catalogo.obter_estacoes.assert_not_called()
        historico.baixar_ano.assert_not_called()

    def test_endpoints_delegam_apenas_ao_servico_inmet(self):
        servico = Mock()
        servico.listar_candidatos.return_value = {"candidatos": [{"codigo": "A904"}]}
        servico.coletar.return_value = {"estacao": {"codigo": "A904"}}
        entrada = main.ColetaInmetIn(data_inicio="2026-07-30", data_fim="2026-07-31")
        with patch.object(main, "_servico_inmet", servico):
            candidatos = main.get_candidatos_inmet("9")
            resultado = main.coletar_inmet("9", entrada)
        self.assertEqual("A904", candidatos["candidatos"][0]["codigo"])
        self.assertEqual("A904", resultado["estacao"]["codigo"])

    def test_score_dashboard_e_alertas_nao_chamam_inmet(self):
        servico = Mock()
        servico.listar_candidatos.side_effect = AssertionError(
            "INMET não deveria ser chamado"
        )
        servico.coletar.side_effect = AssertionError("INMET não deveria ser chamado")
        servico.obter.side_effect = AssertionError("INMET não deveria ser chamado")
        resumo = {"score": 20, "metricas_dia": {}, "fatores_risco": []}

        with patch.object(main, "_servico_inmet", servico), patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(
            main, "coletar_nasa_power", return_value=(Mock(), "teste")
        ), patch.object(
            main, "enriquecer", return_value=Mock()
        ), patch.object(
            main, "salvar_enriquecido_csv"
        ), patch.object(
            main, "consolidar_para_dashboard", return_value=resumo.copy()
        ), patch.object(
            main, "salvar_dashboard_csv"
        ):
            main._cache_score.clear()
            main._gerar_score("9")

        with patch.object(main, "_servico_inmet", servico), patch.object(
            main, "buscar_fazenda", return_value=self.fazenda
        ), patch.object(main, "_gerar_score", return_value=resumo), patch.object(
            main, "previsao_open_meteo", return_value={"alertas": [], "dias": []}
        ):
            main.get_alertas("9")

        with patch.object(main, "_servico_inmet", servico), patch.object(
            main, "_gerar_score", return_value=resumo
        ), patch.object(
            main, "get_alertas", return_value={"alertas": [], "previsao_5d": []}
        ):
            main.get_dashboard("9")

        servico.listar_candidatos.assert_not_called()
        servico.coletar.assert_not_called()
        servico.obter.assert_not_called()


if __name__ == "__main__":
    unittest.main()
