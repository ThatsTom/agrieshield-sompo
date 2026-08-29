from __future__ import annotations

import inspect
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from backend.app.servico_avaliacao_exposicao import (
    CodigoErroAvaliacaoExposicao,
    ContextoTerritorialIndisponivel,
    CoordenadasIndisponiveis,
    FazendaNaoEncontrada,
    FonteMeteorologicaIndisponivel,
    PeriodoHistoricoInvalido,
    RepositorioFazendasPorFuncao,
    ServicoAvaliacaoExposicao,
    avaliar_exposicao_fazenda,
)
from backend.exposicao import (
    AVISO_WARMUP_INCOMPLETO,
    JanelaHistorica,
    PerigoExposicao,
    ResultadoApresentacaoExposicaoMaquinario,
    SerieHistoricaFonte,
    criar_politica_agrishield_equip_v1,
)
from backend.app.servico_parametros_score import OverridesParametrosModelo
from backend.exposicao.politica import PesosPerigos
from backend.risco.modelos import FonteDado, ReferenciaEspacial
from backend.tests.test_exposicao_avaliacao_exposicao import (
    DATA_REFERENCIA,
    criar_serie_avaliacao,
)
from backend.tests.test_exposicao_validacao_integrada import criar_geo


ID_FAZENDA = "fazenda-teste"
FAZENDA = {
    "id_fazenda": ID_FAZENDA,
    "nome_fazenda": "Fazenda Teste",
    "latitude": "-12.545",
    "longitude": "-55.721",
}


class RepositorioFalso:
    def __init__(self, fazenda=FAZENDA, erro: Exception | None = None):
        self.fazenda = fazenda
        self.erro = erro
        self.chamadas: list[str] = []

    def buscar(self, id_fazenda: str):
        self.chamadas.append(id_fazenda)
        if self.erro is not None:
            raise self.erro
        return self.fazenda


class ClienteFalso:
    def __init__(
        self,
        *,
        fonte: FonteDado = FonteDado.NASA_POWER,
        dias_serie: int = 187,
        datas_sem_registro: set[date] | None = None,
        erro: Exception | None = None,
        serie: object | None = None,
    ):
        self.fonte = fonte
        self.dias_serie = dias_serie
        self.datas_sem_registro = datas_sem_registro
        self.erro = erro
        self.serie = serie
        self.chamadas: list[dict[str, object]] = []

    def consultar(
        self,
        latitude: float,
        longitude: float,
        janela: JanelaHistorica,
        *,
        id_fazenda: str | None = None,
    ) -> SerieHistoricaFonte:
        self.chamadas.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "janela": janela,
                "id_fazenda": id_fazenda,
            }
        )
        if self.erro is not None:
            raise self.erro
        if self.serie is not None:
            return self.serie  # type: ignore[return-value]
        return criar_serie_avaliacao(
            dias=self.dias_serie,
            fonte=self.fonte,
            datas_sem_registro=self.datas_sem_registro,
        )


class ProvedorFalso:
    def __init__(self, contexto=None, erro: Exception | None = None):
        self.contexto = contexto if contexto is not None else criar_geo(20)
        self.erro = erro
        self.chamadas: list[dict[str, object]] = []

    def obter(self, *, id_fazenda: str, latitude: float, longitude: float):
        self.chamadas.append(
            {
                "id_fazenda": id_fazenda,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        if self.erro is not None:
            raise self.erro
        return self.contexto


def _overrides_padrao() -> OverridesParametrosModelo:
    base = criar_politica_agrishield_equip_v1()
    return OverridesParametrosModelo(
        pesos_perigos=base.pesos_perigos,
        parametros_territoriais_hidricos=base.parametros_territoriais_hidricos,
        parametros_instabilidade=base.parametros_instabilidade,
        parametros_propagacao_fogo=base.parametros_propagacao_fogo,
        parametros_tempestade=base.parametros_tempestade,
        parametros_trafegabilidade=base.parametros_trafegabilidade,
    )


class ProvedorPesosFalso:
    def __init__(self, overrides: OverridesParametrosModelo | None = None):
        self.overrides = overrides if overrides is not None else _overrides_padrao()
        self.chamadas = 0

    def obter(self) -> OverridesParametrosModelo:
        self.chamadas += 1
        return self.overrides


def criar_servico(
    *,
    repositorio=None,
    nasa=None,
    open_meteo=None,
    provedor=None,
    provedor_pesos=None,
) -> tuple[
    ServicoAvaliacaoExposicao,
    RepositorioFalso,
    ClienteFalso,
    ClienteFalso,
    ProvedorFalso,
]:
    repositorio = repositorio if repositorio is not None else RepositorioFalso()
    nasa = nasa if nasa is not None else ClienteFalso()
    open_meteo = (
        open_meteo
        if open_meteo is not None
        else ClienteFalso(fonte=FonteDado.OPEN_METEO)
    )
    provedor = provedor if provedor is not None else ProvedorFalso()
    servico = ServicoAvaliacaoExposicao(
        repositorio_fazendas=repositorio,
        clientes_meteorologicos={
            FonteDado.NASA_POWER: nasa,
            FonteDado.OPEN_METEO: open_meteo,
        },
        provedor_contexto_territorial=provedor,
        provedor_pesos_perigos=provedor_pesos,
    )
    return servico, repositorio, nasa, open_meteo, provedor


class TestCaminhoFeliz(unittest.TestCase):
    def test_executa_fluxo_completo_e_retorna_dto_8b(self):
        servico, repositorio, nasa, open_meteo, provedor = criar_servico()

        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
        )

        self.assertIsInstance(resultado, ResultadoApresentacaoExposicaoMaquinario)
        self.assertEqual(resultado.id_fazenda, ID_FAZENDA)
        self.assertEqual(
            resultado.politica_id,
            criar_politica_agrishield_equip_v1().id_politica,
        )
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.NASA_POWER)
        self.assertEqual(resultado.data_referencia, DATA_REFERENCIA)
        self.assertEqual(
            tuple(item.perigo for item in resultado.perigos), tuple(PerigoExposicao)
        )
        self.assertEqual(len(resultado.perigos), 5)
        self.assertTrue(resultado.score_publicavel)
        self.assertTrue(resultado.comparacao_publicavel)
        self.assertTrue(resultado.qualidade_dados.warmup_completo)
        self.assertIsInstance(resultado.timeline_eventos, tuple)
        self.assertEqual(resultado.fazenda.nome, "Fazenda Teste")
        self.assertEqual(resultado.contexto_territorial.declividade_media_graus, 20)
        self.assertEqual(
            resultado.contexto_territorial.posicao_topografica_relativa_m, -2
        )
        self.assertEqual(resultado.contexto_territorial.distancia_drenagem_m, 2000)
        self.assertEqual(resultado.contexto_territorial.area_montante_km2, 850)
        fontes = {item.fonte: item for item in resultado.fontes_avaliacao}
        self.assertTrue(fontes["NASA_POWER"].contribui_score)
        self.assertEqual(fontes["NASA_POWER"].status, "USADA")
        self.assertEqual(fontes["OPEN_METEO"].status, "DISPONIVEL")
        self.assertEqual(fontes["OPEN_METEO"].categoria, "METEOROLOGIA")
        self.assertFalse(fontes["OPEN_METEO"].contribui_score)
        self.assertIn("Não utilizada nesta avaliação", fontes["OPEN_METEO"].descricao)
        self.assertTrue(fontes["SRTM"].contribui_score)
        self.assertEqual(fontes["MERIT_HYDRO"].status, "USADA")
        self.assertTrue(fontes["MERIT_HYDRO"].contribui_score)
        self.assertIn("Exposição Hídrica", fontes["MERIT_HYDRO"].indicadores)
        integracoes = {item.fonte: item for item in resultado.integracoes}
        self.assertFalse(integracoes["MAPBIOMAS"].contribui_score)
        self.assertFalse(integracoes["INMET"].contribui_score)
        self.assertEqual(repositorio.chamadas, [ID_FAZENDA])
        self.assertEqual(len(nasa.chamadas), 1)
        self.assertEqual(open_meteo.chamadas, [])
        self.assertEqual(len(provedor.chamadas), 1)

    def test_solicita_exatamente_d_menos_186_ate_d_zero(self):
        servico, _, nasa, _, _ = criar_servico()
        servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        janela = nasa.chamadas[0]["janela"]
        self.assertIsInstance(janela, JanelaHistorica)
        self.assertEqual(janela.inicio, DATA_REFERENCIA - timedelta(days=186))
        self.assertEqual(janela.fim, DATA_REFERENCIA)
        self.assertEqual(janela.dias_esperados, 187)
        self.assertEqual(nasa.chamadas[0]["latitude"], -12.545)
        self.assertEqual(nasa.chamadas[0]["longitude"], -55.721)

    def test_open_meteo_e_identificado_como_fonte_usada(self):
        servico, _, _, _, _ = criar_servico()
        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA, DATA_REFERENCIA, fonte=FonteDado.OPEN_METEO
        )
        fontes = {item.fonte: item for item in resultado.fontes_avaliacao}
        self.assertEqual(fontes["OPEN_METEO"].status, "USADA")
        self.assertTrue(fontes["OPEN_METEO"].contribui_score)
        self.assertEqual(fontes["NASA_POWER"].status, "DISPONIVEL")
        self.assertFalse(fontes["NASA_POWER"].contribui_score)
        self.assertIn("Não utilizada nesta avaliação", fontes["NASA_POWER"].descricao)

    def test_missing_territorial_permanece_none(self):
        servico, _, _, _, _ = criar_servico(provedor=ProvedorFalso(criar_geo(None)))
        resultado = servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        self.assertIsNone(resultado.contexto_territorial.declividade_media_graus)
        self.assertEqual(resultado.contexto_territorial.distancia_drenagem_m, 2000)

    def test_fachada_funcional_e_adaptador_do_cadastro_existente(self):
        nasa = ClienteFalso()
        provedor = ProvedorFalso()
        repositorio = RepositorioFazendasPorFuncao(
            lambda id_fazenda: FAZENDA if id_fazenda == ID_FAZENDA else None
        )
        resultado = avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
            repositorio_fazendas=repositorio,
            clientes_meteorologicos={FonteDado.NASA_POWER: nasa},
            provedor_contexto_territorial=provedor,
        )
        self.assertIsInstance(resultado, ResultadoApresentacaoExposicaoMaquinario)


class TestPeriodosEQualidade(unittest.TestCase):
    def test_serie_de_180_dias_preserva_janelas_e_avisa_warmup(self):
        servico, _, _, _, _ = criar_servico(nasa=ClienteFalso(dias_serie=180))
        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
        )
        qualidade = resultado.qualidade_dados
        self.assertEqual(qualidade.periodo_aquisicao.dias_esperados, 180)
        self.assertFalse(qualidade.warmup_completo)
        self.assertEqual(qualidade.dias_contexto_disponiveis, 0)
        self.assertIn(AVISO_WARMUP_INCOMPLETO, resultado.avisos_metodologicos)

    def test_gaps_nao_sao_rejeitados_por_cardinalidade(self):
        inicio = DATA_REFERENCIA - timedelta(days=186)
        ausentes = {
            inicio + timedelta(days=10),
            inicio + timedelta(days=80),
            inicio + timedelta(days=150),
        }
        servico, _, _, _, _ = criar_servico(
            nasa=ClienteFalso(datas_sem_registro=ausentes)
        )
        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
        )
        self.assertEqual(resultado.qualidade_dados.dias_com_dados_ausentes, 3)
        self.assertEqual(resultado.qualidade_dados.quantidade_gaps, 3)

    def test_periodo_com_menos_de_180_dias_gera_erro_tipado(self):
        servico, _, _, _, _ = criar_servico(nasa=ClienteFalso(dias_serie=179))
        with self.assertRaises(PeriodoHistoricoInvalido) as contexto:
            servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        self.assertEqual(
            contexto.exception.codigo,
            CodigoErroAvaliacaoExposicao.PERIODO_HISTORICO_INVALIDO,
        )

    def test_data_de_referencia_deve_ser_explicita_e_valida(self):
        servico, _, nasa, _, _ = criar_servico()
        with self.assertRaises(PeriodoHistoricoInvalido):
            servico.avaliar_exposicao_fazenda(ID_FAZENDA, None)  # type: ignore[arg-type]
        self.assertEqual(nasa.chamadas, [])


class TestErrosDaAplicacao(unittest.TestCase):
    def test_fazenda_inexistente_gera_erro_tipado(self):
        servico, _, nasa, _, provedor = criar_servico(
            repositorio=RepositorioFalso(fazenda=None)
        )
        with self.assertRaises(FazendaNaoEncontrada) as contexto:
            servico.avaliar_exposicao_fazenda("inexistente", DATA_REFERENCIA)
        self.assertEqual(
            contexto.exception.codigo,
            CodigoErroAvaliacaoExposicao.FAZENDA_NAO_ENCONTRADA,
        )
        self.assertEqual(nasa.chamadas, [])
        self.assertEqual(provedor.chamadas, [])

    def test_coordenadas_ausentes_invalidas_ou_zero_zero_sao_rejeitadas(self):
        casos = (
            {"id_fazenda": ID_FAZENDA},
            {"id_fazenda": ID_FAZENDA, "latitude": "x", "longitude": -55},
            {"id_fazenda": ID_FAZENDA, "latitude": 0, "longitude": 0},
        )
        for fazenda in casos:
            with self.subTest(fazenda=fazenda):
                servico, _, nasa, _, _ = criar_servico(
                    repositorio=RepositorioFalso(fazenda=fazenda)
                )
                with self.assertRaises(CoordenadasIndisponiveis) as contexto:
                    servico.avaliar_exposicao_fazenda(
                        ID_FAZENDA,
                        DATA_REFERENCIA,
                    )
                self.assertEqual(
                    contexto.exception.codigo,
                    CodigoErroAvaliacaoExposicao.COORDENADAS_INDISPONIVEIS,
                )
                self.assertEqual(nasa.chamadas, [])

    def test_falha_nasa_nao_aciona_open_meteo_provider_ou_dominio(self):
        nasa = ClienteFalso(erro=TimeoutError("detalhe externo sensivel"))
        open_meteo = ClienteFalso(fonte=FonteDado.OPEN_METEO)
        servico, _, _, _, provedor = criar_servico(
            nasa=nasa,
            open_meteo=open_meteo,
        )
        with patch(
            "backend.app.servico_avaliacao_exposicao.executar_avaliacao_exposicao_maquinario"
        ) as dominio:
            with self.assertRaises(FonteMeteorologicaIndisponivel) as contexto:
                servico.avaliar_exposicao_fazenda(
                    ID_FAZENDA,
                    DATA_REFERENCIA,
                )
        self.assertEqual(len(nasa.chamadas), 1)
        self.assertEqual(open_meteo.chamadas, [])
        self.assertEqual(provedor.chamadas, [])
        dominio.assert_not_called()
        self.assertEqual(contexto.exception.tipo_causa, "TimeoutError")
        self.assertNotIn("sensivel", str(contexto.exception))

    def test_provider_indisponivel_nao_inventa_contexto_nem_executa_dominio(self):
        provedor = ProvedorFalso(erro=RuntimeError("erro earth engine"))
        servico, _, _, _, _ = criar_servico(provedor=provedor)
        with patch(
            "backend.app.servico_avaliacao_exposicao.executar_avaliacao_exposicao_maquinario"
        ) as dominio:
            with self.assertRaises(ContextoTerritorialIndisponivel) as contexto:
                servico.avaliar_exposicao_fazenda(
                    ID_FAZENDA,
                    DATA_REFERENCIA,
                )
        dominio.assert_not_called()
        self.assertEqual(
            contexto.exception.codigo,
            CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INDISPONIVEL,
        )

    def test_contexto_de_outra_coordenada_e_rejeitado(self):
        contexto = criar_geo(20).model_copy(
            update={
                "referencia": ReferenciaEspacial(
                    latitude=-10,
                    longitude=-50,
                )
            }
        )
        servico, _, _, _, _ = criar_servico(provedor=ProvedorFalso(contexto=contexto))
        with self.assertRaises(ContextoTerritorialIndisponivel):
            servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)


class TestPesosPerigosPersistidos(unittest.TestCase):
    def test_sem_provedor_usa_os_pesos_padrao_da_politica(self):
        servico, _, _, _, _ = criar_servico()
        resultado = servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        pesos = {item.perigo: item.peso for item in resultado.perigos}
        self.assertEqual(pesos[PerigoExposicao.EXPOSICAO_HIDRICA], 0.30)
        self.assertEqual(pesos[PerigoExposicao.TRAFEGABILIDADE], 0.25)

    def test_provedor_de_pesos_e_consultado_uma_vez_por_avaliacao(self):
        provedor_pesos = ProvedorPesosFalso()
        servico, _, _, _, _ = criar_servico(provedor_pesos=provedor_pesos)
        servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        self.assertEqual(provedor_pesos.chamadas, 1)

    def test_pesos_persistidos_diferentes_alteram_a_contribuicao_e_o_score(self):
        provedor_padrao = ProvedorPesosFalso()
        servico_padrao, _, _, _, _ = criar_servico(provedor_pesos=provedor_padrao)
        resultado_padrao = servico_padrao.avaliar_exposicao_fazenda(
            ID_FAZENDA, DATA_REFERENCIA
        )

        pesos_alternativos = PesosPerigos(
            exposicao_hidrica=0.50,
            trafegabilidade=0.20,
            instabilidade=0.15,
            incendio=0.10,
            tempestades=0.05,
        )
        overrides_alternativos = _overrides_padrao().model_copy(
            update={"pesos_perigos": pesos_alternativos}
        )
        servico_alternativo, _, _, _, _ = criar_servico(
            provedor_pesos=ProvedorPesosFalso(overrides_alternativos)
        )
        resultado_alternativo = servico_alternativo.avaliar_exposicao_fazenda(
            ID_FAZENDA, DATA_REFERENCIA
        )

        peso_hidrico_padrao = next(
            item.peso
            for item in resultado_padrao.perigos
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        peso_hidrico_alternativo = next(
            item.peso
            for item in resultado_alternativo.perigos
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        self.assertEqual(peso_hidrico_padrao, 0.30)
        self.assertEqual(peso_hidrico_alternativo, 0.50)
        if resultado_padrao.score_atual is not None:
            self.assertNotEqual(
                resultado_padrao.score_atual, resultado_alternativo.score_atual
            )

    def test_outros_parametros_da_politica_permanecem_intactos(self):
        pesos_alternativos = PesosPerigos(
            exposicao_hidrica=0.50,
            trafegabilidade=0.20,
            instabilidade=0.15,
            incendio=0.10,
            tempestades=0.05,
        )
        overrides_alternativos = _overrides_padrao().model_copy(
            update={"pesos_perigos": pesos_alternativos}
        )
        servico, _, _, _, _ = criar_servico(
            provedor_pesos=ProvedorPesosFalso(overrides_alternativos)
        )
        resultado = servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)
        self.assertEqual(
            resultado.politica_id,
            criar_politica_agrishield_equip_v1().id_politica,
        )
        self.assertEqual(len(resultado.perigos), 5)


class TestSelecaoFonteEDeterminismo(unittest.TestCase):
    def test_nasa_explicita_usa_somente_nasa(self):
        servico, _, nasa, open_meteo, _ = criar_servico()
        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
            fonte=FonteDado.NASA_POWER,
        )
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.NASA_POWER)
        self.assertEqual(len(nasa.chamadas), 1)
        self.assertEqual(open_meteo.chamadas, [])

    def test_open_meteo_explicita_usa_somente_open_meteo(self):
        servico, _, nasa, open_meteo, _ = criar_servico()
        resultado = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
            fonte=FonteDado.OPEN_METEO,
        )
        self.assertEqual(resultado.fonte_meteorologica, FonteDado.OPEN_METEO)
        self.assertEqual(nasa.chamadas, [])
        self.assertEqual(len(open_meteo.chamadas), 1)

    def test_fonte_nao_registrada_falha_sem_fallback(self):
        servico = ServicoAvaliacaoExposicao(
            repositorio_fazendas=RepositorioFalso(),
            clientes_meteorologicos={},
            provedor_contexto_territorial=ProvedorFalso(),
        )
        with self.assertRaises(FonteMeteorologicaIndisponivel):
            servico.avaliar_exposicao_fazenda(ID_FAZENDA, DATA_REFERENCIA)

    def test_mesmos_inputs_e_dependencias_produzem_mesmo_resultado(self):
        servico, _, _, _, _ = criar_servico()
        primeiro = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
        )
        segundo = servico.avaliar_exposicao_fazenda(
            ID_FAZENDA,
            DATA_REFERENCIA,
        )
        self.assertEqual(primeiro, segundo)

    def test_servico_nao_contem_http_fastapi_relogio_ou_score_legado(self):
        from backend.app import servico_avaliacao_exposicao

        codigo = inspect.getsource(servico_avaliacao_exposicao).lower()
        for termo in (
            "requests",
            "fastapi",
            "http://",
            "https://",
            "datetime.now",
            "consolidar_para_dashboard",
            "_gerar_score",
            "etapa3",
        ):
            with self.subTest(termo=termo):
                self.assertNotIn(termo, codigo)


if __name__ == "__main__":
    unittest.main()
