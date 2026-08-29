from __future__ import annotations

import builtins
import inspect
import math
import os
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import requests

from backend.exposicao.clientes.open_meteo_historico import (
    DATASET_OPEN_METEO_HISTORICAL,
    ENDPOINT_OPEN_METEO_HISTORICAL,
    MODELO_OPEN_METEO_HISTORICAL,
    UNIDADES_ESPERADAS,
    VARIAVEIS_DIARIAS_OPEN_METEO,
    ClienteOpenMeteoHistorico,
    ErroContratoOpenMeteoHistorico,
    ErroHttpOpenMeteoHistorico,
    ErroParametroOpenMeteoHistorico,
    ErroTransporteOpenMeteoHistorico,
)
from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
)
from backend.risco.modelos import FonteDado, NaturezaDado


DATA_REFERENCIA = date(2026, 8, 11)
AGORA_UTC = datetime(2026, 8, 12, 13, tzinfo=timezone.utc)


class RespostaFalsa:
    def __init__(self, payload=None, *, status_code=200, json_invalido=False):
        self.status_code = status_code
        self._payload = payload
        self._json_invalido = json_invalido

    def json(self):
        if self._json_invalido:
            raise ValueError("JSON inválido")
        return self._payload


class TransporteFalso:
    def __init__(self, resposta=None, *, erro=None):
        self.resposta = resposta
        self.erro = erro
        self.chamadas = []

    def get(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        if self.erro is not None:
            raise self.erro
        return self.resposta


def payload_completo(janela: JanelaHistorica):
    daily = {
        "time": [],
        "temperature_2m_mean": [],
        "temperature_2m_max": [],
        "temperature_2m_min": [],
        "precipitation_sum": [],
        "relative_humidity_2m_mean": [],
        "wind_speed_10m_mean": [],
    }
    dia = janela.inicio
    while dia <= janela.fim:
        daily["time"].append(dia.isoformat())
        daily["temperature_2m_mean"].append(25.0)
        daily["temperature_2m_max"].append(31.0)
        daily["temperature_2m_min"].append(19.0)
        daily["precipitation_sum"].append(4.5)
        daily["relative_humidity_2m_mean"].append(70.0)
        daily["wind_speed_10m_mean"].append(3.0)
        dia += timedelta(days=1)
    return {
        "latitude": -13.125,
        "longitude": -56.0,
        "elevation": 390.0,
        "generationtime_ms": 1.2,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "daily_units": dict(UNIDADES_ESPERADAS),
        "daily": daily,
    }


def remover_dia(payload, dia: date):
    indice = payload["daily"]["time"].index(dia.isoformat())
    for valores in payload["daily"].values():
        valores.pop(indice)


def cliente_com_payload(payload, *, status_code=200):
    transporte = TransporteFalso(RespostaFalsa(payload, status_code=status_code))
    cliente = ClienteOpenMeteoHistorico(
        transporte=transporte,
        relogio_utc=lambda: AGORA_UTC,
    )
    return cliente, transporte


class TestOpenMeteoHistoricoRequisicao(unittest.TestCase):
    def test_90_dias_usam_uma_chamada(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)

    def test_180_dias_usam_uma_chamada(self):
        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        serie = cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)
        self.assertEqual(len(serie.registros), 180)

    def test_187_dias_usam_uma_chamada(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 187)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        serie = cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)
        self.assertEqual(len(serie.registros), 187)

    def test_endpoint_datas_e_coordenadas(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        url, kwargs = transporte.chamadas[0]
        params = kwargs["params"]
        self.assertEqual(url, ENDPOINT_OPEN_METEO_HISTORICAL)
        self.assertEqual(params["start_date"], janela.inicio.isoformat())
        self.assertEqual(params["end_date"], janela.fim.isoformat())
        self.assertEqual(params["latitude"], -13.15)
        self.assertEqual(params["longitude"], -56.05)

    def test_dataset_era5_land_e_explicito_sem_best_match(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        params = transporte.chamadas[0][1]["params"]
        self.assertEqual(params["models"], "era5_land")
        self.assertNotEqual(params["models"], "best_match")

    def test_variaveis_diarias_corretas(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(
            transporte.chamadas[0][1]["params"]["daily"],
            ",".join(VARIAVEIS_DIARIAS_OPEN_METEO),
        )

    def test_timezone_e_unidades_solicitados_explicitamente(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        params = transporte.chamadas[0][1]["params"]
        self.assertEqual(params["timezone"], "UTC")
        self.assertEqual(params["temperature_unit"], "celsius")
        self.assertEqual(params["precipitation_unit"], "mm")
        self.assertEqual(params["wind_speed_unit"], "ms")
        self.assertEqual(params["timeformat"], "iso8601")

    def test_timeout_explicito(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        transporte = TransporteFalso(RespostaFalsa(payload_completo(janela)))
        cliente = ClienteOpenMeteoHistorico(
            transporte=transporte,
            timeout=(2, 19),
            relogio_utc=lambda: AGORA_UTC,
        )
        cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(transporte.chamadas[0][1]["timeout"], (2.0, 19.0))

    def test_coordenada_invalida_nao_chama_http(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        with self.assertRaises(ErroParametroOpenMeteoHistorico):
            cliente.consultar(-91, -56.05, janela)
        self.assertEqual(transporte.chamadas, [])

    def test_janela_nao_suportada_nao_chama_http(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 30)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        with self.assertRaises(ErroParametroOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(transporte.chamadas, [])


class TestOpenMeteoHistoricoParsing(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        self.payload = payload_completo(self.janela)

    def consultar(self):
        cliente, _ = cliente_com_payload(self.payload)
        return cliente.consultar(-13.15, -56.05, self.janela, id_fazenda="MT-01")

    def test_precipitacao(self):
        self.payload["daily"]["precipitation_sum"][0] = 12.5
        self.assertEqual(self.consultar().registros[0].precipitacao_mm, 12.5)

    def test_temperatura_media(self):
        self.assertEqual(self.consultar().registros[0].temperatura_media_c, 25)

    def test_temperatura_maxima(self):
        self.assertEqual(self.consultar().registros[0].temperatura_maxima_c, 31)

    def test_temperatura_minima(self):
        self.assertEqual(self.consultar().registros[0].temperatura_minima_c, 19)

    def test_umidade_media_diaria(self):
        self.assertEqual(self.consultar().registros[0].umidade_media_pct, 70)

    def test_velocidade_media_vento_10m_em_m_s(self):
        self.payload["daily"]["wind_speed_10m_mean"][0] = 3.75
        self.assertEqual(
            self.consultar().registros[0].velocidade_vento_media_m_s,
            3.75,
        )

    def test_velocidade_vento_zero_e_preservada(self):
        self.payload["daily"]["wind_speed_10m_mean"][0] = 0.0
        registro = self.consultar().registros[0]
        self.assertEqual(registro.velocidade_vento_media_m_s, 0.0)
        self.assertNotIn("velocidade_vento_media_m_s", registro.variaveis_ausentes)

    def test_velocidade_vento_null_e_preservada(self):
        self.payload["daily"]["wind_speed_10m_mean"][0] = None
        registro = self.consultar().registros[0]
        self.assertIsNone(registro.velocidade_vento_media_m_s)
        self.assertIn("velocidade_vento_media_m_s", registro.variaveis_ausentes)

    def test_velocidade_vento_negativa_gera_erro_tipado(self):
        self.payload["daily"]["wind_speed_10m_mean"][0] = -0.1
        cliente, _ = cliente_com_payload(self.payload)
        with self.assertRaises(ErroContratoOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_zero_e_preservado(self):
        self.payload["daily"]["precipitation_sum"][0] = 0.0
        registro = self.consultar().registros[0]
        self.assertEqual(registro.precipitacao_mm, 0.0)
        self.assertNotIn("precipitacao_mm", registro.variaveis_ausentes)

    def test_null_e_preservado(self):
        self.payload["daily"]["precipitation_sum"][0] = None
        registro = self.consultar().registros[0]
        self.assertIsNone(registro.precipitacao_mm)
        self.assertIn("precipitacao_mm", registro.variaveis_ausentes)

    def test_variavel_inteira_nula_tem_cobertura_zero_sem_afetar_as_demais(self):
        self.payload["daily"]["precipitation_sum"] = [None] * 90
        serie = self.consultar()
        self.assertEqual(
            serie.qualidade.cobertura_por_variavel_pct["precipitacao_mm"], 0
        )
        self.assertEqual(
            serie.qualidade.cobertura_por_variavel_pct["temperatura_media_c"], 100
        )
        self.assertTrue(all(r.precipitacao_mm is None for r in serie.registros))

    def test_data_ausente_permanece_como_gap(self):
        ausente = self.janela.inicio + timedelta(days=10)
        remover_dia(self.payload, ausente)
        serie = self.consultar()
        registro = next(item for item in serie.registros if item.data == ausente)
        self.assertFalse(registro.possui_algum_dado())
        self.assertTrue(any(gap.inicio == ausente for gap in serie.qualidade.gaps))

    def test_gap_interno(self):
        inicio_gap = self.janela.inicio + timedelta(days=20)
        remover_dia(self.payload, inicio_gap + timedelta(days=1))
        remover_dia(self.payload, inicio_gap)
        self.assertTrue(
            any(
                gap.inicio == inicio_gap
                and gap.fim == inicio_gap + timedelta(days=1)
                and gap.duracao_dias == 2
                for gap in self.consultar().qualidade.gaps
            )
        )

    def test_gap_final(self):
        remover_dia(self.payload, self.janela.fim)
        serie = self.consultar()
        self.assertTrue(any(gap.fim == self.janela.fim for gap in serie.qualidade.gaps))
        self.assertEqual(serie.periodo_solicitado.fim, self.janela.fim)

    def test_cobertura_geral(self):
        remover_dia(self.payload, self.janela.fim)
        qualidade = self.consultar().qualidade
        self.assertEqual(qualidade.dias_esperados, 90)
        self.assertEqual(qualidade.dias_com_algum_dado, 89)
        self.assertEqual(qualidade.cobertura_pct, 98.89)

    def test_cobertura_por_variavel(self):
        self.payload["daily"]["precipitation_sum"][-1] = None
        qualidade = self.consultar().qualidade
        self.assertEqual(qualidade.cobertura_por_variavel_pct["precipitacao_mm"], 98.89)
        self.assertEqual(
            qualidade.cobertura_por_variavel_pct["temperatura_media_c"], 100
        )

    def test_ultima_data_valida(self):
        self.payload["daily"]["precipitation_sum"][-1] = None
        qualidade = self.consultar().qualidade
        self.assertEqual(
            qualidade.ultima_data_disponivel_por_variavel["precipitacao_mm"],
            self.janela.fim - timedelta(days=1),
        )

    def test_datas_fora_de_ordem_sao_ordenadas(self):
        for valores in self.payload["daily"].values():
            valores.reverse()
        registros = self.consultar().registros
        self.assertEqual(
            tuple(r.data for r in registros), tuple(sorted(r.data for r in registros))
        )

    def test_janela_nao_e_deslocada(self):
        remover_dia(self.payload, self.janela.fim)
        remover_dia(self.payload, self.janela.fim - timedelta(days=1))
        serie = self.consultar()
        self.assertEqual(serie.periodo_solicitado, self.janela)
        self.assertEqual(serie.periodo_efetivo.fim, self.janela.fim - timedelta(days=2))
        self.assertEqual(len(serie.registros), 90)


class TestOpenMeteoHistoricoContrato(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)

    def assert_contrato_invalido(self, payload):
        cliente, _ = cliente_com_payload(payload)
        with self.assertRaises(ErroContratoOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_datas_duplicadas_sao_rejeitadas(self):
        payload = payload_completo(self.janela)
        payload["daily"]["time"][1] = payload["daily"]["time"][0]
        self.assert_contrato_invalido(payload)

    def test_arrays_incompativeis_sao_rejeitados(self):
        payload = payload_completo(self.janela)
        payload["daily"]["precipitation_sum"].pop()
        self.assert_contrato_invalido(payload)

    def test_unidade_incorreta_e_rejeitada(self):
        payload = payload_completo(self.janela)
        payload["daily_units"]["precipitation_sum"] = "inch"
        self.assert_contrato_invalido(payload)

    def test_unidades_ausentes_sao_rejeitadas(self):
        payload = payload_completo(self.janela)
        del payload["daily_units"]
        self.assert_contrato_invalido(payload)

    def test_timezone_incompativel_e_rejeitado(self):
        payload = payload_completo(self.janela)
        payload["timezone"] = "America/Cuiaba"
        self.assert_contrato_invalido(payload)

    def test_offset_incompativel_e_rejeitado(self):
        payload = payload_completo(self.janela)
        payload["utc_offset_seconds"] = -14400
        self.assert_contrato_invalido(payload)

    def test_daily_ausente_e_rejeitado(self):
        payload = payload_completo(self.janela)
        del payload["daily"]
        self.assert_contrato_invalido(payload)

    def test_daily_vazio_e_rejeitado(self):
        payload = payload_completo(self.janela)
        payload["daily"]["time"] = []
        for variavel in VARIAVEIS_DIARIAS_OPEN_METEO:
            payload["daily"][variavel] = []
        self.assert_contrato_invalido(payload)

    def test_variavel_ausente_e_rejeitada(self):
        payload = payload_completo(self.janela)
        del payload["daily"]["temperature_2m_mean"]
        self.assert_contrato_invalido(payload)

    def test_data_invalida_e_rejeitada(self):
        payload = payload_completo(self.janela)
        payload["daily"]["time"][0] = "2026/05/14"
        self.assert_contrato_invalido(payload)

    def test_valor_nao_numerico_e_rejeitado(self):
        payload = payload_completo(self.janela)
        payload["daily"]["temperature_2m_mean"][0] = "25"
        self.assert_contrato_invalido(payload)

    def test_nan_e_infinito_sao_rejeitados(self):
        for valor in (math.nan, math.inf):
            with self.subTest(valor=valor):
                payload = payload_completo(self.janela)
                payload["daily"]["temperature_2m_mean"][0] = valor
                self.assert_contrato_invalido(payload)

    def test_http_500(self):
        cliente, _ = cliente_com_payload({}, status_code=500)
        with self.assertRaises(ErroHttpOpenMeteoHistorico) as contexto:
            cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(contexto.exception.status_code, 500)

    def test_timeout(self):
        transporte = TransporteFalso(erro=requests.Timeout("interno"))
        cliente = ClienteOpenMeteoHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_erro_de_rede(self):
        transporte = TransporteFalso(erro=requests.ConnectionError("interno"))
        cliente = ClienteOpenMeteoHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_json_invalido(self):
        transporte = TransporteFalso(RespostaFalsa(json_invalido=True))
        cliente = ClienteOpenMeteoHistorico(transporte=transporte)
        with self.assertRaises(ErroContratoOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_resposta_nao_objeto(self):
        self.assert_contrato_invalido([])

    def test_falha_nao_produz_serie_sintetica(self):
        transporte = TransporteFalso(erro=requests.Timeout("interno"))
        cliente = ClienteOpenMeteoHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteOpenMeteoHistorico):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_cliente_nao_escreve_em_disco(self):
        cliente, _ = cliente_com_payload(payload_completo(self.janela))
        with patch.object(
            builtins, "open", side_effect=AssertionError("escrita indevida")
        ):
            serie = cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(len(serie.registros), 90)

    def test_modulo_nao_importa_fluxos_operacionais_ou_forecast(self):
        from backend.exposicao.clientes import open_meteo_historico

        codigo = inspect.getsource(open_meteo_historico).lower()
        for termo in (
            "etapa3",
            "score",
            "alertas",
            "fastapi",
            "supabase",
            "to_csv",
            "servicos_externos",
            "api.open-meteo.com/v1/forecast",
            "simulador_interno",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


class TestOpenMeteoHistoricoProveniencia(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)

    def consultar(self):
        cliente, _ = cliente_com_payload(payload_completo(self.janela))
        return cliente.consultar(-13.15, -56.05, self.janela, id_fazenda="MT-01")

    def test_natureza_tipo_produto_e_dataset(self):
        serie = self.consultar()
        self.assertEqual(serie.fonte, FonteDado.OPEN_METEO)
        self.assertEqual(serie.natureza, NaturezaDado.HISTORICO)
        self.assertEqual(serie.tipo_produto, TipoProdutoHistorico.REANALISE_MODELADA)
        self.assertEqual(serie.dataset, DATASET_OPEN_METEO_HISTORICAL)

    def test_referencia_temporal_utc(self):
        serie = self.consultar()
        self.assertEqual(serie.referencia_temporal.tipo, TipoReferenciaTemporal.UTC)
        self.assertEqual(serie.referencia_temporal.timezone, "UTC")
        self.assertEqual(serie.metadados_origem["timezone_resposta"], "GMT")

    def test_proveniencia(self):
        serie = self.consultar()
        metadados = serie.metadados_origem
        self.assertEqual(serie.id_fazenda, "MT-01")
        self.assertEqual(metadados["endpoint"], ENDPOINT_OPEN_METEO_HISTORICAL)
        self.assertEqual(metadados["modelo_api"], MODELO_OPEN_METEO_HISTORICAL)
        self.assertEqual(metadados["dataset"], DATASET_OPEN_METEO_HISTORICAL)
        self.assertEqual(
            tuple(metadados["variaveis_solicitadas"]), VARIAVEIS_DIARIAS_OPEN_METEO
        )
        self.assertEqual(metadados["unidades"], dict(UNIDADES_ESPERADAS))
        self.assertEqual(metadados["inicio_solicitado"], self.janela.inicio.isoformat())
        self.assertEqual(metadados["fim_solicitado"], self.janela.fim.isoformat())
        self.assertEqual(
            metadados["vento"],
            {
                "parametro_fonte": "wind_speed_10m_mean",
                "variavel_canonica": "velocidade_vento_media_m_s",
                "unidade": "m/s",
                "altura_m": 10,
                "agregacao_temporal": "media_diaria",
                "referencia_temporal": "UTC",
            },
        )

    def test_coletado_em_utc(self):
        serie = self.consultar()
        self.assertEqual(serie.coletado_em_utc, AGORA_UTC)
        self.assertEqual(serie.coletado_em_utc.utcoffset(), timedelta(0))

    def test_open_meteo_historico_e_nasa_sao_series_independentes(self):
        open_meteo = self.consultar()
        nasa = SerieHistoricaFonte.criar(
            fonte=FonteDado.NASA_POWER,
            tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
            dataset="NASA POWER Daily Point",
            periodo_solicitado=self.janela,
            referencia_temporal=ReferenciaTemporalHistorica(
                tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
                descricao="NASA POWER LST",
            ),
            registros=(
                RegistroMeteorologicoDiario(
                    data=self.janela.inicio,
                    precipitacao_mm=0,
                ),
            ),
            coletado_em_utc=AGORA_UTC,
        )
        self.assertIsNot(open_meteo, nasa)
        self.assertNotEqual(open_meteo.fonte, nasa.fonte)
        self.assertNotEqual(open_meteo.referencia_temporal, nasa.referencia_temporal)


@unittest.skipUnless(
    os.getenv("RUN_OPEN_METEO_HISTORICAL_INTEGRATION") == "1",
    "integração Open-Meteo Historical opcional",
)
class TestOpenMeteoHistoricoIntegracaoReal(unittest.TestCase):
    def test_mt_180_dias(self):
        class SessaoContadora(requests.Session):
            def __init__(self):
                super().__init__()
                self.quantidade_chamadas = 0

            def get(self, url, **kwargs):
                self.quantidade_chamadas += 1
                return super().get(url, **kwargs)

        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        sessao = SessaoContadora()
        cliente = ClienteOpenMeteoHistorico(
            transporte=sessao,
            timeout=(5, 60),
        )
        inicio = time.monotonic()
        try:
            try:
                serie = cliente.consultar(-13.15, -56.05, janela, id_fazenda="MT-POC")
            except (
                ErroTransporteOpenMeteoHistorico,
                ErroHttpOpenMeteoHistorico,
            ) as exc:
                self.skipTest(f"serviço externo indisponível: {type(exc).__name__}")
        finally:
            sessao.close()
        duracao = time.monotonic() - inicio
        datas_validas = [
            registro.data
            for registro in serie.registros
            if registro.possui_algum_dado()
        ]
        diagnostico = {
            "periodo_solicitado": {
                "inicio": janela.inicio.isoformat(),
                "fim": janela.fim.isoformat(),
            },
            "dias_esperados": janela.dias_esperados,
            "dias_com_dados": serie.qualidade.dias_com_algum_dado,
            "cobertura_por_variavel_pct": serie.qualidade.cobertura_por_variavel_pct,
            "primeira_data_valida": (
                min(datas_validas).isoformat() if datas_validas else None
            ),
            "ultima_data_valida_por_variavel": {
                chave: valor.isoformat() if valor else None
                for chave, valor in serie.qualidade.ultima_data_disponivel_por_variavel.items()
            },
            "gaps": [gap.model_dump(mode="json") for gap in serie.qualidade.gaps],
            "dataset": serie.dataset,
            "referencia_temporal": serie.referencia_temporal.model_dump(mode="json"),
            "duracao_s": round(duracao, 3),
        }
        print(f"Open-Meteo Historical integração MT: {diagnostico}")
        self.assertEqual(sessao.quantidade_chamadas, 1)
        self.assertEqual(len(serie.registros), 180)
        self.assertEqual(serie.periodo_solicitado, janela)


if __name__ == "__main__":
    unittest.main()
