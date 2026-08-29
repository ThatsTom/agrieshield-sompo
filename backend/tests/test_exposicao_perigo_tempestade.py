from __future__ import annotations

import inspect
import math
import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from backend.exposicao import (
    AVISO_METODOLOGIA_TEMPESTADE,
    METODOLOGIA_TEMPESTADE,
    MOTIVO_AMPLIFICACAO_CHUVA_APLICADA,
    MOTIVO_PRECIPITACAO_INDISPONIVEL,
    MOTIVO_VENTO_INDISPONIVEL,
    EstadoDisponibilidade,
    FeatureDiariaCompartilhada,
    FeaturesDiariasCompartilhadas,
    JanelaHistorica,
    ParametrosTempestade,
    PerigoExposicao,
    ReferenciaTemporalHistorica,
    TempestadeDiaria,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    agrupar_eventos,
    calcular_exposicao_tempestade,
    calcular_indice_tempestade,
    calcular_tempestade_diaria,
    criar_politica_agrishield_equip_v1,
    normalizar_chuva_tempestade,
    normalizar_vento_fogo,
    normalizar_vento_tempestade,
)
from backend.risco.modelos import FonteDado, NaturezaDado


DATA_REFERENCIA = date(2026, 8, 11)
VENTO_NASA = {
    "parametro_fonte": "WS2M",
    "variavel_canonica": "velocidade_vento_media_m_s",
    "unidade": "m/s",
    "altura_m": 2,
    "agregacao_temporal": "media_diaria",
    "referencia_temporal": "LST",
}
VENTO_OPEN_METEO = {
    "parametro_fonte": "wind_speed_10m_mean",
    "variavel_canonica": "velocidade_vento_media_m_s",
    "unidade": "m/s",
    "altura_m": 10,
    "agregacao_temporal": "media_diaria",
    "referencia_temporal": "UTC",
}


def criar_feature(
    *,
    data_dia: date = DATA_REFERENCIA,
    vento: float | None = 8.0,
    chuva: float | None = 100.0,
    chuva_d1_d3: float | None = 999.0,
    chuva_d4_d7: float | None = 999.0,
    acumulado_3d: float | None = 999.0,
    acumulado_7d: float | None = 999.0,
) -> FeatureDiariaCompartilhada:
    return FeatureDiariaCompartilhada(
        data=data_dia,
        precipitacao_d0=chuva,
        precipitacao_d1_d3=chuva_d1_d3,
        precipitacao_d4_d7=chuva_d4_d7,
        acumulado_3d=acumulado_3d,
        acumulado_7d=acumulado_7d,
        temperatura_media=25.0,
        temperatura_maxima=30.0,
        temperatura_minima=20.0,
        umidade_relativa=50.0,
        velocidade_vento_media_m_s=vento,
    )


def criar_features(
    *,
    dias: int = 90,
    fonte: FonteDado = FonteDado.NASA_POWER,
    vento: float | None = 8.0,
    chuva: float | None = 100.0,
    alterar=None,
) -> FeaturesDiariasCompartilhadas:
    periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    itens = []
    for indice in range(dias):
        valores = {"vento": vento, "chuva": chuva}
        if alterar is not None:
            valores.update(
                alterar(indice, periodo.inicio + timedelta(days=indice)) or {}
            )
        itens.append(
            criar_feature(
                data_dia=periodo.inicio + timedelta(days=indice),
                **valores,
            )
        )
    if fonte == FonteDado.NASA_POWER:
        produto = TipoProdutoHistorico.HISTORICO_REGIONAL
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        )
        metadados = VENTO_NASA
        dataset = "NASA/POWER DAILY"
    else:
        produto = TipoProdutoHistorico.REANALISE_MODELADA
        referencia = ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC)
        metadados = VENTO_OPEN_METEO
        dataset = "Open-Meteo Historical Weather API"
    return FeaturesDiariasCompartilhadas(
        id_fazenda="fazenda-teste",
        fonte=fonte,
        natureza=NaturezaDado.HISTORICO,
        tipo_produto=produto,
        dataset=dataset,
        periodo=periodo,
        referencia_temporal=referencia,
        metadados_vento=metadados,
        dias=tuple(itens),
    )


class TestPoliticaTempestade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.parametros = self.politica.parametros_tempestade

    def test_curva_de_chuva_e_pesos_estao_centralizados(self):
        self.assertEqual(
            [
                (p.precipitacao_mm, p.componente)
                for p in self.parametros.curva_precipitacao_d0
            ],
            [(0, 0), (10, 0.20), (20, 0.40), (50, 0.70), (100, 1)],
        )
        self.assertEqual(self.parametros.peso_base_vento, 0.75)
        self.assertEqual(self.parametros.peso_amplificacao_chuva, 0.25)

    def test_parametros_sao_imutaveis(self):
        with self.assertRaises(ValidationError):
            self.parametros.peso_base_vento = 1

    def test_pontos_desordenados_e_componentes_decrescentes_sao_rejeitados(self):
        dados = self.parametros.model_dump()
        dados["curva_precipitacao_d0"][1]["precipitacao_mm"] = 0
        with self.assertRaises(ValidationError):
            ParametrosTempestade.model_validate(dados)

        dados = self.parametros.model_dump()
        dados["curva_precipitacao_d0"][1]["componente"] = 0.8
        with self.assertRaises(ValidationError):
            ParametrosTempestade.model_validate(dados)

    def test_pesos_fora_do_dominio_ou_sem_soma_unitaria_sao_rejeitados(self):
        for pesos in ((-0.1, 1.1), (0.8, 0.3), (1.1, -0.1)):
            with self.subTest(pesos=pesos):
                dados = self.parametros.model_dump()
                dados["peso_base_vento"], dados["peso_amplificacao_chuva"] = pesos
                with self.assertRaises(ValidationError):
                    ParametrosTempestade.model_validate(dados)


class TestCurvasTempestade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_vento_reutiliza_exatamente_a_curva_da_propagacao_de_fogo(self):
        for valor, esperado in (
            (0, 0),
            (2, 0.20),
            (4, 0.50),
            (6, 0.75),
            (8, 1),
            (12, 1),
            (3, 0.35),
            (None, None),
        ):
            with self.subTest(valor=valor):
                tempestade = normalizar_vento_tempestade(valor, self.politica)
                self.assertEqual(tempestade, esperado)
                self.assertEqual(
                    tempestade,
                    normalizar_vento_fogo(valor, self.politica),
                )

    def test_curva_de_chuva_pontos_limites_e_none(self):
        for valor, esperado in (
            (0, 0),
            (10, 0.20),
            (20, 0.40),
            (50, 0.70),
            (100, 1),
            (150, 1),
            (None, None),
        ):
            with self.subTest(valor=valor):
                self.assertEqual(
                    normalizar_chuva_tempestade(valor, self.politica),
                    esperado,
                )

    def test_chuva_e_interpolada_linearmente(self):
        self.assertAlmostEqual(normalizar_chuva_tempestade(5, self.politica), 0.10)
        self.assertAlmostEqual(normalizar_chuva_tempestade(35, self.politica), 0.55)
        self.assertAlmostEqual(normalizar_chuva_tempestade(75, self.politica), 0.85)

    def test_valores_invalidos_sao_rejeitados_sem_virar_zero(self):
        casos = (
            (normalizar_vento_tempestade, -1),
            (normalizar_vento_tempestade, math.nan),
            (normalizar_chuva_tempestade, -1),
            (normalizar_chuva_tempestade, math.inf),
            (normalizar_chuva_tempestade, True),
        )
        for funcao, valor in casos:
            with self.subTest(funcao=funcao.__name__, valor=valor), self.assertRaises(
                (TypeError, ValueError)
            ):
                funcao(valor, self.politica)


class TestCalculoDiario(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_formula_aprovada_nucleo_de_vento_e_amplificacao(self):
        indice_vento, fator, final = calcular_indice_tempestade(0.8, 0, self.politica)
        self.assertEqual(indice_vento, 80)
        self.assertEqual(fator, 0.75)
        self.assertEqual(final, 60)

        _, fator_chuva, final_chuva = calcular_indice_tempestade(0.8, 1, self.politica)
        self.assertEqual(fator_chuva, 1)
        self.assertEqual(final_chuva, 80)
        self.assertGreater(final_chuva, final)

    def test_chuva_extrema_sem_vento_produz_indice_zero(self):
        indice_vento, fator, final = calcular_indice_tempestade(0, 1, self.politica)
        self.assertEqual(indice_vento, 0)
        self.assertEqual(fator, 1)
        self.assertEqual(final, 0)

    def test_resultado_completo_permanece_entre_zero_e_cem(self):
        for vento in (0, 0.2, 0.5, 0.75, 1):
            for chuva in (0, 0.2, 0.7, 1):
                with self.subTest(vento=vento, chuva=chuva):
                    _, _, final = calcular_indice_tempestade(
                        vento, chuva, self.politica
                    )
                    self.assertGreaterEqual(final, 0)
                    self.assertLessEqual(final, 100)

    def test_ausencia_de_vento_torna_indice_none_mesmo_com_chuva(self):
        dia = calcular_tempestade_diaria(
            criar_feature(vento=None, chuva=100), self.politica
        )
        self.assertIsNone(dia.componente_vento)
        self.assertIsNone(dia.indice_vento)
        self.assertIsNone(dia.indice_exposicao_tempestade)
        self.assertEqual(dia.motivo, MOTIVO_VENTO_INDISPONIVEL)
        self.assertFalse(dia.amplificacao_chuva_aplicada)

    def test_ausencia_de_chuva_torna_indice_none_sem_superar_chuva_zero(self):
        ausente = calcular_tempestade_diaria(
            criar_feature(vento=8, chuva=None), self.politica
        )
        zero = calcular_tempestade_diaria(
            criar_feature(vento=8, chuva=0), self.politica
        )
        self.assertEqual(ausente.indice_vento, 100)
        self.assertIsNone(ausente.componente_chuva)
        self.assertIsNone(ausente.fator_amplificacao_chuva)
        self.assertIsNone(ausente.indice_exposicao_tempestade)
        self.assertEqual(ausente.motivo, MOTIVO_PRECIPITACAO_INDISPONIVEL)
        self.assertFalse(ausente.amplificacao_chuva_aplicada)
        self.assertEqual(zero.componente_chuva, 0)
        self.assertEqual(zero.indice_exposicao_tempestade, 75)

    def test_zero_de_chuva_e_observacao_valida_e_aplica_formula(self):
        dia = calcular_tempestade_diaria(criar_feature(vento=6, chuva=0), self.politica)
        self.assertEqual(dia.precipitacao_d0, 0)
        self.assertEqual(dia.componente_chuva, 0)
        self.assertEqual(dia.fator_amplificacao_chuva, 0.75)
        self.assertTrue(dia.amplificacao_chuva_aplicada)
        self.assertEqual(dia.motivo, MOTIVO_AMPLIFICACAO_CHUVA_APLICADA)
        self.assertEqual(dia.indice_exposicao_tempestade, 56.25)

    def test_ausencia_nao_e_convertida_em_zero_pelo_calculo_direto(self):
        self.assertEqual(
            calcular_indice_tempestade(None, 1, self.politica),
            (None, None, None),
        )
        self.assertEqual(
            calcular_indice_tempestade(1, None, self.politica),
            (100, None, None),
        )
        self.assertEqual(
            calcular_indice_tempestade(None, None, self.politica),
            (None, None, None),
        )

    def test_granizo_e_descargas_permanecem_indisponiveis_nao_zero(self):
        dia = calcular_tempestade_diaria(criar_feature(), self.politica)
        self.assertEqual(dia.granizo, EstadoDisponibilidade.INDISPONIVEL)
        self.assertEqual(
            dia.descargas_atmosfericas,
            EstadoDisponibilidade.INDISPONIVEL,
        )
        self.assertNotEqual(dia.granizo, 0)
        self.assertNotEqual(dia.descargas_atmosfericas, 0)

    def test_contrato_rejeita_disponibilidade_ficticia_de_granizo_ou_raios(self):
        base = calcular_tempestade_diaria(criar_feature(), self.politica).model_dump()
        for campo in ("granizo", "descargas_atmosfericas"):
            with self.subTest(campo=campo):
                alterado = dict(base)
                alterado[campo] = EstadoDisponibilidade.DISPONIVEL
                with self.assertRaises(ValidationError):
                    TempestadeDiaria.model_validate(alterado)

    def test_d1_d7_acumulados_e_memoria_hidrica_nao_entram_na_formula(self):
        base = criar_feature(
            vento=6,
            chuva=20,
            chuva_d1_d3=0,
            chuva_d4_d7=0,
            acumulado_3d=0,
            acumulado_7d=0,
        )
        alterada = base.model_copy(
            update={
                "precipitacao_d1_d3": 1000,
                "precipitacao_d4_d7": 1000,
                "acumulado_3d": 1000,
                "acumulado_7d": 1000,
                "dias_desde_ultima_chuva_relevante": 100,
            }
        )
        self.assertEqual(
            calcular_tempestade_diaria(base, self.politica),
            calcular_tempestade_diaria(alterada, self.politica),
        )

    def test_determinismo_e_entrada_imutavel(self):
        feature = criar_feature()
        antes = feature.model_dump()
        self.assertEqual(
            calcular_tempestade_diaria(feature, self.politica),
            calcular_tempestade_diaria(feature, self.politica),
        )
        self.assertEqual(feature.model_dump(), antes)


class TestAgregacaoTempestade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_reutiliza_indices_eventos_agregacao_e_classificacao_genericos(self):
        resultado = calcular_exposicao_tempestade(criar_features(), self.politica)
        self.assertEqual(resultado.perigo, PerigoExposicao.TEMPESTADES)
        self.assertEqual(len(resultado.indices_diarios.indices), 90)
        self.assertEqual(
            resultado.agregacao_90d.eventos,
            agrupar_eventos(resultado.indices_diarios, self.politica),
        )
        self.assertEqual(
            resultado.agregacao_90d.classificacao_agregada,
            self.politica.classificar_indice(resultado.agregacao_90d.indice_agregado),
        )

    def test_condicao_continua_forma_um_evento_de_noventa_dias(self):
        resultado = calcular_exposicao_tempestade(criar_features(), self.politica)
        self.assertEqual(resultado.agregacao_90d.quantidade_eventos, 1)
        self.assertEqual(resultado.agregacao_90d.eventos[0].duracao_dias, 90)

    def test_gap_quebra_evento_e_reduz_cobertura(self):
        resultado = calcular_exposicao_tempestade(
            criar_features(
                alterar=lambda indice, _: {"chuva": None} if indice == 45 else {}
            ),
            self.politica,
        )
        agregado = resultado.agregacao_90d
        self.assertEqual(agregado.quantidade_eventos, 2)
        self.assertEqual(agregado.dias_disponiveis, 89)
        self.assertAlmostEqual(agregado.cobertura_percentual, 100 * 89 / 90)

    def test_gaps_podem_tornar_qualidade_insuficiente(self):
        resultado = calcular_exposicao_tempestade(
            criar_features(
                alterar=lambda indice, _: {"vento": None} if indice < 20 else {}
            ),
            self.politica,
        )
        agregado = resultado.agregacao_90d
        self.assertEqual(agregado.dias_disponiveis, 70)
        self.assertFalse(agregado.qualidade_suficiente)

    def test_chuva_isolada_com_vento_zero_nao_cria_evento(self):
        resultado = calcular_exposicao_tempestade(
            criar_features(vento=0, chuva=100), self.politica
        )
        self.assertTrue(
            all(item.indice == 0 for item in resultado.indices_diarios.indices)
        )
        self.assertEqual(resultado.agregacao_90d.quantidade_eventos, 0)
        self.assertEqual(resultado.agregacao_90d.indice_agregado, 0)

    def test_contexto_anterior_nao_entra_em_eventos_cobertura_ou_agregacao(self):
        features = criar_features(dias=97)
        alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        resultado = calcular_exposicao_tempestade(
            features, self.politica, janela_alvo=alvo
        )
        self.assertEqual(resultado.dias_contexto_calendario, 7)
        self.assertEqual(resultado.periodo_features, features.periodo)
        self.assertEqual(resultado.janela_analisada, alvo)
        self.assertEqual(len(resultado.tempestades_diarias), 90)
        self.assertEqual(resultado.agregacao_90d.dias_esperados, 90)


class TestProvenienciaESemanticaTempestade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_preserva_proveniencia_nasa_ws2m_2m_lts(self):
        features = criar_features()
        resultado = calcular_exposicao_tempestade(features, self.politica)
        self.assertEqual(resultado.fonte, FonteDado.NASA_POWER)
        self.assertEqual(resultado.dataset, features.dataset)
        self.assertEqual(resultado.proveniencia_vento, VENTO_NASA)
        self.assertEqual(resultado.proveniencia_vento["altura_m"], 2)
        self.assertEqual(resultado.proveniencia_vento["parametro_fonte"], "WS2M")

    def test_open_meteo_permanece_independente_e_preserva_vento_10m(self):
        nasa = calcular_exposicao_tempestade(criar_features(), self.politica)
        open_meteo = calcular_exposicao_tempestade(
            criar_features(fonte=FonteDado.OPEN_METEO), self.politica
        )
        self.assertEqual(open_meteo.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(open_meteo.proveniencia_vento, VENTO_OPEN_METEO)
        self.assertEqual(open_meteo.proveniencia_vento["altura_m"], 10)
        self.assertNotEqual(nasa.dataset, open_meteo.dataset)

    def test_metodologia_declara_proxy_e_todas_as_limitacoes(self):
        resultado = calcular_exposicao_tempestade(criar_features(), self.politica)
        self.assertEqual(resultado.metodologia, METODOLOGIA_TEMPESTADE)
        self.assertEqual(resultado.aviso_metodologia, AVISO_METODOLOGIA_TEMPESTADE)
        aviso = resultado.aviso_metodologia.lower()
        for trecho in (
            "demonstrativo",
            "nao representa alerta oficial inmet",
            "vendaval confirmado",
            "rajada",
            "granizo",
            "descarga atmosferica",
            "probabilidade de tempestade",
            "probabilidade de sinistro",
        ):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, aviso)

    def test_modulo_nao_tem_io_clientes_score_ou_recalculo_hidrico(self):
        from backend.exposicao import perigo_tempestade

        codigo = inspect.getsource(perigo_tempestade).lower()
        for termo in (
            "requests",
            "http://",
            "https://",
            "open(",
            "read_csv",
            "to_csv",
            "fastapi",
            "supabase",
            "score_geral",
            "etapa3",
            "mapbiomas",
            "calcular_condicoes_hidricas",
            "calcular_condicao_hidrica_diaria",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_resultado_e_entrada_sao_imutaveis(self):
        features = criar_features()
        antes = features.model_dump()
        resultado = calcular_exposicao_tempestade(features, self.politica)
        self.assertEqual(features.model_dump(), antes)
        with self.assertRaises(ValidationError):
            resultado.dataset = "outro"


if __name__ == "__main__":
    unittest.main()
