from __future__ import annotations

import inspect
import json
import unittest
from datetime import timedelta

from pydantic import ValidationError

from backend.exposicao import (
    ClassificacaoIndice,
    EstadoPerigoApresentacao,
    EventoPerigo,
    PerigoExposicao,
    ResultadoApresentacaoExposicaoMaquinario,
    ResultadoAvaliacaoExposicaoMaquinario,
    calcular_score_exposicao_maquinario,
    comparar_scores_exposicao_90d,
    criar_apresentacao_exposicao_maquinario,
    criar_politica_agrishield_equip_v1,
)
from backend.tests.test_exposicao_avaliacao_exposicao import (
    DATA_REFERENCIA,
    criar_serie_avaliacao,
    executar as executar_avaliacao_fixture,
)
from backend.tests.test_exposicao_score_exposicao import (
    _com_indices,
    _com_perigo_insuficiente,
)
from backend.risco.modelos import FonteDado


def _avaliacao_com_score_atual(
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario,
    valores: dict[PerigoExposicao, float],
    *,
    insuficiente: PerigoExposicao | None = None,
) -> ResultadoAvaliacaoExposicaoMaquinario:
    politica = criar_politica_agrishield_equip_v1()
    validacao = _com_indices(avaliacao.validacao_atual, valores)
    if insuficiente is not None:
        validacao = _com_perigo_insuficiente(validacao, insuficiente)
    score = calcular_score_exposicao_maquinario(
        validacao,
        avaliacao.politica_composicao,
        politica,
    )
    comparacao = comparar_scores_exposicao_90d(avaliacao.score_anterior, score)
    atualizada = avaliacao.model_copy(
        update={
            "validacao_atual": validacao,
            "score_atual": score,
            "comparacao": comparacao,
            "avaliacao_publicavel": (
                avaliacao.score_anterior.score_publicavel
                and score.score_publicavel
                and comparacao.comparacao_publicavel
            ),
        }
    )
    return ResultadoAvaliacaoExposicaoMaquinario.model_validate(atualizada.model_dump())


def _avaliacao_com_eventos(
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario,
    eventos_por_perigo: dict[PerigoExposicao, tuple[EventoPerigo, ...]],
) -> ResultadoAvaliacaoExposicaoMaquinario:
    validacao = avaliacao.validacao_atual
    campos = (
        "exposicao_hidrica",
        "trafegabilidade",
        "instabilidade",
        "propagacao_fogo",
        "tempestade",
    )
    alteracoes = {}
    for campo in campos:
        resultado = getattr(validacao, campo)
        eventos = eventos_por_perigo.get(resultado.perigo, ())
        agregado = resultado.agregacao_90d.model_copy(
            update={
                "eventos": eventos,
                "quantidade_eventos": len(eventos),
                "quantidade_dias_relevantes": sum(
                    evento.quantidade_dias_relevantes for evento in eventos
                ),
                "maior_duracao_evento": max(
                    (evento.duracao_dias for evento in eventos),
                    default=0,
                ),
            }
        )
        alteracoes[campo] = resultado.model_copy(update={"agregacao_90d": agregado})
    validacao = validacao.model_copy(update=alteracoes)
    atualizada = avaliacao.model_copy(update={"validacao_atual": validacao})
    return ResultadoAvaliacaoExposicaoMaquinario.model_validate(atualizada.model_dump())


def _evento(inicio, duracao, severidade=70) -> EventoPerigo:
    return EventoPerigo(
        inicio=inicio,
        fim=inicio + timedelta(days=duracao - 1),
        duracao_dias=duracao,
        indice_maximo=severidade,
        indice_medio=severidade - 5,
        classificacao_maxima=ClassificacaoIndice.ALERTA,
        severidade_evento=severidade,
        quantidade_dias_relevantes=duracao,
    )


class BaseApresentacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.avaliacao = executar_avaliacao_fixture(
            criar_serie_avaliacao(cenario="aumento")
        )
        cls.apresentacao = criar_apresentacao_exposicao_maquinario(cls.avaliacao)


class TestTransformacaoPrincipal(BaseApresentacao):
    def test_transformacao_preserva_identidade_scores_e_comparacao(self):
        resultado = self.apresentacao
        self.assertEqual(resultado.id_fazenda, self.avaliacao.id_fazenda)
        self.assertEqual(resultado.politica_id, self.avaliacao.politica_id)
        self.assertEqual(resultado.data_referencia, DATA_REFERENCIA)
        self.assertEqual(
            resultado.fonte_meteorologica, self.avaliacao.fonte_meteorologica
        )
        self.assertEqual(resultado.score_atual, self.avaliacao.score_atual.score)
        self.assertEqual(
            resultado.classificacao_atual, self.avaliacao.score_atual.classificacao
        )
        self.assertEqual(resultado.score_anterior, self.avaliacao.score_anterior.score)
        self.assertEqual(
            resultado.classificacao_anterior,
            self.avaliacao.score_anterior.classificacao,
        )
        self.assertEqual(
            resultado.variacao_pontos, self.avaliacao.comparacao.variacao_pontos
        )
        self.assertEqual(
            resultado.variacao_percentual, self.avaliacao.comparacao.variacao_percentual
        )
        self.assertEqual(resultado.direcao_variacao, self.avaliacao.comparacao.direcao)
        self.assertEqual(
            resultado.score_publicavel, self.avaliacao.score_atual.score_publicavel
        )
        self.assertEqual(
            resultado.comparacao_publicavel,
            self.avaliacao.comparacao.comparacao_publicavel,
        )
        self.assertEqual(
            resultado.avaliacao_publicavel, self.avaliacao.avaliacao_publicavel
        )

    def test_payload_resumido_nao_expoe_features_diarias(self):
        campos = set(ResultadoApresentacaoExposicaoMaquinario.model_fields)
        self.assertNotIn("features_compartilhadas", campos)
        self.assertNotIn("validacao_atual", campos)
        self.assertNotIn("validacao_anterior", campos)

    def test_cinco_perigos_pesos_e_contribuicoes_sao_preservados(self):
        self.assertEqual(
            tuple(item.perigo for item in self.apresentacao.perigos),
            tuple(PerigoExposicao),
        )
        for resumo, contribuicao in zip(
            self.apresentacao.perigos,
            self.avaliacao.score_atual.contribuicoes,
        ):
            with self.subTest(perigo=resumo.perigo):
                self.assertEqual(resumo.indice, contribuicao.indice_perigo)
                self.assertEqual(
                    resumo.classificacao, contribuicao.classificacao_perigo
                )
                self.assertEqual(resumo.peso, contribuicao.peso)
                self.assertEqual(resumo.contribuicao, contribuicao.contribuicao)
                self.assertEqual(
                    resumo.cobertura_percentual, contribuicao.cobertura_percentual
                )

    def test_trafegabilidade_participa_normalmente_do_score(self):
        trafego = self.apresentacao.perigos[1]
        self.assertEqual(trafego.perigo, PerigoExposicao.TRAFEGABILIDADE)
        self.assertTrue(trafego.participa_score)
        self.assertEqual(trafego.peso, 0.25)
        self.assertEqual(trafego.estado, EstadoPerigoApresentacao.PARTICIPANTE_ELEGIVEL)

    def test_detalhes_preservam_componentes_das_agregacoes_oficiais(self):
        detalhes = self.apresentacao.detalhes_perigos
        self.assertIsNotNone(detalhes)
        casos = (
            (detalhes.instabilidade, self.avaliacao.validacao_atual.instabilidade),
            (detalhes.incendio, self.avaliacao.validacao_atual.propagacao_fogo),
            (detalhes.tempestades, self.avaliacao.validacao_atual.tempestade),
        )
        for detalhe, origem in casos:
            with self.subTest(perigo=detalhe.perigo):
                agregado = origem.agregacao_90d
                apresentado = detalhe.agregacao_90d
                self.assertEqual(apresentado.severidade, agregado.severidade_score)
                self.assertEqual(apresentado.frequencia, agregado.frequencia_score)
                self.assertEqual(apresentado.duracao, agregado.duracao_score)
                self.assertEqual(apresentado.recorrencia, agregado.recorrencia_score)
                self.assertEqual(apresentado.indice_agregado, agregado.indice_agregado)
                self.assertEqual(
                    apresentado.classificacao, agregado.classificacao_agregada
                )

    def test_incendio_expoe_maior_dia_e_proveniencia_sem_recalculo(self):
        origem = max(
            (
                item
                for item in self.avaliacao.validacao_atual.propagacao_fogo.propagacao_fogo_diaria
                if item.indice_exposicao_propagacao_fogo is not None
            ),
            key=lambda item: (item.indice_exposicao_propagacao_fogo, item.data),
        )
        detalhe = self.apresentacao.detalhes_perigos.incendio
        dia = detalhe.dia_maior_indice
        self.assertEqual(dia.data, origem.data)
        self.assertEqual(dia.temperatura_maxima_c, origem.temperatura_maxima_c)
        self.assertEqual(
            dia.umidade_relativa_media_pct, origem.umidade_relativa_media_pct
        )
        self.assertEqual(
            dia.velocidade_vento_media_m_s, origem.velocidade_vento_media_m_s
        )
        self.assertEqual(
            dia.dias_desde_ultima_chuva, origem.dias_desde_ultima_chuva_relevante
        )
        self.assertEqual(dia.componente_temperatura, origem.componente_temperatura)
        self.assertEqual(dia.componente_baixa_umidade, origem.componente_baixa_umidade)
        self.assertEqual(dia.componente_vento, origem.componente_vento)
        self.assertEqual(dia.indice_base, origem.indice_fogo_base)
        self.assertEqual(dia.multiplicador_secura, origem.multiplicador_secura)
        self.assertEqual(dia.indice_diario, origem.indice_exposicao_propagacao_fogo)
        self.assertEqual(detalhe.proveniencia.parametro_vento, "WS2M")
        self.assertEqual(detalhe.proveniencia.altura_vento_m, 2)

    def test_instabilidade_expoe_nucleo_interno_e_somente_declividade_srtm(self):
        origem = max(
            (
                item
                for item in self.avaliacao.validacao_atual.instabilidade.instabilidades_diarias
                if item.indice_exposicao_instabilidade is not None
            ),
            key=lambda item: (item.indice_exposicao_instabilidade, item.data),
        )
        detalhe = self.apresentacao.detalhes_perigos.instabilidade
        dia = detalhe.dia_maior_indice
        self.assertEqual(dia.indice_diario, origem.indice_exposicao_instabilidade)
        self.assertEqual(
            dia.condicao_hidrica_meteorologica,
            origem.indice_condicao_hidrica,
        )
        self.assertEqual(dia.fator_ativacao, origem.fator_ativacao_hidrica)
        self.assertEqual(detalhe.fonte_declividade.value, "SRTM")
        self.assertFalse(detalhe.posicao_topografica_participa_formula)
        self.assertNotIn("MERIT", json.dumps(detalhe.model_dump(mode="json")))

    def test_tempestades_expoe_maior_dia_e_vento_medio(self):
        origem = max(
            (
                item
                for item in self.avaliacao.validacao_atual.tempestade.tempestades_diarias
                if item.indice_exposicao_tempestade is not None
            ),
            key=lambda item: (item.indice_exposicao_tempestade, item.data),
        )
        detalhe = self.apresentacao.detalhes_perigos.tempestades
        dia = detalhe.dia_maior_indice
        self.assertEqual(dia.data, origem.data)
        self.assertEqual(
            dia.velocidade_vento_media_m_s, origem.velocidade_vento_media_m_s
        )
        self.assertEqual(dia.precipitacao_diaria_mm, origem.precipitacao_d0)
        self.assertEqual(dia.componente_vento, origem.componente_vento)
        self.assertEqual(dia.componente_chuva, origem.componente_chuva)
        self.assertEqual(dia.indice_vento, origem.indice_vento)
        self.assertEqual(
            dia.fator_combinado_vento_chuva,
            origem.fator_amplificacao_chuva,
        )
        self.assertEqual(dia.indice_diario, origem.indice_exposicao_tempestade)

    def test_trafegabilidade_expoe_maior_dia_pesos_limiar_e_proveniencia_sem_recalculo(
        self,
    ):
        origem_resultado = self.avaliacao.validacao_atual.trafegabilidade
        origem = max(
            (
                item
                for item in origem_resultado.trafegabilidade_diaria
                if item.indice_trafegabilidade is not None
            ),
            key=lambda item: (item.indice_trafegabilidade, item.data),
        )
        detalhe = self.apresentacao.detalhes_perigos.trafegabilidade
        resumo = next(
            item
            for item in self.apresentacao.perigos
            if item.perigo == PerigoExposicao.TRAFEGABILIDADE
        )
        dia = detalhe.dia_maior_indice

        # dia de pico e dados utilizados
        self.assertEqual(dia.data, origem.data)
        self.assertEqual(dia.precipitacao_d0, origem.precipitacao_d0)
        self.assertEqual(dia.acumulado_3d, origem.acumulado_3d)
        self.assertEqual(
            dia.dias_desde_ultima_chuva_relevante,
            origem.dias_desde_ultima_chuva_relevante,
        )
        # componentes intermediarios
        self.assertEqual(dia.componente_dia, origem.componente_dia)
        self.assertEqual(dia.componente_acumulado, origem.componente_acumulado)
        self.assertEqual(dia.componente_recuperacao, origem.componente_recuperacao)
        self.assertEqual(dia.indice_diario, origem.indice_trafegabilidade)

        # pesos e limiar efetivamente usados (nao hardcoded)
        parametros = origem_resultado.parametros_trafegabilidade
        self.assertEqual(detalhe.peso_dia, parametros.peso_dia)
        self.assertEqual(detalhe.peso_acumulado, parametros.peso_acumulado)
        self.assertEqual(detalhe.peso_recuperacao, parametros.peso_recuperacao)
        self.assertEqual(detalhe.limiar_relevancia, parametros.limiar_relevancia)

        # agregacao 90d, contribuicao e peso no indice batem com o resumo oficial
        self.assertEqual(detalhe.agregacao_90d.indice_agregado, resumo.indice)
        self.assertEqual(detalhe.agregacao_90d.classificacao, resumo.classificacao)
        self.assertEqual(
            detalhe.agregacao_90d.quantidade_dias_relevantes,
            origem_resultado.agregacao_90d.quantidade_dias_relevantes,
        )
        self.assertEqual(
            detalhe.agregacao_90d.quantidade_eventos,
            origem_resultado.agregacao_90d.quantidade_eventos,
        )
        self.assertEqual(
            detalhe.agregacao_90d.maior_duracao_evento,
            origem_resultado.agregacao_90d.maior_duracao_evento,
        )
        self.assertEqual(
            detalhe.agregacao_90d.cobertura_percentual,
            origem_resultado.agregacao_90d.cobertura_percentual,
        )

        # proveniencia: mesma fonte meteorologica da avaliacao (sem vento, pois
        # Trafegabilidade nao usa vento)
        self.assertEqual(
            detalhe.proveniencia.fonte_meteorologica,
            self.avaliacao.validacao_atual.fonte_meteorologica,
        )
        self.assertEqual(
            detalhe.proveniencia.dataset_meteorologico,
            self.avaliacao.validacao_atual.dataset,
        )
        self.assertIsNone(detalhe.proveniencia.parametro_vento)

        # metodologia e aviso experimental
        self.assertEqual(detalhe.metodologia, origem_resultado.metodologia)
        self.assertEqual(detalhe.aviso_metodologia, origem_resultado.aviso_metodologia)
        self.assertIn("experimental", detalhe.aviso_metodologia.lower())

    def test_proveniencia_open_meteo_preserva_vento_medio_a_dez_metros(self):
        avaliacao = executar_avaliacao_fixture(
            criar_serie_avaliacao(
                cenario="aumento",
                fonte=FonteDado.OPEN_METEO,
            )
        )
        detalhes = criar_apresentacao_exposicao_maquinario(avaliacao).detalhes_perigos
        for detalhe in (detalhes.incendio, detalhes.tempestades):
            with self.subTest(perigo=detalhe.perigo):
                self.assertEqual(
                    detalhe.proveniencia.fonte_meteorologica,
                    FonteDado.OPEN_METEO,
                )
                self.assertEqual(
                    detalhe.proveniencia.parametro_vento,
                    "wind_speed_10m_mean",
                )
                self.assertEqual(detalhe.proveniencia.altura_vento_m, 10)

    def test_dia_destaque_ausente_permanece_none_sem_fabricar_zero(self):
        base = criar_serie_avaliacao(cenario="aumento")
        avaliacao = executar_avaliacao_fixture(
            criar_serie_avaliacao(
                cenario="aumento",
                gaps_vento={item.data for item in base.registros},
            )
        )
        detalhes = criar_apresentacao_exposicao_maquinario(avaliacao).detalhes_perigos
        for detalhe in (detalhes.incendio, detalhes.tempestades):
            with self.subTest(perigo=detalhe.perigo):
                self.assertIsNone(detalhe.dia_maior_indice)
                self.assertIsNone(detalhe.agregacao_90d.indice_agregado)
                self.assertIsNone(detalhe.agregacao_90d.classificacao)


class TestDominancia(BaseApresentacao):
    def test_dominante_usa_contribuicao_e_nao_maior_indice_bruto(self):
        valores = {
            PerigoExposicao.EXPOSICAO_HIDRICA: 75,
            PerigoExposicao.TRAFEGABILIDADE: 10,
            PerigoExposicao.INSTABILIDADE: 100,
            PerigoExposicao.INCENDIO: 30,
            PerigoExposicao.TEMPESTADES: 30,
        }
        avaliacao = _avaliacao_com_score_atual(self.avaliacao, valores)
        resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
        self.assertGreater(
            resultado.perigos[2].indice,
            resultado.perigos[0].indice,
        )
        self.assertGreater(
            resultado.perigos[0].contribuicao,
            resultado.perigos[2].contribuicao,
        )
        self.assertEqual(resultado.perigo_dominante, PerigoExposicao.EXPOSICAO_HIDRICA)
        self.assertEqual(
            resultado.perigos_dominantes, (PerigoExposicao.EXPOSICAO_HIDRICA,)
        )

    def test_empate_preserva_todos_sem_desempate_arbitrario(self):
        valores = {
            PerigoExposicao.EXPOSICAO_HIDRICA: 50,
            PerigoExposicao.TRAFEGABILIDADE: 10,
            PerigoExposicao.INSTABILIDADE: 75,
            PerigoExposicao.INCENDIO: 20,
            PerigoExposicao.TEMPESTADES: 20,
        }
        resultado = criar_apresentacao_exposicao_maquinario(
            _avaliacao_com_score_atual(self.avaliacao, valores)
        )
        self.assertEqual(
            resultado.perigos_dominantes,
            (
                PerigoExposicao.EXPOSICAO_HIDRICA,
                PerigoExposicao.INSTABILIDADE,
            ),
        )
        self.assertIsNone(resultado.perigo_dominante)

    def test_score_indisponivel_nao_declara_dominante_mas_preserva_perigos(self):
        valores = {perigo: 60.0 for perigo in PerigoExposicao}
        avaliacao = _avaliacao_com_score_atual(
            self.avaliacao,
            valores,
            insuficiente=PerigoExposicao.INCENDIO,
        )
        resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
        self.assertFalse(resultado.score_publicavel)
        self.assertIsNone(resultado.score_atual)
        self.assertIsNone(resultado.classificacao_atual)
        self.assertEqual(resultado.perigos_dominantes, ())
        self.assertIsNone(resultado.perigo_dominante)
        self.assertEqual(len(resultado.perigos), 5)
        fogo = resultado.perigos[3]
        self.assertIsNotNone(fogo.indice)
        self.assertFalse(fogo.qualidade_suficiente)
        self.assertEqual(fogo.estado, EstadoPerigoApresentacao.DADO_INSUFICIENTE)


class TestTimeline(BaseApresentacao):
    def test_timeline_usa_eventos_existentes_em_ordem_e_inclui_trafegabilidade(self):
        esperado = sum(
            len(resultado.agregacao_90d.eventos)
            for resultado in (
                self.avaliacao.validacao_atual.exposicao_hidrica,
                self.avaliacao.validacao_atual.trafegabilidade,
                self.avaliacao.validacao_atual.instabilidade,
                self.avaliacao.validacao_atual.propagacao_fogo,
                self.avaliacao.validacao_atual.tempestade,
            )
        )
        self.assertEqual(len(self.apresentacao.timeline_eventos), esperado)
        self.assertIn(
            PerigoExposicao.TRAFEGABILIDADE,
            tuple(item.perigo for item in self.apresentacao.timeline_eventos),
        )
        self.assertEqual(
            tuple(item.perigo for item in self.apresentacao.timeline_eventos[:5]),
            tuple(PerigoExposicao),
        )

    def test_eventos_consecutivos_sobrepostos_e_gaps_sao_preservados(self):
        inicio = self.avaliacao.janela_atual.inicio
        eventos = {
            PerigoExposicao.EXPOSICAO_HIDRICA: (_evento(inicio, 2),),
            PerigoExposicao.TRAFEGABILIDADE: (_evento(inicio + timedelta(days=2), 1),),
            PerigoExposicao.INSTABILIDADE: (_evento(inicio, 4),),
            PerigoExposicao.INCENDIO: (_evento(inicio + timedelta(days=6), 2),),
        }
        avaliacao = _avaliacao_com_eventos(self.avaliacao, eventos)
        resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
        self.assertEqual(len(resultado.timeline_eventos), 4)
        self.assertEqual(
            tuple(item.perigo for item in resultado.timeline_eventos),
            (
                PerigoExposicao.EXPOSICAO_HIDRICA,
                PerigoExposicao.INSTABILIDADE,
                PerigoExposicao.TRAFEGABILIDADE,
                PerigoExposicao.INCENDIO,
            ),
        )
        self.assertEqual(
            resultado.timeline_eventos[0].inicio, resultado.timeline_eventos[1].inicio
        )
        self.assertEqual(
            resultado.timeline_eventos[0].fim + timedelta(days=1),
            resultado.timeline_eventos[2].inicio,
        )
        self.assertGreater(
            resultado.timeline_eventos[3].inicio,
            resultado.timeline_eventos[2].fim + timedelta(days=1),
        )


class TestTimelineTrafegabilidade(unittest.TestCase):
    """Complementa TestTimeline: efeito do limiar_relevancia especifico de
    Trafegabilidade na apresentacao final (card + timeline), sem afetar os
    demais quatro perigos."""

    @staticmethod
    def _apresentacao_com_limiar(limiar: float):
        from backend.exposicao.politica import ParametrosTrafegabilidade

        avaliacao = executar_avaliacao_fixture(criar_serie_avaliacao(cenario="aumento"))
        politica_base = (
            avaliacao.validacao_atual.trafegabilidade.parametros_trafegabilidade
        )
        # Recalcula a validacao atual/anterior com um limiar diferente,
        # reaproveitando o motor oficial (nao recalcula nada no teste).
        from backend.exposicao.perigo_trafegabilidade import (
            calcular_trafegabilidade_desfavoravel,
        )
        from backend.exposicao.politica import criar_politica_agrishield_equip_v1

        politica = criar_politica_agrishield_equip_v1().model_copy(
            update={
                "parametros_trafegabilidade": ParametrosTrafegabilidade(
                    peso_dia=politica_base.peso_dia,
                    peso_acumulado=politica_base.peso_acumulado,
                    peso_recuperacao=politica_base.peso_recuperacao,
                    limiar_relevancia=limiar,
                )
            }
        )
        nova_trafegabilidade_atual = calcular_trafegabilidade_desfavoravel(
            avaliacao.features_compartilhadas,
            politica,
            janela_alvo=avaliacao.validacao_atual.janela,
        )
        validacao_atual = avaliacao.validacao_atual.model_copy(
            update={"trafegabilidade": nova_trafegabilidade_atual}
        )
        avaliacao_alterada = avaliacao.model_copy(
            update={"validacao_atual": validacao_atual}
        )
        return (
            criar_apresentacao_exposicao_maquinario(avaliacao_alterada),
            nova_trafegabilidade_atual,
        )

    def test_mudar_limiar_pode_mudar_eventos_de_trafegabilidade_na_timeline(self):
        apresentacao_25, resultado_25 = self._apresentacao_com_limiar(25)
        apresentacao_5, resultado_5 = self._apresentacao_com_limiar(5)

        eventos_25 = tuple(
            item
            for item in apresentacao_25.timeline_eventos
            if item.perigo == PerigoExposicao.TRAFEGABILIDADE
        )
        eventos_5 = tuple(
            item
            for item in apresentacao_5.timeline_eventos
            if item.perigo == PerigoExposicao.TRAFEGABILIDADE
        )
        self.assertEqual(len(eventos_25), resultado_25.agregacao_90d.quantidade_eventos)
        self.assertEqual(len(eventos_5), resultado_5.agregacao_90d.quantidade_eventos)
        # limiar mais baixo nunca gera menos dias relevantes/eventos que o mais alto
        self.assertGreaterEqual(
            resultado_5.agregacao_90d.quantidade_dias_relevantes,
            resultado_25.agregacao_90d.quantidade_dias_relevantes,
        )

    def test_mudar_limiar_nao_muda_indices_diarios_de_trafegabilidade(self):
        _, resultado_25 = self._apresentacao_com_limiar(25)
        _, resultado_5 = self._apresentacao_com_limiar(5)
        indices_25 = tuple(i.indice for i in resultado_25.indices_diarios.indices)
        indices_5 = tuple(i.indice for i in resultado_5.indices_diarios.indices)
        self.assertEqual(indices_25, indices_5)
        classes_25 = tuple(
            i.classificacao for i in resultado_25.indices_diarios.indices
        )
        classes_5 = tuple(i.classificacao for i in resultado_5.indices_diarios.indices)
        self.assertEqual(classes_25, classes_5)

    def test_mudar_limiar_de_trafegabilidade_nao_altera_timeline_dos_outros_perigos(
        self,
    ):
        apresentacao_25, _ = self._apresentacao_com_limiar(25)
        apresentacao_5, _ = self._apresentacao_com_limiar(5)
        outros_25 = tuple(
            item
            for item in apresentacao_25.timeline_eventos
            if item.perigo != PerigoExposicao.TRAFEGABILIDADE
        )
        outros_5 = tuple(
            item
            for item in apresentacao_5.timeline_eventos
            if item.perigo != PerigoExposicao.TRAFEGABILIDADE
        )
        self.assertEqual(outros_25, outros_5)

    def test_periodo_sem_dias_relevantes_gera_timeline_sem_eventos_e_sem_erro(self):
        apresentacao, resultado = self._apresentacao_com_limiar(100)
        eventos_trafegabilidade = tuple(
            item
            for item in apresentacao.timeline_eventos
            if item.perigo == PerigoExposicao.TRAFEGABILIDADE
        )
        self.assertEqual(
            len(eventos_trafegabilidade), resultado.agregacao_90d.quantidade_eventos
        )


class TestQualidadeAvisosEContrato(BaseApresentacao):
    def test_qualidade_preserva_coberturas_warmup_e_resume_gaps(self):
        inicio_atual = DATA_REFERENCIA - timedelta(days=89)
        gaps = {inicio_atual + timedelta(days=indice) for indice in range(5)}
        avaliacao = executar_avaliacao_fixture(criar_serie_avaliacao(gaps_vento=gaps))
        resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
        qualidade = resultado.qualidade_dados
        self.assertEqual(len(qualidade.coberturas_por_perigo), 5)
        self.assertEqual(qualidade.warmup_completo, avaliacao.warmup_completo)
        self.assertEqual(
            qualidade.dias_contexto_esperados, avaliacao.dias_contexto_esperados
        )
        self.assertEqual(
            qualidade.dias_contexto_disponiveis, avaliacao.dias_contexto_disponiveis
        )
        self.assertEqual(
            qualidade.quantidade_gaps, len(avaliacao.qualidade_aquisicao.gaps)
        )
        self.assertEqual(qualidade.dias_com_dados_ausentes, 5)
        self.assertNotIn("confidence", _campos_resumo(qualidade))

    def test_avisos_sao_preservados_deduplicados_e_ordenados(self):
        aviso = self.avaliacao.avisos_metodologicos[0]
        avaliacao = self.avaliacao.model_copy(
            update={
                "avisos_metodologicos": (
                    aviso,
                    *reversed(self.avaliacao.avisos_metodologicos),
                    aviso,
                )
            }
        )
        resultado = criar_apresentacao_exposicao_maquinario(avaliacao)
        self.assertEqual(
            resultado.avisos_metodologicos,
            tuple(sorted(set(avaliacao.avisos_metodologicos))),
        )

    def test_disclaimers_sao_preservados(self):
        self.assertEqual(
            self.apresentacao.disclaimer, self.avaliacao.score_atual.disclaimer
        )
        self.assertEqual(
            self.apresentacao.disclaimer_comparacao,
            self.avaliacao.comparacao.disclaimer,
        )

    def test_numeros_none_e_serializacao_sao_coerentes(self):
        self.assertIsInstance(self.apresentacao.score_atual, float)
        self.assertNotIsInstance(self.apresentacao.score_atual, str)
        indisponivel = criar_apresentacao_exposicao_maquinario(
            _avaliacao_com_score_atual(
                self.avaliacao,
                {perigo: 60.0 for perigo in PerigoExposicao},
                insuficiente=PerigoExposicao.TEMPESTADES,
            )
        )
        self.assertIsNone(indisponivel.score_atual)
        serializado = self.apresentacao.model_dump(mode="json")
        json.dumps(serializado)
        self.assertEqual(
            ResultadoApresentacaoExposicaoMaquinario.model_validate(serializado),
            self.apresentacao,
        )

    def test_determinismo_input_nao_mutado_e_imutabilidade(self):
        antes = self.avaliacao.model_dump()
        primeiro = criar_apresentacao_exposicao_maquinario(self.avaliacao)
        segundo = criar_apresentacao_exposicao_maquinario(self.avaliacao)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(self.avaliacao.model_dump(), antes)
        with self.assertRaises(ValidationError):
            primeiro.score_atual = 10

    def test_transformacao_nao_executa_formulas_io_ou_thresholds(self):
        from backend.exposicao import apresentacao_exposicao

        codigo = inspect.getsource(apresentacao_exposicao).lower()
        for termo in (
            "validar_cinco_perigos",
            "calcular_score_exposicao_maquinario",
            "comparar_scores_exposicao_90d",
            "agrupar_eventos",
            "classificar_indice",
            "inicio_atencao",
            "inicio_alerta",
            "inicio_critico",
            "requests",
            "http://",
            "https://",
            "fastapi",
            "supabase",
            "calcular_propagacao_fogo_diaria",
            "calcular_instabilidade_diaria",
            "calcular_tempestade_diaria",
            "normalizar_vento_fogo",
            "normalizar_declividade",
            "normalizar_chuva_tempestade",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


def _campos_resumo(modelo) -> set[str]:
    return set(type(modelo).model_fields)


if __name__ == "__main__":
    unittest.main()
