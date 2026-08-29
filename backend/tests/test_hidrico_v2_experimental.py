from __future__ import annotations

import csv
import math
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.exposicao.hidrico_v2_experimental import (
    METODOLOGIA_HIDRICO_V2,
    PARAMETROS_T3_G3,
    PESOS_SCORE_EXPERIMENTAL,
    ContextoTerritorialHidricoV2,
    agregar_hidrico_v2_experimental,
    calcular_a2,
    calcular_d2,
    calcular_h2_experimental,
    calcular_hidrico_v2_diario,
    calcular_p2,
    calcular_score_paralelo,
    calcular_t3,
)
from backend.exposicao.modelos import FinalidadeJanela, JanelaHistorica
from backend.exposicao.perigos_hidricos import normalizar_precipitacao
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.scripts.prototipo_hidrico_v2 import BASELINE, COMPARACAO, executar


def _ler(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


class TesteHidricoV2Experimental(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.politica = criar_politica_agrishield_equip_v1()
        cls.ctx = ContextoTerritorialHidricoV2(
            distancia_drenagem_m=2001.65263222744,
            area_drenagem_montante_km2=850.3291015625,
            posicao_topografica_relativa_m=-1.45720997093969,
        )

    def diario(self, h1=20.0, chuva=30.0, contexto=None):
        return calcular_hidrico_v2_diario(
            data=date(2026, 1, 1),
            h1_meteorologico=h1,
            acumulado_3d=chuva,
            contexto=contexto or self.ctx,
            politica=self.politica,
        )

    def test_invariantes_zero_limites_e_metodologia(self):
        sem_chuva = self.diario(h1=37, chuva=0)
        self.assertEqual(sem_chuva.g3, 0)
        self.assertEqual(sem_chuva.h2_final, 37)
        susc_zero = ContextoTerritorialHidricoV2(
            distancia_drenagem_m=1e300,
            area_drenagem_montante_km2=0,
            posicao_topografica_relativa_m=1e6,
        )
        # Um T3 numericamente nulo preserva H1.
        zero = self.diario(h1=37, chuva=100, contexto=susc_zero)
        self.assertAlmostEqual(zero.h2_final, 37, places=12)
        for h1 in (0, 5, 25, 70, 100):
            r = self.diario(h1=h1, chuva=200)
            self.assertGreaterEqual(r.h2_final, h1)
            self.assertLessEqual(r.h2_final, 100)
            self.assertGreaterEqual(r.incremento_territorial, 0)
        self.assertEqual(sem_chuva.metodologia, METODOLOGIA_HIDRICO_V2)

    def test_suscetibilidade_zero_mantem_h1_exatamente(self):
        self.assertEqual(calcular_h2_experimental(37, 0.8, 0), (37.0, 0.0, 0.0))

    def test_missing_territorial_e_meteorologico_permanece_missing(self):
        casos = [
            ContextoTerritorialHidricoV2(
                distancia_drenagem_m=None,
                area_drenagem_montante_km2=100,
                posicao_topografica_relativa_m=0,
            ),
            ContextoTerritorialHidricoV2(
                distancia_drenagem_m=100,
                area_drenagem_montante_km2=None,
                posicao_topografica_relativa_m=0,
            ),
            ContextoTerritorialHidricoV2(
                distancia_drenagem_m=100,
                area_drenagem_montante_km2=100,
                posicao_topografica_relativa_m=None,
            ),
        ]
        for contexto in casos:
            resultado = self.diario(contexto=contexto)
            self.assertIsNone(resultado.h2_final)
            self.assertIsNone(resultado.incremento_territorial)
        self.assertIsNone(self.diario(chuva=None).h2_final)

    @unittest.skipUnless(
        (
            BASELINE.parent
            / "simulacao_hidrico_v2"
            / "01_suscetibilidade_territorial.csv"
        ).exists(),
        "artefatos históricos de simulação não estão presentes no workspace",
    )
    def test_d2_a2_p2_t3_reproduzem_simulacao(self):
        esperado = _ler(
            BASELINE.parent
            / "simulacao_hidrico_v2"
            / "01_suscetibilidade_territorial.csv"
        )[0]
        self.assertAlmostEqual(
            calcular_d2(self.ctx.distancia_drenagem_m), float(esperado["d2"]), places=12
        )
        self.assertAlmostEqual(
            calcular_a2(self.ctx.area_drenagem_montante_km2),
            float(esperado["a2"]),
            places=12,
        )
        self.assertAlmostEqual(
            calcular_p2(self.ctx.posicao_topografica_relativa_m),
            float(esperado["p2"]),
            places=12,
        )
        self.assertAlmostEqual(
            calcular_t3(self.ctx).t3, float(esperado["t3"]), places=12
        )

    def test_g3_reutiliza_curva_oficial(self):
        r = self.diario(chuva=35)
        self.assertEqual(r.g3, normalizar_precipitacao(35, self.politica) / 100)
        self.assertGreaterEqual(r.g3, 0)
        self.assertLessEqual(r.g3, 1)

    @unittest.skipUnless(
        (COMPARACAO / "06_casos_reais.csv").exists()
        and (BASELINE / "02_contexto_territorial.csv").exists()
        and (BASELINE / "05_features_diarias.csv").exists(),
        "artefatos históricos de comparação não estão presentes no workspace",
    )
    def test_casos_reais_reproduzem_comparacao_final(self):
        casos = _ler(COMPARACAO / "06_casos_reais.csv")
        contextos = {
            int(x["id_fazenda"]): x
            for x in _ler(BASELINE / "02_contexto_territorial.csv")
        }
        features = {
            (int(x["id_fazenda"]), x["data"]): x
            for x in _ler(BASELINE / "05_features_diarias.csv")
        }
        for esperado in casos:
            fid = int(esperado["id_fazenda"])
            f = features[(fid, esperado["data"])]
            c = contextos[fid]
            r = calcular_hidrico_v2_diario(
                data=date.fromisoformat(f["data"]),
                h1_meteorologico=float(f["indice_hidrico"]),
                acumulado_3d=float(f["acumulado_3d"]),
                contexto=ContextoTerritorialHidricoV2(
                    distancia_drenagem_m=float(c["distancia_drenagem_m"]),
                    area_drenagem_montante_km2=float(c["area_drenagem_montante_km2"]),
                    posicao_topografica_relativa_m=float(
                        c["posicao_topografica_relativa_m"]
                    ),
                ),
                politica=self.politica,
            )
            self.assertAlmostEqual(r.h2_final, float(esperado["h2_T3_g3"]), places=10)

    def test_agregacao_e_score_reutilizam_resultados_oficiais(self):
        periodo = JanelaHistorica(
            data_referencia=date(2026, 3, 31),
            inicio=date(2026, 1, 1),
            fim=date(2026, 3, 31),
            dias_esperados=90,
            finalidade=FinalidadeJanela.ATUAL,
        )
        resultados = [
            calcular_hidrico_v2_diario(
                data=periodo.inicio + timedelta(days=i),
                h1_meteorologico=30 if i in {0, 1, 5} else 0,
                acumulado_3d=0,
                contexto=self.ctx,
                politica=self.politica,
            )
            for i in range(90)
        ]
        agregado = agregar_hidrico_v2_experimental(resultados, periodo, self.politica)
        self.assertEqual(agregado.agregacao_v1, agregado.agregacao_v2)
        score = calcular_score_paralelo(
            score_v1=20,
            indice_hidrico_v1_90d=20,
            indice_hidrico_v2_90d=30,
            politica=self.politica,
        )
        self.assertEqual(score.score_v2_experimental, 24)
        self.assertEqual(score.delta_score, 4)

    def test_pesos_trafegabilidade_e_instabilidade_isolados(self):
        self.assertTrue(
            math.isclose(sum(PESOS_SCORE_EXPERIMENTAL.values()), 1, abs_tol=1e-12)
        )
        self.assertEqual(PESOS_SCORE_EXPERIMENTAL["TRAFEGABILIDADE"], 0)
        score = calcular_score_paralelo(
            score_v1=20,
            indice_hidrico_v1_90d=20,
            indice_hidrico_v2_90d=30,
            politica=self.politica,
        )
        self.assertTrue(score.instabilidade_permanece_baseada_em_h1)

    @unittest.skipUnless(
        (BASELINE / "02_contexto_territorial.csv").exists(),
        "baseline histórico não está presente no workspace",
    )
    def test_execucao_integral_reproduz_1080_dias_12_agregacoes_e_score(self):
        with TemporaryDirectory() as tmp:
            resultado = executar(Path(tmp))
            self.assertEqual(len(resultado["diarios"]), 1080)
            self.assertEqual(len(resultado["agregados"]), 12)
            self.assertEqual(resultado["divergencias"], [])
            self.assertEqual(
                {p.name for p in Path(tmp).iterdir()},
                {
                    "01_resultados_diarios_t3_g3.csv",
                    "02_resultados_90d_score.csv",
                    "RELATORIO_PROTOTIPO_HIDRICO_V2.md",
                },
            )

    def test_v1_e_endpoint_oficial_permanecem_default(self):
        from backend.app.main import app, get_exposicao_v1
        from backend.exposicao.exposicao_hidrica import calcular_exposicao_hidrica

        rotas = [
            r
            for r in app.routes
            if getattr(r, "path", None) == "/api/v1/exposicao/{id_fazenda}"
        ]
        self.assertEqual(len(rotas), 1)
        self.assertIs(rotas[0].endpoint, get_exposicao_v1)
        self.assertNotIn("experimental", calcular_exposicao_hidrica.__module__)

    def test_parametros_sao_fixos_e_exatos(self):
        self.assertEqual(PARAMETROS_T3_G3.mediana_distancia_m, 1868.12508034684)
        with self.assertRaises(Exception):
            PARAMETROS_T3_G3.mediana_distancia_m = 1


if __name__ == "__main__":
    unittest.main()
