from __future__ import annotations

from datetime import date
import unittest

from fastapi.testclient import TestClient

from backend.app import main
from backend.app.servico_avaliacao_exposicao import ContextoTerritorialIndisponivel
from backend.app.servico_hidrico_v2_experimental import ServicoHidricoV2Experimental
from backend.risco.modelos import FonteDado
from backend.tests.test_exposicao_validacao_integrada import criar_geo
from backend.tests.test_servico_avaliacao_exposicao import (
    DATA_REFERENCIA,
    ID_FAZENDA,
    ProvedorFalso,
    RepositorioFalso,
    criar_servico,
)


class TesteServicoExperimental(unittest.TestCase):
    def test_retorna_dto_proveniencia_avisos_e_dias_filtrados(self):
        base, _, _, _, _ = criar_servico()
        resultado = ServicoHidricoV2Experimental(base).avaliar(
            ID_FAZENDA, DATA_REFERENCIA
        )
        self.assertEqual(resultado.status.value, "EXPERIMENTAL")
        self.assertIn("T3_G3", resultado.metodologia)
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.NASA_POWER)
        self.assertIsNotNone(resultado.territorio.t3)
        self.assertLessEqual(len(resultado.dias_relevantes), 180)
        self.assertEqual(
            {x.fonte for x in resultado.proveniencia},
            {
                "NASA_POWER",
                "MERIT_HYDRO",
                "SRTM",
                "DECLIVIDADE",
                "MAPBIOMAS",
                "INMET",
                "TRAFEGABILIDADE",
                "INSTABILIDADE",
            },
        )
        self.assertTrue(
            any("não calibrado" in x.lower() for x in resultado.avisos_metodologicos)
        )

    def test_detalhe_completo_retorna_180_dias(self):
        base, _, _, _, _ = criar_servico()
        resultado = ServicoHidricoV2Experimental(base).avaliar(
            ID_FAZENDA, DATA_REFERENCIA, detalhe_completo=True
        )
        self.assertEqual(len(resultado.dias_relevantes), 180)

    def test_open_meteo_nao_mistura_fontes(self):
        base, _, nasa, open_meteo, _ = criar_servico()
        resultado = ServicoHidricoV2Experimental(base).avaliar(
            ID_FAZENDA, DATA_REFERENCIA, fonte=FonteDado.OPEN_METEO
        )
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.OPEN_METEO)
        self.assertEqual(nasa.chamadas, [])
        self.assertEqual(len(open_meteo.chamadas), 1)

    def test_missing_territorial_falha_sem_fabricar_zero(self):
        original = criar_geo(20)
        geo = original.model_copy(
            update={
                "posicao_topografica_relativa_m": original.posicao_topografica_relativa_m.model_copy(
                    update={"valor": None}
                )
            }
        )
        base, *_ = criar_servico(provedor=ProvedorFalso(contexto=geo))
        with self.assertRaises(ContextoTerritorialIndisponivel):
            ServicoHidricoV2Experimental(base).avaliar(ID_FAZENDA, DATA_REFERENCIA)


class TesteEndpointExperimental(unittest.TestCase):
    def setUp(self):
        base, *_ = criar_servico()
        self.servico = ServicoHidricoV2Experimental(base)
        main.app.dependency_overrides[main.obter_servico_hidrico_v2_experimental] = (
            lambda: self.servico
        )
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_200_e_contrato_experimental(self):
        resposta = self.client.get(
            f"/api/experimental/exposicao-hidrica-v2/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 200)
        payload = resposta.json()
        self.assertEqual(payload["status"], "EXPERIMENTAL")
        self.assertIn("territorio", payload)
        self.assertIn("janela_atual", payload)
        self.assertIn("dias_relevantes", payload)

    def test_fazenda_inexistente_contexto_ausente_e_fonte_invalida(self):
        base, *_ = criar_servico(repositorio=RepositorioFalso(fazenda=None))
        main.app.dependency_overrides[main.obter_servico_hidrico_v2_experimental] = (
            lambda: ServicoHidricoV2Experimental(base)
        )
        resposta = self.client.get(
            "/api/experimental/exposicao-hidrica-v2/inexistente",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(resposta.status_code, 404)
        base, *_ = criar_servico(
            provedor=ProvedorFalso(erro=ContextoTerritorialIndisponivel(ID_FAZENDA))
        )
        main.app.dependency_overrides[main.obter_servico_hidrico_v2_experimental] = (
            lambda: ServicoHidricoV2Experimental(base)
        )
        contexto = self.client.get(
            f"/api/experimental/exposicao-hidrica-v2/{ID_FAZENDA}",
            params={"data_referencia": DATA_REFERENCIA.isoformat()},
        )
        self.assertEqual(contexto.status_code, 422)
        invalida = self.client.get(
            f"/api/experimental/exposicao-hidrica-v2/{ID_FAZENDA}",
            params={"fonte": "INMET"},
        )
        self.assertEqual(invalida.status_code, 422)

    def test_endpoint_v1_permanece_registrado_com_mesmo_response_model(self):
        rota = next(
            r
            for r in main.app.routes
            if getattr(r, "path", None) == "/api/v1/exposicao/{id_fazenda}"
        )
        self.assertEqual(rota.endpoint, main.get_exposicao_v1)
        self.assertNotEqual(
            rota.response_model,
            next(
                r
                for r in main.app.routes
                if getattr(r, "path", None)
                == "/api/experimental/exposicao-hidrica-v2/{id_fazenda}"
            ).response_model,
        )


if __name__ == "__main__":
    unittest.main()
