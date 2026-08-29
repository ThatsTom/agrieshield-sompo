from __future__ import annotations

import inspect
import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from backend.exposicao import (
    AVISO_CHUVA_COMPARTILHADA,
    AVISO_FOGO_TEMPESTADE_VENTO,
    AVISO_INSTABILIDADE_HIDRICA,
    GRUPO_DEPENDENCIA_HIDRICA,
    GRUPO_TRAFEGABILIDADE_METEOROLOGICA,
    FeatureDiariaCompartilhada,
    FeaturesDiariasCompartilhadas,
    JanelaHistorica,
    PerigoExposicao,
    ReferenciaTemporalHistorica,
    ResultadoValidacaoIntegradaPerigos,
    TipoDependenciaMetodologica,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
    calcular_exposicao_hidrica,
    calcular_exposicao_instabilidade,
    calcular_exposicao_propagacao_fogo,
    calcular_exposicao_tempestade,
    calcular_trafegabilidade_desfavoravel,
    criar_politica_agrishield_equip_v1,
    validar_cinco_perigos,
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


def _atributo_geo(
    variavel: str,
    valor: float | None,
    unidade: str,
    fonte: FonteDado,
    dataset: str,
    banda: str,
) -> AtributoGeoespacial:
    return AtributoGeoespacial(
        variavel=variavel,
        valor=valor,
        unidade=unidade,
        fonte=fonte,
        dataset=dataset,
        banda=banda,
        resolucao_m=30 if fonte == FonteDado.SRTM else 92.77,
        metodologia="metodologia-teste",
        qualidade=QualidadeDado(
            status=(
                StatusQualidade.DISPONIVEL
                if valor is not None
                else StatusQualidade.AUSENTE
            )
        ),
    )


def criar_geo(declividade: float | None = 0) -> AnaliseGeoespacialNormalizada:
    return AnaliseGeoespacialNormalizada(
        referencia=ReferenciaEspacial(latitude=-12.545, longitude=-55.721),
        declividade_media_graus=_atributo_geo(
            "declividade_media_graus",
            declividade,
            "graus",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "slope",
        ),
        posicao_topografica_relativa_m=_atributo_geo(
            "posicao_topografica_relativa_m",
            -2,
            "m",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "elevation",
        ),
        distancia_drenagem_m=_atributo_geo(
            "distancia_drenagem_m",
            2000,
            "m",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
        ),
        area_drenagem_montante_km2=_atributo_geo(
            "area_drenagem_montante_km2",
            850,
            "km2",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
        ),
        parametros=ParametrosGeoespaciais(
            raio_analise_m=1000,
            limiar_drenagem_km2=10,
            raio_busca_drenagem_m=50000,
        ),
        qualidade=QualidadeDado(status=StatusQualidade.DISPONIVEL),
        schema_version="1",
        algorithm_version="fase1-v3",
        status_fonte="sucesso",
    )


CENARIOS = {
    "seco_calmo": {
        "chuva": 0.0,
        "d1_d3": 0.0,
        "d4_d7": 0.0,
        "temperatura": 25.0,
        "umidade": 80.0,
        "vento": 0.0,
        "dias_secura": 10,
        "declividade": 0.0,
    },
    "chuva_persistente": {
        "chuva": 100.0,
        "d1_d3": 200.0,
        "d4_d7": 200.0,
        "temperatura": 20.0,
        "umidade": 90.0,
        "vento": 0.0,
        "dias_secura": 0,
        "declividade": 15.0,
    },
    "quente_seco_ventoso": {
        "chuva": 0.0,
        "d1_d3": 0.0,
        "d4_d7": 0.0,
        "temperatura": 40.0,
        "umidade": 20.0,
        "vento": 8.0,
        "dias_secura": 10,
        "declividade": 0.0,
    },
    "vento_chuva_forte": {
        "chuva": 100.0,
        "d1_d3": 200.0,
        "d4_d7": 200.0,
        "temperatura": 25.0,
        "umidade": 60.0,
        "vento": 8.0,
        "dias_secura": 0,
        "declividade": 5.0,
    },
    "relevo_chuva": {
        "chuva": 100.0,
        "d1_d3": 200.0,
        "d4_d7": 200.0,
        "temperatura": 20.0,
        "umidade": 90.0,
        "vento": 0.0,
        "dias_secura": 0,
        "declividade": 25.0,
    },
}


def criar_features(
    cenario: str = "seco_calmo",
    *,
    dias: int = 90,
    fonte: FonteDado = FonteDado.NASA_POWER,
    alterar=None,
) -> FeaturesDiariasCompartilhadas:
    valores_base = CENARIOS[cenario]
    periodo = JanelaHistorica.criar_atual(DATA_REFERENCIA, dias)
    itens = []
    for indice in range(dias):
        valores = dict(valores_base)
        if alterar is not None:
            valores.update(
                alterar(indice, periodo.inicio + timedelta(days=indice)) or {}
            )
        chuva = valores["chuva"]
        itens.append(
            FeatureDiariaCompartilhada(
                data=periodo.inicio + timedelta(days=indice),
                precipitacao_d0=chuva,
                precipitacao_d1_d3=valores["d1_d3"],
                precipitacao_d4_d7=valores["d4_d7"],
                acumulado_3d=(chuva * 3 if chuva is not None else None),
                acumulado_7d=(chuva * 7 if chuva is not None else None),
                dias_consecutivos_com_chuva=(
                    (indice + 1 if chuva is not None and chuva > 0 else 0)
                    if chuva is not None
                    else None
                ),
                dias_desde_ultima_chuva_relevante=valores["dias_secura"],
                temperatura_media=valores["temperatura"],
                temperatura_maxima=valores["temperatura"],
                temperatura_minima=valores["temperatura"],
                umidade_relativa=valores["umidade"],
                velocidade_vento_media_m_s=valores["vento"],
            )
        )
    if fonte == FonteDado.NASA_POWER:
        produto = TipoProdutoHistorico.HISTORICO_REGIONAL
        referencia = ReferenciaTemporalHistorica(
            tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
            descricao="Local Solar Time",
        )
        vento = VENTO_NASA
        dataset = "NASA/POWER DAILY"
    else:
        produto = TipoProdutoHistorico.REANALISE_MODELADA
        referencia = ReferenciaTemporalHistorica(tipo=TipoReferenciaTemporal.UTC)
        vento = VENTO_OPEN_METEO
        dataset = "Open-Meteo Historical Weather API"
    return FeaturesDiariasCompartilhadas(
        id_fazenda="fazenda-teste",
        fonte=fonte,
        natureza=NaturezaDado.HISTORICO,
        tipo_produto=produto,
        dataset=dataset,
        periodo=periodo,
        referencia_temporal=referencia,
        metadados_vento=vento,
        dias=tuple(itens),
    )


def executar(cenario: str, *, alterar=None, dias: int = 90):
    politica = criar_politica_agrishield_equip_v1()
    features = criar_features(cenario, alterar=alterar, dias=dias)
    geo = criar_geo(CENARIOS[cenario]["declividade"])
    alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90) if dias != 90 else None
    return validar_cinco_perigos(
        features,
        geo,
        politica,
        janela_alvo=alvo,
    )


class TestContratoIntegrado(unittest.TestCase):
    def setUp(self):
        self.politica = criar_politica_agrishield_equip_v1()
        self.features = criar_features("vento_chuva_forte")
        self.geo = criar_geo(5)
        self.resultado = validar_cinco_perigos(self.features, self.geo, self.politica)

    def test_cinco_perigos_compartilham_janela_politica_e_fonte(self):
        resultados = (
            self.resultado.exposicao_hidrica,
            self.resultado.trafegabilidade,
            self.resultado.instabilidade,
            self.resultado.propagacao_fogo,
            self.resultado.tempestade,
        )
        self.assertEqual(
            tuple(item.perigo for item in resultados),
            tuple(PerigoExposicao),
        )
        self.assertTrue(
            all(item.janela_analisada == self.resultado.janela for item in resultados)
        )
        self.assertTrue(
            all(item.politica_id == self.politica.id_politica for item in resultados)
        )
        self.assertEqual(self.resultado.fonte_meteorologica, FonteDado.NASA_POWER)
        self.assertEqual(self.resultado.propagacao_fogo.fonte, FonteDado.NASA_POWER)
        self.assertEqual(self.resultado.tempestade.fonte, FonteDado.NASA_POWER)

    def test_resultados_individuais_nao_foram_alterados_pela_integracao(self):
        alvo = self.features.periodo
        self.assertEqual(
            self.resultado.exposicao_hidrica,
            calcular_exposicao_hidrica(
                self.features,
                self.geo,
                self.politica,
                janela_alvo=alvo,
            ),
        )
        self.assertEqual(
            self.resultado.trafegabilidade,
            calcular_trafegabilidade_desfavoravel(
                self.features, self.politica, janela_alvo=alvo
            ),
        )
        self.assertEqual(
            self.resultado.instabilidade,
            calcular_exposicao_instabilidade(
                self.features, self.geo, self.politica, janela_alvo=alvo
            ),
        )
        self.assertEqual(
            self.resultado.propagacao_fogo,
            calcular_exposicao_propagacao_fogo(
                self.features, self.politica, janela_alvo=alvo
            ),
        )
        self.assertEqual(
            self.resultado.tempestade,
            calcular_exposicao_tempestade(
                self.features, self.politica, janela_alvo=alvo
            ),
        )

    def test_trafegabilidade_tem_metodologia_propria_e_nao_reutiliza_o_nucleo_hidrico(
        self,
    ):
        # Trafegabilidade deixou de compartilhar o núcleo meteorológico do
        # Hídrico: os campos e o tipo do resultado são estruturalmente
        # diferentes.
        self.assertNotIn(
            "condicoes_hidricas", type(self.resultado.trafegabilidade).model_fields
        )
        self.assertEqual(self.resultado.conflitos_para_composicao, ())

    def test_dependencias_metodologicas_estao_explicitas(self):
        por_perigo = {item.perigo: item for item in self.resultado.dependencias}
        self.assertEqual(
            por_perigo[PerigoExposicao.EXPOSICAO_HIDRICA].grupo_dependencia,
            GRUPO_DEPENDENCIA_HIDRICA,
        )
        self.assertEqual(
            por_perigo[PerigoExposicao.EXPOSICAO_HIDRICA].tipo_dependencia,
            TipoDependenciaMetodologica.DEPENDENCIA_PARCIAL,
        )
        self.assertEqual(
            por_perigo[PerigoExposicao.TRAFEGABILIDADE].grupo_dependencia,
            GRUPO_TRAFEGABILIDADE_METEOROLOGICA,
        )
        self.assertEqual(
            por_perigo[PerigoExposicao.TRAFEGABILIDADE].tipo_dependencia,
            TipoDependenciaMetodologica.EVIDENCIA_COMPARTILHADA,
        )
        for perigo in (
            PerigoExposicao.EXPOSICAO_HIDRICA,
            PerigoExposicao.TRAFEGABILIDADE,
        ):
            self.assertFalse(por_perigo[perigo].evidencia_independente)
        self.assertEqual(
            por_perigo[PerigoExposicao.INSTABILIDADE].tipo_dependencia,
            TipoDependenciaMetodologica.DEPENDENCIA_PARCIAL,
        )
        for perigo in (PerigoExposicao.INCENDIO, PerigoExposicao.TEMPESTADES):
            self.assertEqual(
                por_perigo[perigo].tipo_dependencia,
                TipoDependenciaMetodologica.EVIDENCIA_COMPARTILHADA,
            )

    def test_chuva_e_vento_compartilhados_diferenciam_mecanismos(self):
        mapa = {
            item.evidencia: item for item in self.resultado.evidencias_compartilhadas
        }
        self.assertEqual(
            set(mapa["precipitacao"].perigos),
            set(PerigoExposicao),
        )
        self.assertFalse(mapa["precipitacao"].mesmo_mecanismo)
        self.assertEqual(
            set(mapa["velocidade_vento_media_m_s"].perigos),
            {PerigoExposicao.INCENDIO, PerigoExposicao.TEMPESTADES},
        )
        self.assertFalse(mapa["velocidade_vento_media_m_s"].mesmo_mecanismo)
        self.assertIn(AVISO_INSTABILIDADE_HIDRICA, self.resultado.avisos)
        self.assertIn(AVISO_FOGO_TEMPESTADE_VENTO, self.resultado.avisos)
        self.assertIn(AVISO_CHUVA_COMPARTILHADA, self.resultado.avisos)

    def test_coberturas_individuais_refletem_cada_agregacao(self):
        for perigo, resultado in zip(
            PerigoExposicao,
            (
                self.resultado.exposicao_hidrica,
                self.resultado.trafegabilidade,
                self.resultado.instabilidade,
                self.resultado.propagacao_fogo,
                self.resultado.tempestade,
            ),
        ):
            cobertura = self.resultado.cobertura_de(perigo)
            self.assertEqual(
                cobertura.dias_esperados, resultado.agregacao_90d.dias_esperados
            )
            self.assertEqual(
                cobertura.dias_disponiveis, resultado.agregacao_90d.dias_disponiveis
            )
            self.assertEqual(
                cobertura.cobertura_percentual,
                resultado.agregacao_90d.cobertura_percentual,
            )
            self.assertEqual(
                cobertura.qualidade_suficiente,
                resultado.agregacao_90d.qualidade_suficiente,
            )

    def test_divergencia_de_janela_e_rejeitada(self):
        features = criar_features("vento_chuva_forte", dias=97)
        alvo = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        base = validar_cinco_perigos(
            features, self.geo, self.politica, janela_alvo=alvo
        )
        alvo_divergente = JanelaHistorica(
            data_referencia=DATA_REFERENCIA,
            inicio=alvo.inicio - timedelta(days=1),
            fim=alvo.fim - timedelta(days=1),
            dias_esperados=90,
            finalidade="COMPARACAO_ANTERIOR",
        )
        tempestade_divergente = calcular_exposicao_tempestade(
            features,
            self.politica,
            janela_alvo=alvo_divergente,
        )
        dados = base.model_dump()
        dados["tempestade"] = tempestade_divergente.model_dump()
        with self.assertRaisesRegex(ValidationError, "janela"):
            ResultadoValidacaoIntegradaPerigos.model_validate(dados)

    def test_mistura_silenciosa_de_fonte_e_rejeitada(self):
        open_meteo = criar_features("vento_chuva_forte", fonte=FonteDado.OPEN_METEO)
        fogo_open = calcular_exposicao_propagacao_fogo(open_meteo, self.politica)
        dados = self.resultado.model_dump()
        dados["propagacao_fogo"] = fogo_open.model_dump()
        with self.assertRaisesRegex(ValidationError, "fonte meteorologica"):
            ResultadoValidacaoIntegradaPerigos.model_validate(dados)

    def test_execucao_open_meteo_coerente_preserva_uma_unica_fonte(self):
        features = criar_features("vento_chuva_forte", fonte=FonteDado.OPEN_METEO)
        resultado = validar_cinco_perigos(features, self.geo, self.politica)
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.OPEN_METEO)
        self.assertEqual(resultado.propagacao_fogo.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(resultado.tempestade.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(resultado.propagacao_fogo.proveniencia_vento, VENTO_OPEN_METEO)
        self.assertEqual(resultado.tempestade.proveniencia_vento, VENTO_OPEN_METEO)

    def test_sem_score_pesos_gerais_ou_contribuicao_ponderada(self):
        campos = set(ResultadoValidacaoIntegradaPerigos.model_fields)
        self.assertTrue(
            campos.isdisjoint(
                {"score", "score_geral", "contribuicoes", "indice_composto"}
            )
        )
        from backend.exposicao import validacao_integrada

        codigo = inspect.getsource(validacao_integrada).lower()
        for termo in ("pesos_perigos", "contribuicao_ponderada", "score_geral"):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_determinismo_input_nao_mutado_e_resultado_imutavel(self):
        antes_features = self.features.model_dump()
        antes_geo = self.geo.model_dump()
        repetido = validar_cinco_perigos(self.features, self.geo, self.politica)
        self.assertEqual(self.resultado, repetido)
        self.assertEqual(self.features.model_dump(), antes_features)
        self.assertEqual(self.geo.model_dump(), antes_geo)
        with self.assertRaises(ValidationError):
            self.resultado.conflitos_para_composicao = ()

    def test_contexto_anterior_nao_entra_na_janela(self):
        resultado = executar("vento_chuva_forte", dias=97)
        self.assertEqual(resultado.periodo_features.dias_esperados, 97)
        self.assertEqual(resultado.janela.dias_esperados, 90)
        self.assertTrue(
            all(cobertura.dias_esperados == 90 for cobertura in resultado.coberturas)
        )
        self.assertEqual(resultado.exposicao_hidrica.dias_contexto_calendario, 7)
        self.assertEqual(resultado.propagacao_fogo.dias_contexto_calendario, 7)

    def test_proveniencia_meteorologica_e_territorial_preservadas(self):
        self.assertEqual(self.resultado.dataset, self.features.dataset)
        self.assertEqual(
            self.resultado.referencia_temporal, self.features.referencia_temporal
        )
        self.assertEqual(self.resultado.propagacao_fogo.proveniencia_vento, VENTO_NASA)
        self.assertEqual(self.resultado.tempestade.proveniencia_vento, VENTO_NASA)
        self.assertEqual(self.resultado.instabilidade.evidencia_geoespacial, self.geo)


class TestCenariosIntegrados(unittest.TestCase):
    def test_cenario_seco_e_calmo_tem_indices_baixos_sem_eventos(self):
        resultado = executar("seco_calmo")
        for perigo in (
            resultado.exposicao_hidrica,
            resultado.trafegabilidade,
            resultado.instabilidade,
            resultado.propagacao_fogo,
            resultado.tempestade,
        ):
            self.assertEqual(perigo.agregacao_90d.quantidade_eventos, 0)
            self.assertEqual(perigo.agregacao_90d.indice_agregado, 0)

    def test_cenario_chuva_persistente_eleva_nucleo_hidrico_e_ativa_instabilidade(self):
        resultado = executar("chuva_persistente")
        self.assertGreater(resultado.exposicao_hidrica.agregacao_90d.indice_agregado, 0)
        # Trafegabilidade tem metodologia própria: também reage à chuva
        # persistente, mas não precisa (nem deve) produzir o mesmo valor do
        # Hídrico — as fórmulas são independentes (neste cenário sintético
        # extremo, ambas apenas saturam em 100 pelo mesmo motivo: o cenário
        # foi desenhado para maximizar todos os perigos).
        self.assertGreater(resultado.trafegabilidade.agregacao_90d.indice_agregado, 0)
        self.assertGreater(resultado.instabilidade.agregacao_90d.indice_agregado, 0)
        self.assertNotEqual(
            resultado.instabilidade.indices_diarios.indices,
            resultado.exposicao_hidrica.indices_diarios.indices,
        )
        self.assertEqual(resultado.propagacao_fogo.agregacao_90d.indice_agregado, 0)
        self.assertEqual(resultado.tempestade.agregacao_90d.indice_agregado, 0)

    def test_cenario_quente_seco_ventoso_separa_fogo_de_tempestade(self):
        resultado = executar("quente_seco_ventoso")
        self.assertEqual(resultado.exposicao_hidrica.agregacao_90d.indice_agregado, 0)
        fogo_dia = resultado.propagacao_fogo.propagacao_fogo_diaria[0]
        tempestade_dia = resultado.tempestade.tempestades_diarias[0]
        self.assertEqual(fogo_dia.indice_exposicao_propagacao_fogo, 100)
        self.assertEqual(tempestade_dia.indice_exposicao_tempestade, 75)
        self.assertNotEqual(
            resultado.propagacao_fogo.indices_diarios.indices,
            resultado.tempestade.indices_diarios.indices,
        )

    def test_cenario_vento_e_chuva_forte_eleva_tempestade_e_hidrico_sem_somar(self):
        resultado = executar("vento_chuva_forte")
        self.assertEqual(
            resultado.tempestade.tempestades_diarias[0].indice_exposicao_tempestade,
            100,
        )
        self.assertGreater(resultado.exposicao_hidrica.agregacao_90d.indice_agregado, 0)

    def test_cenario_relevo_e_chuva_separa_suscetibilidade_da_ativacao(self):
        com_chuva = executar("relevo_chuva")
        seco = validar_cinco_perigos(
            criar_features("seco_calmo"),
            criar_geo(25),
            criar_politica_agrishield_equip_v1(),
        )
        self.assertEqual(
            com_chuva.instabilidade.suscetibilidade_topografica.indice_suscetibilidade_topografica,
            100,
        )
        self.assertEqual(
            seco.instabilidade.suscetibilidade_topografica.indice_suscetibilidade_topografica,
            100,
        )
        self.assertGreater(com_chuva.instabilidade.agregacao_90d.quantidade_eventos, 0)
        self.assertEqual(seco.instabilidade.agregacao_90d.quantidade_eventos, 0)


class TestGapsIntegrados(unittest.TestCase):
    def test_gap_de_chuva_afeta_dependencias_corretas_sem_virar_zero(self):
        def gap(indice, _):
            if indice != 45:
                return {}
            return {
                "chuva": None,
                "d1_d3": None,
                "d4_d7": None,
                "dias_secura": None,
            }

        resultado = executar("vento_chuva_forte", alterar=gap)
        esperados = {
            PerigoExposicao.EXPOSICAO_HIDRICA: 89,
            PerigoExposicao.TRAFEGABILIDADE: 89,
            PerigoExposicao.INSTABILIDADE: 89,
            PerigoExposicao.INCENDIO: 90,
            PerigoExposicao.TEMPESTADES: 89,
        }
        for perigo, dias in esperados.items():
            self.assertEqual(resultado.cobertura_de(perigo).dias_disponiveis, dias)
        self.assertIsNone(
            resultado.exposicao_hidrica.indices_diarios.indices[45].indice
        )
        self.assertIsNone(resultado.tempestade.indices_diarios.indices[45].indice)
        self.assertIsNotNone(
            resultado.propagacao_fogo.indices_diarios.indices[45].indice
        )
        self.assertEqual(
            resultado.exposicao_hidrica.agregacao_90d.quantidade_eventos, 2
        )
        self.assertEqual(resultado.tempestade.agregacao_90d.quantidade_eventos, 2)

    def test_gap_de_vento_afeta_fogo_e_tempestade(self):
        resultado = executar(
            "vento_chuva_forte",
            alterar=lambda indice, _: {"vento": None} if indice == 45 else {},
        )
        self.assertEqual(
            resultado.cobertura_de(PerigoExposicao.INCENDIO).dias_disponiveis, 89
        )
        self.assertEqual(
            resultado.cobertura_de(PerigoExposicao.TEMPESTADES).dias_disponiveis, 89
        )
        self.assertEqual(
            resultado.cobertura_de(PerigoExposicao.EXPOSICAO_HIDRICA).dias_disponiveis,
            90,
        )
        self.assertIsNone(resultado.propagacao_fogo.indices_diarios.indices[45].indice)
        self.assertIsNone(resultado.tempestade.indices_diarios.indices[45].indice)
        self.assertEqual(resultado.propagacao_fogo.agregacao_90d.quantidade_eventos, 2)
        self.assertEqual(resultado.tempestade.agregacao_90d.quantidade_eventos, 2)

    def test_gap_de_umidade_ou_temperatura_afeta_somente_fogo(self):
        for campo in ("umidade", "temperatura"):
            with self.subTest(campo=campo):
                resultado = executar(
                    "vento_chuva_forte",
                    alterar=lambda indice, _, campo=campo: (
                        {campo: None} if indice == 45 else {}
                    ),
                )
                self.assertEqual(
                    resultado.cobertura_de(PerigoExposicao.INCENDIO).dias_disponiveis,
                    89,
                )
                for perigo in (
                    PerigoExposicao.EXPOSICAO_HIDRICA,
                    PerigoExposicao.TRAFEGABILIDADE,
                    PerigoExposicao.INSTABILIDADE,
                    PerigoExposicao.TEMPESTADES,
                ):
                    self.assertEqual(
                        resultado.cobertura_de(perigo).dias_disponiveis, 90
                    )
                self.assertIsNone(
                    resultado.propagacao_fogo.indices_diarios.indices[45].indice
                )

    def test_coberturas_distintas_preservam_qualidade_individual(self):
        resultado = executar(
            "vento_chuva_forte",
            alterar=lambda indice, _: {"vento": None} if indice < 20 else {},
        )
        fogo = resultado.cobertura_de(PerigoExposicao.INCENDIO)
        tempestade = resultado.cobertura_de(PerigoExposicao.TEMPESTADES)
        hidrico = resultado.cobertura_de(PerigoExposicao.EXPOSICAO_HIDRICA)
        self.assertEqual(fogo.dias_disponiveis, 70)
        self.assertFalse(fogo.qualidade_suficiente)
        self.assertEqual(tempestade.dias_disponiveis, 70)
        self.assertFalse(tempestade.qualidade_suficiente)
        self.assertEqual(hidrico.dias_disponiveis, 90)
        self.assertTrue(hidrico.qualidade_suficiente)


if __name__ == "__main__":
    unittest.main()
