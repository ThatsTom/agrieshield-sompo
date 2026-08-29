from datetime import date, datetime, timezone
import sys
from pathlib import Path
import unittest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from risco.agregador import _qualidade_global, agregar_features  # noqa: E402
from risco.modelos import (  # noqa: E402
    AgregacaoTemporal,
    AnaliseGeoespacialNormalizada,
    AnaliseTerritorialNormalizada,
    AtributoGeoespacial,
    CadastroNormalizado,
    ContextoGeometriaTerritorial,
    DistribuicaoClasseTerritorial,
    FeatureNeutra,
    FonteDado,
    GrupoFeatures,
    LinhagemFeature,
    NaturezaDado,
    ParametrosGeoespaciais,
    QualidadeDado,
    QualidadeTerritorial,
    ReferenciaEspacial,
    ReferenciaTemporal,
    StatusQualidade,
)


def cadastro(area=250.0):
    return CadastroNormalizado(
        id_fazenda="1",
        nome="Boa Esperança",
        numero_apolice="AP-1",
        cep="00000000",
        cidade="Sorriso",
        uf="MT",
        latitude=-12.5,
        longitude=-55.7,
        area_ha=area,
        tipo_operacao="campo",
        proximidade_agua_declarada=False,
    )


def climaticas():
    qualidade = QualidadeDado(status=StatusQualidade.DISPONIVEL, cobertura_pct=100)
    feature = FeatureNeutra(
        nome="chuva_acumulada_7_dias_mm",
        valor=10.0,
        unidade="mm",
        fonte=FonteDado.NASA_POWER,
        natureza=NaturezaDado.HISTORICO,
        referencia_temporal=ReferenciaTemporal(
            inicio=date(2026, 8, 5),
            fim=date(2026, 8, 11),
            agregacao=AgregacaoTemporal.DIARIA,
        ),
        qualidade=qualidade,
        linhagem=LinhagemFeature(
            algoritmo="soma_precipitacao_janela_calendario",
            fonte=FonteDado.NASA_POWER,
            natureza=NaturezaDado.HISTORICO,
            janela="7_dias_calendario_inclusivos",
            entradas=("precipitacao_diaria_mm",),
        ),
    )
    return GrupoFeatures(features=(feature,), qualidade=qualidade)


def atributo(nome, valor, unidade, fonte, dataset, banda, resolucao):
    return AtributoGeoespacial(
        variavel=nome,
        valor=valor,
        unidade=unidade,
        fonte=fonte,
        dataset=dataset,
        banda=banda,
        resolucao_m=resolucao,
        metodologia="método",
        qualidade=QualidadeDado(),
    )


def geoespacial():
    return AnaliseGeoespacialNormalizada(
        referencia=ReferenciaEspacial(latitude=-12.5, longitude=-55.7),
        declividade_media_graus=atributo(
            "declividade_media_graus",
            3.2,
            "graus",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "elevation→slope",
            30,
        ),
        posicao_topografica_relativa_m=atributo(
            "posicao_topografica_relativa_m",
            -1.4,
            "m",
            FonteDado.SRTM,
            "USGS/SRTMGL1_003",
            "elevation",
            30,
        ),
        distancia_drenagem_m=atributo(
            "distancia_drenagem_m",
            2001.0,
            "m",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
            92.77,
        ),
        area_drenagem_montante_km2=atributo(
            "area_drenagem_montante_km2",
            850.0,
            "km²",
            FonteDado.MERIT_HYDRO,
            "MERIT/Hydro/v1_0_1",
            "upa",
            92.77,
        ),
        parametros=ParametrosGeoespaciais(
            raio_analise_m=1000, limiar_drenagem_km2=10, raio_busca_drenagem_m=50000
        ),
        qualidade=QualidadeDado(status=StatusQualidade.DISPONIVEL, cobertura_pct=100),
        qualidade_contexto={"pixels_srtm_validos": 3500},
        fontes=(
            {"identificador": "USGS/SRTMGL1_003"},
            {"identificador": "MERIT/Hydro/v1_0_1"},
        ),
        schema_version="1",
        algorithm_version="fase1-v3",
        status_fonte="sucesso",
    )


def territorial():
    qualidade_territorial = QualidadeTerritorial(
        area_nominal_m2=2500000,
        area_geometria_m2=2500000,
        area_grade_analisada_m2=2500000,
        area_mapeada_m2=2500000,
        area_valida_m2=2500000,
        area_nao_observada_m2=0,
        area_codigo_27_m2=0,
        area_no_data_m2=0,
        cobertura_valida_pct=100,
        soma_percentuais_validos=100,
    )
    return AnaliseTerritorialNormalizada(
        id_fazenda="1",
        referencia=ReferenciaEspacial(
            latitude=-12.5, longitude=-55.7, area_ha=250, raio_equivalente_m=892.06
        ),
        geometria=ContextoGeometriaTerritorial(
            tipo_geometria="ESTIMADA",
            metodo_geometria="circulo_equivalente_por_area",
            origem_coordenada="CEP",
            precisao_espacial="APROXIMADA",
            warning="Não representa o polígono real.",
        ),
        ano_referencia=2024,
        asset_id="asset",
        colecao="10",
        asset_version="2",
        banda="classification_2024",
        legend_version="legenda-v1",
        algorithm_version="mapbiomas-territorial-v1",
        schema_version="1",
        fingerprint="abc",
        classe_predominante_codigo=15,
        classe_predominante_nome="Pastagem",
        agricultura_pct=20,
        pastagem_pct=50,
        vegetacao_nativa_pct=20,
        agua_pct=0,
        outros_pct=10,
        distribuicao_bruta=(
            DistribuicaoClasseTerritorial(
                codigo=15, nome="Pastagem", area_m2=1250000, percentual_area_valida=50
            ),
        ),
        qualidade_territorial=qualidade_territorial,
        qualidade=QualidadeDado(
            status=StatusQualidade.DISPONIVEL,
            cobertura_pct=100,
            flags=("GEOMETRIA_ESTIMADA",),
        ),
        calculado_em_utc=datetime(2026, 8, 11, 12, tzinfo=timezone.utc),
    )


class AgregadorRiscoTests(unittest.TestCase):
    def test_conjunto_completo_preserva_grupos(self):
        clima = climaticas()
        conjunto = agregar_features(
            cadastro=cadastro(),
            climaticas=clima,
            geoespacial=geoespacial(),
            territorial=territorial(),
            calculado_em_utc=datetime(2026, 8, 11, 14, tzinfo=timezone.utc),
        )
        self.assertEqual(conjunto.qualidade_global.status, StatusQualidade.DISPONIVEL)
        self.assertIsNone(conjunto.qualidade_global.cobertura_pct)
        self.assertEqual(conjunto.climaticas, clima)
        self.assertEqual(len(conjunto.geoespaciais_hidrologicas.features), 4)
        self.assertEqual(len(conjunto.territoriais.features), 8)
        self.assertEqual(len(conjunto.operacionais.features), 3)
        self.assertEqual(conjunto.versao, "risk-features-v2")

    def test_sem_mapbiomas_marca_grupo_ausente(self):
        conjunto = agregar_features(
            cadastro=cadastro(), climaticas=climaticas(), geoespacial=geoespacial()
        )
        self.assertEqual(
            conjunto.territoriais.qualidade.status, StatusQualidade.AUSENTE
        )
        self.assertEqual(conjunto.territoriais.features, ())
        self.assertEqual(conjunto.qualidade_global.status, StatusQualidade.PARCIAL)

    def test_clima_disponivel_com_geoespacial_e_territorial_ausentes(self):
        conjunto = agregar_features(cadastro=cadastro(), climaticas=climaticas())
        self.assertEqual(conjunto.qualidade_global.status, StatusQualidade.PARCIAL)
        self.assertIsNone(conjunto.qualidade_global.cobertura_pct)

    def test_todos_os_grupos_sem_informacao_util_resultam_ausente(self):
        ausente = GrupoFeatures(qualidade=QualidadeDado(status=StatusQualidade.AUSENTE))
        qualidade = _qualidade_global((ausente, ausente, ausente, ausente))
        self.assertEqual(qualidade.status, StatusQualidade.AUSENTE)
        self.assertIsNone(qualidade.cobertura_pct)

    def test_grupo_parcial_resulta_qualidade_global_parcial(self):
        parcial = GrupoFeatures(
            qualidade=QualidadeDado(status=StatusQualidade.PARCIAL, cobertura_pct=50)
        )
        qualidade = _qualidade_global((climaticas(), parcial))
        self.assertEqual(qualidade.status, StatusQualidade.PARCIAL)
        self.assertIsNone(qualidade.cobertura_pct)

    def test_coberturas_locais_distintas_nao_geram_media_global(self):
        grupos = tuple(
            GrupoFeatures(
                qualidade=QualidadeDado(
                    status=StatusQualidade.PARCIAL,
                    cobertura_pct=cobertura,
                )
            )
            for cobertura in (25, 100, 50)
        )
        qualidade = _qualidade_global(grupos)
        self.assertEqual(qualidade.status, StatusQualidade.PARCIAL)
        self.assertIsNone(qualidade.cobertura_pct)
        self.assertNotEqual(qualidade.cobertura_pct, 58.333333333333336)

    def test_sem_geoespacial_marca_grupo_ausente(self):
        conjunto = agregar_features(
            cadastro=cadastro(), climaticas=climaticas(), territorial=territorial()
        )
        self.assertEqual(
            conjunto.geoespaciais_hidrologicas.qualidade.status, StatusQualidade.AUSENTE
        )
        self.assertEqual(conjunto.qualidade_global.status, StatusQualidade.PARCIAL)

    def test_sem_climaticas_marca_grupo_ausente(self):
        conjunto = agregar_features(
            cadastro=cadastro(), geoespacial=geoespacial(), territorial=territorial()
        )
        self.assertEqual(conjunto.climaticas.qualidade.status, StatusQualidade.AUSENTE)
        self.assertEqual(conjunto.qualidade_global.status, StatusQualidade.PARCIAL)

    def test_area_ausente_nao_vira_zero(self):
        conjunto = agregar_features(cadastro=cadastro(area=None))
        areas = [f for f in conjunto.operacionais.features if f.nome == "area_ha"]
        self.assertEqual(len(areas), 1)
        self.assertIsNone(areas[0].valor)
        self.assertEqual(areas[0].qualidade.status, StatusQualidade.AUSENTE)

    def test_proximidade_declarada_nao_e_combinada_com_merit(self):
        conjunto = agregar_features(cadastro=cadastro(), geoespacial=geoespacial())
        operacional = next(
            f
            for f in conjunto.operacionais.features
            if f.nome == "proximidade_agua_declarada"
        )
        distancia = next(
            f
            for f in conjunto.geoespaciais_hidrologicas.features
            if f.nome == "distancia_drenagem_m"
        )
        self.assertFalse(operacional.valor)
        self.assertEqual(distancia.valor, 2001.0)

    def test_modelo_nao_possui_score_estado_alertas_ou_subscores(self):
        serializado = agregar_features(cadastro=cadastro()).model_dump()
        for chave in ("score", "estado", "alertas", "subscores"):
            self.assertNotIn(chave, serializado)


if __name__ == "__main__":
    unittest.main()
