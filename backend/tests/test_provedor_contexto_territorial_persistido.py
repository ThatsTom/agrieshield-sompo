from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.provedor_contexto_territorial_persistido import (
    CarregadorCacheGeoespacialJson,
    ProvedorContextoTerritorialPersistido,
)
from backend.app.servico_avaliacao_exposicao import (
    CodigoErroAvaliacaoExposicao,
    ContextoTerritorialIncompativel,
    ContextoTerritorialIndisponivel,
    ServicoAvaliacaoExposicao,
)
from backend.etl import etapa4_dados_geoespaciais as etapa4
from backend.etl import repositorio_fazendas_geoespaciais as repositorio_geo
from backend.exposicao import ResultadoApresentacaoExposicaoMaquinario
from backend.risco.modelos import (
    AnaliseGeoespacialNormalizada,
    FonteDado,
    StatusQualidade,
)
from backend.tests.test_servico_avaliacao_exposicao import (
    ClienteFalso,
    DATA_REFERENCIA,
    FAZENDA,
    ID_FAZENDA,
    RepositorioFalso,
)


CHAVE_CACHE = "a" * 64
CALCULADO_EM_UTC = "2026-08-11T12:00:00+00:00"
LATITUDE = float(FAZENDA["latitude"])
LONGITUDE = float(FAZENDA["longitude"])


def _atributo(
    valor,
    unidade: str,
    fonte: str,
    banda: str,
    resolucao_m: float,
):
    return {
        "valor": valor,
        "unidade": unidade,
        "status": "disponivel" if valor is not None else "indisponivel",
        "metodologia": "metodologia persistida pela Etapa 4",
        "fonte": fonte,
        "banda": banda,
        "resolucao_m": resolucao_m,
    }


def payload_geoespacial(*, parcial: bool = False):
    return {
        "schema_version": "1",
        "algorithm_version": "fase1-v3",
        "status": "parcial" if parcial else "sucesso",
        "localizacao": {"latitude": LATITUDE, "longitude": LONGITUDE},
        "parametros": {
            "raio_analise_m": 1000.0,
            "limiar_drenagem_km2": 10.0,
            "raio_busca_drenagem_m": 50000.0,
        },
        "atributos": {
            "declividade_media": _atributo(
                3.2,
                "graus",
                "USGS/SRTMGL1_003",
                "elevation→slope",
                30.0,
            ),
            "posicao_topografica_relativa": _atributo(
                None if parcial else -1.45,
                "m",
                "USGS/SRTMGL1_003",
                "elevation",
                30.0,
            ),
            "distancia_drenagem": _atributo(
                2001.65,
                "m",
                "MERIT/Hydro/v1_0_1",
                "upa",
                92.77,
            ),
            "area_drenagem_montante": _atributo(
                850.33,
                "km²",
                "MERIT/Hydro/v1_0_1",
                "upa",
                92.77,
            ),
        },
        "qualidade": {
            "cobertura_srtm_pct": 100.0,
            "pixels_srtm_validos": 3541,
            "drenagem_encontrada": True,
            "pixel_drenagem": {
                "latitude": -12.53478,
                "longitude": -55.7058,
            },
            "candidatos_drenagem": 32,
            "flags": ["coordenada_pontual_nao_representa_poligono_da_fazenda"],
        },
        "fontes": [
            {
                "identificador": "USGS/SRTMGL1_003",
                "banda": "elevation",
                "resolucao_m": 30.0,
            },
            {
                "identificador": "MERIT/Hydro/v1_0_1",
                "banda": "upa",
                "resolucao_m": 92.77,
            },
        ],
        "cache": {"hit": False, "chave": CHAVE_CACHE},
        "erros": (
            [{"codigo": "srtm_parcial", "fonte": "USGS/SRTMGL1_003"}] if parcial else []
        ),
    }


def registro_persistido(payload=None):
    payload = payload if payload is not None else payload_geoespacial()
    registro_csv = repositorio_geo.montar_registro_geoespacial(
        {
            "id_fazenda": ID_FAZENDA,
            "latitude": str(LATITUDE),
            "longitude": str(LONGITUDE),
            "area_ha": "250",
        },
        payload,
    )
    registro_csv["calculado_em_utc"] = CALCULADO_EM_UTC
    return repositorio_geo.normalizar_registro_geoespacial(registro_csv)


class BaseProviderPersistido(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.diretorio_cache = Path(self.tempdir.name) / "cache"
        self.diretorio_cache.mkdir()
        self.payload = payload_geoespacial()
        self.registro = registro_persistido(self.payload)
        self._salvar_cache(self.payload)

    def tearDown(self):
        self.tempdir.cleanup()

    def _salvar_cache(self, payload, *, chave=CHAVE_CACHE):
        (self.diretorio_cache / f"{chave}.json").write_text(
            json.dumps(payload, ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )

    def _provider(self, *, buscar_registro=None, diretorio=None):
        return ProvedorContextoTerritorialPersistido(
            buscar_registro=(
                buscar_registro
                if buscar_registro is not None
                else lambda _: self.registro
            ),
            carregador_cache=CarregadorCacheGeoespacialJson(
                diretorio if diretorio is not None else self.diretorio_cache
            ),
        )

    def _obter(self, provider=None):
        return (provider or self._provider()).obter(
            id_fazenda=ID_FAZENDA,
            latitude=LATITUDE,
            longitude=LONGITUDE,
        )


class TestLeituraENormalizacao(BaseProviderPersistido):
    def test_registro_encontrado_retorna_contrato_normalizado(self):
        contexto = self._obter()
        self.assertIsInstance(contexto, AnaliseGeoespacialNormalizada)
        self.assertEqual(contexto.status_fonte, "sucesso")
        self.assertEqual(contexto.calculado_em_utc.isoformat(), CALCULADO_EM_UTC)

    def test_reutiliza_normalizador_existente(self):
        from backend.app import provedor_contexto_territorial_persistido as modulo

        with patch.object(
            modulo,
            "normalizar_geoespacial",
            wraps=modulo.normalizar_geoespacial,
        ) as normalizar:
            contexto = self._obter()
        normalizar.assert_called_once()
        self.assertIsInstance(contexto, AnaliseGeoespacialNormalizada)

    def test_preserva_declividade_posicao_e_proveniencia(self):
        contexto = self._obter()
        self.assertEqual(contexto.declividade_media_graus.valor, 3.2)
        self.assertEqual(contexto.posicao_topografica_relativa_m.valor, -1.45)
        self.assertEqual(contexto.declividade_media_graus.fonte, FonteDado.SRTM)
        self.assertEqual(
            contexto.distancia_drenagem_m.fonte,
            FonteDado.MERIT_HYDRO,
        )
        self.assertEqual(contexto.declividade_media_graus.dataset, "USGS/SRTMGL1_003")
        self.assertEqual(contexto.algorithm_version, "fase1-v3")
        self.assertEqual(contexto.fontes, tuple(self.payload["fontes"]))

    def test_dado_parcial_preserva_none_sem_converter_em_zero(self):
        payload = payload_geoespacial(parcial=True)
        registro = registro_persistido(payload)
        self._salvar_cache(payload)
        contexto = self._obter(self._provider(buscar_registro=lambda _: registro))
        self.assertIsNone(contexto.posicao_topografica_relativa_m.valor)
        self.assertEqual(contexto.qualidade.status, StatusQualidade.PARCIAL)

    def test_determinismo_e_input_nao_mutado(self):
        registro_antes = deepcopy(self.registro)
        payload_antes = deepcopy(self.payload)
        primeiro = self._obter()
        segundo = self._obter()
        self.assertEqual(primeiro, segundo)
        self.assertEqual(self.registro, registro_antes)
        self.assertEqual(self.payload, payload_antes)

    def test_leitura_concreta_do_csv_por_id_fazenda(self):
        arquivo_csv = Path(self.tempdir.name) / "fazendas_geoespaciais.csv"
        registro_csv = repositorio_geo.montar_registro_geoespacial(
            {
                "id_fazenda": ID_FAZENDA,
                "latitude": str(LATITUDE),
                "longitude": str(LONGITUDE),
                "area_ha": "250",
            },
            self.payload,
        )
        registro_csv["calculado_em_utc"] = CALCULADO_EM_UTC
        with (
            patch.object(
                repositorio_geo,
                "ARQUIVO_FAZENDAS_GEOESPACIAIS",
                arquivo_csv,
            ),
            patch.object(repositorio_geo, "PASTA_DADOS", Path(self.tempdir.name)),
        ):
            repositorio_geo.upsert_registro_geoespacial(registro_csv)
            provider = ProvedorContextoTerritorialPersistido(
                carregador_cache=CarregadorCacheGeoespacialJson(self.diretorio_cache)
            )
            contexto = self._obter(provider)
        self.assertEqual(contexto.declividade_media_graus.valor, 3.2)


class TestValidacoesEFalhas(BaseProviderPersistido):
    def test_diferenca_decimal_minima_e_aceita(self):
        contexto = self._provider().obter(
            id_fazenda=ID_FAZENDA,
            latitude=LATITUDE + 0.0000005,
            longitude=LONGITUDE - 0.0000005,
        )
        self.assertEqual(contexto.referencia.latitude, LATITUDE)

    def test_coordenadas_incompativeis_sao_rejeitadas(self):
        with self.assertRaises(ContextoTerritorialIncompativel) as contexto:
            self._provider().obter(
                id_fazenda=ID_FAZENDA,
                latitude=-10,
                longitude=-50,
            )
        self.assertEqual(
            contexto.exception.codigo,
            CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INCOMPATIVEL,
        )

    def test_registro_inexistente_e_rejeitado(self):
        provider = self._provider(buscar_registro=lambda _: None)
        with self.assertRaises(ContextoTerritorialIndisponivel):
            self._obter(provider)

    def test_arquivo_csv_inexistente_e_rejeitado(self):
        def buscar(_):
            raise FileNotFoundError("arquivo geoespacial ausente")

        provider = self._provider(buscar_registro=buscar)
        with self.assertRaises(ContextoTerritorialIndisponivel) as contexto:
            self._obter(provider)
        self.assertEqual(contexto.exception.tipo_causa, "FileNotFoundError")

    def test_cache_inexistente_e_reconstruido_do_registro_persistido(self):
        diretorio_vazio = Path(self.tempdir.name) / "vazio"
        provider = self._provider(diretorio=diretorio_vazio)
        contexto = self._obter(provider)
        self.assertEqual(contexto.status_fonte, "sucesso")
        self.assertEqual(contexto.declividade_media_graus.valor, 3.2)
        self.assertEqual(contexto.distancia_drenagem_m.valor, 2001.65)

    def test_cache_corrompido_e_rejeitado(self):
        (self.diretorio_cache / f"{CHAVE_CACHE}.json").write_text(
            "{invalido",
            encoding="utf-8",
        )
        with self.assertRaises(ContextoTerritorialIndisponivel):
            self._obter()

    def test_registro_invalido_e_rejeitado(self):
        self.registro["algorithm_version"] = "outra-versao"
        with self.assertRaises(ContextoTerritorialIndisponivel):
            self._obter()

    def test_campo_obrigatorio_ausente_nao_vira_zero(self):
        self.registro["declividade_media_graus"] = None
        from backend.app import provedor_contexto_territorial_persistido as modulo

        with patch.object(modulo, "normalizar_geoespacial") as normalizar:
            with self.assertRaises(ContextoTerritorialIndisponivel):
                self._obter()
        normalizar.assert_not_called()

    def test_identidade_de_outra_fazenda_e_rejeitada(self):
        self.registro["id_fazenda"] = "outra-fazenda"
        with self.assertRaises(ContextoTerritorialIncompativel):
            self._obter()

    def test_nao_possui_cliente_externo_ou_aquisicao_remota(self):
        from backend.app import provedor_contexto_territorial_persistido as modulo

        codigo = inspect.getsource(modulo).lower()
        for termo in (
            "requests",
            "urlopen",
            "initialize(",
            "authenticate(",
            "consultar_dados_geoespaciais(",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


class TestComposicaoComServico(BaseProviderPersistido):
    def test_produz_apresentacao_sem_earth_engine_ou_http(self):
        provider = self._provider()
        servico = ServicoAvaliacaoExposicao(
            repositorio_fazendas=RepositorioFalso(),
            clientes_meteorologicos={
                FonteDado.NASA_POWER: ClienteFalso(),
            },
            provedor_contexto_territorial=provider,
        )
        with patch.object(
            etapa4,
            "_carregar_ee",
            side_effect=AssertionError("Earth Engine nao deve ser carregado"),
        ) as carregar_ee:
            resultado = servico.avaliar_exposicao_fazenda(
                ID_FAZENDA,
                DATA_REFERENCIA,
            )
        carregar_ee.assert_not_called()
        self.assertIsInstance(resultado, ResultadoApresentacaoExposicaoMaquinario)
        self.assertEqual(resultado.id_fazenda, ID_FAZENDA)
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.NASA_POWER)
        self.assertEqual(len(resultado.perigos), 5)


if __name__ == "__main__":
    unittest.main()
