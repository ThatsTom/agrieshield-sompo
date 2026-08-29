"""Exporta diagnosticos do motor AGRISHIELD-EQUIP sem alterar suas regras.

O modulo reutiliza a aquisicao, os validadores, a politica e a avaliacao
oficiais. A logica propria limita-se a estatisticas descritivas, serializacao
tabular e validacoes de consistencia das tabelas exportadas.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
import math
from pathlib import Path
from statistics import fmean
from typing import Any, Protocol

from backend.app.provedor_contexto_territorial_persistido import (
    ProvedorContextoTerritorialPersistido,
)
from backend.app.servico_avaliacao_exposicao import (
    ClienteMeteorologicoHistorico,
    ErroAvaliacaoExposicao,
    FonteMeteorologicaIndisponivel,
    ProvedorContextoTerritorial,
    _coordenadas,
    _validar_contexto,
    _validar_serie,
)
from backend.etl.etapa1_cadastro_fazendas import listar_fazendas
from backend.etl.repositorio_fazendas_geoespaciais import (
    buscar_registro_geoespacial,
)
from backend.exposicao.apresentacao_exposicao import (
    ResultadoApresentacaoExposicaoMaquinario,
    _estado_perigo,
    criar_apresentacao_exposicao_maquinario,
)
from backend.exposicao.avaliacao_exposicao import (
    ResultadoAvaliacaoExposicaoMaquinario,
    executar_avaliacao_exposicao_maquinario,
)
from backend.exposicao.clientes import ClienteNasaPowerHistorico
from backend.exposicao.features_diarias import (
    FeaturesDiariasCompartilhadas,
    calcular_features_diarias_compartilhadas,
)
from backend.exposicao.modelos import (
    JanelaHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
)
from backend.exposicao.perigos_hidricos import (
    DIAS_AQUISICAO_DUAS_JANELAS_90D,
)
from backend.exposicao.politica import (
    PerigoExposicao,
    criar_politica_agrishield_equip_v1,
)
from backend.exposicao.validacao_integrada import (
    ResultadoValidacaoIntegradaPerigos,
)
from backend.risco.modelos import AnaliseGeoespacialNormalizada, FonteDado


BASE_BACKEND = Path(__file__).resolve().parents[1]
SAIDA_PADRAO = BASE_BACKEND / "data" / "diagnostico_calibracao"
NOMES_ARQUIVOS = (
    "01_resumo_fazendas.csv",
    "02_contexto_territorial.csv",
    "03_meteorologia_janelas.csv",
    "04_perigos.csv",
    "05_features_diarias.csv",
    "06_fontes_proveniencia.csv",
)
TOLERANCIA_NUMERICA = 1e-9


COLUNAS_RESUMO = (
    "id_fazenda",
    "nome",
    "cidade",
    "uf",
    "latitude",
    "longitude",
    "area_ha",
    "fonte_meteorologica",
    "data_referencia",
    "score_anterior",
    "classificacao_anterior",
    "score_atual",
    "classificacao_atual",
    "variacao_pontos",
    "variacao_percentual",
    "direcao_variacao",
    "perigo_dominante",
    "perigos_dominantes",
    "cobertura_minima_atual_pct",
    "dias_dados_ausentes",
    "quantidade_gaps",
    "warmup_completo",
    "score_publicavel",
    "comparacao_publicavel",
    "avaliacao_publicavel",
    "erro",
    "tipo_erro",
    "detalhe",
)

COLUNAS_CONTEXTO = (
    "id_fazenda",
    "nome",
    "latitude_referencia",
    "longitude_referencia",
    "area_ha_referencia",
    "raio_equivalente_m",
    "raio_analise_m",
    "declividade_media_graus",
    "posicao_topografica_relativa_m",
    "distancia_drenagem_m",
    "area_drenagem_montante_km2",
    "cobertura_srtm_pct",
    "pixels_srtm_validos",
    "drenagem_encontrada",
    "candidatos_drenagem",
    "distancia_geodesica_final_m",
    "fonte_srtm",
    "fonte_merit",
    "algorithm_version",
    "calculado_em_utc",
    "declividade_participa_score",
    "posicao_topografica_participa_score",
    "distancia_drenagem_participa_score",
    "area_montante_participa_score",
    "erro",
    "tipo_erro",
    "detalhe",
)

COLUNAS_METEOROLOGIA = (
    "id_fazenda",
    "nome",
    "janela",
    "data_inicio",
    "data_fim",
    "dias_esperados",
    "dias_com_registro",
    "precipitacao_total_mm",
    "precipitacao_media_mm",
    "precipitacao_max_dia_mm",
    "temperatura_media_media_c",
    "temperatura_maxima_media_c",
    "temperatura_maxima_absoluta_c",
    "temperatura_minima_media_c",
    "temperatura_minima_absoluta_c",
    "umidade_media_pct",
    "umidade_minima_das_medias_diarias_pct",
    "vento_medio_m_s",
    "vento_maximo_das_medias_diarias_m_s",
    "dias_precipitacao_disponivel",
    "dias_temperatura_maxima_disponivel",
    "dias_umidade_disponivel",
    "dias_vento_disponivel",
    "erro",
    "tipo_erro",
    "detalhe",
)

COLUNAS_PERIGOS = (
    "id_fazenda",
    "nome",
    "janela",
    "perigo",
    "indice_90d",
    "classificacao",
    "cobertura_percentual",
    "qualidade_suficiente",
    "severidade",
    "frequencia",
    "duracao",
    "recorrencia",
    "quantidade_eventos",
    "dias_relevantes",
    "maior_evento_dias",
    "peso",
    "participa_score",
    "elegivel",
    "contribuicao",
    "estado",
    "metodologia",
)

COLUNAS_FEATURES = (
    "id_fazenda",
    "nome",
    "data",
    "janela",
    "precipitacao_d0",
    "precipitacao_d1_d3",
    "precipitacao_d4_d7",
    "acumulado_3d",
    "acumulado_7d",
    "dias_consecutivos_com_chuva",
    "dias_desde_ultima_chuva_relevante",
    "temperatura_media",
    "temperatura_maxima",
    "temperatura_minima",
    "umidade_relativa",
    "velocidade_vento_media_m_s",
    "indice_hidrico",
    "classificacao_hidrica",
    "indice_trafegabilidade",
    "classificacao_trafegabilidade",
    "indice_instabilidade",
    "classificacao_instabilidade",
    "indice_incendio",
    "classificacao_incendio",
    "indice_tempestade",
    "classificacao_tempestade",
)

COLUNAS_FONTES = (
    "id_fazenda",
    "nome",
    "fonte",
    "estado",
    "papel",
    "participa_matematicamente_score",
    "observacao",
)

COLUNAS_POR_ARQUIVO = dict(
    zip(
        NOMES_ARQUIVOS,
        (
            COLUNAS_RESUMO,
            COLUNAS_CONTEXTO,
            COLUNAS_METEOROLOGIA,
            COLUNAS_PERIGOS,
            COLUNAS_FEATURES,
            COLUNAS_FONTES,
        ),
    )
)


class BuscadorContextoPersistido(Protocol):
    def __call__(self, id_fazenda: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class FalhaFazenda:
    erro: str
    tipo_erro: str
    detalhe: str


@dataclass
class ExecucaoFazenda:
    fazenda: Mapping[str, Any]
    data_referencia: date
    registro_contexto: Mapping[str, Any] | None = None
    serie: SerieHistoricaFonte | None = None
    features: FeaturesDiariasCompartilhadas | None = None
    contexto: AnaliseGeoespacialNormalizada | None = None
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario | None = None
    apresentacao: ResultadoApresentacaoExposicaoMaquinario | None = None
    falha: FalhaFazenda | None = None

    @property
    def id_fazenda(self) -> str:
        return str(self.fazenda.get("id_fazenda") or "").strip()

    @property
    def nome(self) -> str:
        return str(self.fazenda.get("nome_fazenda") or "")


@dataclass(frozen=True)
class TabelasDiagnostico:
    resumo: tuple[dict[str, Any], ...]
    contexto: tuple[dict[str, Any], ...]
    meteorologia: tuple[dict[str, Any], ...]
    perigos: tuple[dict[str, Any], ...]
    features: tuple[dict[str, Any], ...]
    fontes: tuple[dict[str, Any], ...]

    def por_arquivo(self) -> dict[str, tuple[dict[str, Any], ...]]:
        return dict(
            zip(
                NOMES_ARQUIVOS,
                (
                    self.resumo,
                    self.contexto,
                    self.meteorologia,
                    self.perigos,
                    self.features,
                    self.fontes,
                ),
            )
        )


def _valor_enum(valor: Any) -> Any:
    return valor.value if isinstance(valor, Enum) else valor


def _sim_nao(valor: bool | None) -> str | None:
    if valor is None:
        return None
    return "SIM" if valor else "NAO"


def _texto_lista(valores: Iterable[Any]) -> str:
    return "|".join(str(_valor_enum(valor)) for valor in valores)


def _erro_da_excecao(exc: Exception) -> FalhaFazenda:
    if isinstance(exc, ErroAvaliacaoExposicao):
        return FalhaFazenda(
            erro=exc.codigo.value,
            tipo_erro=exc.tipo_causa or type(exc).__name__,
            detalhe=str(exc),
        )
    return FalhaFazenda(
        erro=type(exc).__name__,
        tipo_erro=type(exc).__name__,
        detalhe=str(exc) or type(exc).__name__,
    )


def _campos_erro(execucao: ExecucaoFazenda) -> dict[str, Any]:
    if execucao.falha is None:
        return {"erro": None, "tipo_erro": None, "detalhe": None}
    return {
        "erro": execucao.falha.erro,
        "tipo_erro": execucao.falha.tipo_erro,
        "detalhe": execucao.falha.detalhe,
    }


def executar_fazendas(
    fazendas: Sequence[Mapping[str, Any]],
    *,
    data_referencia: date,
    cliente_nasa: ClienteMeteorologicoHistorico,
    provedor_contexto: ProvedorContextoTerritorial,
    buscar_contexto: BuscadorContextoPersistido = buscar_registro_geoespacial,
) -> tuple[ExecucaoFazenda, ...]:
    """Executa fazendas isoladamente, preservando resultados parciais e falhas."""

    resultados: list[ExecucaoFazenda] = []
    for fazenda_recebida in fazendas:
        fazenda = dict(fazenda_recebida)
        execucao = ExecucaoFazenda(fazenda=fazenda, data_referencia=data_referencia)
        resultados.append(execucao)
        try:
            execucao.registro_contexto = buscar_contexto(execucao.id_fazenda)
        except Exception:
            # A leitura tipada pelo provider continua sendo a autoridade do fluxo.
            execucao.registro_contexto = None

        try:
            latitude, longitude = _coordenadas(fazenda, execucao.id_fazenda)
            janela = JanelaHistorica.criar_atual(
                data_referencia,
                dias=DIAS_AQUISICAO_DUAS_JANELAS_90D,
            )
            try:
                serie_bruta = cliente_nasa.consultar(
                    latitude,
                    longitude,
                    janela,
                    id_fazenda=execucao.id_fazenda,
                )
            except Exception as exc:
                raise FonteMeteorologicaIndisponivel(
                    execucao.id_fazenda,
                    FonteDado.NASA_POWER,
                    exc,
                ) from exc
            execucao.serie = _validar_serie(
                serie_bruta,
                id_fazenda=execucao.id_fazenda,
                fonte=FonteDado.NASA_POWER,
                data_referencia=data_referencia,
                janela_solicitada=janela,
            )
            execucao.features = calcular_features_diarias_compartilhadas(execucao.serie)
            contexto_bruto = provedor_contexto.obter(
                id_fazenda=execucao.id_fazenda,
                latitude=latitude,
                longitude=longitude,
            )
            execucao.contexto = _validar_contexto(
                contexto_bruto,
                id_fazenda=execucao.id_fazenda,
                latitude=latitude,
                longitude=longitude,
            )
            execucao.avaliacao = executar_avaliacao_exposicao_maquinario(
                execucao.serie,
                execucao.contexto,
                criar_politica_agrishield_equip_v1(),
            )
            execucao.features = execucao.avaliacao.features_compartilhadas
            execucao.apresentacao = criar_apresentacao_exposicao_maquinario(
                execucao.avaliacao
            )
        except Exception as exc:
            execucao.falha = _erro_da_excecao(exc)
    return tuple(resultados)


def _linha_resumo(execucao: ExecucaoFazenda) -> dict[str, Any]:
    apresentacao = execucao.apresentacao
    coberturas = (
        [item.cobertura_percentual for item in apresentacao.perigos]
        if apresentacao is not None
        else []
    )
    return {
        "id_fazenda": execucao.id_fazenda,
        "nome": execucao.nome,
        "cidade": execucao.fazenda.get("cidade"),
        "uf": execucao.fazenda.get("uf"),
        "latitude": execucao.fazenda.get("latitude"),
        "longitude": execucao.fazenda.get("longitude"),
        "area_ha": execucao.fazenda.get("area_ha"),
        "fonte_meteorologica": FonteDado.NASA_POWER.value,
        "data_referencia": execucao.data_referencia,
        "score_anterior": apresentacao.score_anterior if apresentacao else None,
        "classificacao_anterior": (
            apresentacao.classificacao_anterior if apresentacao else None
        ),
        "score_atual": apresentacao.score_atual if apresentacao else None,
        "classificacao_atual": (
            apresentacao.classificacao_atual if apresentacao else None
        ),
        "variacao_pontos": apresentacao.variacao_pontos if apresentacao else None,
        "variacao_percentual": (
            apresentacao.variacao_percentual if apresentacao else None
        ),
        "direcao_variacao": apresentacao.direcao_variacao if apresentacao else None,
        "perigo_dominante": apresentacao.perigo_dominante if apresentacao else None,
        "perigos_dominantes": (
            _texto_lista(apresentacao.perigos_dominantes) if apresentacao else ""
        ),
        "cobertura_minima_atual_pct": min(coberturas) if coberturas else None,
        "dias_dados_ausentes": (
            apresentacao.qualidade_dados.dias_com_dados_ausentes
            if apresentacao
            else None
        ),
        "quantidade_gaps": (
            apresentacao.qualidade_dados.quantidade_gaps if apresentacao else None
        ),
        "warmup_completo": (
            apresentacao.qualidade_dados.warmup_completo if apresentacao else None
        ),
        "score_publicavel": apresentacao.score_publicavel if apresentacao else False,
        "comparacao_publicavel": (
            apresentacao.comparacao_publicavel if apresentacao else False
        ),
        "avaliacao_publicavel": (
            apresentacao.avaliacao_publicavel if apresentacao else False
        ),
        **_campos_erro(execucao),
    }


def _identificador_fonte(
    fontes: Iterable[Mapping[str, Any]],
    trecho: str,
) -> str | None:
    trecho = trecho.lower()
    for fonte in fontes:
        identificador = str(fonte.get("identificador") or "")
        if trecho in identificador.lower():
            return identificador
    return None


def _linha_contexto(execucao: ExecucaoFazenda) -> dict[str, Any]:
    registro = dict(execucao.registro_contexto or {})
    qualidade = dict(registro.get("qualidade") or {})
    fontes = tuple(
        item for item in (registro.get("fontes") or ()) if isinstance(item, Mapping)
    )
    erro_contexto = (
        _campos_erro(execucao)
        if execucao.contexto is None
        else {"erro": None, "tipo_erro": None, "detalhe": None}
    )
    return {
        "id_fazenda": execucao.id_fazenda,
        "nome": execucao.nome,
        "latitude_referencia": registro.get("latitude_referencia"),
        "longitude_referencia": registro.get("longitude_referencia"),
        "area_ha_referencia": registro.get("area_ha_referencia"),
        "raio_equivalente_m": registro.get("raio_equivalente_m"),
        "raio_analise_m": registro.get("raio_analise_m"),
        "declividade_media_graus": registro.get("declividade_media_graus"),
        "posicao_topografica_relativa_m": registro.get(
            "posicao_topografica_relativa_m"
        ),
        "distancia_drenagem_m": registro.get("distancia_drenagem_m"),
        "area_drenagem_montante_km2": registro.get("area_drenagem_montante_km2"),
        "cobertura_srtm_pct": qualidade.get("cobertura_srtm_pct"),
        "pixels_srtm_validos": qualidade.get("pixels_srtm_validos"),
        "drenagem_encontrada": qualidade.get("drenagem_encontrada"),
        "candidatos_drenagem": qualidade.get("candidatos_drenagem"),
        "distancia_geodesica_final_m": qualidade.get("distancia_geodesica_final_m"),
        "fonte_srtm": _identificador_fonte(fontes, "srtm"),
        "fonte_merit": _identificador_fonte(fontes, "merit"),
        "algorithm_version": registro.get("algorithm_version"),
        "calculado_em_utc": registro.get("calculado_em_utc"),
        "declividade_participa_score": "SIM",
        "posicao_topografica_participa_score": "NAO",
        "distancia_drenagem_participa_score": "NAO",
        "area_montante_participa_score": "NAO",
        **erro_contexto,
    }


def _valores(
    registros: Iterable[RegistroMeteorologicoDiario],
    atributo: str,
) -> list[float]:
    return [
        valor
        for registro in registros
        if (valor := getattr(registro, atributo)) is not None
    ]


def _media(valores: Sequence[float]) -> float | None:
    return fmean(valores) if valores else None


def _maximo(valores: Sequence[float]) -> float | None:
    return max(valores) if valores else None


def _minimo(valores: Sequence[float]) -> float | None:
    return min(valores) if valores else None


def _registros_da_janela(
    serie: SerieHistoricaFonte | None,
    janela: JanelaHistorica,
) -> tuple[RegistroMeteorologicoDiario, ...]:
    if serie is None:
        return ()
    return tuple(
        registro
        for registro in serie.registros
        if janela.inicio <= registro.data <= janela.fim
    )


def _linha_meteorologia(
    execucao: ExecucaoFazenda,
    nome_janela: str,
    janela: JanelaHistorica,
) -> dict[str, Any]:
    registros = _registros_da_janela(execucao.serie, janela)
    precipitacao = _valores(registros, "precipitacao_mm")
    temperatura_media = _valores(registros, "temperatura_media_c")
    temperatura_maxima = _valores(registros, "temperatura_maxima_c")
    temperatura_minima = _valores(registros, "temperatura_minima_c")
    umidade = _valores(registros, "umidade_media_pct")
    vento = _valores(registros, "velocidade_vento_media_m_s")
    return {
        "id_fazenda": execucao.id_fazenda,
        "nome": execucao.nome,
        "janela": nome_janela,
        "data_inicio": janela.inicio,
        "data_fim": janela.fim,
        "dias_esperados": janela.dias_esperados,
        "dias_com_registro": sum(
            registro.possui_algum_dado() for registro in registros
        ),
        "precipitacao_total_mm": sum(precipitacao) if precipitacao else None,
        "precipitacao_media_mm": _media(precipitacao),
        "precipitacao_max_dia_mm": _maximo(precipitacao),
        "temperatura_media_media_c": _media(temperatura_media),
        "temperatura_maxima_media_c": _media(temperatura_maxima),
        "temperatura_maxima_absoluta_c": _maximo(temperatura_maxima),
        "temperatura_minima_media_c": _media(temperatura_minima),
        "temperatura_minima_absoluta_c": _minimo(temperatura_minima),
        "umidade_media_pct": _media(umidade),
        "umidade_minima_das_medias_diarias_pct": _minimo(umidade),
        "vento_medio_m_s": _media(vento),
        "vento_maximo_das_medias_diarias_m_s": _maximo(vento),
        "dias_precipitacao_disponivel": len(precipitacao),
        "dias_temperatura_maxima_disponivel": len(temperatura_maxima),
        "dias_umidade_disponivel": len(umidade),
        "dias_vento_disponivel": len(vento),
        **(
            _campos_erro(execucao)
            if execucao.serie is None
            else {"erro": None, "tipo_erro": None, "detalhe": None}
        ),
    }


def _resultados_perigos(
    validacao: ResultadoValidacaoIntegradaPerigos,
) -> tuple[Any, ...]:
    return (
        validacao.exposicao_hidrica,
        validacao.trafegabilidade,
        validacao.instabilidade,
        validacao.propagacao_fogo,
        validacao.tempestade,
    )


def _linhas_perigos(execucao: ExecucaoFazenda) -> list[dict[str, Any]]:
    if execucao.avaliacao is None:
        return []
    linhas: list[dict[str, Any]] = []
    pares = (
        (
            "ANTERIOR",
            execucao.avaliacao.validacao_anterior,
            execucao.avaliacao.score_anterior,
        ),
        (
            "ATUAL",
            execucao.avaliacao.validacao_atual,
            execucao.avaliacao.score_atual,
        ),
    )
    for nome_janela, validacao, score in pares:
        for resultado in _resultados_perigos(validacao):
            agregado = resultado.agregacao_90d
            contribuicao = score.contribuicao_de(resultado.perigo)
            linhas.append(
                {
                    "id_fazenda": execucao.id_fazenda,
                    "nome": execucao.nome,
                    "janela": nome_janela,
                    "perigo": resultado.perigo,
                    "indice_90d": agregado.indice_agregado,
                    "classificacao": agregado.classificacao_agregada,
                    "cobertura_percentual": agregado.cobertura_percentual,
                    "qualidade_suficiente": agregado.qualidade_suficiente,
                    "severidade": agregado.severidade_score,
                    "frequencia": agregado.frequencia_score,
                    "duracao": agregado.duracao_score,
                    "recorrencia": agregado.recorrencia_score,
                    "quantidade_eventos": agregado.quantidade_eventos,
                    "dias_relevantes": agregado.quantidade_dias_relevantes,
                    "maior_evento_dias": agregado.maior_duracao_evento,
                    "peso": contribuicao.peso,
                    "participa_score": contribuicao.participa_score,
                    "elegivel": contribuicao.elegivel,
                    "contribuicao": contribuicao.contribuicao,
                    "estado": _estado_perigo(
                        contribuicao.participa_score,
                        contribuicao.elegivel,
                    ),
                    "metodologia": resultado.metodologia,
                }
            )
    return linhas


def _indice_por_data(resultado: Any) -> dict[date, Any]:
    return {item.data: item for item in resultado.indices_diarios.indices}


def _mapas_indices(
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario | None,
) -> dict[PerigoExposicao, dict[date, Any]]:
    mapas = {perigo: {} for perigo in PerigoExposicao}
    if avaliacao is None:
        return mapas
    for validacao in (avaliacao.validacao_anterior, avaliacao.validacao_atual):
        for resultado in _resultados_perigos(validacao):
            mapas[resultado.perigo].update(_indice_por_data(resultado))
    return mapas


def _nome_janela_feature(
    data_feature: date,
    anterior: JanelaHistorica,
    atual: JanelaHistorica,
) -> str:
    if anterior.inicio <= data_feature <= anterior.fim:
        return "ANTERIOR"
    if atual.inicio <= data_feature <= atual.fim:
        return "ATUAL"
    return "WARMUP"


def _linhas_features(execucao: ExecucaoFazenda) -> list[dict[str, Any]]:
    if execucao.features is None:
        return []
    periodo_180 = JanelaHistorica.criar_atual(execucao.data_referencia, dias=180)
    anterior, atual = periodo_180.dividir_em_periodos_90()
    mapas = _mapas_indices(execucao.avaliacao)
    linhas: list[dict[str, Any]] = []
    for feature in execucao.features.dias:
        indices = {
            perigo: mapas[perigo].get(feature.data) for perigo in PerigoExposicao
        }
        linhas.append(
            {
                "id_fazenda": execucao.id_fazenda,
                "nome": execucao.nome,
                "data": feature.data,
                "janela": _nome_janela_feature(feature.data, anterior, atual),
                "precipitacao_d0": feature.precipitacao_d0,
                "precipitacao_d1_d3": feature.precipitacao_d1_d3,
                "precipitacao_d4_d7": feature.precipitacao_d4_d7,
                "acumulado_3d": feature.acumulado_3d,
                "acumulado_7d": feature.acumulado_7d,
                "dias_consecutivos_com_chuva": feature.dias_consecutivos_com_chuva,
                "dias_desde_ultima_chuva_relevante": (
                    feature.dias_desde_ultima_chuva_relevante
                ),
                "temperatura_media": feature.temperatura_media,
                "temperatura_maxima": feature.temperatura_maxima,
                "temperatura_minima": feature.temperatura_minima,
                "umidade_relativa": feature.umidade_relativa,
                "velocidade_vento_media_m_s": feature.velocidade_vento_media_m_s,
                "indice_hidrico": (
                    indices[PerigoExposicao.EXPOSICAO_HIDRICA].indice
                    if indices[PerigoExposicao.EXPOSICAO_HIDRICA]
                    else None
                ),
                "classificacao_hidrica": (
                    indices[PerigoExposicao.EXPOSICAO_HIDRICA].classificacao
                    if indices[PerigoExposicao.EXPOSICAO_HIDRICA]
                    else None
                ),
                "indice_trafegabilidade": (
                    indices[PerigoExposicao.TRAFEGABILIDADE].indice
                    if indices[PerigoExposicao.TRAFEGABILIDADE]
                    else None
                ),
                "classificacao_trafegabilidade": (
                    indices[PerigoExposicao.TRAFEGABILIDADE].classificacao
                    if indices[PerigoExposicao.TRAFEGABILIDADE]
                    else None
                ),
                "indice_instabilidade": (
                    indices[PerigoExposicao.INSTABILIDADE].indice
                    if indices[PerigoExposicao.INSTABILIDADE]
                    else None
                ),
                "classificacao_instabilidade": (
                    indices[PerigoExposicao.INSTABILIDADE].classificacao
                    if indices[PerigoExposicao.INSTABILIDADE]
                    else None
                ),
                "indice_incendio": (
                    indices[PerigoExposicao.INCENDIO].indice
                    if indices[PerigoExposicao.INCENDIO]
                    else None
                ),
                "classificacao_incendio": (
                    indices[PerigoExposicao.INCENDIO].classificacao
                    if indices[PerigoExposicao.INCENDIO]
                    else None
                ),
                "indice_tempestade": (
                    indices[PerigoExposicao.TEMPESTADES].indice
                    if indices[PerigoExposicao.TEMPESTADES]
                    else None
                ),
                "classificacao_tempestade": (
                    indices[PerigoExposicao.TEMPESTADES].classificacao
                    if indices[PerigoExposicao.TEMPESTADES]
                    else None
                ),
            }
        )
    return linhas


def _linha_fonte(
    execucao: ExecucaoFazenda,
    *,
    fonte: FonteDado,
    estado: str,
    papel: str,
    participa: bool,
    observacao: str,
) -> dict[str, Any]:
    return {
        "id_fazenda": execucao.id_fazenda,
        "nome": execucao.nome,
        "fonte": fonte.value,
        "estado": estado,
        "papel": papel,
        "participa_matematicamente_score": _sim_nao(participa),
        "observacao": observacao,
    }


def _linhas_fontes(execucao: ExecucaoFazenda) -> list[dict[str, Any]]:
    nasa_ok = execucao.serie is not None
    srtm_ok = (
        execucao.contexto is not None
        and execucao.contexto.declividade_media_graus.valor is not None
    )
    merit_ok = execucao.contexto is not None and (
        execucao.contexto.distancia_drenagem_m.valor is not None
        or execucao.contexto.area_drenagem_montante_km2.valor is not None
    )
    return [
        _linha_fonte(
            execucao,
            fonte=FonteDado.NASA_POWER,
            estado=("UTILIZADA_MATEMATICAMENTE" if nasa_ok else "INDISPONIVEL"),
            papel="Serie meteorologica historica selecionada para a execucao",
            participa=nasa_ok,
            observacao=(
                "Fonte unica da execucao; nenhuma mistura com Open-Meteo."
                if nasa_ok
                else "Aquisicao NASA POWER nao concluida."
            ),
        ),
        _linha_fonte(
            execucao,
            fonte=FonteDado.OPEN_METEO,
            estado="IMPLEMENTADA_MAS_NAO_EXECUTADA",
            papel="Fonte meteorologica historica alternativa",
            participa=False,
            observacao="Nao executada e nao misturada com NASA POWER.",
        ),
        _linha_fonte(
            execucao,
            fonte=FonteDado.SRTM,
            estado=("UTILIZADA_MATEMATICAMENTE" if srtm_ok else "INDISPONIVEL"),
            papel="Contexto topografico estrutural",
            participa=srtm_ok,
            observacao=(
                "Apenas declividade influencia Instabilidade."
                if srtm_ok
                else "Contexto SRTM normalizado indisponivel."
            ),
        ),
        _linha_fonte(
            execucao,
            fonte=FonteDado.MERIT_HYDRO,
            estado=("CARREGADA_COMO_CONTEXTO" if merit_ok else "INDISPONIVEL"),
            papel="Contexto hidrologico estrutural",
            participa=False,
            observacao=(
                "Distancia e area montante nao influenciam o score v1."
                if merit_ok
                else "Contexto MERIT Hydro normalizado indisponivel."
            ),
        ),
        _linha_fonte(
            execucao,
            fonte=FonteDado.MAPBIOMAS,
            estado="IMPLEMENTADA_MAS_NAO_EXECUTADA",
            papel="Uso e cobertura territorial",
            participa=False,
            observacao="Subsistema existente, nao executado pelo diagnostico.",
        ),
        _linha_fonte(
            execucao,
            fonte=FonteDado.INMET,
            estado="IMPLEMENTADA_MAS_NAO_EXECUTADA",
            papel="Observacao meteorologica por estacao",
            participa=False,
            observacao="Subsistema existente, nao executado pelo diagnostico.",
        ),
    ]


def montar_tabelas(
    execucoes: Sequence[ExecucaoFazenda],
) -> TabelasDiagnostico:
    resumo = tuple(_linha_resumo(item) for item in execucoes)
    contexto = tuple(_linha_contexto(item) for item in execucoes)
    meteorologia: list[dict[str, Any]] = []
    perigos: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    fontes: list[dict[str, Any]] = []
    for item in execucoes:
        periodo = JanelaHistorica.criar_atual(item.data_referencia, dias=180)
        anterior, atual = periodo.dividir_em_periodos_90()
        meteorologia.extend(
            (
                _linha_meteorologia(item, "ANTERIOR", anterior),
                _linha_meteorologia(item, "ATUAL", atual),
            )
        )
        perigos.extend(_linhas_perigos(item))
        features.extend(_linhas_features(item))
        fontes.extend(_linhas_fontes(item))
    tabelas = TabelasDiagnostico(
        resumo=resumo,
        contexto=contexto,
        meteorologia=tuple(meteorologia),
        perigos=tuple(perigos),
        features=tuple(features),
        fontes=tuple(fontes),
    )
    validar_tabelas(execucoes, tabelas)
    return tabelas


def _validar_sem_duplicatas(
    linhas: Sequence[Mapping[str, Any]],
    campos: tuple[str, ...],
    nome: str,
) -> None:
    chaves = [tuple(linha.get(campo) for campo in campos) for linha in linhas]
    if len(chaves) != len(set(chaves)):
        raise ValueError(f"duplicidade indevida em {nome}: {campos}")


def _validar_indices(tabelas: TabelasDiagnostico) -> None:
    campos_perigos = (
        "indice_90d",
        "severidade",
        "frequencia",
        "duracao",
        "recorrencia",
    )
    campos_features = (
        "indice_hidrico",
        "indice_trafegabilidade",
        "indice_instabilidade",
        "indice_incendio",
        "indice_tempestade",
    )
    for linha in tabelas.perigos:
        for campo in campos_perigos:
            valor = linha[campo]
            if valor is not None and not 0 <= float(valor) <= 100:
                raise ValueError(f"{campo} fora do dominio 0..100")
    for linha in tabelas.features:
        for campo in campos_features:
            valor = linha[campo]
            if valor is not None and not 0 <= float(valor) <= 100:
                raise ValueError(f"{campo} fora do dominio 0..100")


def _validar_pesos_e_score(
    execucoes: Sequence[ExecucaoFazenda],
    tabelas: TabelasDiagnostico,
) -> None:
    for execucao in execucoes:
        if execucao.avaliacao is None:
            continue
        linhas_fazenda = [
            linha
            for linha in tabelas.perigos
            if linha["id_fazenda"] == execucao.id_fazenda
        ]
        for nome_janela, score in (
            ("ANTERIOR", execucao.avaliacao.score_anterior),
            ("ATUAL", execucao.avaliacao.score_atual),
        ):
            linhas = [
                linha for linha in linhas_fazenda if linha["janela"] == nome_janela
            ]
            participantes = [linha for linha in linhas if linha["participa_score"]]
            soma_pesos = math.fsum(float(linha["peso"]) for linha in participantes)
            if not math.isclose(
                soma_pesos, 1.0, rel_tol=0.0, abs_tol=TOLERANCIA_NUMERICA
            ):
                raise ValueError("pesos dos participantes nao somam 1")
            contribuicoes = [
                linha["contribuicao"]
                for linha in participantes
                if linha["contribuicao"] is not None
            ]
            if score.score is not None:
                recalculado = math.fsum(float(valor) for valor in contribuicoes)
                if not math.isclose(
                    recalculado,
                    score.score,
                    rel_tol=0.0,
                    abs_tol=TOLERANCIA_NUMERICA,
                ):
                    raise ValueError(
                        "score diverge da soma diagnostica das contribuicoes"
                    )


def _validar_missing_preservado(
    execucoes: Sequence[ExecucaoFazenda],
    tabelas: TabelasDiagnostico,
) -> None:
    por_chave = {
        (linha["id_fazenda"], linha["data"]): linha for linha in tabelas.features
    }
    campos = (
        "temperatura_media",
        "temperatura_maxima",
        "temperatura_minima",
        "umidade_relativa",
        "velocidade_vento_media_m_s",
    )
    for execucao in execucoes:
        if execucao.features is None:
            continue
        for feature in execucao.features.dias:
            linha = por_chave[(execucao.id_fazenda, feature.data)]
            for campo in campos:
                if getattr(feature, campo) is None and linha[campo] is not None:
                    raise ValueError(f"missing convertido indevidamente em {campo}")


def validar_tabelas(
    execucoes: Sequence[ExecucaoFazenda],
    tabelas: TabelasDiagnostico,
) -> None:
    """Valida cardinalidade e invariantes sem introduzir regras de score."""

    quantidade = len(execucoes)
    ids = [item.id_fazenda for item in execucoes]
    if any(not id_fazenda for id_fazenda in ids) or len(ids) != len(set(ids)):
        raise ValueError("IDs de fazenda devem ser validos e unicos")
    if len(tabelas.resumo) != quantidade or len(tabelas.contexto) != quantidade:
        raise ValueError("resumo e contexto exigem uma linha por fazenda")
    if len(tabelas.meteorologia) != quantidade * 2:
        raise ValueError("meteorologia exige duas janelas por fazenda")
    if len(tabelas.fontes) != quantidade * 6:
        raise ValueError("proveniencia exige seis fontes por fazenda")

    _validar_sem_duplicatas(tabelas.resumo, ("id_fazenda",), "resumo")
    _validar_sem_duplicatas(tabelas.contexto, ("id_fazenda",), "contexto")
    _validar_sem_duplicatas(
        tabelas.meteorologia, ("id_fazenda", "janela"), "meteorologia"
    )
    _validar_sem_duplicatas(
        tabelas.perigos, ("id_fazenda", "janela", "perigo"), "perigos"
    )
    _validar_sem_duplicatas(tabelas.features, ("id_fazenda", "data"), "features")
    _validar_sem_duplicatas(tabelas.fontes, ("id_fazenda", "fonte"), "fontes")

    for execucao in execucoes:
        linhas_meteo = [
            linha
            for linha in tabelas.meteorologia
            if linha["id_fazenda"] == execucao.id_fazenda
        ]
        if {linha["janela"] for linha in linhas_meteo} != {"ANTERIOR", "ATUAL"}:
            raise ValueError("separacao ANTERIOR/ATUAL invalida")
        linhas_perigos = [
            linha
            for linha in tabelas.perigos
            if linha["id_fazenda"] == execucao.id_fazenda
        ]
        esperado_perigos = 10 if execucao.avaliacao is not None else 0
        if len(linhas_perigos) != esperado_perigos:
            raise ValueError("cardinalidade de perigos invalida")
        linhas_features = [
            linha
            for linha in tabelas.features
            if linha["id_fazenda"] == execucao.id_fazenda
        ]
        esperado_features = len(execucao.features.dias) if execucao.features else 0
        if len(linhas_features) != esperado_features:
            raise ValueError("cardinalidade de features invalida")

    _validar_indices(tabelas)
    _validar_missing_preservado(execucoes, tabelas)
    _validar_pesos_e_score(execucoes, tabelas)


def _serializar(valor: Any) -> str:
    valor = _valor_enum(valor)
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return _sim_nao(valor) or ""
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError("valor nao finito nao pode ser exportado")
        return format(valor, ".15g")
    return str(valor)


def salvar_tabelas(
    tabelas: TabelasDiagnostico,
    diretorio: Path = SAIDA_PADRAO,
) -> tuple[Path, ...]:
    diretorio = Path(diretorio)
    diretorio.mkdir(parents=True, exist_ok=True)
    caminhos: list[Path] = []
    for nome, linhas in tabelas.por_arquivo().items():
        caminho = diretorio / nome
        colunas = COLUNAS_POR_ARQUIVO[nome]
        with caminho.open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.DictWriter(
                arquivo,
                fieldnames=colunas,
                delimiter=";",
                extrasaction="raise",
            )
            escritor.writeheader()
            escritor.writerows(
                {coluna: _serializar(linha.get(coluna)) for coluna in colunas}
                for linha in linhas
            )
        caminhos.append(caminho)
    return tuple(caminhos)


def _texto_numero(valor: Any, casas: int = 2) -> str:
    if valor is None:
        return "-"
    return f"{float(valor):.{casas}f}"


def _resumo_terminal(
    execucoes: Sequence[ExecucaoFazenda],
    caminhos: Sequence[Path],
) -> None:
    cabecalhos = (
        "ID",
        "Fazenda",
        "UF",
        "Anterior",
        "Atual",
        "Variacao",
        "Hidrico",
        "Trafeg.",
        "Instab.",
        "Incendio",
        "Tempest.",
        "Decliv.",
        "Drenagem",
        "Cobert.",
        "Status",
    )
    linhas: list[tuple[str, ...]] = []
    for item in execucoes:
        apresentacao = item.apresentacao
        perigos = {
            perigo.perigo: perigo.indice
            for perigo in (apresentacao.perigos if apresentacao else ())
        }
        registro = item.registro_contexto or {}
        cobertura = (
            min(perigo.cobertura_percentual for perigo in apresentacao.perigos)
            if apresentacao
            else None
        )
        linhas.append(
            (
                item.id_fazenda,
                item.nome,
                str(item.fazenda.get("uf") or ""),
                _texto_numero(apresentacao.score_anterior if apresentacao else None),
                _texto_numero(apresentacao.score_atual if apresentacao else None),
                _texto_numero(apresentacao.variacao_pontos if apresentacao else None),
                _texto_numero(perigos.get(PerigoExposicao.EXPOSICAO_HIDRICA)),
                _texto_numero(perigos.get(PerigoExposicao.TRAFEGABILIDADE)),
                _texto_numero(perigos.get(PerigoExposicao.INSTABILIDADE)),
                _texto_numero(perigos.get(PerigoExposicao.INCENDIO)),
                _texto_numero(perigos.get(PerigoExposicao.TEMPESTADES)),
                _texto_numero(registro.get("declividade_media_graus"), 3),
                _texto_numero(registro.get("distancia_drenagem_m"), 1),
                _texto_numero(cobertura, 1),
                "OK" if item.falha is None else item.falha.erro,
            )
        )
    larguras = (
        [
            min(
                28,
                max(len(cabecalhos[indice]), *(len(linha[indice]) for linha in linhas)),
            )
            for indice in range(len(cabecalhos))
        ]
        if linhas
        else [len(cabecalho) for cabecalho in cabecalhos]
    )

    def formatar(linha: Sequence[str]) -> str:
        return " | ".join(
            valor[: larguras[indice]].ljust(larguras[indice])
            for indice, valor in enumerate(linha)
        )

    print(formatar(cabecalhos))
    print("-+-".join("-" * largura for largura in larguras))
    for linha in linhas:
        print(formatar(linha))
    print()
    print(f"Fazendas processadas: {len(execucoes)}")
    print(f"Falhas: {sum(item.falha is not None for item in execucoes)}")
    print("Arquivos gerados:")
    for caminho in caminhos:
        print(f"- {caminho.resolve()}")


def executar_diagnostico(
    *,
    data_referencia: date | None = None,
    diretorio_saida: Path = SAIDA_PADRAO,
    fazendas: Sequence[Mapping[str, Any]] | None = None,
    cliente_nasa: ClienteMeteorologicoHistorico | None = None,
    provedor_contexto: ProvedorContextoTerritorial | None = None,
    buscar_contexto: BuscadorContextoPersistido = buscar_registro_geoespacial,
) -> tuple[tuple[ExecucaoFazenda, ...], TabelasDiagnostico, tuple[Path, ...]]:
    referencia = data_referencia or date.today()
    cadastros = tuple(fazendas if fazendas is not None else listar_fazendas())
    execucoes = executar_fazendas(
        cadastros,
        data_referencia=referencia,
        cliente_nasa=cliente_nasa or ClienteNasaPowerHistorico(),
        provedor_contexto=(
            provedor_contexto or ProvedorContextoTerritorialPersistido()
        ),
        buscar_contexto=buscar_contexto,
    )
    tabelas = montar_tabelas(execucoes)
    caminhos = salvar_tabelas(tabelas, diretorio_saida)
    return execucoes, tabelas, caminhos


def criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Executa todas as fazendas com NASA POWER e exporta diagnostico "
            "do motor AGRISHIELD-EQUIP-v1.0."
        )
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=SAIDA_PADRAO,
        help=f"diretorio dos seis CSVs (default: {SAIDA_PADRAO})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argumentos = criar_parser().parse_args(argv)
    execucoes, _, caminhos = executar_diagnostico(
        diretorio_saida=argumentos.saida,
    )
    _resumo_terminal(execucoes, caminhos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
