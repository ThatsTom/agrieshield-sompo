"""Teste de regressao critico: com todos os parametros em seus valores padrao,
o pipeline com overrides carregados do repositorio deve ser matematicamente
identico ao pipeline anterior a parametrizacao (politica crua, sem overrides).

Cobre exatamente o que a tarefa exige: indices diarios, agregacao de 90 dias,
score e classificacao. Se este teste falhar, a parametrizacao alterou o
comportamento do MVP com os defaults - o que nao pode acontecer.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.servico_avaliacao_exposicao import ServicoAvaliacaoExposicao
from backend.app.servico_parametros_score import carregar_overrides_parametros_modelo
from backend.etl import repositorio_parametros_score as repositorio
from backend.exposicao import (
    calcular_score_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
    criar_politica_composicao_score,
    validar_cinco_perigos,
)
from backend.tests.test_exposicao_validacao_integrada import (
    CENARIOS,
    criar_features,
    criar_geo,
)


def _aplicar_overrides(politica, overrides):
    return politica.model_copy(
        update={
            "pesos_perigos": overrides.pesos_perigos,
            "parametros_territoriais_hidricos": overrides.parametros_territoriais_hidricos,
            "parametros_instabilidade": overrides.parametros_instabilidade,
            "parametros_propagacao_fogo": overrides.parametros_propagacao_fogo,
            "parametros_tempestade": overrides.parametros_tempestade,
            "parametros_trafegabilidade": overrides.parametros_trafegabilidade,
        }
    )


class TestEquivalenciaComParametrosPadrao(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        pasta = Path(self.tempdir.name)
        arquivo = pasta / "parametros_score.csv"
        self.patch_pasta = patch.object(repositorio, "PASTA_DADOS", pasta)
        self.patch_arquivo = patch.object(
            repositorio, "ARQUIVO_PARAMETROS_SCORE", arquivo
        )
        self.patch_pasta.start()
        self.patch_arquivo.start()
        self.addCleanup(self.patch_pasta.stop)
        self.addCleanup(self.patch_arquivo.stop)

        self.politica_base = criar_politica_agrishield_equip_v1()
        overrides = carregar_overrides_parametros_modelo()
        self.politica_com_overrides = _aplicar_overrides(self.politica_base, overrides)

    def test_politica_com_overrides_padrao_e_byte_a_byte_identica_a_politica_crua(self):
        self.assertEqual(self.politica_base, self.politica_com_overrides)

    def test_indices_diarios_agregacao_score_e_classificacao_sao_identicos(self):
        for nome_cenario, definicao in CENARIOS.items():
            with self.subTest(cenario=nome_cenario):
                features = criar_features(nome_cenario)
                geo = criar_geo(definicao["declividade"])

                resultado_base = validar_cinco_perigos(
                    features, geo, self.politica_base
                )
                resultado_overrides = validar_cinco_perigos(
                    features, geo, self.politica_com_overrides
                )
                self.assertEqual(
                    resultado_base.model_dump(), resultado_overrides.model_dump()
                )

                composicao_base = criar_politica_composicao_score(self.politica_base)
                composicao_overrides = criar_politica_composicao_score(
                    self.politica_com_overrides
                )
                score_base = calcular_score_exposicao_maquinario(
                    resultado_base, composicao_base, self.politica_base
                )
                score_overrides = calcular_score_exposicao_maquinario(
                    resultado_overrides,
                    composicao_overrides,
                    self.politica_com_overrides,
                )
                self.assertEqual(score_base.model_dump(), score_overrides.model_dump())
                self.assertEqual(score_base.score, score_overrides.score)
                self.assertEqual(
                    score_base.classificacao, score_overrides.classificacao
                )

    def test_indice_hidrico_territorial_padrao_e_identico(self):
        """Cobre especificamente o T3 (proximidade/area/posicao), fora do escopo
        generico de validar_cinco_perigos usado acima por outra rota interna."""
        features = criar_features("relevo_chuva")
        geo = criar_geo(CENARIOS["relevo_chuva"]["declividade"])
        resultado_base = validar_cinco_perigos(features, geo, self.politica_base)
        resultado_overrides = validar_cinco_perigos(
            features, geo, self.politica_com_overrides
        )
        self.assertEqual(
            resultado_base.exposicao_hidrica.suscetibilidade_territorial,
            resultado_overrides.exposicao_hidrica.suscetibilidade_territorial,
        )
        self.assertEqual(
            resultado_base.exposicao_hidrica.detalhes_diarios,
            resultado_overrides.exposicao_hidrica.detalhes_diarios,
        )

    def test_servico_de_avaliacao_com_provedor_persistido_e_sem_provedor_produzem_mesmo_dto(
        self,
    ):
        """Fim a fim: o provedor real (lendo o CSV recem-criado com defaults)
        nao pode alterar o DTO publicado em relacao a nao ter provedor algum."""
        from backend.tests.test_servico_avaliacao_exposicao import (
            DATA_REFERENCIA,
            ID_FAZENDA,
            ClienteFalso,
            ProvedorFalso,
            RepositorioFalso,
        )
        from backend.app.provedor_pesos_perigos_persistido import (
            ProvedorPesosPerigosPersistido,
        )
        from backend.risco.modelos import FonteDado

        def _construir(provedor_pesos):
            return ServicoAvaliacaoExposicao(
                repositorio_fazendas=RepositorioFalso(),
                clientes_meteorologicos={
                    FonteDado.NASA_POWER: ClienteFalso(),
                    FonteDado.OPEN_METEO: ClienteFalso(fonte=FonteDado.OPEN_METEO),
                },
                provedor_contexto_territorial=ProvedorFalso(),
                provedor_pesos_perigos=provedor_pesos,
            )

        sem_provedor = _construir(None)
        com_provedor = _construir(ProvedorPesosPerigosPersistido())

        resultado_sem = sem_provedor.avaliar_exposicao_fazenda(
            ID_FAZENDA, DATA_REFERENCIA
        )
        resultado_com = com_provedor.avaliar_exposicao_fazenda(
            ID_FAZENDA, DATA_REFERENCIA
        )
        self.assertEqual(resultado_sem, resultado_com)


if __name__ == "__main__":
    unittest.main()
