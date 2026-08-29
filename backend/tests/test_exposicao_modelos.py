from __future__ import annotations

import math
import unittest
from datetime import date, datetime, timedelta, timezone

from pydantic import ValidationError

from backend.exposicao import (
    VARIAVEIS_METEOROLOGICAS,
    FinalidadeJanela,
    GapTemporal,
    JanelaHistorica,
    QualidadeHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
)
from backend.risco.modelos import FonteDado, NaturezaDado


DATA_REFERENCIA = date(2026, 8, 11)


def registro_completo(data_registro: date, *, chuva: float = 1.0):
    return RegistroMeteorologicoDiario(
        data=data_registro,
        precipitacao_mm=chuva,
        temperatura_media_c=24.0,
        temperatura_maxima_c=30.0,
        temperatura_minima_c=18.0,
        umidade_media_pct=70.0,
    )


def criar_serie(
    fonte: FonteDado,
    tipo_produto: TipoProdutoHistorico,
    registros: tuple[RegistroMeteorologicoDiario, ...],
    *,
    janela: JanelaHistorica | None = None,
    referencia_temporal: ReferenciaTemporalHistorica | None = None,
    metadados: dict | None = None,
):
    return SerieHistoricaFonte.criar(
        id_fazenda="1",
        fonte=fonte,
        tipo_produto=tipo_produto,
        dataset="dataset-oficial",
        periodo_solicitado=janela or JanelaHistorica.criar_atual(DATA_REFERENCIA, 4),
        referencia_temporal=referencia_temporal
        or ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC),
        registros=registros,
        coletado_em_utc=datetime(2026, 8, 12, 12, tzinfo=timezone.utc),
        metadados_origem=metadados,
    )


class TestJanelaHistorica(unittest.TestCase):
    def test_janela_90_dias_inclusivos(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA)
        self.assertEqual(janela.inicio, DATA_REFERENCIA - timedelta(days=89))
        self.assertEqual((janela.fim - janela.inicio).days + 1, 90)
        self.assertEqual(janela.dias_esperados, 90)

    def test_janela_180_dias_inclusivos(self):
        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        self.assertEqual(janela.inicio, DATA_REFERENCIA - timedelta(days=179))
        self.assertEqual((janela.fim - janela.inicio).days + 1, 180)

    def test_divisao_180_em_dois_periodos_de_90(self):
        anterior, atual = JanelaHistorica.criar_aquisicao_180(
            DATA_REFERENCIA
        ).dividir_em_periodos_90()
        self.assertEqual(anterior.dias_esperados, 90)
        self.assertEqual(atual.dias_esperados, 90)
        self.assertEqual(anterior.finalidade, FinalidadeJanela.COMPARACAO_ANTERIOR)
        self.assertEqual(atual.finalidade, FinalidadeJanela.ATUAL)

    def test_periodos_nao_se_sobrepoem(self):
        anterior, atual = JanelaHistorica.criar_aquisicao_180(
            DATA_REFERENCIA
        ).dividir_em_periodos_90()
        self.assertLess(anterior.fim, atual.inicio)

    def test_periodos_nao_possuem_gap(self):
        anterior, atual = JanelaHistorica.criar_aquisicao_180(
            DATA_REFERENCIA
        ).dividir_em_periodos_90()
        self.assertEqual(anterior.fim + timedelta(days=1), atual.inicio)

    def test_virada_de_mes(self):
        janela = JanelaHistorica.criar_atual(date(2026, 3, 2), 4)
        self.assertEqual(janela.inicio, date(2026, 2, 27))

    def test_virada_de_ano(self):
        janela = JanelaHistorica.criar_atual(date(2026, 1, 2), 4)
        self.assertEqual(janela.inicio, date(2025, 12, 30))

    def test_fevereiro_em_ano_bissexto(self):
        janela = JanelaHistorica.criar_atual(date(2024, 3, 1), 3)
        self.assertEqual(janela.inicio, date(2024, 2, 28))
        self.assertEqual(janela.inicio + timedelta(days=1), date(2024, 2, 29))

    def test_intervalo_inclusivo_incoerente_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            JanelaHistorica(
                data_referencia=DATA_REFERENCIA,
                inicio=DATA_REFERENCIA - timedelta(days=89),
                fim=DATA_REFERENCIA,
                dias_esperados=89,
                finalidade=FinalidadeJanela.ATUAL,
            )

    def test_janela_atual_nao_desloca_quando_d0_esta_ausente(self):
        with self.assertRaises(ValidationError):
            JanelaHistorica(
                data_referencia=DATA_REFERENCIA,
                inicio=DATA_REFERENCIA - timedelta(days=91),
                fim=DATA_REFERENCIA - timedelta(days=2),
                dias_esperados=90,
                finalidade=FinalidadeJanela.ATUAL,
            )


class TestRegistroMeteorologicoDiario(unittest.TestCase):
    def test_velocidade_vento_positiva_zero_e_none_sao_preservados(self):
        for valor in (3.5, 0.0, None):
            with self.subTest(valor=valor):
                registro = RegistroMeteorologicoDiario(
                    data=DATA_REFERENCIA,
                    velocidade_vento_media_m_s=valor,
                )
                self.assertEqual(registro.velocidade_vento_media_m_s, valor)
                self.assertEqual(
                    "velocidade_vento_media_m_s" in registro.variaveis_ausentes,
                    valor is None,
                )

    def test_velocidade_vento_invalida_e_rejeitada(self):
        for valor in (-0.01, math.nan, math.inf, True):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                RegistroMeteorologicoDiario(
                    data=DATA_REFERENCIA,
                    velocidade_vento_media_m_s=valor,
                )

    def test_velocidade_vento_e_serializada(self):
        registro = RegistroMeteorologicoDiario(
            data=DATA_REFERENCIA,
            velocidade_vento_media_m_s=2.75,
        )
        self.assertEqual(
            registro.model_dump()["velocidade_vento_media_m_s"],
            2.75,
        )

    def test_zero_de_precipitacao_e_preservado(self):
        registro = RegistroMeteorologicoDiario(
            data=DATA_REFERENCIA, precipitacao_mm=0.0
        )
        self.assertEqual(registro.precipitacao_mm, 0.0)
        self.assertNotIn("precipitacao_mm", registro.variaveis_ausentes)

    def test_none_e_preservado_como_ausencia(self):
        registro = RegistroMeteorologicoDiario(data=DATA_REFERENCIA)
        self.assertIsNone(registro.precipitacao_mm)
        self.assertIn("precipitacao_mm", registro.variaveis_ausentes)

    def test_nan_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            RegistroMeteorologicoDiario(data=DATA_REFERENCIA, precipitacao_mm=math.nan)

    def test_infinito_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            RegistroMeteorologicoDiario(
                data=DATA_REFERENCIA, temperatura_maxima_c=math.inf
            )

    def test_umidade_valida(self):
        registro = RegistroMeteorologicoDiario(
            data=DATA_REFERENCIA, umidade_media_pct=0
        )
        self.assertEqual(registro.umidade_media_pct, 0)

    def test_umidade_invalida_e_rejeitada(self):
        for valor in (-0.01, 100.01):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                RegistroMeteorologicoDiario(
                    data=DATA_REFERENCIA, umidade_media_pct=valor
                )

    def test_ausencias_informadas_nao_podem_divergir(self):
        with self.assertRaises(ValidationError):
            RegistroMeteorologicoDiario(
                data=DATA_REFERENCIA,
                precipitacao_mm=0,
                variaveis_ausentes=VARIAVEIS_METEOROLOGICAS,
            )

    def test_flags_sao_deterministicas(self):
        registro = RegistroMeteorologicoDiario(
            data=DATA_REFERENCIA,
            flags_qualidade=("B", "A", "B"),
        )
        self.assertEqual(registro.flags_qualidade, ("A", "B"))


class TestGapEQualidadeHistorica(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 4)

    def test_gap_interno_e_representavel(self):
        gap = GapTemporal(
            inicio=self.janela.inicio + timedelta(days=1),
            fim=self.janela.inicio + timedelta(days=2),
            duracao_dias=2,
            variaveis_afetadas=("precipitacao_mm",),
        )
        self.assertEqual(gap.duracao_dias, 2)

    def test_gap_final_e_representavel_sem_deslocar_janela(self):
        registros = (registro_completo(self.janela.inicio),)
        qualidade = QualidadeHistorica.calcular(self.janela, registros)
        gap_final = qualidade.gaps[-1]
        self.assertEqual(gap_final.fim, DATA_REFERENCIA)
        self.assertEqual(self.janela.fim, DATA_REFERENCIA)

    def test_duracao_incoerente_do_gap_e_rejeitada(self):
        with self.assertRaises(ValidationError):
            GapTemporal(
                inicio=self.janela.inicio,
                fim=self.janela.inicio + timedelta(days=1),
                duracao_dias=1,
                variaveis_afetadas=("precipitacao_mm",),
            )

    def test_cobertura_geral_correta(self):
        registros = (
            registro_completo(self.janela.inicio),
            registro_completo(self.janela.inicio + timedelta(days=2)),
            RegistroMeteorologicoDiario(data=self.janela.fim),
        )
        qualidade = QualidadeHistorica.calcular(self.janela, registros)
        self.assertEqual(qualidade.dias_com_algum_dado, 2)
        self.assertEqual(qualidade.cobertura_pct, 50.0)

    def test_cobertura_por_variavel_correta(self):
        registros = (
            registro_completo(self.janela.inicio),
            RegistroMeteorologicoDiario(
                data=self.janela.inicio + timedelta(days=1), precipitacao_mm=2
            ),
        )
        qualidade = QualidadeHistorica.calcular(self.janela, registros)
        self.assertEqual(qualidade.cobertura_por_variavel_pct["precipitacao_mm"], 50)
        self.assertEqual(
            qualidade.cobertura_por_variavel_pct["temperatura_maxima_c"], 25
        )

    def test_zero_conta_como_observacao(self):
        registro = RegistroMeteorologicoDiario(
            data=self.janela.inicio, precipitacao_mm=0.0
        )
        qualidade = QualidadeHistorica.calcular(self.janela, (registro,))
        self.assertEqual(qualidade.dias_disponiveis_por_variavel["precipitacao_mm"], 1)
        self.assertEqual(qualidade.dias_com_algum_dado, 1)

    def test_none_nao_conta_como_observacao(self):
        registro = RegistroMeteorologicoDiario(data=self.janela.inicio)
        qualidade = QualidadeHistorica.calcular(self.janela, (registro,))
        self.assertEqual(qualidade.dias_disponiveis_por_variavel["precipitacao_mm"], 0)
        self.assertEqual(qualidade.dias_com_algum_dado, 0)

    def test_dia_ausente_no_calendario_aparece_como_gap(self):
        registros = (
            registro_completo(self.janela.inicio),
            registro_completo(self.janela.inicio + timedelta(days=1)),
            registro_completo(self.janela.fim),
        )
        qualidade = QualidadeHistorica.calcular(self.janela, registros)
        self.assertTrue(
            any(
                gap.inicio == self.janela.inicio + timedelta(days=2)
                and gap.variaveis_afetadas == VARIAVEIS_METEOROLOGICAS
                for gap in qualidade.gaps
            )
        )

    def test_ultima_data_disponivel_e_por_variavel(self):
        primeiro = registro_completo(self.janela.inicio)
        ultimo = RegistroMeteorologicoDiario(data=self.janela.fim, precipitacao_mm=0)
        qualidade = QualidadeHistorica.calcular(self.janela, (primeiro, ultimo))
        self.assertEqual(
            qualidade.ultima_data_disponivel_por_variavel["precipitacao_mm"],
            self.janela.fim,
        )
        self.assertEqual(
            qualidade.ultima_data_disponivel_por_variavel["temperatura_maxima_c"],
            self.janela.inicio,
        )


class TestSerieHistoricaFonte(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 4)

    def test_datas_fora_de_ordem_sao_ordenadas(self):
        registros = (
            registro_completo(self.janela.fim),
            registro_completo(self.janela.inicio),
        )
        serie = criar_serie(
            FonteDado.NASA_POWER,
            TipoProdutoHistorico.HISTORICO_REGIONAL,
            registros,
            janela=self.janela,
        )
        self.assertEqual(
            [r.data for r in serie.registros], sorted(r.data for r in registros)
        )

    def test_datas_duplicadas_sao_rejeitadas(self):
        registro = registro_completo(self.janela.inicio)
        with self.assertRaises(ValueError):
            criar_serie(
                FonteDado.NASA_POWER,
                TipoProdutoHistorico.HISTORICO_REGIONAL,
                (registro, registro),
                janela=self.janela,
            )

    def test_nasa_e_open_meteo_sao_series_independentes(self):
        nasa = criar_serie(
            FonteDado.NASA_POWER,
            TipoProdutoHistorico.HISTORICO_REGIONAL,
            (registro_completo(self.janela.inicio, chuva=1),),
            janela=self.janela,
        )
        open_meteo = criar_serie(
            FonteDado.OPEN_METEO,
            TipoProdutoHistorico.REANALISE_MODELADA,
            (registro_completo(self.janela.inicio, chuva=2),),
            janela=self.janela,
        )
        self.assertEqual(nasa.fonte, FonteDado.NASA_POWER)
        self.assertEqual(open_meteo.fonte, FonteDado.OPEN_METEO)
        self.assertNotEqual(
            nasa.registros[0].precipitacao_mm, open_meteo.registros[0].precipitacao_mm
        )

    def test_tipo_de_produto_incoerente_com_fonte_e_rejeitado(self):
        with self.assertRaises(ValidationError):
            criar_serie(
                FonteDado.NASA_POWER,
                TipoProdutoHistorico.REANALISE_MODELADA,
                (registro_completo(self.janela.inicio),),
                janela=self.janela,
            )

    def test_referencia_temporal_e_preservada(self):
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time conforme documentação da fonte",
        )
        serie = criar_serie(
            FonteDado.NASA_POWER,
            TipoProdutoHistorico.HISTORICO_REGIONAL,
            (registro_completo(self.janela.inicio),),
            janela=self.janela,
            referencia_temporal=referencia,
        )
        self.assertEqual(serie.referencia_temporal, referencia)

    def test_timezone_civil_exige_identificador(self):
        with self.assertRaises(ValidationError):
            ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.TIMEZONE_CIVIL)

    def test_coleta_e_normalizada_para_utc(self):
        serie = SerieHistoricaFonte.criar(
            fonte=FonteDado.NASA_POWER,
            tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
            dataset="dataset-oficial",
            periodo_solicitado=self.janela,
            referencia_temporal=ReferenciaTemporalHistorica(
                tipo=TipoReferenciaTemporal.UTC
            ),
            registros=(registro_completo(self.janela.inicio),),
            coletado_em_utc=datetime(
                2026, 8, 12, 9, tzinfo=timezone(timedelta(hours=-3))
            ),
        )
        self.assertEqual(serie.coletado_em_utc.hour, 12)
        self.assertEqual(serie.coletado_em_utc.utcoffset(), timedelta(0))

    def test_coleta_sem_timezone_e_rejeitada(self):
        with self.assertRaises(ValidationError):
            SerieHistoricaFonte.criar(
                fonte=FonteDado.NASA_POWER,
                tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
                dataset="dataset-oficial",
                periodo_solicitado=self.janela,
                referencia_temporal=ReferenciaTemporalHistorica(
                    tipo=TipoReferenciaTemporal.UTC
                ),
                registros=(),
                coletado_em_utc=datetime(2026, 8, 12, 12),
            )

    def test_periodo_efetivo_considera_zero_como_dado(self):
        registro = RegistroMeteorologicoDiario(
            data=self.janela.fim, precipitacao_mm=0.0
        )
        serie = criar_serie(
            FonteDado.NASA_POWER,
            TipoProdutoHistorico.HISTORICO_REGIONAL,
            (registro,),
            janela=self.janela,
        )
        self.assertEqual(serie.periodo_efetivo.inicio, self.janela.fim)
        self.assertEqual(serie.periodo_efetivo.fim, self.janela.fim)

    def test_serie_sem_dados_tem_periodo_efetivo_ausente(self):
        serie = criar_serie(
            FonteDado.OPEN_METEO,
            TipoProdutoHistorico.REANALISE_MODELADA,
            (),
            janela=self.janela,
        )
        self.assertIsNone(serie.periodo_efetivo)
        self.assertEqual(serie.qualidade.cobertura_pct, 0)

    def test_modelos_nao_expoem_classificacao_operacional(self):
        nomes = {
            *JanelaHistorica.model_fields,
            *RegistroMeteorologicoDiario.model_fields,
            *QualidadeHistorica.model_fields,
            *SerieHistoricaFonte.model_fields,
        }
        proibidos = {"normal", "atencao", "alerta", "critico", "score"}
        self.assertTrue(proibidos.isdisjoint(nomes))
        self.assertEqual(
            SerieHistoricaFonte.model_fields["natureza"].default, NaturezaDado.HISTORICO
        )

    def test_modelos_sao_imutaveis(self):
        registro = registro_completo(self.janela.inicio)
        with self.assertRaises(ValidationError):
            registro.precipitacao_mm = 99

    def test_metadados_de_series_nao_compartilham_estado_de_entrada(self):
        metadados = {"produto": {"versao": "1"}}
        serie = criar_serie(
            FonteDado.NASA_POWER,
            TipoProdutoHistorico.HISTORICO_REGIONAL,
            (),
            janela=self.janela,
            metadados=metadados,
        )
        metadados["produto"]["versao"] = "2"
        self.assertEqual(serie.metadados_origem["produto"]["versao"], "1")


if __name__ == "__main__":
    unittest.main()
