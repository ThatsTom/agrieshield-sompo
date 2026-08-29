from __future__ import annotations

import inspect
import math
import unittest
from datetime import date, timedelta
from statistics import fmean

from pydantic import ValidationError

from backend.exposicao import (
    AVISO_METODOLOGIA_PROPAGACAO_FOGO,
    METODOLOGIA_PROPAGACAO_FOGO,
    MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL,
    MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL,
    MOTIVO_SECURA_APLICADA,
    FeatureDiariaCompartilhada,
    FeaturesDiariasCompartilhadas,
    JanelaHistorica,
    ParametrosPropagacaoFogo,
    PerigoExposicao,
    ReferenciaTemporalHistorica,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    agrupar_eventos,
    calcular_exposicao_propagacao_fogo,
    calcular_indice_fogo_base,
    calcular_propagacao_fogo_diaria,
    criar_politica_agrishield_equip_v1,
    normalizar_baixa_umidade_fogo,
    normalizar_temperatura_fogo,
    normalizar_vento_fogo,
    obter_multiplicador_secura,
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
    temperatura_maxima: float | None = 40.0,
    temperatura_media: float | None = 5.0,
    umidade: float | None = 20.0,
    vento: float | None = 8.0,
    dias_secura: int | None = 7,
) -> FeatureDiariaCompartilhada:
    return FeatureDiariaCompartilhada(
        data=data_dia,
        precipitacao_d0=0.0,
        temperatura_media=temperatura_media,
        temperatura_maxima=temperatura_maxima,
        temperatura_minima=0.0,
        umidade_relativa=umidade,
        velocidade_vento_media_m_s=vento,
        dias_desde_ultima_chuva_relevante=dias_secura,
    )


def criar_features(
    *,
    dias: int = 90,
    fonte: FonteDado = FonteDado.NASA_POWER,
    temperatura_maxima: float | None = 40.0,
    umidade: float | None = 20.0,
    vento: float | None = 8.0,
    dias_secura: int | None = 7,
    alterar=None,
) -> FeaturesDiariasCompartilhadas:
    periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    itens = []
    for indice in range(dias):
        valores = {
            "temperatura_maxima": temperatura_maxima,
            "temperatura_media": 5.0,
            "umidade": umidade,
            "vento": vento,
            "dias_secura": dias_secura,
        }
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
        tipo_produto = TipoProdutoHistorico.HISTORICO_REGIONAL
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        )
        metadados = VENTO_NASA
        dataset = "NASA/POWER DAILY"
    else:
        tipo_produto = TipoProdutoHistorico.REANALISE_MODELADA
        referencia = ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC)
        metadados = VENTO_OPEN_METEO
        dataset = "Open-Meteo Historical Weather API"
    return FeaturesDiariasCompartilhadas(
        id_fazenda="fazenda-teste",
        fonte=fonte,
        natureza=NaturezaDado.HISTORICO,
        tipo_produto=tipo_produto,
        dataset=dataset,
        periodo=periodo,
        referencia_temporal=referencia,
        metadados_vento=metadados,
        dias=tuple(itens),
    )


class TestPoliticaPropagacaoFogo(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.parametros = self.politica.parametros_propagacao_fogo

    def test_curvas_e_faixas_da_politica_v1(self):
        self.assertEqual(
            [
                (p.temperatura_c, p.componente)
                for p in self.parametros.curva_temperatura_maxima
            ],
            [(20, 0), (25, 0.25), (30, 0.60), (35, 0.85), (40, 1)],
        )
        self.assertEqual(
            [
                (p.umidade_pct, p.componente)
                for p in self.parametros.curva_baixa_umidade_media
            ],
            [(20, 1), (30, 0.75), (40, 0.50), (50, 0.25), (70, 0)],
        )
        self.assertEqual(
            [
                (p.velocidade_m_s, p.componente)
                for p in self.parametros.curva_velocidade_vento_media
            ],
            [(0, 0), (2, 0.20), (4, 0.50), (6, 0.75), (8, 1)],
        )
        self.assertEqual(
            [
                (p.inicio_dias, p.multiplicador)
                for p in self.parametros.faixas_secura_antecedente
            ],
            [(0, 0.90), (2, 1), (4, 1.05), (7, 1.10)],
        )

    def test_parametros_sao_imutaveis(self):
        with self.assertRaises(ValidationError):
            self.parametros.faixas_secura_antecedente = ()

    def test_curvas_desordenadas_ou_outputs_incoerentes_sao_rejeitados(self):
        dados = self.parametros.model_dump()
        dados["curva_temperatura_maxima"][1]["temperatura_c"] = 20
        with self.assertRaises(ValidationError):
            ParametrosPropagacaoFogo.model_validate(dados)

        dados = self.parametros.model_dump()
        dados["curva_baixa_umidade_media"][1]["componente"] = 1.01
        with self.assertRaises(ValidationError):
            ParametrosPropagacaoFogo.model_validate(dados)

        dados = self.parametros.model_dump()
        dados["faixas_secura_antecedente"][0]["inicio_dias"] = 1
        with self.assertRaises(ValidationError):
            ParametrosPropagacaoFogo.model_validate(dados)


class TestCurvasMeteorologicas(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_temperatura_pontos_limites_e_none(self):
        casos = (
            (-10, 0),
            (20, 0),
            (25, 0.25),
            (30, 0.60),
            (35, 0.85),
            (40, 1),
            (50, 1),
            (None, None),
        )
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(
                    normalizar_temperatura_fogo(valor, self.politica), esperado
                )

    def test_temperatura_interpolada_linearmente(self):
        self.assertAlmostEqual(normalizar_temperatura_fogo(27.5, self.politica), 0.425)
        self.assertAlmostEqual(normalizar_temperatura_fogo(37.5, self.politica), 0.925)

    def test_umidade_pontos_limites_e_none(self):
        casos = (
            (0, 1),
            (20, 1),
            (30, 0.75),
            (40, 0.50),
            (50, 0.25),
            (70, 0),
            (100, 0),
            (None, None),
        )
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(
                    normalizar_baixa_umidade_fogo(valor, self.politica), esperado
                )

    def test_umidade_e_interpolada_inversamente(self):
        self.assertAlmostEqual(normalizar_baixa_umidade_fogo(35, self.politica), 0.625)
        self.assertAlmostEqual(normalizar_baixa_umidade_fogo(60, self.politica), 0.125)

    def test_vento_pontos_limites_e_none(self):
        casos = (
            (0, 0),
            (2, 0.20),
            (4, 0.50),
            (6, 0.75),
            (8, 1),
            (12, 1),
            (None, None),
        )
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_vento_fogo(valor, self.politica), esperado)

    def test_vento_e_interpolado_linearmente(self):
        self.assertAlmostEqual(normalizar_vento_fogo(3, self.politica), 0.35)
        self.assertAlmostEqual(normalizar_vento_fogo(7, self.politica), 0.875)

    def test_valores_invalidos_sao_rejeitados_sem_virar_zero(self):
        funcoes_e_valores = (
            (normalizar_temperatura_fogo, math.nan),
            (normalizar_temperatura_fogo, math.inf),
            (normalizar_baixa_umidade_fogo, -1),
            (normalizar_baixa_umidade_fogo, 101),
            (normalizar_vento_fogo, -0.1),
            (normalizar_vento_fogo, True),
        )
        for funcao, valor in funcoes_e_valores:
            with self.subTest(funcao=funcao.__name__, valor=valor), self.assertRaises(
                (TypeError, ValueError)
            ):
                funcao(valor, self.politica)


class TestCombinacaoESecura(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_media_geometrica_completa_e_componente_zero(self):
        self.assertEqual(calcular_indice_fogo_base(1, 1, 1), 100)
        self.assertEqual(calcular_indice_fogo_base(1, 0, 1), 0)

    def test_componentes_moderados_usam_media_geometrica_nao_soma(self):
        resultado = calcular_indice_fogo_base(0.25, 0.50, 0.75)
        esperado = (0.25 * 0.50 * 0.75) ** (1 / 3) * 100
        soma_disfarcada = fmean((0.25, 0.50, 0.75)) * 100
        self.assertAlmostEqual(resultado, esperado)
        self.assertNotAlmostEqual(resultado, soma_disfarcada)
        self.assertGreaterEqual(resultado, 0)
        self.assertLessEqual(resultado, 100)

    def test_qualquer_componente_none_torna_base_indisponivel(self):
        for componentes in ((None, 1, 1), (1, None, 1), (1, 1, None)):
            with self.subTest(componentes=componentes):
                self.assertIsNone(calcular_indice_fogo_base(*componentes))

    def test_componentes_fora_do_dominio_sao_rejeitados(self):
        for componentes in ((-0.1, 1, 1), (1, 1.1, 1), (1, True, 1)):
            with self.subTest(componentes=componentes), self.assertRaises(
                (TypeError, ValueError)
            ):
                calcular_indice_fogo_base(*componentes)

    def test_faixas_de_secura_incluem_todos_os_limites(self):
        casos = (
            (0, 0.90),
            (1, 0.90),
            (2, 1),
            (3, 1),
            (4, 1.05),
            (6, 1.05),
            (7, 1.10),
            (100, 1.10),
            (None, None),
        )
        for dias, esperado in casos:
            with self.subTest(dias=dias):
                self.assertEqual(
                    obter_multiplicador_secura(dias, self.politica), esperado
                )

    def test_secura_invalida_e_rejeitada(self):
        for valor in (-1, 1.5, True):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                obter_multiplicador_secura(valor, self.politica)

    def test_indice_diario_aplica_secura_e_satura_em_cem(self):
        dia_umido = calcular_propagacao_fogo_diaria(
            criar_feature(temperatura_maxima=35, umidade=30, vento=6, dias_secura=0),
            self.politica,
        )
        self.assertAlmostEqual(
            dia_umido.indice_exposicao_propagacao_fogo,
            dia_umido.indice_fogo_base * 0.90,
        )
        self.assertTrue(dia_umido.secura_antecedente_aplicada)
        self.assertEqual(dia_umido.motivo, MOTIVO_SECURA_APLICADA)

        dia_seco = calcular_propagacao_fogo_diaria(criar_feature(), self.politica)
        self.assertEqual(dia_seco.indice_fogo_base, 100)
        self.assertEqual(dia_seco.indice_exposicao_propagacao_fogo, 100)

    def test_contexto_de_secura_ausente_preserva_base_sem_amplificacao(self):
        dia = calcular_propagacao_fogo_diaria(
            criar_feature(temperatura_maxima=35, umidade=30, vento=6, dias_secura=None),
            self.politica,
        )
        self.assertEqual(dia.indice_exposicao_propagacao_fogo, dia.indice_fogo_base)
        self.assertIsNone(dia.multiplicador_secura)
        self.assertFalse(dia.secura_antecedente_aplicada)
        self.assertEqual(dia.motivo, MOTIVO_CONTEXTO_PRECIPITACAO_INDISPONIVEL)

    def test_ausencia_essencial_nao_calcula_com_dois_componentes(self):
        casos = (
            {"temperatura_maxima": None},
            {"umidade": None},
            {"vento": None},
        )
        for alteracao in casos:
            with self.subTest(alteracao=alteracao):
                dia = calcular_propagacao_fogo_diaria(
                    criar_feature(**alteracao), self.politica
                )
                self.assertIsNone(dia.indice_fogo_base)
                self.assertIsNone(dia.indice_exposicao_propagacao_fogo)
                self.assertIsNone(dia.multiplicador_secura)
                self.assertFalse(dia.secura_antecedente_aplicada)
                self.assertEqual(dia.motivo, MOTIVO_COMPONENTE_ESSENCIAL_INDISPONIVEL)

    def test_usa_temperatura_maxima_sem_fallback_para_media(self):
        dia = calcular_propagacao_fogo_diaria(
            criar_feature(temperatura_maxima=None, temperatura_media=40),
            self.politica,
        )
        self.assertIsNone(dia.componente_temperatura)
        self.assertIsNone(dia.indice_exposicao_propagacao_fogo)

    def test_calculo_e_deterministico_e_nao_muta_feature(self):
        feature = criar_feature()
        antes = feature.model_dump()
        self.assertEqual(
            calcular_propagacao_fogo_diaria(feature, self.politica),
            calcular_propagacao_fogo_diaria(feature, self.politica),
        )
        self.assertEqual(feature.model_dump(), antes)


class TestIntegracaoAgregacaoNoventaDias(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_reutiliza_indices_eventos_agregacao_e_classificacao_genericos(self):
        resultado = calcular_exposicao_propagacao_fogo(criar_features(), self.politica)
        self.assertEqual(resultado.perigo, PerigoExposicao.INCENDIO)
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
        resultado = calcular_exposicao_propagacao_fogo(criar_features(), self.politica)
        self.assertEqual(resultado.agregacao_90d.quantidade_eventos, 1)
        self.assertEqual(resultado.agregacao_90d.eventos[0].duracao_dias, 90)
        self.assertEqual(resultado.agregacao_90d.quantidade_dias_relevantes, 90)

    def test_gap_essencial_quebra_evento_e_reduz_cobertura(self):
        resultado = calcular_exposicao_propagacao_fogo(
            criar_features(
                alterar=lambda indice, _: {"vento": None} if indice == 45 else {}
            ),
            self.politica,
        )
        agregado = resultado.agregacao_90d
        self.assertEqual(agregado.quantidade_eventos, 2)
        self.assertEqual(agregado.dias_disponiveis, 89)
        self.assertAlmostEqual(agregado.cobertura_percentual, 100 * 89 / 90)
        self.assertTrue(agregado.qualidade_suficiente)

    def test_ausencia_essencial_pode_tornar_qualidade_insuficiente(self):
        resultado = calcular_exposicao_propagacao_fogo(
            criar_features(
                alterar=lambda indice, _: {"umidade": None} if indice < 20 else {}
            ),
            self.politica,
        )
        agregado = resultado.agregacao_90d
        self.assertEqual(agregado.dias_disponiveis, 70)
        self.assertLess(agregado.cobertura_percentual, 80)
        self.assertFalse(agregado.qualidade_suficiente)

    def test_contexto_de_secura_ausente_nao_reduz_cobertura(self):
        resultado = calcular_exposicao_propagacao_fogo(
            criar_features(dias_secura=None), self.politica
        )
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 90)
        self.assertEqual(resultado.agregacao_90d.cobertura_percentual, 100)

    def test_agregado_nao_e_media_aritmetica_dos_noventa_dias(self):
        resultado = calcular_exposicao_propagacao_fogo(
            criar_features(
                temperatura_maxima=20,
                alterar=lambda indice, _: (
                    {"temperatura_maxima": 40} if indice == 89 else {}
                ),
            ),
            self.politica,
        )
        media_diaria = fmean(
            item.indice
            for item in resultado.indices_diarios.indices
            if item.indice is not None
        )
        self.assertNotAlmostEqual(resultado.agregacao_90d.indice_agregado, media_diaria)

    def test_warmup_fica_fora_da_agregacao_eventos_e_cobertura(self):
        features = criar_features(dias=97)
        alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        resultado = calcular_exposicao_propagacao_fogo(
            features, self.politica, janela_alvo=alvo
        )
        self.assertEqual(resultado.dias_contexto_calendario, 7)
        self.assertEqual(resultado.periodo_features, features.periodo)
        self.assertEqual(resultado.janela_analisada, alvo)
        self.assertEqual(len(resultado.propagacao_fogo_diaria), 90)
        self.assertEqual(resultado.agregacao_90d.dias_esperados, 90)
        self.assertEqual(resultado.agregacao_90d.eventos[0].duracao_dias, 90)


class TestProvenienciaESemantica(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_preserva_fonte_dataset_referencia_e_proveniencia_nasa(self):
        features = criar_features()
        resultado = calcular_exposicao_propagacao_fogo(features, self.politica)
        self.assertEqual(resultado.fonte, FonteDado.NASA_POWER)
        self.assertEqual(resultado.dataset, features.dataset)
        self.assertEqual(resultado.referencia_temporal, features.referencia_temporal)
        self.assertEqual(resultado.proveniencia_vento, VENTO_NASA)
        self.assertEqual(resultado.proveniencia_vento["altura_m"], 2)
        self.assertEqual(resultado.proveniencia_vento["parametro_fonte"], "WS2M")

    def test_open_meteo_permanece_serie_independente_sem_equivaler_alturas(self):
        nasa = calcular_exposicao_propagacao_fogo(criar_features(), self.politica)
        open_meteo = calcular_exposicao_propagacao_fogo(
            criar_features(fonte=FonteDado.OPEN_METEO), self.politica
        )
        self.assertEqual(open_meteo.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(open_meteo.proveniencia_vento, VENTO_OPEN_METEO)
        self.assertEqual(nasa.proveniencia_vento["altura_m"], 2)
        self.assertEqual(open_meteo.proveniencia_vento["altura_m"], 10)
        self.assertNotEqual(nasa.dataset, open_meteo.dataset)

    def test_metodologia_declara_proxy_e_limites_sem_probabilidade(self):
        resultado = calcular_exposicao_propagacao_fogo(criar_features(), self.politica)
        self.assertEqual(resultado.metodologia, METODOLOGIA_PROPAGACAO_FOGO)
        self.assertEqual(resultado.aviso_metodologia, AVISO_METODOLOGIA_PROPAGACAO_FOGO)
        self.assertIn("demonstrativo", resultado.aviso_metodologia.lower())
        self.assertIn("nao reproduz", resultado.aviso_metodologia.lower())
        self.assertIn(
            "nem representa probabilidade", resultado.aviso_metodologia.lower()
        )

    def test_contrato_diario_preserva_valores_componentes_e_metadados(self):
        dia = calcular_exposicao_propagacao_fogo(
            criar_features(), self.politica
        ).propagacao_fogo_diaria[0]
        self.assertEqual(dia.temperatura_maxima_c, 40)
        self.assertEqual(dia.umidade_relativa_media_pct, 20)
        self.assertEqual(dia.velocidade_vento_media_m_s, 8)
        self.assertEqual(dia.dias_desde_ultima_chuva_relevante, 7)
        self.assertEqual(dia.metodologia, METODOLOGIA_PROPAGACAO_FOGO)
        self.assertEqual(dia.politica_id, self.politica.id_politica)

    def test_modulo_nao_tem_io_mapbiomas_rajada_outros_perigos_ou_score(self):
        from backend.exposicao import perigo_propagacao_fogo

        codigo = inspect.getsource(perigo_propagacao_fogo).lower()
        for termo in (
            "requests",
            "http://",
            "https://",
            "open(",
            "read_csv",
            "to_csv",
            "fastapi",
            "supabase",
            "mapbiomas",
            "rajada",
            "tempestade",
            "granizo",
            "raio",
            "score_geral",
            "etapa3",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_entrada_e_resultado_sao_imutaveis(self):
        features = criar_features()
        antes = features.model_dump()
        resultado = calcular_exposicao_propagacao_fogo(features, self.politica)
        self.assertEqual(features.model_dump(), antes)
        with self.assertRaises(ValidationError):
            resultado.dataset = "outro"


if __name__ == "__main__":
    unittest.main()
