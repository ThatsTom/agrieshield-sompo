"""Camada de aplicacao da avaliacao AGRISHIELD-EQUIP.

Este modulo coordena cadastro, aquisicao historica e contexto territorial sem
conhecer transporte web, persistencia concreta ou regras matematicas do motor.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from math import isclose, isfinite
from typing import Any, Protocol

from backend.exposicao.apresentacao_exposicao import (
    ContextoTerritorialApresentacao,
    FazendaApresentacao,
    FonteAvaliacaoApresentacao,
    IntegracaoApresentacao,
    ResultadoApresentacaoExposicaoMaquinario,
    criar_apresentacao_exposicao_maquinario,
)
from backend.exposicao.avaliacao_exposicao import (
    executar_avaliacao_exposicao_maquinario,
)
from backend.exposicao.modelos import JanelaHistorica, SerieHistoricaFonte
from backend.exposicao.perigos_hidricos import (
    DIAS_AQUISICAO_DUAS_JANELAS_90D,
)
from backend.app.servico_parametros_score import OverridesParametrosModelo
from backend.exposicao.politica import criar_politica_agrishield_equip_v1
from backend.risco.modelos import AnaliseGeoespacialNormalizada, FonteDado


DIAS_MINIMOS_AVALIACAO = 180


class CodigoErroAvaliacaoExposicao(str, Enum):
    FAZENDA_NAO_ENCONTRADA = "FAZENDA_NAO_ENCONTRADA"
    REPOSITORIO_FAZENDAS_INDISPONIVEL = "REPOSITORIO_FAZENDAS_INDISPONIVEL"
    COORDENADAS_INDISPONIVEIS = "COORDENADAS_INDISPONIVEIS"
    FONTE_METEOROLOGICA_INDISPONIVEL = "FONTE_METEOROLOGICA_INDISPONIVEL"
    CONTEXTO_TERRITORIAL_INDISPONIVEL = "CONTEXTO_TERRITORIAL_INDISPONIVEL"
    CONTEXTO_TERRITORIAL_INCOMPATIVEL = "CONTEXTO_TERRITORIAL_INCOMPATIVEL"
    PERIODO_HISTORICO_INVALIDO = "PERIODO_HISTORICO_INVALIDO"


class ErroAvaliacaoExposicao(RuntimeError):
    """Erro tipado da camada de aplicacao, sem semantica HTTP."""

    def __init__(
        self,
        codigo: CodigoErroAvaliacaoExposicao,
        mensagem: str,
        *,
        id_fazenda: str,
        fonte: FonteDado | None = None,
        tipo_causa: str | None = None,
    ) -> None:
        self.codigo = codigo
        self.id_fazenda = id_fazenda
        self.fonte = fonte
        self.tipo_causa = tipo_causa
        super().__init__(mensagem)


class FazendaNaoEncontrada(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.FAZENDA_NAO_ENCONTRADA,
            "Fazenda nao encontrada",
            id_fazenda=id_fazenda,
        )


class RepositorioFazendasIndisponivel(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str, causa: Exception) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.REPOSITORIO_FAZENDAS_INDISPONIVEL,
            "Nao foi possivel consultar o cadastro de fazendas",
            id_fazenda=id_fazenda,
            tipo_causa=type(causa).__name__,
        )


class CoordenadasIndisponiveis(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.COORDENADAS_INDISPONIVEIS,
            "Fazenda sem coordenadas validas",
            id_fazenda=id_fazenda,
        )


class FonteMeteorologicaIndisponivel(ErroAvaliacaoExposicao):
    def __init__(
        self,
        id_fazenda: str,
        fonte: FonteDado | None,
        causa: Exception | None = None,
    ) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.FONTE_METEOROLOGICA_INDISPONIVEL,
            "Fonte meteorologica historica indisponivel",
            id_fazenda=id_fazenda,
            fonte=fonte,
            tipo_causa=type(causa).__name__ if causa is not None else None,
        )


class ContextoTerritorialIndisponivel(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str, causa: Exception | None = None) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INDISPONIVEL,
            "Contexto territorial normalizado indisponivel",
            id_fazenda=id_fazenda,
            tipo_causa=type(causa).__name__ if causa is not None else None,
        )


class ContextoTerritorialIncompativel(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.CONTEXTO_TERRITORIAL_INCOMPATIVEL,
            "Contexto territorial nao corresponde a fazenda solicitada",
            id_fazenda=id_fazenda,
        )


class PeriodoHistoricoInvalido(ErroAvaliacaoExposicao):
    def __init__(self, id_fazenda: str, fonte: FonteDado | None = None) -> None:
        super().__init__(
            CodigoErroAvaliacaoExposicao.PERIODO_HISTORICO_INVALIDO,
            "Serie historica incompativel com a avaliacao de duas janelas",
            id_fazenda=id_fazenda,
            fonte=fonte,
        )


class RepositorioFazendas(Protocol):
    def buscar(self, id_fazenda: str) -> Mapping[str, Any] | None: ...


class ClienteMeteorologicoHistorico(Protocol):
    def consultar(
        self,
        latitude: float,
        longitude: float,
        janela: JanelaHistorica,
        *,
        id_fazenda: str | None = None,
    ) -> SerieHistoricaFonte: ...


class ProvedorContextoTerritorial(Protocol):
    def obter(
        self,
        *,
        id_fazenda: str,
        latitude: float,
        longitude: float,
    ) -> AnaliseGeoespacialNormalizada: ...


class ProvedorPesosPerigos(Protocol):
    def obter(self) -> OverridesParametrosModelo: ...


@dataclass(frozen=True)
class RepositorioFazendasPorFuncao:
    """Adapta a funcao buscar_fazenda existente sem duplicar o cadastro."""

    buscar_fazenda: Callable[[str], Mapping[str, Any] | None]

    def buscar(self, id_fazenda: str) -> Mapping[str, Any] | None:
        return self.buscar_fazenda(id_fazenda)


@dataclass(frozen=True)
class InsumosAvaliacaoExposicao:
    fazenda: Mapping[str, Any]
    serie: SerieHistoricaFonte
    contexto_territorial: AnaliseGeoespacialNormalizada


def _normalizar_fonte(
    fonte: FonteDado | str,
    id_fazenda: str,
) -> FonteDado:
    try:
        normalizada = FonteDado(fonte)
    except (TypeError, ValueError) as exc:
        raise FonteMeteorologicaIndisponivel(id_fazenda, None, exc) from exc
    if normalizada not in {FonteDado.NASA_POWER, FonteDado.OPEN_METEO}:
        raise FonteMeteorologicaIndisponivel(id_fazenda, normalizada)
    return normalizada


def _coordenadas(
    fazenda: Mapping[str, Any],
    id_fazenda: str,
) -> tuple[float, float]:
    latitude_bruta = fazenda.get("latitude")
    longitude_bruta = fazenda.get("longitude")
    if isinstance(latitude_bruta, bool) or isinstance(longitude_bruta, bool):
        raise CoordenadasIndisponiveis(id_fazenda)
    try:
        latitude = float(latitude_bruta)
        longitude = float(longitude_bruta)
    except (TypeError, ValueError) as exc:
        raise CoordenadasIndisponiveis(id_fazenda) from exc
    if (
        not isfinite(latitude)
        or not isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or (latitude == 0 and longitude == 0)
    ):
        raise CoordenadasIndisponiveis(id_fazenda)
    return latitude, longitude


def _validar_serie(
    serie: object,
    *,
    id_fazenda: str,
    fonte: FonteDado,
    data_referencia: date,
    janela_solicitada: JanelaHistorica,
) -> SerieHistoricaFonte:
    if not isinstance(serie, SerieHistoricaFonte):
        raise PeriodoHistoricoInvalido(id_fazenda, fonte)
    inicio_minimo = data_referencia - timedelta(days=DIAS_MINIMOS_AVALIACAO - 1)
    periodo = serie.periodo_solicitado
    if (
        serie.id_fazenda != id_fazenda
        or serie.fonte != fonte
        or periodo.data_referencia != data_referencia
        or periodo.fim != data_referencia
        or periodo.inicio < janela_solicitada.inicio
        or periodo.inicio > inicio_minimo
    ):
        raise PeriodoHistoricoInvalido(id_fazenda, fonte)
    return serie


def _validar_contexto(
    contexto: object,
    *,
    id_fazenda: str,
    latitude: float,
    longitude: float,
) -> AnaliseGeoespacialNormalizada:
    if not isinstance(contexto, AnaliseGeoespacialNormalizada):
        raise ContextoTerritorialIndisponivel(id_fazenda)
    referencia = contexto.referencia
    if not (
        isclose(referencia.latitude, latitude, rel_tol=0, abs_tol=1e-6)
        and isclose(referencia.longitude, longitude, rel_tol=0, abs_tol=1e-6)
    ):
        raise ContextoTerritorialIndisponivel(id_fazenda)
    return contexto


class ServicoAvaliacaoExposicao:
    """Coordena infraestrutura e nucleo existente para uma fazenda."""

    def __init__(
        self,
        *,
        repositorio_fazendas: RepositorioFazendas,
        clientes_meteorologicos: Mapping[FonteDado, ClienteMeteorologicoHistorico],
        provedor_contexto_territorial: ProvedorContextoTerritorial,
        provedor_pesos_perigos: ProvedorPesosPerigos | None = None,
    ) -> None:
        self._repositorio_fazendas = repositorio_fazendas
        self._clientes_meteorologicos = dict(clientes_meteorologicos)
        self._provedor_contexto_territorial = provedor_contexto_territorial
        self._provedor_pesos_perigos = provedor_pesos_perigos

    def avaliar_exposicao_fazenda(
        self,
        id_fazenda: str,
        data_referencia: date,
        *,
        fonte: FonteDado | str = FonteDado.NASA_POWER,
    ) -> ResultadoApresentacaoExposicaoMaquinario:
        insumos = self.obter_insumos_avaliacao(id_fazenda, data_referencia, fonte=fonte)
        politica = criar_politica_agrishield_equip_v1()
        if self._provedor_pesos_perigos is not None:
            overrides = self._provedor_pesos_perigos.obter()
            politica = politica.model_copy(
                update={
                    "pesos_perigos": overrides.pesos_perigos,
                    "parametros_territoriais_hidricos": (
                        overrides.parametros_territoriais_hidricos
                    ),
                    "parametros_instabilidade": overrides.parametros_instabilidade,
                    "parametros_propagacao_fogo": (
                        overrides.parametros_propagacao_fogo
                    ),
                    "parametros_tempestade": overrides.parametros_tempestade,
                    "parametros_trafegabilidade": (
                        overrides.parametros_trafegabilidade
                    ),
                }
            )
        avaliacao = executar_avaliacao_exposicao_maquinario(
            insumos.serie,
            insumos.contexto_territorial,
            politica,
        )
        apresentacao = criar_apresentacao_exposicao_maquinario(avaliacao)
        geo = insumos.contexto_territorial
        fazenda = insumos.fazenda
        fonte_meteo = insumos.serie.fonte.value
        fonte_alternativa = (
            "OPEN_METEO" if fonte_meteo == "NASA_POWER" else "NASA_POWER"
        )
        fontes = (
            FonteAvaliacaoApresentacao(
                fonte=fonte_meteo,
                nome_exibicao=(
                    "NASA POWER" if fonte_meteo == "NASA_POWER" else "Open-Meteo"
                ),
                status="USADA",
                categoria="METEOROLOGIA",
                contribui_score=True,
                indicadores=(
                    "Precipitação",
                    "Temperatura",
                    "Umidade relativa",
                    "Vento",
                ),
                descricao="Meteorologia histórica usada nesta avaliação.",
            ),
            FonteAvaliacaoApresentacao(
                fonte=fonte_alternativa,
                nome_exibicao=(
                    "NASA POWER" if fonte_alternativa == "NASA_POWER" else "Open-Meteo"
                ),
                status="DISPONIVEL",
                categoria="METEOROLOGIA",
                contribui_score=False,
                indicadores=(
                    "Precipitação",
                    "Temperatura",
                    "Umidade relativa",
                    "Vento",
                ),
                descricao="Fonte meteorológica alternativa. Não utilizada nesta avaliação.",
            ),
            FonteAvaliacaoApresentacao(
                fonte="SRTM",
                nome_exibicao="SRTM",
                status="USADA",
                categoria="TERRITORIO",
                contribui_score=True,
                indicadores=(
                    "Declividade média",
                    "Posição topográfica relativa",
                    "Instabilidade",
                    "Exposição Hídrica",
                ),
                descricao=(
                    "Relevo usado em Instabilidade e na suscetibilidade territorial "
                    "da Exposição Hídrica."
                ),
            ),
            FonteAvaliacaoApresentacao(
                fonte="MERIT_HYDRO",
                nome_exibicao="MERIT Hydro",
                status="USADA",
                categoria="TERRITORIO",
                contribui_score=True,
                indicadores=(
                    "Distância à drenagem",
                    "Área montante",
                    "Exposição Hídrica",
                ),
                descricao=(
                    "Drenagem e área montante usadas na suscetibilidade territorial "
                    "da Exposição Hídrica."
                ),
            ),
        )
        integracoes = (
            IntegracaoApresentacao(
                fonte="MAPBIOMAS",
                nome_exibicao="MapBiomas",
                status="DISPONIVEL",
                descricao="Uso e cobertura do solo; não participa do score atual.",
            ),
            IntegracaoApresentacao(
                fonte="INMET",
                nome_exibicao="INMET",
                status="NAO_UTILIZADO",
                descricao="Integração disponível, mas não usada nesta avaliação.",
            ),
        )
        return apresentacao.model_copy(
            update={
                "fazenda": FazendaApresentacao(
                    nome=str(
                        fazenda.get("nome_fazenda")
                        or fazenda.get("nome")
                        or f"Fazenda {id_fazenda}"
                    ),
                    cidade=(
                        str(fazenda.get("cidade")) if fazenda.get("cidade") else None
                    ),
                    uf=(str(fazenda.get("uf")) if fazenda.get("uf") else None),
                    area_ha=(
                        float(fazenda["area_ha"])
                        if fazenda.get("area_ha") not in (None, "")
                        else None
                    ),
                    latitude=geo.referencia.latitude,
                    longitude=geo.referencia.longitude,
                ),
                "contexto_territorial": ContextoTerritorialApresentacao(
                    declividade_media_graus=geo.declividade_media_graus.valor,
                    posicao_topografica_relativa_m=geo.posicao_topografica_relativa_m.valor,
                    distancia_drenagem_m=geo.distancia_drenagem_m.valor,
                    area_montante_km2=geo.area_drenagem_montante_km2.valor,
                ),
                "fontes_avaliacao": fontes,
                "integracoes": integracoes,
            }
        )

    def obter_insumos_avaliacao(
        self,
        id_fazenda: str,
        data_referencia: date,
        *,
        fonte: FonteDado | str = FonteDado.NASA_POWER,
    ) -> InsumosAvaliacaoExposicao:
        """Adquire uma vez os mesmos insumos validados usados pelo fluxo v1."""

        id_normalizado = str(id_fazenda or "").strip()
        if not id_normalizado:
            raise FazendaNaoEncontrada(id_normalizado)
        if type(data_referencia) is not date:
            raise PeriodoHistoricoInvalido(id_normalizado)

        try:
            fazenda = self._repositorio_fazendas.buscar(id_normalizado)
        except Exception as exc:
            raise RepositorioFazendasIndisponivel(id_normalizado, exc) from exc
        if not isinstance(fazenda, Mapping):
            raise FazendaNaoEncontrada(id_normalizado)
        latitude, longitude = _coordenadas(fazenda, id_normalizado)

        fonte_normalizada = _normalizar_fonte(fonte, id_normalizado)
        cliente = self._clientes_meteorologicos.get(fonte_normalizada)
        if cliente is None:
            raise FonteMeteorologicaIndisponivel(
                id_normalizado,
                fonte_normalizada,
            )
        janela = JanelaHistorica.criar_atual(
            data_referencia,
            dias=DIAS_AQUISICAO_DUAS_JANELAS_90D,
        )
        try:
            serie_bruta = cliente.consultar(
                latitude,
                longitude,
                janela,
                id_fazenda=id_normalizado,
            )
        except Exception as exc:
            raise FonteMeteorologicaIndisponivel(
                id_normalizado,
                fonte_normalizada,
                exc,
            ) from exc
        serie = _validar_serie(
            serie_bruta,
            id_fazenda=id_normalizado,
            fonte=fonte_normalizada,
            data_referencia=data_referencia,
            janela_solicitada=janela,
        )

        try:
            contexto_bruto = self._provedor_contexto_territorial.obter(
                id_fazenda=id_normalizado,
                latitude=latitude,
                longitude=longitude,
            )
        except ErroAvaliacaoExposicao:
            raise
        except Exception as exc:
            raise ContextoTerritorialIndisponivel(
                id_normalizado,
                exc,
            ) from exc
        contexto = _validar_contexto(
            contexto_bruto,
            id_fazenda=id_normalizado,
            latitude=latitude,
            longitude=longitude,
        )

        return InsumosAvaliacaoExposicao(
            fazenda=dict(fazenda),
            serie=serie,
            contexto_territorial=contexto,
        )


def avaliar_exposicao_fazenda(
    id_fazenda: str,
    data_referencia: date,
    *,
    repositorio_fazendas: RepositorioFazendas,
    clientes_meteorologicos: Mapping[FonteDado, ClienteMeteorologicoHistorico],
    provedor_contexto_territorial: ProvedorContextoTerritorial,
    provedor_pesos_perigos: ProvedorPesosPerigos | None = None,
    fonte: FonteDado | str = FonteDado.NASA_POWER,
) -> ResultadoApresentacaoExposicaoMaquinario:
    """Fachada funcional, mantendo todas as dependencias explicitas."""

    return ServicoAvaliacaoExposicao(
        repositorio_fazendas=repositorio_fazendas,
        clientes_meteorologicos=clientes_meteorologicos,
        provedor_contexto_territorial=provedor_contexto_territorial,
        provedor_pesos_perigos=provedor_pesos_perigos,
    ).avaliar_exposicao_fazenda(
        id_fazenda,
        data_referencia,
        fonte=fonte,
    )


__all__ = [
    "ClienteMeteorologicoHistorico",
    "CodigoErroAvaliacaoExposicao",
    "ContextoTerritorialIncompativel",
    "ContextoTerritorialIndisponivel",
    "CoordenadasIndisponiveis",
    "ErroAvaliacaoExposicao",
    "FazendaNaoEncontrada",
    "FonteMeteorologicaIndisponivel",
    "InsumosAvaliacaoExposicao",
    "PeriodoHistoricoInvalido",
    "ProvedorContextoTerritorial",
    "ProvedorPesosPerigos",
    "RepositorioFazendas",
    "RepositorioFazendasIndisponivel",
    "RepositorioFazendasPorFuncao",
    "ServicoAvaliacaoExposicao",
    "avaliar_exposicao_fazenda",
]
