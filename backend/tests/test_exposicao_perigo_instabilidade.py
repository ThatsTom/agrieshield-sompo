from __future__ import annotations

import inspect
import math
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from pydantic import ValidationError

from backend.exposicao import (
    CondicaoHidricaDiaria,
    FaixaAtivacaoHidrica,
    FeatureDiariaCompartilhada,
    FeaturesDiariasCompartilhadas,
    JanelaHistorica,
    MOTIVO_ATIVACAO_APLICADA,
    MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL,
    MOTIVO_DADO_HIDRICO_INDISPONIVEL,
    ParametrosInstabilidade,
    PerigoExposicao,
    PontoCurvaDeclividade,
    ReferenciaTemporalHistorica,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    agrupar_eventos,
    calcular_exposicao_instabilidade,
    calcular_instabilidade_diaria,
    calcular_suscetibilidade_topografica,
    criar_politica_agrishield_equip_v1,
    normalizar_declividade,
    obter_fator_ativacao_hidrica,
)
from backend.risco.modelos import (
    AnaliseGeoespacialNormalizada,
    AtributoGeoespacial,
    FonteDado,
    NaturezaDado,
    ParametrosGeoespaciais,
    QualidadeDado,
    ReferenciaEspacial,
    StatusQualidade,
)


DATA_REFERENCIA = date(2026, 8, 11)


def _atributo_geo(
    variavel: str,
    valor: float | None,
    unidade: str,
    fonte: FonteDado,
    dataset: str,
    banda: str,
    metodologia: str,
) -> AtributoGeoespacial:
    return AtributoGeoespacial(
        variavel=variavel,
        valor=valor,
        unidade=unidade,
        fonte=fonte,
        dataset=dataset,
        banda=banda,
        resolucao_m=30 if fonte == FonteDado.SRTM else 92.77,
        metodologia=metodologia,
        qualidade=QualidadeDado(
            status=(
                StatusQualidade.DISPONIVEL
                if valor is not None
                else StatusQualidade.AUSENTE
            )
        ),
    )


def criar_geo(
    declividade: float | None = 10,
    posicao: float | None = -2,
) -> AnaliseGeoespacialNormalizada:
    return AnaliseGeoespacialNormalizada(
        referencia=ReferenciaEspacial(latitude=-12.545, longitude=-55.721),
        declividade_media_graus=_atributo_geo(
            "declividade_media_graus",
            declividade,
            "graus",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "slope",
            "Media da declividade no buffer de analise",
        ),
        posicao_topografica_relativa_m=_atributo_geo(
            "posicao_topografica_relativa_m",
            posicao,
            "m",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "elevation",
            "Elevacao no ponto menos a elevacao media no buffer de analise",
        ),
        distancia_drenagem_m=_atributo_geo(
            "distancia_drenagem_m",
            2000,
            "m",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
            "Distancia geodesica ao centro do pixel MERIT selecionado",
        ),
        area_drenagem_montante_km2=_atributo_geo(
            "area_drenagem_montante_km2",
            850,
            "km2",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
            "Area contribuinte do mesmo pixel selecionado",
        ),
        parametros=ParametrosGeoespaciais(
            raio_analise_m=1000,
            limiar_drenagem_km2=10,
            raio_busca_drenagem_m=50000,
        ),
        qualidade=QualidadeDado(status=StatusQualidade.DISPONIVEL),
        qualidade_contexto={"representatividade": "entorno_de_ponto"},
        fontes=(
            {"identificador": "USGS/SRTMGL1_003", "resolucao_m": 30},
            {"identificador": "MERIT/Hydro/v1_0_1", "resolucao_m": 92.77},
        ),
        schema_version="1",
        algorithm_version="fase1-v3",
        status_fonte="sucesso",
    )


def criar_features(
    *,
    hidrico_disponivel: bool = True,
    chuva: float = 0,
    dias: int = 90,
) -> FeaturesDiariasCompartilhadas:
    periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    valor = chuva if hidrico_disponivel else None
    features = tuple(
        FeatureDiariaCompartilhada(
            data=periodo.inicio + timedelta(days=indice),
            precipitacao_d0=valor,
            precipitacao_d1_d3=(valor * 3 if valor is not None else None),
            precipitacao_d4_d7=(valor * 4 if valor is not None else None),
            dias_consecutivos_com_chuva=(
                (indice + 1 if valor is not None and valor > 0 else 0)
                if valor is not None
                else None
            ),
        )
        for indice in range(dias)
    )
    return FeaturesDiariasCompartilhadas(
        id_fazenda="fazenda-teste",
        fonte=FonteDado.NASA_POWER,
        natureza=NaturezaDado.HISTORICO,
        tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
        dataset="NASA/POWER",
        periodo=periodo,
        referencia_temporal=ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        ),
        dias=features,
    )


def condicao(indice: float | None) -> CondicaoHidricaDiaria:
    return CondicaoHidricaDiaria(
        data=DATA_REFERENCIA,
        indice_hidrico_meteorologico=indice,
    )


class TestPoliticaInstabilidade(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_parametros_default_exatos(self):
        parametros = self.politica.parametros_instabilidade
        self.assertEqual(
            tuple(
                (p.declividade_graus, p.indice) for p in parametros.curva_declividade
            ),
            ((0, 0), (5, 15), (10, 35), (15, 60), (20, 80), (25, 100)),
        )
        self.assertEqual(
            tuple(
                (f.inicio_indice_hidrico, f.fator_ativacao)
                for f in parametros.faixas_ativacao_hidrica
            ),
            ((0, 0.0), (25, 0.35), (50, 0.65), (75, 1.0)),
        )

    def test_curva_rejeita_pontos_desordenados(self):
        dados = self.politica.parametros_instabilidade.model_dump()
        dados["curva_declividade"] = (
            PontoCurvaDeclividade(declividade_graus=0, indice=0),
            PontoCurvaDeclividade(declividade_graus=10, indice=50),
            PontoCurvaDeclividade(declividade_graus=5, indice=60),
        )
        with self.assertRaises(ValidationError):
            ParametrosInstabilidade(**dados)

    def test_curva_rejeita_indices_decrescentes(self):
        dados = self.politica.parametros_instabilidade.model_dump()
        dados["curva_declividade"] = (
            PontoCurvaDeclividade(declividade_graus=0, indice=20),
            PontoCurvaDeclividade(declividade_graus=5, indice=10),
        )
        with self.assertRaises(ValidationError):
            ParametrosInstabilidade(**dados)

    def test_faixas_rejeitam_ordem_e_fator_invalido(self):
        dados = self.politica.parametros_instabilidade.model_dump()
        for faixas in (
            (
                FaixaAtivacaoHidrica(inicio_indice_hidrico=0, fator_ativacao=0),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=50, fator_ativacao=0.5),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=25, fator_ativacao=1),
            ),
            (
                FaixaAtivacaoHidrica(inicio_indice_hidrico=0, fator_ativacao=0.5),
                FaixaAtivacaoHidrica(inicio_indice_hidrico=25, fator_ativacao=0.4),
            ),
        ):
            dados["faixas_ativacao_hidrica"] = faixas
            with self.subTest(faixas=faixas), self.assertRaises(ValidationError):
                ParametrosInstabilidade(**dados)
        with self.assertRaises(ValidationError):
            FaixaAtivacaoHidrica(inicio_indice_hidrico=0, fator_ativacao=1.01)

    def test_configuracao_e_imutavel(self):
        with self.assertRaises(ValidationError):
            self.politica.parametros_instabilidade.curva_declividade = ()


class TestCurvaTopografica(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_pontos_exatos(self):
        for graus, esperado in (
            (0, 0),
            (5, 15),
            (10, 35),
            (15, 60),
            (20, 80),
            (25, 100),
        ):
            with self.subTest(graus=graus):
                self.assertEqual(normalizar_declividade(graus, self.politica), esperado)

    def test_acima_do_ultimo_ponto_satura(self):
        self.assertEqual(normalizar_declividade(40, self.politica), 100)

    def test_interpolacao_linear(self):
        self.assertEqual(normalizar_declividade(2.5, self.politica), 7.5)
        self.assertEqual(normalizar_declividade(7.5, self.politica), 25)
        self.assertEqual(normalizar_declividade(12.5, self.politica), 47.5)

    def test_none_permanece_ausente(self):
        self.assertIsNone(normalizar_declividade(None, self.politica))

    def test_valores_invalidos_sao_rejeitados(self):
        for valor in (-0.1, math.nan, math.inf, True, "10"):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                normalizar_declividade(valor, self.politica)

    def test_unidade_diferente_de_graus_e_rejeitada(self):
        geo = criar_geo()
        declividade = geo.declividade_media_graus.model_copy(
            update={"unidade": "percentual"}
        )
        geo_incoerente = geo.model_copy(update={"declividade_media_graus": declividade})
        with self.assertRaises(ValueError):
            calcular_suscetibilidade_topografica(geo_incoerente, self.politica)

    def test_posicao_topografica_e_preservada_mas_nao_altera_indice(self):
        baixa = calcular_suscetibilidade_topografica(
            criar_geo(posicao=-20), self.politica
        )
        alta = calcular_suscetibilidade_topografica(
            criar_geo(posicao=20), self.politica
        )
        self.assertEqual(
            baixa.indice_suscetibilidade_topografica,
            alta.indice_suscetibilidade_topografica,
        )
        self.assertEqual(baixa.posicao_topografica_relativa.valor, -20)
        self.assertFalse(baixa.posicao_topografica_aplicada_no_calculo)

    def test_proveniencia_srtm_e_metodologia_sao_preservadas(self):
        geo = criar_geo()
        resultado = calcular_suscetibilidade_topografica(geo, self.politica)
        self.assertEqual(resultado.declividade_media, geo.declividade_media_graus)
        self.assertEqual(resultado.declividade_media.fonte, FonteDado.SRTM)
        self.assertEqual(resultado.declividade_media.dataset, "USGS/SRTMGL1_003")
        self.assertEqual(resultado.declividade_media.unidade, "graus")
        self.assertIn("buffer", resultado.declividade_media.metodologia.lower())


class TestAtivacaoHidrica(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_limites_das_faixas(self):
        casos = (
            (0, 0.0),
            (24.999, 0.0),
            (25, 0.35),
            (49.999, 0.35),
            (50, 0.65),
            (74.999, 0.65),
            (75, 1.0),
            (100, 1.0),
        )
        for indice, esperado in casos:
            with self.subTest(indice=indice):
                self.assertEqual(
                    obter_fator_ativacao_hidrica(indice, self.politica), esperado
                )

    def test_none_nao_vira_ativacao_zero(self):
        self.assertIsNone(obter_fator_ativacao_hidrica(None, self.politica))

    def test_indice_hidrico_invalido_e_rejeitado(self):
        for valor in (-1, 101, math.nan, math.inf, True, "25"):
            with self.subTest(valor=valor), self.assertRaises((TypeError, ValueError)):
                obter_fator_ativacao_hidrica(valor, self.politica)


class TestInstabilidadeDiaria(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def _calcular(self, declividade: float | None, indice_hidrico: float | None):
        suscetibilidade = calcular_suscetibilidade_topografica(
            criar_geo(declividade=declividade), self.politica
        )
        return calcular_instabilidade_diaria(
            suscetibilidade, condicao(indice_hidrico), self.politica
        )

    def test_terreno_plano_e_seco(self):
        dia = self._calcular(0, 0)
        self.assertEqual(dia.indice_suscetibilidade_topografica, 0)
        self.assertEqual(dia.indice_exposicao_instabilidade, 0)

    def test_terreno_inclinado_preserva_suscetibilidade_mas_exposicao_seca_e_zero(self):
        dia = self._calcular(10, 0)
        self.assertEqual(dia.indice_suscetibilidade_topografica, 35)
        self.assertEqual(dia.fator_ativacao_hidrica, 0)
        self.assertEqual(dia.indice_exposicao_instabilidade, 0)
        self.assertTrue(dia.ativacao_hidrica_aplicada)

    def test_exemplos_de_ativacao_para_suscetibilidade_sessenta(self):
        for indice_hidrico, fator, exposicao in (
            (10, 0.0, 0),
            (25, 0.35, 21),
            (50, 0.65, 39),
            (75, 1.0, 60),
        ):
            with self.subTest(indice_hidrico=indice_hidrico):
                dia = self._calcular(15, indice_hidrico)
                self.assertEqual(dia.indice_suscetibilidade_topografica, 60)
                self.assertEqual(dia.fator_ativacao_hidrica, fator)
                self.assertEqual(dia.indice_exposicao_instabilidade, exposicao)
                self.assertEqual(dia.motivo, MOTIVO_ATIVACAO_APLICADA)

    def test_indice_final_satura_em_cem(self):
        self.assertEqual(self._calcular(25, 100).indice_exposicao_instabilidade, 100)

    def test_declividade_ausente_torna_indice_indisponivel(self):
        dia = self._calcular(None, 75)
        self.assertIsNone(dia.indice_suscetibilidade_topografica)
        self.assertIsNone(dia.indice_exposicao_instabilidade)
        self.assertFalse(dia.ativacao_hidrica_aplicada)
        self.assertEqual(dia.motivo, MOTIVO_DADO_DECLIVIDADE_INDISPONIVEL)

    def test_hidrico_ausente_preserva_base_mas_nao_fabrica_exposicao(self):
        dia = self._calcular(10, None)
        self.assertEqual(dia.indice_suscetibilidade_topografica, 35)
        self.assertIsNone(dia.indice_exposicao_instabilidade)
        self.assertIsNone(dia.fator_ativacao_hidrica)
        self.assertFalse(dia.ativacao_hidrica_aplicada)
        self.assertEqual(dia.motivo, MOTIVO_DADO_HIDRICO_INDISPONIVEL)

    def test_determinismo_e_entrada_imutavel(self):
        geo = criar_geo()
        antes = geo.model_dump()
        suscetibilidade = calcular_suscetibilidade_topografica(geo, self.politica)
        primeiro = calcular_instabilidade_diaria(
            suscetibilidade, condicao(50), self.politica
        )
        segundo = calcular_instabilidade_diaria(
            suscetibilidade, condicao(50), self.politica
        )
        self.assertEqual(primeiro, segundo)
        self.assertEqual(geo.model_dump(), antes)


class TestResultadoNoventaDias(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()

    def test_usa_indices_eventos_e_agregacao_da_fase_tres(self):
        resultado = calcular_exposicao_instabilidade(
            criar_features(), criar_geo(declividade=10), self.politica
        )
        self.assertEqual(resultado.perigo, PerigoExposicao.INSTABILIDADE)
        self.assertEqual(len(resultado.indices_diarios.indices), 90)
        self.assertEqual(
            resultado.agregacao_90d.eventos,
            agrupar_eventos(resultado.indices_diarios, self.politica),
        )
        self.assertEqual(
            resultado.agregacao_90d.classificacao_agregada,
            self.politica.classificar_indice(resultado.agregacao_90d.indice_agregado),
        )

    def test_exposicao_temporal_continua_forma_um_evento_de_noventa_dias(self):
        resultado = calcular_exposicao_instabilidade(
            criar_features(chuva=100), criar_geo(declividade=10), self.politica
        )
        self.assertEqual(resultado.agregacao_90d.quantidade_eventos, 1)
        self.assertEqual(resultado.agregacao_90d.eventos[0].duracao_dias, 90)
        self.assertEqual(resultado.agregacao_90d.quantidade_dias_relevantes, 90)

    def test_cobertura_completa_com_declividade_disponivel(self):
        resultado = calcular_exposicao_instabilidade(
            criar_features(), criar_geo(), self.politica
        )
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 90)
        self.assertEqual(resultado.agregacao_90d.cobertura_percentual, 100)
        self.assertTrue(resultado.agregacao_90d.qualidade_suficiente)

    def test_ausencia_territorial_reduz_disponibilidade_e_qualidade(self):
        resultado = calcular_exposicao_instabilidade(
            criar_features(), criar_geo(declividade=None), self.politica
        )
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 0)
        self.assertEqual(resultado.agregacao_90d.cobertura_percentual, 0)
        self.assertFalse(resultado.agregacao_90d.qualidade_suficiente)
        self.assertIsNone(resultado.agregacao_90d.indice_agregado)

    def test_ausencia_hidrica_preserva_suscetibilidade_mas_reduz_cobertura_temporal(
        self,
    ):
        resultado = calcular_exposicao_instabilidade(
            criar_features(hidrico_disponivel=False),
            criar_geo(declividade=10),
            self.politica,
        )
        self.assertEqual(resultado.agregacao_90d.dias_disponiveis, 0)
        self.assertIsNone(resultado.agregacao_90d.indice_agregado)
        self.assertTrue(
            all(
                item.indice_suscetibilidade_topografica == 35
                and item.indice_exposicao_instabilidade is None
                and item.fator_ativacao_hidrica is None
                and not item.ativacao_hidrica_aplicada
                and item.motivo == MOTIVO_DADO_HIDRICO_INDISPONIVEL
                for item in resultado.instabilidades_diarias
            )
        )

    def test_topografia_suscetivel_e_noventa_dias_secos_nao_formam_evento(self):
        resultado = calcular_exposicao_instabilidade(
            criar_features(chuva=0), criar_geo(declividade=15), self.politica
        )
        self.assertEqual(
            resultado.suscetibilidade_topografica.indice_suscetibilidade_topografica,
            60,
        )
        self.assertTrue(
            all(
                item.indice_suscetibilidade_topografica == 60
                and item.indice_exposicao_instabilidade == 0
                for item in resultado.instabilidades_diarias
            )
        )
        agregado = resultado.agregacao_90d
        self.assertEqual(agregado.quantidade_eventos, 0)
        self.assertEqual(agregado.frequencia_score, 0)
        self.assertEqual(agregado.duracao_score, 0)
        self.assertEqual(agregado.recorrencia_score, 0)
        self.assertEqual(agregado.indice_agregado, 0)

    def test_reutiliza_nucleo_hidrico_da_fase_quatro_uma_vez(self):
        features = criar_features()
        from backend.exposicao import perigo_instabilidade

        original = perigo_instabilidade.calcular_condicoes_hidricas
        with patch.object(
            perigo_instabilidade,
            "calcular_condicoes_hidricas",
            wraps=original,
        ) as calcular:
            calcular_exposicao_instabilidade(features, criar_geo(), self.politica)
        calcular.assert_called_once_with(features, self.politica, features.periodo)

    def test_resultado_preserva_contexto_geoespacial_versionado(self):
        geo = criar_geo()
        resultado = calcular_exposicao_instabilidade(
            criar_features(), geo, self.politica
        )
        self.assertEqual(resultado.evidencia_geoespacial, geo)
        self.assertEqual(resultado.evidencia_geoespacial.algorithm_version, "fase1-v3")
        self.assertEqual(resultado.evidencia_geoespacial.schema_version, "1")
        self.assertEqual(
            resultado.evidencia_geoespacial.parametros.raio_analise_m, 1000
        )
        self.assertEqual(
            resultado.parametros_instabilidade, self.politica.parametros_instabilidade
        )

    def test_warmup_nao_entra_na_janela_final(self):
        features = criar_features(dias=97)
        alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        resultado = calcular_exposicao_instabilidade(
            features, criar_geo(), self.politica, janela_alvo=alvo
        )
        self.assertEqual(resultado.dias_contexto_calendario, 7)
        self.assertEqual(resultado.indices_diarios.periodo, alvo)
        self.assertEqual(len(resultado.instabilidades_diarias), 90)


class TestEscopoSemantico(unittest.TestCase):
    def test_modulo_e_puro_e_nao_implementa_outros_perigos(self):
        from backend.exposicao import perigo_instabilidade

        codigo = inspect.getsource(perigo_instabilidade).lower()
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
            "incendio",
            "tempestades",
            "probabilidade",
            "tombamento",
            "fabricante",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_nao_usa_drenagem_no_calculo(self):
        base = criar_geo()
        alterada = base.model_copy(
            update={
                "distancia_drenagem_m": base.distancia_drenagem_m.model_copy(
                    update={"valor": 1}
                ),
                "area_drenagem_montante_km2": (
                    base.area_drenagem_montante_km2.model_copy(update={"valor": 999999})
                ),
            }
        )
        politica = criar_politica_agrishield_equip_v1()
        self.assertEqual(
            calcular_suscetibilidade_topografica(
                base, politica
            ).indice_suscetibilidade_topografica,
            calcular_suscetibilidade_topografica(
                alterada, politica
            ).indice_suscetibilidade_topografica,
        )


if __name__ == "__main__":
    unittest.main()
