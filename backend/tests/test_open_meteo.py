from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

BACKEND = Path(__file__).resolve().parents[1]
for pasta in (BACKEND, BACKEND / "app", BACKEND / "etl"):
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))

import servicos_externos as servicos  # noqa: E402
from etapa3_engenharia_variaveis import avaliar_risco_alagamento  # noqa: E402


AGORA_UTC = datetime(2026, 8, 12, 2, 30, tzinfo=timezone.utc)


def payload_valido():
    return {
        "latitude": -12.5,
        "longitude": -55.75,
        "generationtime_ms": 0.41,
        "utc_offset_seconds": -14400,
        "timezone": "America/Cuiaba",
        "timezone_abbreviation": "-04",
        "elevation": 380.0,
        "daily_units": {
            "time": "iso8601",
            "precipitation_sum": "mm",
            "precipitation_probability_max": "%",
            "temperature_2m_max": "\N{DEGREE SIGN}C",
        },
        "daily": {
            "time": [
                "2026-08-11",
                "2026-08-12",
                "2026-08-13",
                "2026-08-14",
                "2026-08-15",
            ],
            "precipitation_sum": [0.0, None, 30.0, 18.0, 2.0],
            "precipitation_probability_max": [0, None, None, 70, 15],
            "temperature_2m_max": [0.0, None, 31.0, 32.0, 33.0],
        },
    }


class RespostaFake:
    def __init__(self, payload=None, *, erro_http=None, erro_json=None):
        self._payload = payload
        self._erro_http = erro_http
        self._erro_json = erro_json

    def raise_for_status(self):
        if self._erro_http:
            raise self._erro_http

    def json(self):
        if self._erro_json:
            raise self._erro_json
        return self._payload


class OpenMeteoTests(unittest.TestCase):
    def consultar(self, payload=None, *, getter=None):
        http_get = getter or Mock(
            return_value=RespostaFake(payload_valido() if payload is None else payload)
        )
        resultado = servicos.consultar_open_meteo(
            -12.545,
            -55.721,
            relogio=lambda: AGORA_UTC,
            http_get=http_get,
        )
        return resultado, http_get

    def test_resposta_real_valida_em_uma_chamada_preserva_metadados(self):
        resultado, getter = self.consultar()

        self.assertEqual(getter.call_count, 1)
        getter.assert_called_once_with(
            servicos.OPEN_METEO_URL,
            params={
                "latitude": -12.545,
                "longitude": -55.721,
                "daily": servicos.OPEN_METEO_DAILY,
                "forecast_days": 5,
                "timezone": "America/Cuiaba",
            },
            timeout=(5, 20),
        )
        self.assertEqual(resultado["fonte"], "OPEN_METEO")
        self.assertEqual(resultado["natureza"], "PREVISTO")
        self.assertFalse(resultado["simulado"])
        self.assertEqual(resultado["coletado_em_utc"], AGORA_UTC.isoformat())
        self.assertEqual(resultado["qualidade"]["status"], "PARCIAL")
        self.assertEqual(resultado["qualidade"]["dias_recebidos"], 5)
        self.assertEqual(resultado["resposta"]["latitude_grade"], -12.5)
        self.assertEqual(resultado["resposta"]["longitude_grade"], -55.75)
        self.assertEqual(resultado["resposta"]["elevacao_m"], 380.0)
        self.assertEqual(resultado["resposta"]["timezone"], "America/Cuiaba")
        self.assertEqual(resultado["resposta"]["timezone_abbreviation"], "-04")
        self.assertEqual(resultado["resposta"]["utc_offset_seconds"], -14400)
        self.assertEqual(resultado["resposta"]["generationtime_ms"], 0.41)
        self.assertEqual(
            resultado["resposta"]["unidades"], payload_valido()["daily_units"]
        )
        self.assertNotIn("gerado_em", resultado)
        self.assertIsNone(resultado["erro_origem"])

    def test_zero_e_none_sao_preservados_sem_imputacao(self):
        resultado, _ = self.consultar()

        primeiro, segundo = resultado["dias"][:2]
        self.assertEqual(primeiro["precipitacao_mm"], 0)
        self.assertEqual(primeiro["prob_precip_pct"], 0)
        self.assertEqual(primeiro["temp_max_c"], 0)
        self.assertIsNone(segundo["precipitacao_mm"])
        self.assertIsNone(segundo["prob_precip_pct"])
        self.assertIsNone(segundo["temp_max_c"])
        self.assertEqual(
            resultado["qualidade"]["variaveis_ausentes"],
            ["precipitacao_mm", "prob_precip_pct", "temp_max_c"],
        )

    def test_respostas_estruturalmente_invalidas_geram_fallback_integral(self):
        casos = {}
        payload = payload_valido()
        payload.pop("daily")
        casos["daily ausente"] = payload
        casos["daily vazio"] = {**payload_valido(), "daily": {}}
        payload = payload_valido()
        payload["daily"].pop("time")
        casos["time ausente"] = payload
        payload = payload_valido()
        payload["daily"]["precipitation_sum"] = [99.0]
        casos["comprimentos diferentes"] = payload
        payload = payload_valido()
        payload["daily"]["time"] = []
        casos["sem dias"] = payload

        for nome, resposta in casos.items():
            with self.subTest(nome=nome):
                resultado, _ = self.consultar(resposta)
                self.assertEqual(resultado["fonte"], "SIMULADOR_INTERNO")
                self.assertTrue(resultado["simulado"])
                self.assertEqual(len(resultado["dias"]), 5)
                self.assertNotIn("99.0", str(resultado["dias"]))
                self.assertEqual(
                    resultado["erro_origem"]["categoria"], "contrato_invalido"
                )

    def test_fallback_usa_data_civil_do_timezone_solicitado(self):
        getter = Mock(side_effect=requests.Timeout("tempo esgotado"))
        resultado, _ = self.consultar(getter=getter)

        # 02:30 UTC ainda corresponde ao dia anterior em America/Cuiaba.
        self.assertEqual(resultado["dias"][0]["data_local"], "2026-08-11")
        self.assertEqual(
            [dia["precipitacao_mm"] for dia in resultado["dias"]],
            [4.0, 18.5, 34.0, 22.0, 6.0],
        )
        self.assertEqual(resultado["fonte"], "SIMULADOR_INTERNO")
        self.assertEqual(resultado["natureza"], "PREVISTO")
        self.assertTrue(resultado["simulado"])
        self.assertIn("DADO_SINTETICO", resultado["qualidade"]["flags"])

    def test_falhas_http_transporte_json_e_valor_nao_numerico_sao_tipadas(self):
        payload_invalido = payload_valido()
        payload_invalido["daily"]["temperature_2m_max"][2] = "quente"
        casos = (
            (
                "http_4xx",
                Mock(
                    return_value=RespostaFake(
                        erro_http=requests.HTTPError("400 Client Error")
                    )
                ),
                "http",
            ),
            (
                "http_5xx",
                Mock(
                    return_value=RespostaFake(
                        erro_http=requests.HTTPError("503 Server Error")
                    )
                ),
                "http",
            ),
            ("timeout", Mock(side_effect=requests.Timeout("timeout")), "transporte"),
            (
                "json",
                Mock(
                    return_value=RespostaFake(erro_json=ValueError("JSONDecodeError"))
                ),
                "parsing",
            ),
            (
                "nao_numerico",
                Mock(return_value=RespostaFake(payload_invalido)),
                "contrato_invalido",
            ),
        )

        for nome, getter, categoria in casos:
            with self.subTest(nome=nome):
                resultado, _ = self.consultar(getter=getter)
                self.assertTrue(resultado["simulado"])
                self.assertEqual(resultado["erro_origem"]["categoria"], categoria)
                self.assertNotIn("Traceback", resultado["erro_origem"]["detalhe"])

    def test_erro_origem_e_sanitizado(self):
        getter = Mock(
            side_effect=requests.ConnectionError(
                "falha token=segredo-supersecreto api_key:outrosegredo "
                "Authorization: Bearer terceirosegredo"
            )
        )
        resultado, _ = self.consultar(getter=getter)

        detalhe = resultado["erro_origem"]["detalhe"]
        self.assertNotIn("segredo-supersecreto", detalhe)
        self.assertNotIn("outrosegredo", detalhe)
        self.assertNotIn("terceirosegredo", detalhe)
        self.assertIn("[redacted]", detalhe)

    def test_unidade_incompativel_falha_e_unidades_ausentes_nao_sao_inventadas(self):
        payload = payload_valido()
        payload["daily_units"]["precipitation_sum"] = "cm"
        invalido, _ = self.consultar(payload)
        self.assertTrue(invalido["simulado"])

        payload = payload_valido()
        payload.pop("daily_units")
        sem_unidades, _ = self.consultar(payload)
        self.assertFalse(sem_unidades["simulado"])
        self.assertEqual(sem_unidades["resposta"]["unidades"], {})
        self.assertIn("UNIDADES_AUSENTES", sem_unidades["qualidade"]["flags"])

    def test_fachada_legada_preserva_dias_reais_none_e_alertas(self):
        rico, _ = self.consultar()
        with patch.object(servicos, "consultar_open_meteo", return_value=rico):
            legado = servicos.previsao_open_meteo(-12.545, -55.721)

        self.assertEqual(legado["origem"], "api_open_meteo")
        self.assertEqual(len(legado["dias"]), 5)
        self.assertIsNone(legado["dias"][1]["precipitacao_mm"])
        self.assertEqual(len(legado["alertas"]), 2)

    def test_fachada_legada_nao_expoe_dias_sinteticos_para_decisao(self):
        rico, _ = self.consultar(getter=Mock(side_effect=requests.Timeout("timeout")))
        self.assertEqual(
            [dia["precipitacao_mm"] for dia in rico["dias"]],
            [4.0, 18.5, 34.0, 22.0, 6.0],
        )
        with patch.object(servicos, "consultar_open_meteo", return_value=rico):
            legado = servicos.previsao_open_meteo(-12.545, -55.721)

        self.assertEqual(legado["origem"], "fallback_simulado")
        self.assertEqual(legado["dias"], [])
        self.assertEqual(legado["alertas"], [])
        self.assertEqual(legado["erro"], "Timeout")

    def test_alertas_preservam_thresholds_e_tratam_ausencia(self):
        dias = [
            {"data": "d1", "precipitacao_mm": 30, "prob_precip_pct": None},
            {"data": "d2", "precipitacao_mm": 18, "prob_precip_pct": 70},
            {"data": "d3", "precipitacao_mm": 18, "prob_precip_pct": None},
            {"data": "d4", "precipitacao_mm": None, "prob_precip_pct": 100},
            {"data": "d5", "precipitacao_mm": 0, "prob_precip_pct": 100},
        ]

        alertas = servicos.gerar_alertas_chuva(dias)

        self.assertEqual([alerta["data"] for alerta in alertas], ["d1", "d2"])
        self.assertIn("probabilidade indispon", alertas[0]["detalhe"])

    def test_fallback_nao_contribui_para_regra_legada_de_alagamento(self):
        rico, _ = self.consultar(getter=Mock(side_effect=requests.Timeout("timeout")))
        with patch.object(servicos, "consultar_open_meteo", return_value=rico):
            legado = servicos.previsao_open_meteo(-12.545, -55.721)

        alerta = avaliar_risco_alagamento(
            {
                "metricas_dia": {
                    "chuva_acumulada_7d": 0,
                    "solo_encharcado": False,
                }
            },
            legado["dias"],
            proximidade_agua=False,
        )
        self.assertIsNone(alerta)

    def test_get_score_nao_depende_de_open_meteo(self):
        import main

        with patch.object(
            main, "_gerar_score", return_value={"score": 42}
        ) as gerar, patch.object(main, "previsao_open_meteo") as open_meteo:
            resultado = main.get_score("1")

        self.assertEqual(resultado, {"score": 42})
        gerar.assert_called_once_with("1")
        open_meteo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
