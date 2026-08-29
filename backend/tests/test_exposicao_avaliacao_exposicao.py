from __future__ import annotations

import inspect
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from pydantic import ValidationError

from backend.exposicao import (
    AVISO_WARMUP_INCOMPLETO,
    DIAS_AQUISICAO_DUAS_JANELAS_90D,
    DirecaoVariacaoScore,
    FinalidadeJanela,
    JanelaHistorica,
    PerigoExposicao,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    ResultadoAvaliacaoExposicaoMaquinario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    executar_avaliacao_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
)
from backend.risco.modelos import FonteDado
from backend.tests.test_exposicao_validacao_integrada import (
    VENTO_NASA,
    VENTO_OPEN_METEO,
    criar_geo,
)


DATA_REFERENCIA = date(2026, 8, 11)


def criar_serie_avaliacao(
    *,
    dias: int = DIAS_AQUISICAO_DUAS_JANELAS_90D,
    fonte: FonteDado = FonteDado.NASA_POWER,
    cenario: str = "estavel",
    gaps_precipitacao: set[date] | None = None,
    gaps_vento: set[date] | None = None,
    gaps_umidade: set[date] | None = None,
    datas_sem_registro: set[date] | None = None,
) -> SerieHistoricaFonte:
    periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    inicio_atual = DATA_REFERENCIA - timedelta(days=89)
    registros = []
    for indice in range(dias):
        data_registro = periodo.inicio + timedelta(days=indice)
        if data_registro in (datas_sem_registro or set()):
            continue
        atual = data_registro >= inicio_atual
        if cenario == "aumento":
            chuva, temperatura, umidade, vento = (
                (100.0, 35.0, 30.0, 8.0) if atual else (0.0, 25.0, 70.0, 0.0)
            )
            if not atual and indice == 0:
                # Uma chuva mínima no primeiro dia da série inteira estabelece
                # "dias desde a última chuva relevante" sem mudar o cenário
                # seco-depois-molhado; sem isso, uma janela inteiramente seca
                # desde o início da aquisição deixa esse campo indisponível
                # (nunca choveu, então não há referência), não zero.
                chuva = 1.0
        elif cenario == "reducao":
            chuva, temperatura, umidade, vento = (
                (0.0, 25.0, 70.0, 0.0) if atual else (100.0, 35.0, 30.0, 8.0)
            )
        else:
            chuva, temperatura, umidade, vento = 10.0, 30.0, 50.0, 3.0
        registros.append(
            RegistroMeteorologicoDiario(
                data=data_registro,
                precipitacao_mm=(
                    None if data_registro in (gaps_precipitacao or set()) else chuva
                ),
                temperatura_media_c=temperatura - 3,
                temperatura_maxima_c=temperatura,
                temperatura_minima_c=temperatura - 6,
                umidade_media_pct=(
                    None if data_registro in (gaps_umidade or set()) else umidade
                ),
                velocidade_vento_media_m_s=(
                    None if data_registro in (gaps_vento or set()) else vento
                ),
            )
        )
    if fonte == FonteDado.NASA_POWER:
        produto = TipoProdutoHistorico.HISTORICO_REGIONAL
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        )
        vento_meta = VENTO_NASA
        dataset = "NASA/POWER DAILY"
    else:
        produto = TipoProdutoHistorico.REANALISE_MODELADA
        referencia = ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC)
        vento_meta = VENTO_OPEN_METEO
        dataset = "Open-Meteo Historical Weather API"
    return SerieHistoricaFonte.criar(
        id_fazenda="fazenda-teste",
        fonte=fonte,
        tipo_produto=produto,
        dataset=dataset,
        periodo_solicitado=periodo,
        referencia_temporal=referencia,
        registros=registros,
        coletado_em_utc=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        metadados_origem={"vento": vento_meta},
    )


def executar(serie: SerieHistoricaFonte):
    return executar_avaliacao_exposicao_maquinario(
        serie,
        criar_geo(20),
        criar_politica_agrishield_equip_v1(),
    )


class TestPipelineCompleto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.serie = criar_serie_avaliacao()
        cls.resultado = executar(cls.serie)

    def test_execucao_completa_divide_sete_mais_noventa_mais_noventa(self):
        resultado = self.resultado
        self.assertEqual(resultado.periodo_aquisicao.dias_esperados, 187)
        self.assertEqual(resultado.dias_contexto_esperados, 7)
        self.assertEqual(resultado.dias_contexto_disponiveis, 7)
        self.assertTrue(resultado.warmup_completo)
        self.assertEqual(resultado.janela_anterior.dias_esperados, 90)
        self.assertEqual(resultado.janela_atual.dias_esperados, 90)
        self.assertEqual(
            resultado.janela_anterior.fim + timedelta(days=1),
            resultado.janela_atual.inicio,
        )

    def test_janelas_tem_finalidade_e_datas_corretas(self):
        self.assertEqual(
            self.resultado.janela_anterior.finalidade,
            FinalidadeJanela.COMPARACAO_ANTERIOR,
        )
        self.assertEqual(self.resultado.janela_atual.finalidade, FinalidadeJanela.ATUAL)
        self.assertEqual(
            self.resultado.janela_anterior.inicio,
            DATA_REFERENCIA - timedelta(days=179),
        )
        self.assertEqual(
            self.resultado.janela_atual.inicio, DATA_REFERENCIA - timedelta(days=89)
        )

    def test_cinco_perigos_e_validacao_integrada_em_cada_janela(self):
        for validacao, janela in (
            (self.resultado.validacao_anterior, self.resultado.janela_anterior),
            (self.resultado.validacao_atual, self.resultado.janela_atual),
        ):
            with self.subTest(janela=janela.finalidade):
                perigos = (
                    validacao.exposicao_hidrica.perigo,
                    validacao.trafegabilidade.perigo,
                    validacao.instabilidade.perigo,
                    validacao.propagacao_fogo.perigo,
                    validacao.tempestade.perigo,
                )
                self.assertEqual(perigos, tuple(PerigoExposicao))
                self.assertEqual(validacao.janela, janela)

    def test_composicao_unica_dois_scores_e_comparacao(self):
        resultado = self.resultado
        self.assertEqual(
            resultado.politica_composicao.politica_id, resultado.politica_id
        )
        self.assertEqual(resultado.score_anterior.politica_id, resultado.politica_id)
        self.assertEqual(resultado.score_atual.politica_id, resultado.politica_id)
        self.assertEqual(
            resultado.comparacao.score_anterior, resultado.score_anterior.score
        )
        self.assertEqual(resultado.comparacao.score_atual, resultado.score_atual.score)
        self.assertTrue(resultado.avaliacao_publicavel)

    def test_features_e_componentes_sao_chamados_na_cardinalidade_correta(self):
        from backend.exposicao import avaliacao_exposicao

        with (
            patch.object(
                avaliacao_exposicao,
                "calcular_features_diarias_compartilhadas",
                wraps=avaliacao_exposicao.calcular_features_diarias_compartilhadas,
            ) as features,
            patch.object(
                avaliacao_exposicao,
                "validar_cinco_perigos",
                wraps=avaliacao_exposicao.validar_cinco_perigos,
            ) as perigos,
            patch.object(
                avaliacao_exposicao,
                "criar_politica_composicao_score",
                wraps=avaliacao_exposicao.criar_politica_composicao_score,
            ) as composicao,
            patch.object(
                avaliacao_exposicao,
                "calcular_score_exposicao_maquinario",
                wraps=avaliacao_exposicao.calcular_score_exposicao_maquinario,
            ) as score,
            patch.object(
                avaliacao_exposicao,
                "comparar_scores_exposicao_90d",
                wraps=avaliacao_exposicao.comparar_scores_exposicao_90d,
            ) as comparacao,
        ):
            executar(self.serie)
        self.assertEqual(features.call_count, 1)
        self.assertEqual(perigos.call_count, 2)
        self.assertEqual(composicao.call_count, 1)
        self.assertEqual(score.call_count, 2)
        self.assertEqual(comparacao.call_count, 1)


class TestCenariosTemporais(unittest.TestCase):
    def test_aumento(self):
        resultado = executar(criar_serie_avaliacao(cenario="aumento"))
        self.assertGreater(resultado.score_atual.score, resultado.score_anterior.score)
        self.assertEqual(resultado.comparacao.direcao, DirecaoVariacaoScore.AUMENTO)

    def test_reducao(self):
        resultado = executar(criar_serie_avaliacao(cenario="reducao"))
        self.assertLess(resultado.score_atual.score, resultado.score_anterior.score)
        self.assertEqual(resultado.comparacao.direcao, DirecaoVariacaoScore.REDUCAO)

    def test_estabilidade(self):
        resultado = executar(criar_serie_avaliacao(cenario="estavel"))
        self.assertEqual(resultado.score_atual.score, resultado.score_anterior.score)
        self.assertEqual(resultado.comparacao.variacao_pontos, 0)
        self.assertEqual(resultado.comparacao.direcao, DirecaoVariacaoScore.ESTAVEL)

    def test_warmup_parcial_nao_falha_nem_imputa(self):
        periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 187)
        gap = periodo.inicio + timedelta(days=2)
        resultado = executar(criar_serie_avaliacao(gaps_precipitacao={gap}))
        self.assertEqual(resultado.dias_contexto_disponiveis, 6)
        self.assertFalse(resultado.warmup_completo)
        self.assertIn(AVISO_WARMUP_INCOMPLETO, resultado.avisos_metodologicos)
        primeira = resultado.features_compartilhadas.por_data(
            resultado.janela_anterior.inicio
        )
        self.assertIsNone(primeira.precipitacao_d4_d7)

    def test_somente_180_dias_mantem_janelas_e_marca_warmup_incompleto(self):
        resultado = executar(criar_serie_avaliacao(dias=180))
        self.assertEqual(resultado.dias_contexto_disponiveis, 0)
        self.assertFalse(resultado.warmup_completo)
        self.assertEqual(
            resultado.janela_anterior.inicio, DATA_REFERENCIA - timedelta(days=179)
        )
        self.assertEqual(
            resultado.janela_atual.inicio, DATA_REFERENCIA - timedelta(days=89)
        )
        self.assertEqual(resultado.periodo_features.dias_esperados, 180)

    def test_intervalo_menor_que_180_dias_e_rejeitado(self):
        with self.assertRaisesRegex(ValueError, "duas janelas"):
            executar(criar_serie_avaliacao(dias=179))

    def test_menos_de_187_registros_com_intervalo_completo_e_aceito(self):
        periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 187)
        ausentes = {
            periodo.inicio + timedelta(days=20),
            periodo.inicio + timedelta(days=80),
            periodo.inicio + timedelta(days=150),
        }
        serie = criar_serie_avaliacao(datas_sem_registro=ausentes)
        resultado = executar(serie)
        self.assertEqual(len(serie.registros), 184)
        self.assertEqual(len(resultado.features_compartilhadas.dias), 187)
        for data_gap in ausentes:
            self.assertIsNone(
                resultado.features_compartilhadas.por_data(data_gap).precipitacao_d0
            )


class TestGapsEQualidade(unittest.TestCase):
    def setUp(self):
        inicio_atual = DATA_REFERENCIA - timedelta(days=89)
        self.gaps = {inicio_atual + timedelta(days=indice) for indice in range(25)}

    def test_gap_de_chuva_permanece_none_e_afeta_perigos_dependentes(self):
        resultado = executar(criar_serie_avaliacao(gaps_precipitacao=self.gaps))
        dia = resultado.features_compartilhadas.por_data(min(self.gaps))
        self.assertIsNone(dia.precipitacao_d0)
        self.assertNotEqual(dia.precipitacao_d0, 0)
        self.assertFalse(resultado.score_atual.score_publicavel)
        self.assertIn(
            PerigoExposicao.EXPOSICAO_HIDRICA,
            resultado.score_atual.perigos_indisponiveis,
        )

    def test_gap_de_vento_permanece_none_e_afeta_fogo_e_tempestade(self):
        resultado = executar(criar_serie_avaliacao(gaps_vento=self.gaps))
        dia = resultado.features_compartilhadas.por_data(min(self.gaps))
        self.assertIsNone(dia.velocidade_vento_media_m_s)
        self.assertIn(
            PerigoExposicao.INCENDIO, resultado.score_atual.perigos_indisponiveis
        )
        self.assertIn(
            PerigoExposicao.TEMPESTADES, resultado.score_atual.perigos_indisponiveis
        )

    def test_gap_de_umidade_permanece_none_e_afeta_fogo(self):
        resultado = executar(criar_serie_avaliacao(gaps_umidade=self.gaps))
        dia = resultado.features_compartilhadas.por_data(min(self.gaps))
        self.assertIsNone(dia.umidade_relativa)
        self.assertIn(
            PerigoExposicao.INCENDIO, resultado.score_atual.perigos_indisponiveis
        )

    def test_diagnosticos_sao_preservados_quando_avaliacao_nao_publicavel(self):
        resultado = executar(criar_serie_avaliacao(gaps_vento=self.gaps))
        self.assertFalse(resultado.avaliacao_publicavel)
        self.assertTrue(resultado.score_anterior.score_publicavel)
        self.assertFalse(resultado.score_atual.score_publicavel)
        self.assertFalse(resultado.comparacao.comparacao_publicavel)
        self.assertIsNotNone(resultado.validacao_atual)
        self.assertTrue(resultado.score_atual.perigos_indisponiveis)


class TestProvenienciaEContrato(unittest.TestCase):
    def test_nasa_e_open_meteo_preservam_proveniencia_sem_mistura(self):
        for fonte in (FonteDado.NASA_POWER, FonteDado.OPEN_METEO):
            with self.subTest(fonte=fonte):
                resultado = executar(criar_serie_avaliacao(fonte=fonte))
                self.assertEqual(resultado.fonte_meteorologica, fonte)
                self.assertEqual(resultado.features_compartilhadas.fonte, fonte)
                self.assertEqual(
                    resultado.validacao_anterior.fonte_meteorologica, fonte
                )
                self.assertEqual(resultado.validacao_atual.fonte_meteorologica, fonte)
                self.assertEqual(
                    resultado.validacao_anterior.dataset,
                    resultado.validacao_atual.dataset,
                )

    def test_determinismo_input_nao_mutado_e_imutabilidade(self):
        serie = criar_serie_avaliacao()
        antes = serie.model_dump()
        primeiro = executar(serie)
        segundo = executar(serie)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(serie.model_dump(), antes)
        with self.assertRaises(ValidationError):
            primeiro.avaliacao_publicavel = False

    def test_serializacao_coerente(self):
        resultado = executar(criar_serie_avaliacao())
        serializado = resultado.model_dump(mode="json")
        json.dumps(serializado)
        self.assertEqual(
            ResultadoAvaliacaoExposicaoMaquinario.model_validate(serializado),
            resultado,
        )

    def test_orquestracao_nao_duplica_regras_nem_acessa_io(self):
        from backend.exposicao import avaliacao_exposicao

        codigo = inspect.getsource(avaliacao_exposicao).lower()
        for termo in (
            "requests",
            "http://",
            "https://",
            "fastapi",
            "supabase",
            "classificar_indice",
            "peso =",
            "variacao_percentual =",
            "evento_perigo(",
            "datetime.now",
            "random",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
