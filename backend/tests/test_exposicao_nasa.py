from __future__ import annotations

import builtins
import inspect
import os
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import requests

from backend.exposicao.clientes.nasa_power_historico import (
    DATASET_NASA_POWER_DAILY,
    ENDPOINT_NASA_POWER_DAILY,
    PARAMETROS_NASA_POWER,
    ClienteNasaPowerHistorico,
    ErroContratoNasaPower,
    ErroHttpNasaPower,
    ErroParametroNasaPower,
    ErroTransporteNasaPower,
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
AGORA_UTC = datetime(2026, 8, 12, 12, 30, tzinfo=timezone.utc)


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
    valores_padrao = {
        "T2M": 25.0,
        "T2M_MAX": 31.0,
        "T2M_MIN": 19.0,
        "PRECTOTCORR": 4.5,
        "RH2M": 70.0,
        "ALLSKY_SFC_SW_DWN": 20.0,
        "WS2M": 2.0,
    }
    parametros = {nome: {} for nome in PARAMETROS_NASA_POWER}
    dia = janela.inicio
    while dia <= janela.fim:
        chave = dia.strftime("%Y%m%d")
        for nome, valor in valores_padrao.items():
            parametros[nome][chave] = valor
        dia += timedelta(days=1)
    return {"properties": {"parameter": parametros}}


def remover_dia(payload, dia: date, parametros=PARAMETROS_NASA_POWER):
    chave = dia.strftime("%Y%m%d")
    for parametro in parametros:
        payload["properties"]["parameter"].get(parametro, {}).pop(chave, None)


def cliente_com_payload(payload, *, status_code=200):
    transporte = TransporteFalso(RespostaFalsa(payload, status_code=status_code))
    cliente = ClienteNasaPowerHistorico(
        transporte=transporte,
        relogio_utc=lambda: AGORA_UTC,
    )
    return cliente, transporte


class TestClienteNasaPowerRequisicao(unittest.TestCase):
    def test_90_dias_usam_uma_chamada_http(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)

    def test_180_dias_usam_uma_chamada_http(self):
        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        serie = cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)
        self.assertEqual(len(serie.registros), 180)

    def test_187_dias_usam_uma_chamada_http(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 187)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        serie = cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(len(transporte.chamadas), 1)
        self.assertEqual(len(serie.registros), 187)

    def test_endpoint_start_e_end_corretos(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        url, kwargs = transporte.chamadas[0]
        self.assertEqual(url, ENDPOINT_NASA_POWER_DAILY)
        self.assertEqual(kwargs["params"]["start"], janela.inicio.strftime("%Y%m%d"))
        self.assertEqual(kwargs["params"]["end"], janela.fim.strftime("%Y%m%d"))

    def test_parametros_da_requisicao(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        cliente.consultar(-13.15, -56.05, janela)
        params = transporte.chamadas[0][1]["params"]
        self.assertEqual(params["parameters"], ",".join(PARAMETROS_NASA_POWER))
        self.assertEqual(params["community"], "AG")
        self.assertEqual(params["format"], "JSON")
        self.assertEqual(params["time-standard"], "LST")
        self.assertEqual(params["latitude"], -13.15)
        self.assertEqual(params["longitude"], -56.05)

    def test_timeout_explicito_e_encaminhado(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        transporte = TransporteFalso(RespostaFalsa(payload_completo(janela)))
        cliente = ClienteNasaPowerHistorico(
            transporte=transporte,
            timeout=(2, 17),
            relogio_utc=lambda: AGORA_UTC,
        )
        cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(transporte.chamadas[0][1]["timeout"], (2.0, 17.0))

    def test_coordenada_invalida_e_rejeitada_sem_http(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        with self.assertRaises(ErroParametroNasaPower):
            cliente.consultar(91, -56.05, janela)
        self.assertEqual(transporte.chamadas, [])

    def test_janela_diferente_de_90_180_ou_187_e_rejeitada(self):
        janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 30)
        cliente, transporte = cliente_com_payload(payload_completo(janela))
        with self.assertRaises(ErroParametroNasaPower):
            cliente.consultar(-13.15, -56.05, janela)
        self.assertEqual(transporte.chamadas, [])

    def test_timeout_booleano_e_rejeitado(self):
        with self.assertRaises(ErroParametroNasaPower):
            ClienteNasaPowerHistorico(timeout=True)


class TestClienteNasaPowerParsing(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)
        self.payload = payload_completo(self.janela)

    def consultar(self):
        cliente, _ = cliente_com_payload(self.payload)
        return cliente.consultar(-13.15, -56.05, self.janela, id_fazenda="MT-01")

    def test_parsing_precipitacao(self):
        self.payload["properties"]["parameter"]["PRECTOTCORR"][
            self.janela.inicio.strftime("%Y%m%d")
        ] = 12.75
        self.assertEqual(self.consultar().registros[0].precipitacao_mm, 12.75)

    def test_parsing_temperatura_media(self):
        self.assertEqual(self.consultar().registros[0].temperatura_media_c, 25.0)

    def test_parsing_temperatura_maxima(self):
        self.assertEqual(self.consultar().registros[0].temperatura_maxima_c, 31.0)

    def test_parsing_temperatura_minima(self):
        self.assertEqual(self.consultar().registros[0].temperatura_minima_c, 19.0)

    def test_parsing_umidade(self):
        self.assertEqual(self.consultar().registros[0].umidade_media_pct, 70.0)

    def test_ws2m_valido_e_mapeado_sem_alterar_outras_variaveis(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["WS2M"][chave] = 3.25
        registro = self.consultar().registros[0]
        self.assertEqual(registro.velocidade_vento_media_m_s, 3.25)
        self.assertEqual(registro.precipitacao_mm, 4.5)
        self.assertEqual(registro.temperatura_media_c, 25.0)
        self.assertEqual(registro.umidade_media_pct, 70.0)

    def test_ws2m_zero_permanece_zero(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["WS2M"][chave] = 0.0
        registro = self.consultar().registros[0]
        self.assertEqual(registro.velocidade_vento_media_m_s, 0.0)
        self.assertNotIn("velocidade_vento_media_m_s", registro.variaveis_ausentes)

    def test_ws2m_sentinela_vira_none(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["WS2M"][chave] = -999
        registro = self.consultar().registros[0]
        self.assertIsNone(registro.velocidade_vento_media_m_s)
        self.assertIn("velocidade_vento_media_m_s", registro.variaveis_ausentes)
        self.assertIn("SENTINELA_NASA:WS2M", registro.flags_qualidade)

    def test_ws2m_ausente_vira_none(self):
        del self.payload["properties"]["parameter"]["WS2M"]
        serie = self.consultar()
        self.assertTrue(
            all(
                registro.velocidade_vento_media_m_s is None
                for registro in serie.registros
            )
        )

    def test_ws2m_negativo_invalido_gera_erro_tipado(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["WS2M"][chave] = -0.1
        with self.assertRaises(ErroContratoNasaPower):
            self.consultar()

    def test_ws2m_nao_finito_gera_erro_tipado(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        for valor in (float("nan"), float("inf")):
            with self.subTest(valor=valor):
                self.payload["properties"]["parameter"]["WS2M"][chave] = valor
                with self.assertRaises(ErroContratoNasaPower):
                    self.consultar()

    def test_zero_e_preservado(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["PRECTOTCORR"][chave] = 0.0
        registro = self.consultar().registros[0]
        self.assertEqual(registro.precipitacao_mm, 0.0)
        self.assertNotIn("precipitacao_mm", registro.variaveis_ausentes)

    def test_sentinela_menos_999_vira_none(self):
        chave = self.janela.inicio.strftime("%Y%m%d")
        self.payload["properties"]["parameter"]["PRECTOTCORR"][chave] = -999
        registro = self.consultar().registros[0]
        self.assertIsNone(registro.precipitacao_mm)
        self.assertIn("precipitacao_mm", registro.variaveis_ausentes)
        self.assertIn("SENTINELA_NASA:PRECTOTCORR", registro.flags_qualidade)

    def test_data_ausente_permanece_no_calendario_como_gap(self):
        ausente = self.janela.inicio + timedelta(days=10)
        remover_dia(self.payload, ausente)
        serie = self.consultar()
        registro = next(item for item in serie.registros if item.data == ausente)
        self.assertFalse(registro.possui_algum_dado())
        self.assertTrue(any(gap.inicio == ausente for gap in serie.qualidade.gaps))

    def test_gap_interno(self):
        inicio_gap = self.janela.inicio + timedelta(days=20)
        remover_dia(self.payload, inicio_gap)
        remover_dia(self.payload, inicio_gap + timedelta(days=1))
        gaps = self.consultar().qualidade.gaps
        self.assertTrue(
            any(
                gap.inicio == inicio_gap
                and gap.fim == inicio_gap + timedelta(days=1)
                and gap.duracao_dias == 2
                for gap in gaps
            )
        )

    def test_gap_final(self):
        remover_dia(self.payload, self.janela.fim)
        serie = self.consultar()
        self.assertTrue(any(gap.fim == self.janela.fim for gap in serie.qualidade.gaps))
        self.assertEqual(serie.periodo_solicitado.fim, self.janela.fim)

    def test_cobertura_geral_considera_janela_completa(self):
        remover_dia(self.payload, self.janela.fim)
        qualidade = self.consultar().qualidade
        self.assertEqual(qualidade.dias_esperados, 90)
        self.assertEqual(qualidade.dias_com_algum_dado, 89)
        self.assertEqual(qualidade.cobertura_pct, 98.89)

    def test_cobertura_por_variavel(self):
        remover_dia(self.payload, self.janela.fim, ("PRECTOTCORR",))
        qualidade = self.consultar().qualidade
        self.assertEqual(qualidade.cobertura_por_variavel_pct["precipitacao_mm"], 98.89)
        self.assertEqual(
            qualidade.cobertura_por_variavel_pct["temperatura_media_c"], 100
        )

    def test_ultima_data_disponivel_por_variavel(self):
        remover_dia(self.payload, self.janela.fim, ("PRECTOTCORR",))
        qualidade = self.consultar().qualidade
        self.assertEqual(
            qualidade.ultima_data_disponivel_por_variavel["precipitacao_mm"],
            self.janela.fim - timedelta(days=1),
        )

    def test_resposta_fora_de_ordem_resulta_em_serie_ordenada(self):
        parametros = self.payload["properties"]["parameter"]
        for nome, serie in parametros.items():
            parametros[nome] = dict(reversed(tuple(serie.items())))
        registros = self.consultar().registros
        self.assertEqual(
            tuple(r.data for r in registros), tuple(sorted(r.data for r in registros))
        )

    def test_parametro_parcialmente_ausente(self):
        dia = self.janela.inicio + timedelta(days=3)
        remover_dia(self.payload, dia, ("T2M",))
        registro = next(item for item in self.consultar().registros if item.data == dia)
        self.assertIsNone(registro.temperatura_media_c)
        self.assertEqual(registro.precipitacao_mm, 4.5)

    def test_variavel_inteira_ausente(self):
        del self.payload["properties"]["parameter"]["RH2M"]
        serie = self.consultar()
        self.assertTrue(all(r.umidade_media_pct is None for r in serie.registros))
        self.assertEqual(
            serie.qualidade.cobertura_por_variavel_pct["umidade_media_pct"], 0
        )

    def test_janela_nao_e_deslocada_pela_ultima_observacao(self):
        remover_dia(self.payload, self.janela.fim)
        remover_dia(self.payload, self.janela.fim - timedelta(days=1))
        serie = self.consultar()
        self.assertEqual(serie.periodo_solicitado.inicio, self.janela.inicio)
        self.assertEqual(serie.periodo_solicitado.fim, self.janela.fim)
        self.assertEqual(serie.periodo_efetivo.fim, self.janela.fim - timedelta(days=2))
        self.assertEqual(len(serie.registros), 90)


class TestClienteNasaPowerContratoEProveniencia(unittest.TestCase):
    def setUp(self):
        self.janela = JanelaHistorica.criar_atual(DATA_REFERENCIA, 90)

    def test_http_500_gera_erro_tipado(self):
        cliente, _ = cliente_com_payload({}, status_code=500)
        with self.assertRaises(ErroHttpNasaPower) as contexto:
            cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(contexto.exception.status_code, 500)

    def test_timeout_gera_erro_tipado(self):
        transporte = TransporteFalso(erro=requests.Timeout("interno"))
        cliente = ClienteNasaPowerHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_erro_de_rede_gera_erro_tipado(self):
        transporte = TransporteFalso(erro=requests.ConnectionError("interno"))
        cliente = ClienteNasaPowerHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_json_invalido_gera_erro_de_contrato(self):
        transporte = TransporteFalso(RespostaFalsa(json_invalido=True))
        cliente = ClienteNasaPowerHistorico(transporte=transporte)
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_contrato_sem_properties_e_rejeitado(self):
        cliente, _ = cliente_com_payload({})
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_contrato_sem_parametros_e_rejeitado(self):
        cliente, _ = cliente_com_payload({"properties": {"parameter": {}}})
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_serie_de_parametro_invalida_e_rejeitada(self):
        payload = payload_completo(self.janela)
        payload["properties"]["parameter"]["T2M"] = []
        cliente, _ = cliente_com_payload(payload)
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_data_invalida_e_rejeitada(self):
        payload = payload_completo(self.janela)
        payload["properties"]["parameter"]["T2M"]["2026-08-01"] = 25
        cliente, _ = cliente_com_payload(payload)
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_valor_nao_numerico_e_rejeitado(self):
        payload = payload_completo(self.janela)
        chave = self.janela.inicio.strftime("%Y%m%d")
        payload["properties"]["parameter"]["T2M"][chave] = "25"
        cliente, _ = cliente_com_payload(payload)
        with self.assertRaises(ErroContratoNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_falha_nao_produz_fallback(self):
        transporte = TransporteFalso(erro=requests.Timeout("interno"))
        cliente = ClienteNasaPowerHistorico(transporte=transporte)
        with self.assertRaises(ErroTransporteNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_cliente_nao_escreve_em_disco(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        with patch.object(
            builtins, "open", side_effect=AssertionError("escrita indevida")
        ):
            serie = cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(len(serie.registros), 90)

    def test_modulo_nao_importa_fluxos_operacionais(self):
        from backend.exposicao.clientes import nasa_power_historico

        codigo = inspect.getsource(nasa_power_historico).lower()
        for termo in ("etapa3", "score", "alertas", "fastapi", "supabase", "to_csv"):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)

    def test_natureza_fonte_produto_e_dataset(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        serie = cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(serie.fonte, FonteDado.NASA_POWER)
        self.assertEqual(serie.natureza, NaturezaDado.HISTORICO)
        self.assertEqual(serie.tipo_produto, TipoProdutoHistorico.HISTORICO_REGIONAL)
        self.assertEqual(serie.dataset, DATASET_NASA_POWER_DAILY)

    def test_referencia_temporal_lst_e_preservada(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        serie = cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(
            serie.referencia_temporal.tipo,
            TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
        )
        self.assertEqual(serie.metadados_origem["time_standard"], "LST")

    def test_proveniencia_preserva_endpoint_parametros_e_janela(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        serie = cliente.consultar(-13.15, -56.05, self.janela, id_fazenda="MT-01")
        metadados = serie.metadados_origem
        self.assertEqual(serie.id_fazenda, "MT-01")
        self.assertEqual(metadados["endpoint"], ENDPOINT_NASA_POWER_DAILY)
        self.assertEqual(
            tuple(metadados["parametros_solicitados"]), PARAMETROS_NASA_POWER
        )
        self.assertEqual(
            metadados["inicio_solicitado"], self.janela.inicio.strftime("%Y%m%d")
        )
        self.assertEqual(
            metadados["fim_solicitado"], self.janela.fim.strftime("%Y%m%d")
        )
        self.assertEqual(
            metadados["vento"],
            {
                "parametro_fonte": "WS2M",
                "variavel_canonica": "velocidade_vento_media_m_s",
                "unidade": "m/s",
                "altura_m": 2,
                "agregacao_temporal": "media_diaria",
                "referencia_temporal": "LST",
            },
        )

    def test_coletado_em_utc_e_timezone_aware(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        serie = cliente.consultar(-13.15, -56.05, self.janela)
        self.assertEqual(serie.coletado_em_utc, AGORA_UTC)
        self.assertEqual(serie.coletado_em_utc.utcoffset(), timedelta(0))

    def test_relogio_sem_timezone_e_rejeitado(self):
        payload = payload_completo(self.janela)
        transporte = TransporteFalso(RespostaFalsa(payload))
        cliente = ClienteNasaPowerHistorico(
            transporte=transporte,
            relogio_utc=lambda: datetime(2026, 8, 12, 12, 30),
        )
        with self.assertRaises(ErroParametroNasaPower):
            cliente.consultar(-13.15, -56.05, self.janela)

    def test_nasa_permanece_independente_de_open_meteo(self):
        payload = payload_completo(self.janela)
        cliente, _ = cliente_com_payload(payload)
        nasa = cliente.consultar(-13.15, -56.05, self.janela)
        open_meteo = SerieHistoricaFonte.criar(
            fonte=FonteDado.OPEN_METEO,
            tipo_produto=TipoProdutoHistorico.REANALISE_MODELADA,
            dataset="Open-Meteo Historical futuro",
            periodo_solicitado=self.janela,
            referencia_temporal=ReferenciaTemporalHistorica(
                tipo=TipoReferenciaTemporal.TIMEZONE_CIVIL,
                timezone="America/Cuiaba",
            ),
            registros=(
                RegistroMeteorologicoDiario(
                    data=self.janela.inicio,
                    precipitacao_mm=0,
                ),
            ),
            coletado_em_utc=AGORA_UTC,
        )
        self.assertIsNot(nasa, open_meteo)
        self.assertNotEqual(nasa.fonte, open_meteo.fonte)
        self.assertNotEqual(nasa.referencia_temporal, open_meteo.referencia_temporal)


@unittest.skipUnless(
    os.getenv("RUN_NASA_POWER_INTEGRATION") == "1",
    "integração NASA POWER opcional; defina RUN_NASA_POWER_INTEGRATION=1",
)
class TestClienteNasaPowerIntegracaoReal(unittest.TestCase):
    def test_mt_180_dias_sem_persistencia(self):
        class SessaoContadora(requests.Session):
            def __init__(self):
                super().__init__()
                self.quantidade_chamadas = 0

            def get(self, url, **kwargs):
                self.quantidade_chamadas += 1
                return super().get(url, **kwargs)

        janela = JanelaHistorica.criar_aquisicao_180(DATA_REFERENCIA)
        sessao = SessaoContadora()
        cliente = ClienteNasaPowerHistorico(
            transporte=sessao,
            timeout=(5, 60),
        )
        inicio = time.monotonic()
        try:
            try:
                serie = cliente.consultar(-13.15, -56.05, janela, id_fazenda="MT-POC")
            except (ErroTransporteNasaPower, ErroHttpNasaPower) as exc:
                self.skipTest(f"serviço externo indisponível: {type(exc).__name__}")
        finally:
            sessao.close()
        duracao = time.monotonic() - inicio
        gaps_finais = [
            gap.model_dump(mode="json")
            for gap in serie.qualidade.gaps
            if gap.fim == janela.fim
        ]
        diagnostico = {
            "dias_solicitados": janela.dias_esperados,
            "registros_no_calendario": len(serie.registros),
            "dias_com_algum_dado": serie.qualidade.dias_com_algum_dado,
            "cobertura_por_variavel_pct": serie.qualidade.cobertura_por_variavel_pct,
            "primeira_data": serie.registros[0].data.isoformat(),
            "ultima_data_solicitada": serie.registros[-1].data.isoformat(),
            "ultima_data_valida_por_variavel": {
                chave: valor.isoformat() if valor else None
                for chave, valor in serie.qualidade.ultima_data_disponivel_por_variavel.items()
            },
            "gaps_finais": gaps_finais,
            "duracao_s": round(duracao, 3),
        }
        print(f"NASA POWER integração MT: {diagnostico}")
        self.assertEqual(sessao.quantidade_chamadas, 1)
        self.assertEqual(len(serie.registros), 180)
        self.assertEqual(serie.periodo_solicitado, janela)


if __name__ == "__main__":
    unittest.main()
