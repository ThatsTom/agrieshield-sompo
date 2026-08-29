from datetime import date, datetime, timezone
import sys
from pathlib import Path
import unittest

from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from risco.modelos import (  # noqa: E402
    AgregacaoTemporal,
    ContextoTemporalFeature,
    DadoNormalizado,
    FonteDado,
    FreshnessStatus,
    NaturezaDado,
    NivelProcessamento,
    QualidadeDado,
    ReferenciaTemporal,
    StatusQualidade,
)


class ModelosRiscoTests(unittest.TestCase):
    def test_enums_contem_eixos_independentes(self):
        self.assertEqual(NaturezaDado.HISTORICO.value, "HISTORICO")
        self.assertEqual(FonteDado.SIMULADOR_INTERNO.value, "SIMULADOR_INTERNO")
        self.assertNotIn("SINTETICO", NaturezaDado.__members__)
        self.assertEqual(NivelProcessamento.DERIVADO.value, "DERIVADO")
        self.assertEqual(FreshnessStatus.DEFASADO.value, "DEFASADO")
        self.assertNotIn("DEFASADO", StatusQualidade.__members__)

    def test_contexto_temporal_rejeita_data_efetiva_futura(self):
        with self.assertRaises(ValidationError):
            ContextoTemporalFeature(
                data_referencia_solicitada=date(2026, 8, 11),
                data_referencia_efetiva=date(2026, 8, 12),
                defasagem_dias=0,
                freshness_status=FreshnessStatus.ATUAL,
                dias_esperados=1,
                dias_disponiveis=1,
                cobertura_pct=100,
            )

    def test_qualidade_defaults(self):
        qualidade = QualidadeDado()
        self.assertEqual(qualidade.status, StatusQualidade.DISPONIVEL)
        self.assertFalse(qualidade.imputado)
        self.assertFalse(qualidade.simulado)
        self.assertIsNone(qualidade.cobertura_pct)
        self.assertEqual(qualidade.flags, ())

    def test_cobertura_aceita_limites(self):
        self.assertEqual(QualidadeDado(cobertura_pct=0).cobertura_pct, 0)
        self.assertEqual(QualidadeDado(cobertura_pct=100).cobertura_pct, 100)

    def test_cobertura_fora_do_intervalo_rejeitada(self):
        for cobertura in (-0.1, 100.1):
            with self.subTest(cobertura=cobertura), self.assertRaises(ValidationError):
                QualidadeDado(cobertura_pct=cobertura)

    def test_dado_aceita_none_e_zero_sem_confundir(self):
        base = dict(
            variavel="precipitacao_diaria_mm",
            unidade="mm/dia",
            fonte=FonteDado.NASA_POWER,
            natureza=NaturezaDado.HISTORICO,
            nivel_processamento=NivelProcessamento.NORMALIZADO,
        )
        self.assertIsNone(DadoNormalizado(valor=None, **base).valor)
        self.assertEqual(DadoNormalizado(valor=0, **base).valor, 0)

    def test_referencia_diaria_sem_timezone_inventado(self):
        referencia = ReferenciaTemporal(
            inicio=date(2026, 8, 1),
            fim=date(2026, 8, 1),
            timezone=None,
            agregacao=AgregacaoTemporal.DIARIA,
        )
        self.assertIsNone(referencia.timezone)

    def test_referencia_horaria_utc(self):
        instante = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
        referencia = ReferenciaTemporal(
            inicio=instante,
            fim=instante,
            timezone="UTC",
            agregacao=AgregacaoTemporal.HORARIA,
        )
        self.assertEqual(referencia.inicio.utcoffset().total_seconds(), 0)

    def test_referencia_horaria_naive_rejeitada(self):
        with self.assertRaises(ValidationError):
            ReferenciaTemporal(
                inicio=datetime(2026, 8, 1, 12),
                timezone="UTC",
                agregacao=AgregacaoTemporal.HORARIA,
            )

    def test_intervalo_invertido_rejeitado(self):
        with self.assertRaises(ValidationError):
            ReferenciaTemporal(
                inicio=date(2026, 8, 2),
                fim=date(2026, 8, 1),
                agregacao=AgregacaoTemporal.DIARIA,
            )


if __name__ == "__main__":
    unittest.main()
