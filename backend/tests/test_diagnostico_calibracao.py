from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.exposicao.modelos import SerieHistoricaFonte
from backend.exposicao.politica import PerigoExposicao
from backend.scripts.diagnostico_calibracao import (
    NOMES_ARQUIVOS,
    executar_fazendas,
    montar_tabelas,
    salvar_tabelas,
    validar_tabelas,
)
from backend.tests.test_exposicao_avaliacao_exposicao import (
    DATA_REFERENCIA,
    criar_serie_avaliacao,
)
from backend.tests.test_exposicao_validacao_integrada import criar_geo


FAZENDA = {
    "id_fazenda": "fazenda-teste",
    "nome_fazenda": "Fazenda Teste",
    "cidade": "Sorriso",
    "uf": "MT",
    "latitude": "-12.545",
    "longitude": "-55.721",
    "area_ha": "100",
}


def _serie_com_id(serie: SerieHistoricaFonte, id_fazenda: str) -> SerieHistoricaFonte:
    dados = serie.model_dump()
    dados["id_fazenda"] = id_fazenda
    return SerieHistoricaFonte.model_validate(dados)


class ClienteFalso:
    def __init__(
        self,
        *,
        gaps_vento: set[date] | None = None,
        falhar_ids: set[str] | None = None,
    ) -> None:
        self.gaps_vento = gaps_vento or set()
        self.falhar_ids = falhar_ids or set()
        self.chamadas: list[str] = []

    def consultar(self, latitude, longitude, janela, *, id_fazenda=None):
        self.chamadas.append(str(id_fazenda))
        if id_fazenda in self.falhar_ids:
            raise TimeoutError("falha controlada")
        serie = criar_serie_avaliacao(gaps_vento=self.gaps_vento)
        return _serie_com_id(serie, str(id_fazenda))


class ProvedorFalso:
    def obter(self, *, id_fazenda, latitude, longitude):
        return criar_geo(20)


def _contexto_persistido(id_fazenda: str):
    return {
        "id_fazenda": id_fazenda,
        "latitude_referencia": -12.545,
        "longitude_referencia": -55.721,
        "area_ha_referencia": 100.0,
        "raio_equivalente_m": 564.19,
        "raio_analise_m": 1000.0,
        "declividade_media_graus": 20.0,
        "posicao_topografica_relativa_m": -1.5,
        "distancia_drenagem_m": 2000.0,
        "area_drenagem_montante_km2": 850.0,
        "algorithm_version": "fase1-v3",
        "calculado_em_utc": "2026-08-10T12:00:00+00:00",
        "qualidade": {
            "cobertura_srtm_pct": 100.0,
            "pixels_srtm_validos": 42,
            "drenagem_encontrada": True,
            "candidatos_drenagem": 3,
            "distancia_geodesica_final_m": 2000.0,
        },
        "fontes": [
            {"identificador": "USGS/SRTMGL1_003"},
            {"identificador": "MERIT/Hydro/v1_0_1"},
        ],
    }


def _executar(
    fazendas=None,
    *,
    cliente=None,
):
    return executar_fazendas(
        fazendas or [FAZENDA],
        data_referencia=DATA_REFERENCIA,
        cliente_nasa=cliente or ClienteFalso(),
        provedor_contexto=ProvedorFalso(),
        buscar_contexto=_contexto_persistido,
    )


class TestGeracaoTabelas(unittest.TestCase):
    def test_gera_seis_tabelas_com_cardinalidades_esperadas(self):
        execucoes = _executar()
        tabelas = montar_tabelas(execucoes)

        self.assertIsNone(execucoes[0].falha)
        self.assertEqual(len(tabelas.resumo), 1)
        self.assertEqual(len(tabelas.contexto), 1)
        self.assertEqual(len(tabelas.meteorologia), 2)
        self.assertEqual(len(tabelas.perigos), 10)
        self.assertEqual(len(tabelas.features), 187)
        self.assertEqual(len(tabelas.fontes), 6)

        with TemporaryDirectory() as temporario:
            caminhos = salvar_tabelas(tabelas, Path(temporario))
            self.assertEqual(tuple(path.name for path in caminhos), NOMES_ARQUIVOS)
            self.assertTrue(all(path.exists() for path in caminhos))
            with caminhos[0].open(encoding="utf-8", newline="") as arquivo:
                leitor = csv.DictReader(arquivo, delimiter=";")
                self.assertEqual(len(list(leitor)), 1)

    def test_estatisticas_simples_e_separacao_das_janelas(self):
        tabelas = montar_tabelas(_executar())
        anterior, atual = tabelas.meteorologia

        self.assertEqual(anterior["janela"], "ANTERIOR")
        self.assertEqual(atual["janela"], "ATUAL")
        self.assertEqual(anterior["data_inicio"], DATA_REFERENCIA - timedelta(days=179))
        self.assertEqual(atual["data_inicio"], DATA_REFERENCIA - timedelta(days=89))
        for linha in (anterior, atual):
            self.assertEqual(linha["dias_esperados"], 90)
            self.assertEqual(linha["dias_com_registro"], 90)
            self.assertEqual(linha["precipitacao_total_mm"], 900.0)
            self.assertEqual(linha["precipitacao_media_mm"], 10.0)
            self.assertEqual(linha["temperatura_maxima_media_c"], 30.0)
            self.assertEqual(linha["vento_medio_m_s"], 3.0)
            self.assertEqual(linha["vento_maximo_das_medias_diarias_m_s"], 3.0)

    def test_warmup_e_indices_diarios_reutilizados(self):
        tabelas = montar_tabelas(_executar())
        warmup = [linha for linha in tabelas.features if linha["janela"] == "WARMUP"]
        anterior = [
            linha for linha in tabelas.features if linha["janela"] == "ANTERIOR"
        ]
        atual = [linha for linha in tabelas.features if linha["janela"] == "ATUAL"]

        self.assertEqual(len(warmup), 7)
        self.assertEqual(len(anterior), 90)
        self.assertEqual(len(atual), 90)
        self.assertTrue(all(linha["indice_hidrico"] is None for linha in warmup))
        self.assertTrue(any(linha["indice_hidrico"] is not None for linha in anterior))


class TestMissingEIsolamento(unittest.TestCase):
    def test_missing_permanece_vazio_e_vento_nao_e_chamado_de_rajada(self):
        data_gap = DATA_REFERENCIA - timedelta(days=10)
        tabelas = montar_tabelas(_executar(cliente=ClienteFalso(gaps_vento={data_gap})))
        feature_gap = next(
            linha for linha in tabelas.features if linha["data"] == data_gap
        )
        meteo_atual = next(
            linha for linha in tabelas.meteorologia if linha["janela"] == "ATUAL"
        )

        self.assertIsNone(feature_gap["velocidade_vento_media_m_s"])
        self.assertEqual(meteo_atual["dias_vento_disponivel"], 89)
        self.assertEqual(meteo_atual["vento_medio_m_s"], 3.0)
        self.assertEqual(meteo_atual["vento_maximo_das_medias_diarias_m_s"], 3.0)
        self.assertNotIn(
            "rajada",
            " ".join(tabelas.meteorologia[0]).lower(),
        )

        with TemporaryDirectory() as temporario:
            caminhos = salvar_tabelas(tabelas, Path(temporario))
            caminho_features = next(
                caminho
                for caminho in caminhos
                if caminho.name == "05_features_diarias.csv"
            )
            with caminho_features.open(encoding="utf-8", newline="") as arquivo:
                linhas = list(csv.DictReader(arquivo, delimiter=";"))
            serializada = next(
                linha for linha in linhas if linha["data"] == data_gap.isoformat()
            )
            self.assertEqual(serializada["velocidade_vento_media_m_s"], "")

    def test_falha_de_uma_fazenda_nao_interrompe_as_demais(self):
        fazenda_falha = {
            **FAZENDA,
            "id_fazenda": "fazenda-falha",
            "nome_fazenda": "Falha",
        }
        cliente = ClienteFalso(falhar_ids={"fazenda-falha"})
        execucoes = _executar([FAZENDA, fazenda_falha], cliente=cliente)
        tabelas = montar_tabelas(execucoes)

        self.assertIsNone(execucoes[0].falha)
        self.assertIsNotNone(execucoes[1].falha)
        self.assertEqual(len(tabelas.resumo), 2)
        self.assertEqual(len(tabelas.meteorologia), 4)
        self.assertEqual(len(tabelas.perigos), 10)
        self.assertEqual(len(tabelas.features), 187)
        self.assertEqual(len(tabelas.fontes), 12)
        resumo_falha = next(
            linha for linha in tabelas.resumo if linha["id_fazenda"] == "fazenda-falha"
        )
        self.assertEqual(resumo_falha["erro"], "FONTE_METEOROLOGICA_INDISPONIVEL")


class TestProvenienciaEPesos(unittest.TestCase):
    def test_proveniencia_reflete_fontes_executadas_e_nao_executadas(self):
        tabelas = montar_tabelas(_executar())
        por_fonte = {linha["fonte"]: linha for linha in tabelas.fontes}

        self.assertEqual(por_fonte["NASA_POWER"]["estado"], "UTILIZADA_MATEMATICAMENTE")
        self.assertEqual(por_fonte["SRTM"]["estado"], "UTILIZADA_MATEMATICAMENTE")
        self.assertEqual(por_fonte["MERIT_HYDRO"]["estado"], "CARREGADA_COMO_CONTEXTO")
        for fonte in ("OPEN_METEO", "MAPBIOMAS", "INMET"):
            self.assertEqual(
                por_fonte[fonte]["estado"], "IMPLEMENTADA_MAS_NAO_EXECUTADA"
            )

    def test_pesos_somam_um_e_trafegabilidade_participa_normalmente(self):
        tabelas = montar_tabelas(_executar())
        for janela in ("ANTERIOR", "ATUAL"):
            linhas = [linha for linha in tabelas.perigos if linha["janela"] == janela]
            participantes = [linha for linha in linhas if linha["participa_score"]]
            self.assertAlmostEqual(
                sum(linha["peso"] for linha in participantes),
                1.0,
            )
            trafegabilidade = next(
                linha
                for linha in linhas
                if linha["perigo"] == PerigoExposicao.TRAFEGABILIDADE
            )
            self.assertEqual(trafegabilidade["peso"], 0.25)
            self.assertTrue(trafegabilidade["participa_score"])
            self.assertIsNotNone(trafegabilidade["contribuicao"])

    def test_validacao_detecta_divergencia_diagnostica_do_score(self):
        execucoes = _executar()
        tabelas = montar_tabelas(execucoes)
        linha = next(
            item
            for item in tabelas.perigos
            if item["janela"] == "ATUAL" and item["participa_score"]
        )
        original = linha["contribuicao"]
        linha["contribuicao"] = float(original) + 1.0
        with self.assertRaisesRegex(ValueError, "score diverge"):
            validar_tabelas(execucoes, tabelas)


if __name__ == "__main__":
    unittest.main()
