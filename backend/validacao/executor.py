"""Executor sequencial e isolado do teste de mesa multi-regional."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
import re
import subprocess
from time import perf_counter
from typing import Any, Callable, Mapping

import pandas as pd

from backend.app.servicos_externos import consultar_open_meteo, geocoding_por_cep
from backend.etl.etapa2_coleta_nasa_power import coletar_nasa_power
from backend.etl.etapa3_engenharia_variaveis import (
    enriquecer,
    consolidar_para_dashboard,
)
from backend.etl.etapa4_dados_geoespaciais import consultar_dados_geoespaciais
from backend.inmet import (
    ClienteCatalogoInmet,
    ClienteHistoricoInmet,
    RepositorioInmetMemoria,
    ServicoInmet,
)
from backend.mapbiomas import (
    ANO_DEFAULT,
    ClienteEarthEngineMapBiomas,
    RepositorioMapBiomasMemoria,
    ServicoMapBiomas,
)
from backend.risco import (
    FreshnessStatus,
    agregar_features,
    calcular_features_climaticas,
    normalizar_cadastro,
    normalizar_geoespacial,
    normalizar_inmet,
    normalizar_mapbiomas,
    normalizar_nasa,
    normalizar_open_meteo,
)

from .modelos import (
    HARNESS_SCHEMA_VERSION,
    CenarioValidacao,
    ModoCenario,
    StatusFonte,
)
from .relatorio import comparar_resultados, para_json_compativel


FONTES = ("NASA_POWER", "OPEN_METEO", "INMET", "SRTM", "MERIT_HYDRO", "MAPBIOMAS")
LOOKBACK_DIAGNOSTICO_INMET_DIAS = 14
VARIAVEIS_INMET = (
    "temperatura_c",
    "precipitacao_mm",
    "umidade_pct",
    "pressao_hpa",
    "vento_m_s",
    "rajada_m_s",
    "direcao_vento_graus",
    "radiacao_kj_m2",
)
WARNING_GEOMETRIA_VALIDACAO = (
    "Geometria circular estimada por área e ponto de referência; não representa "
    "polígono real, cadastral ou fundiário e pode incluir áreas vizinhas."
)


@dataclass(frozen=True)
class DependenciasValidacao:
    geocodificar: Callable[[str], Mapping[str, Any]]
    nasa: Callable[[float, float, str, str], tuple[pd.DataFrame, str]]
    openmeteo: Callable[[float, float], Mapping[str, Any]]
    inmet: Callable[[Mapping[str, Any], date, date], Mapping[str, Any]]
    geoespacial: Callable[[float, float], Mapping[str, Any]]
    mapbiomas: Callable[[Mapping[str, Any], int], Mapping[str, Any]]


def _nasa_real(lat: float, lon: float, inicio: str, fim: str):
    return coletar_nasa_power(lat, lon, inicio, fim, salvar_csv=False)


def _inmet_real(referencia: Mapping[str, Any], inicio: date, fim: date):
    id_cenario = str(referencia["id_cenario"])
    fazenda = {
        "id_fazenda": id_cenario,
        "latitude": referencia["latitude"],
        "longitude": referencia["longitude"],
    }
    servico = ServicoInmet(
        cliente_catalogo=ClienteCatalogoInmet(),
        cliente_historico=ClienteHistoricoInmet(),
        repositorio=RepositorioInmetMemoria(),
        buscar_fazenda=lambda identificador: (
            fazenda if str(identificador) == id_cenario else None
        ),
    )
    return servico.coletar(id_cenario, data_inicio=inicio, data_fim=fim)


def _geoespacial_real(lat: float, lon: float):
    return consultar_dados_geoespaciais(lat, lon, usar_cache=False)


def _mapbiomas_real(referencia: Mapping[str, Any], ano: int):
    id_cenario = str(referencia["id_cenario"])
    fazenda = {
        "id_fazenda": id_cenario,
        "latitude": referencia["latitude"],
        "longitude": referencia["longitude"],
        "area_ha": referencia["area_ha"],
    }
    servico = ServicoMapBiomas(
        cliente=ClienteEarthEngineMapBiomas(),
        repositorio=RepositorioMapBiomasMemoria(),
        buscar_fazenda=lambda identificador: (
            fazenda if str(identificador) == id_cenario else None
        ),
    )
    resultado = servico.analisar(id_cenario, ano=ano)
    resultado["referencia"]["origem_coordenada"] = referencia["origem_coordenada"]
    resultado["referencia"]["precisao_espacial"] = "APROXIMADA"
    resultado["metadados"]["warning_geometria"] = WARNING_GEOMETRIA_VALIDACAO
    return resultado


def dependencias_reais() -> DependenciasValidacao:
    return DependenciasValidacao(
        geocodificar=geocoding_por_cep,
        nasa=_nasa_real,
        openmeteo=consultar_open_meteo,
        inmet=_inmet_real,
        geoespacial=_geoespacial_real,
        mapbiomas=_mapbiomas_real,
    )


def _erro_sanitizado(fonte: str, exc: Exception) -> dict[str, str]:
    mensagem = " ".join(str(exc).split())
    mensagem = re.sub(
        r"(?i)\b(token|authorization|credential|api[_ -]?key)\b"
        r"(\s*[:=]\s*)(?:bearer\s+)?\S+",
        r"\1\2[redacted]",
        mensagem,
    )[:300]
    return {
        "fonte": fonte,
        "codigo": type(exc).__name__,
        "mensagem": mensagem or "Falha sem detalhe seguro",
    }


def _status_qualidade(status: Any) -> StatusFonte:
    valor = getattr(status, "value", status)
    return {
        "DISPONIVEL": StatusFonte.SUCESSO,
        "SUCESSO": StatusFonte.SUCESSO,
        "PARCIAL": StatusFonte.PARCIAL,
        "AUSENTE": StatusFonte.AUSENTE,
        "INVALIDO": StatusFonte.ERRO,
        "ERRO": StatusFonte.ERRO,
    }.get(str(valor or "").upper(), StatusFonte.PARCIAL)


def _entrada_fonte(
    status: StatusFonte,
    duracao_ms: float,
    *,
    dados: Any = None,
    erro: Mapping[str, Any] | None = None,
    **metadados: Any,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "duracao_ms": round(duracao_ms, 3),
        "dados": dados,
        "erro": dict(erro) if erro else None,
        **metadados,
    }


def _resumo_observacoes(observacoes: list[Mapping[str, Any]]) -> dict[str, Any]:
    resumo: dict[str, Any] = {}
    for variavel in VARIAVEIS_INMET:
        valores = [
            float(item[variavel])
            for item in observacoes
            if item.get(variavel) is not None and math.isfinite(float(item[variavel]))
        ]
        resumo[variavel] = {
            "quantidade": len(valores),
            "minimo": min(valores) if valores else None,
            "maximo": max(valores) if valores else None,
            "media": sum(valores) / len(valores) if valores else None,
            "soma": sum(valores) if valores and variavel == "precipitacao_mm" else None,
        }
    return resumo


def _diagnostico_temporal_inmet(
    bruto: Mapping[str, Any],
    data_referencia: date,
    inicio_lookback: date,
) -> dict[str, Any]:
    observacoes_validas: list[tuple[datetime, Mapping[str, Any]]] = []
    for observacao in bruto.get("observacoes") or ():
        if not any(observacao.get(campo) is not None for campo in VARIAVEIS_INMET):
            continue
        valor = observacao.get("observado_em_utc")
        if not valor:
            continue
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
        if instante.tzinfo is None:
            raise ValueError("observação INMET sem timezone explícito")
        instante_utc = instante.astimezone(timezone.utc)
        if instante_utc.date() <= data_referencia:
            observacoes_validas.append((instante_utc, observacao))

    ultima = max((instante for instante, _ in observacoes_validas), default=None)
    if ultima is None:
        defasagem = None
        freshness = FreshnessStatus.AUSENTE
    else:
        defasagem = (data_referencia - ultima.date()).days
        if defasagem <= 1:
            freshness = FreshnessStatus.ATUAL
        elif defasagem <= 3:
            freshness = FreshnessStatus.DEFASADO
        else:
            freshness = FreshnessStatus.DESATUALIZADO
    inicio_operacional = max(
        date(data_referencia.year, 1, 1), data_referencia - timedelta(days=6)
    )

    def disponibilidade_chuva(inicio: date) -> dict[str, Any]:
        horas_esperadas = ((data_referencia - inicio).days + 1) * 24
        horas_disponiveis = len(
            {
                instante
                for instante, observacao in observacoes_validas
                if inicio <= instante.date() <= data_referencia
                and observacao.get("precipitacao_mm") is not None
            }
        )
        return {
            "inicio": inicio.isoformat(),
            "fim": data_referencia.isoformat(),
            "horas_esperadas": horas_esperadas,
            "horas_disponiveis_precipitacao": horas_disponiveis,
            "disponibilidade_precipitacao_pct": round(
                horas_disponiveis * 100.0 / horas_esperadas, 2
            ),
        }

    return {
        "data_referencia_solicitada": data_referencia.isoformat(),
        "ultima_observacao_disponivel": ultima.isoformat() if ultima else None,
        "defasagem_dias": defasagem,
        "freshness_status": freshness.value,
        "distancia_estacao_km": (bruto.get("estacao") or {}).get("distancia_km"),
        "lookback_diagnostico_dias": LOOKBACK_DIAGNOSTICO_INMET_DIAS,
        "janela_operacional": disponibilidade_chuva(inicio_operacional),
        "janela_lookback": disponibilidade_chuva(inicio_lookback),
        "qualidade_bruta_refere_se_a": "janela_lookback",
    }


class ExecutorValidacaoMultiregional:
    def __init__(
        self,
        dependencias: DependenciasValidacao | None = None,
        *,
        agora_utc: Callable[[], datetime] | None = None,
        cronometro: Callable[[], float] = perf_counter,
    ) -> None:
        self.dependencias = dependencias or dependencias_reais()
        self.agora_utc = agora_utc or (lambda: datetime.now(timezone.utc))
        self.cronometro = cronometro

    def _referencia(self, cenario: CenarioValidacao) -> dict[str, Any]:
        if cenario.modo == ModoCenario.CEP:
            geo = dict(self.dependencias.geocodificar(str(cenario.cep)))
            latitude = float(geo["latitude"])
            longitude = float(geo["longitude"])
            origem = "CEP"
            origem_detalhada = str(geo.get("origem") or "geocodificacao_atual")
        else:
            latitude = float(cenario.latitude)
            longitude = float(cenario.longitude)
            origem = "COORDENADA_INFORMADA"
            origem_detalhada = "PONTO_RURAL_DE_VALIDACAO"
        return {
            "id_cenario": cenario.id_cenario,
            "latitude": latitude,
            "longitude": longitude,
            "area_ha": cenario.area_ha,
            "cep": cenario.cep,
            "origem_coordenada": origem,
            "origem_coordenada_detalhada": origem_detalhada,
            "precisao_espacial": "APROXIMADA",
            "tipo_geometria": "ESTIMADA",
            "metodo_geometria": "circulo_equivalente_por_area",
            "warning": WARNING_GEOMETRIA_VALIDACAO,
        }

    @staticmethod
    def _cadastro(cenario: CenarioValidacao, referencia: Mapping[str, Any]):
        return normalizar_cadastro(
            {
                "id_fazenda": cenario.id_cenario,
                "nome_fazenda": cenario.nome,
                "numero_apolice": "",
                "cep": cenario.cep or "",
                "cidade": "",
                "uf": cenario.uf,
                "latitude": referencia["latitude"],
                "longitude": referencia["longitude"],
                "area_ha": cenario.area_ha,
                "tipo_operacao": cenario.tipo_operacao,
                "proximidade_agua": cenario.proximidade_agua_declarada,
            }
        )

    def _nasa(
        self,
        referencia: Mapping[str, Any],
        data_referencia: date,
    ) -> tuple[dict[str, Any], Any, Any, pd.DataFrame | None]:
        inicio = data_referencia - timedelta(days=39)
        tic = self.cronometro()
        try:
            dataframe, origem = self.dependencias.nasa(
                referencia["latitude"],
                referencia["longitude"],
                inicio.strftime("%Y%m%d"),
                data_referencia.strftime("%Y%m%d"),
            )
            serie = normalizar_nasa(
                dataframe, origem, {"id_fazenda": referencia["id_cenario"]}
            )
            features = calcular_features_climaticas(
                serie, data_referencia=data_referencia
            )
            status = _status_qualidade(serie.qualidade.status)
            if serie.qualidade.simulado:
                status = StatusFonte.PARCIAL
            dados = {
                "origem": origem,
                "simulado": serie.qualidade.simulado,
                "periodo": {
                    "inicio": inicio.isoformat(),
                    "fim": data_referencia.isoformat(),
                },
                "registros": dataframe.to_dict(orient="records"),
                "normalizado": serie,
                "features": features,
            }
            return (
                _entrada_fonte(status, (self.cronometro() - tic) * 1000, dados=dados),
                serie,
                features,
                dataframe,
            )
        except Exception as exc:
            return (
                _entrada_fonte(
                    StatusFonte.ERRO,
                    (self.cronometro() - tic) * 1000,
                    erro=_erro_sanitizado("NASA_POWER", exc),
                ),
                None,
                None,
                None,
            )

    def _openmeteo(self, referencia: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
        tic = self.cronometro()
        try:
            bruto = dict(
                self.dependencias.openmeteo(
                    referencia["latitude"], referencia["longitude"]
                )
            )
            serie = normalizar_open_meteo(bruto)
            status = _status_qualidade(serie.qualidade.status)
            if serie.qualidade.simulado:
                status = StatusFonte.PARCIAL
            return (
                _entrada_fonte(
                    status,
                    (self.cronometro() - tic) * 1000,
                    dados={
                        "bruto": bruto,
                        "normalizado": serie,
                        "evidencia_meteorologica_real": not serie.qualidade.simulado,
                    },
                ),
                serie,
            )
        except Exception as exc:
            return (
                _entrada_fonte(
                    StatusFonte.ERRO,
                    (self.cronometro() - tic) * 1000,
                    erro=_erro_sanitizado("OPEN_METEO", exc),
                ),
                None,
            )

    def _inmet(
        self,
        referencia: Mapping[str, Any],
        data_referencia: date,
    ) -> tuple[dict[str, Any], Any]:
        fim = data_referencia
        inicio = max(
            date(fim.year, 1, 1),
            fim - timedelta(days=LOOKBACK_DIAGNOSTICO_INMET_DIAS - 1),
        )
        tic = self.cronometro()
        try:
            bruto = dict(self.dependencias.inmet(referencia, inicio, fim))
            serie = normalizar_inmet(bruto)
            status = _status_qualidade(serie.qualidade.status)
            qualidade = bruto.get("qualidade") or {}
            esperadas = qualidade.get("horas_esperadas")
            observadas = qualidade.get("horas_observadas")
            if esperadas and not observadas:
                status = StatusFonte.AUSENTE
            elif esperadas and float(observadas) < float(esperadas):
                status = StatusFonte.PARCIAL
            return (
                _entrada_fonte(
                    status,
                    (self.cronometro() - tic) * 1000,
                    dados={
                        "bruto": bruto,
                        "normalizado": serie,
                        "resumo_variaveis": _resumo_observacoes(
                            bruto.get("observacoes") or []
                        ),
                        "diagnostico_temporal": _diagnostico_temporal_inmet(
                            bruto, data_referencia, inicio
                        ),
                    },
                ),
                serie,
            )
        except Exception as exc:
            return (
                _entrada_fonte(
                    StatusFonte.ERRO,
                    (self.cronometro() - tic) * 1000,
                    erro=_erro_sanitizado("INMET", exc),
                ),
                None,
            )

    @staticmethod
    def _status_atributos(
        atributos: list[Mapping[str, Any]], erros: list[Any]
    ) -> StatusFonte:
        disponiveis = sum(item.get("valor") is not None for item in atributos)
        if disponiveis == len(atributos):
            return StatusFonte.SUCESSO
        if disponiveis:
            return StatusFonte.PARCIAL
        return StatusFonte.ERRO if erros else StatusFonte.AUSENTE

    def _geoespacial(
        self,
        referencia: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], Any]:
        tic = self.cronometro()
        try:
            bruto = dict(
                self.dependencias.geoespacial(
                    referencia["latitude"], referencia["longitude"]
                )
            )
            duracao = (self.cronometro() - tic) * 1000
            normalizado = normalizar_geoespacial(bruto)
            atributos = bruto.get("atributos") or {}
            erros = list(bruto.get("erros") or [])
            srtm_atributos = {
                chave: atributos.get(chave)
                for chave in ("declividade_media", "posicao_topografica_relativa")
            }
            merit_atributos = {
                chave: atributos.get(chave)
                for chave in ("distancia_drenagem", "area_drenagem_montante")
            }
            srtm_erros = [
                item for item in erros if "SRTM" in str(item.get("fonte", "")).upper()
            ]
            merit_erros = [
                item for item in erros if "MERIT" in str(item.get("fonte", "")).upper()
            ]
            if (
                erros
                and not srtm_erros
                and not any(
                    item and item.get("valor") is not None
                    for item in srtm_atributos.values()
                )
            ):
                srtm_erros = erros
            if (
                erros
                and not merit_erros
                and not any(
                    item and item.get("valor") is not None
                    for item in merit_atributos.values()
                )
            ):
                merit_erros = erros
            comuns = {
                "parametros": bruto.get("parametros"),
                "qualidade": bruto.get("qualidade"),
                "schema_version": bruto.get("schema_version"),
                "algorithm_version": bruto.get("algorithm_version"),
            }
            srtm = _entrada_fonte(
                self._status_atributos(list(srtm_atributos.values()), srtm_erros),
                duracao,
                dados={**comuns, "atributos": srtm_atributos, "erros": srtm_erros},
                duracao_compartilhada=True,
            )
            merit = _entrada_fonte(
                self._status_atributos(list(merit_atributos.values()), merit_erros),
                duracao,
                dados={**comuns, "atributos": merit_atributos, "erros": merit_erros},
                duracao_compartilhada=True,
            )
            return srtm, merit, normalizado
        except Exception as exc:
            duracao = (self.cronometro() - tic) * 1000
            return (
                _entrada_fonte(
                    StatusFonte.ERRO,
                    duracao,
                    erro=_erro_sanitizado("SRTM", exc),
                    duracao_compartilhada=True,
                ),
                _entrada_fonte(
                    StatusFonte.ERRO,
                    duracao,
                    erro=_erro_sanitizado("MERIT_HYDRO", exc),
                    duracao_compartilhada=True,
                ),
                None,
            )

    def _mapbiomas(
        self,
        referencia: Mapping[str, Any],
        ano: int,
    ) -> tuple[dict[str, Any], Any]:
        tic = self.cronometro()
        try:
            bruto = dict(self.dependencias.mapbiomas(referencia, ano))
            normalizado = normalizar_mapbiomas(bruto)
            return (
                _entrada_fonte(
                    _status_qualidade(normalizado.qualidade.status),
                    (self.cronometro() - tic) * 1000,
                    dados={"bruto": bruto, "normalizado": normalizado},
                ),
                normalizado,
            )
        except Exception as exc:
            return (
                _entrada_fonte(
                    StatusFonte.ERRO,
                    (self.cronometro() - tic) * 1000,
                    erro=_erro_sanitizado("MAPBIOMAS", exc),
                ),
                None,
            )

    @staticmethod
    def _score_legado(
        dataframe: pd.DataFrame | None,
        *,
        tipo_operacao: str,
        proximidade_agua: bool | None,
        origem_nasa: str | None,
        nasa_simulada: bool | None,
    ) -> dict[str, Any]:
        if dataframe is None or nasa_simulada is True or proximidade_agua is None:
            if dataframe is None:
                motivo = "serie_nasa_indisponivel"
            elif nasa_simulada is True:
                motivo = "serie_nasa_sintetica"
            else:
                motivo = "proximidade_agua_declarada_ausente"
            return {
                "status": StatusFonte.NAO_EXECUTADO.value,
                "score_tipo": "LEGADO",
                "motivo": motivo,
                "score": None,
                "estado": None,
                "origem_nasa": origem_nasa,
            }
        try:
            enriquecido = enriquecer(dataframe)
            resumo = consolidar_para_dashboard(
                enriquecido,
                tipo_operacao=tipo_operacao,
                proximidade_agua=bool(proximidade_agua),
            )
            return {
                "status": "EXECUTADO",
                "score_tipo": "LEGADO",
                "score": resumo.get("score"),
                "estado": resumo.get("condicao_atual"),
                "fatores": resumo.get("fatores_risco"),
                "variaveis_usadas": resumo.get("metricas_dia"),
                "origem_nasa": origem_nasa,
                "observacao": (
                    "Score legado reproduzido sem consumir INMET, Open-Meteo, "
                    "SRTM/MERIT, MapBiomas ou camada canônica."
                ),
            }
        except Exception as exc:
            return {
                "status": StatusFonte.NAO_EXECUTADO.value,
                "score_tipo": "LEGADO",
                "motivo": "calculo_legado_falhou",
                "erro": _erro_sanitizado("SCORE_LEGADO", exc),
                "score": None,
                "estado": None,
            }

    @staticmethod
    def _status_cenario(fontes: Mapping[str, Mapping[str, Any]]) -> StatusFonte:
        statuses = [item.get("status") for item in fontes.values()]
        utilizaveis = {StatusFonte.SUCESSO.value, StatusFonte.PARCIAL.value}
        if not any(status in utilizaveis for status in statuses):
            return StatusFonte.ERRO
        if all(status == StatusFonte.SUCESSO.value for status in statuses):
            return StatusFonte.SUCESSO
        return StatusFonte.PARCIAL

    def executar_cenario(
        self,
        cenario: CenarioValidacao,
        *,
        data_referencia: date,
        ano_mapbiomas: int = ANO_DEFAULT,
    ) -> dict[str, Any]:
        inicio_total = self.cronometro()
        parametros = cenario.model_dump(mode="json")
        try:
            referencia = self._referencia(cenario)
            cadastro = self._cadastro(cenario, referencia)
        except Exception as exc:
            fontes = {
                fonte: _entrada_fonte(StatusFonte.NAO_EXECUTADO, 0.0)
                for fonte in FONTES
            }
            return para_json_compativel(
                {
                    "id_cenario": cenario.id_cenario,
                    "tipo": "TESTE_DE_MESA",
                    "parametros": parametros,
                    "referencia": None,
                    "fontes": fontes,
                    "camada_canonica": None,
                    "score_legado": {
                        "status": StatusFonte.NAO_EXECUTADO.value,
                        "score_tipo": "LEGADO",
                        "motivo": "referencia_espacial_indisponivel",
                    },
                    "erros": [_erro_sanitizado("REFERENCIA", exc)],
                    "status_execucao": StatusFonte.ERRO.value,
                    "duracoes_ms": {
                        "total_ms": round((self.cronometro() - inicio_total) * 1000, 3)
                    },
                }
            )

        fontes: dict[str, Any] = {}
        nasa, serie_nasa, climaticas, dataframe_nasa = self._nasa(
            referencia, data_referencia
        )
        fontes["NASA_POWER"] = nasa
        openmeteo, _ = self._openmeteo(referencia)
        fontes["OPEN_METEO"] = openmeteo
        inmet, _ = self._inmet(referencia, data_referencia)
        fontes["INMET"] = inmet
        srtm, merit, geo_normalizado = self._geoespacial(referencia)
        fontes["SRTM"] = srtm
        fontes["MERIT_HYDRO"] = merit
        mapa, mapa_normalizado = self._mapbiomas(referencia, ano_mapbiomas)
        fontes["MAPBIOMAS"] = mapa

        conjunto = agregar_features(
            cadastro=cadastro,
            climaticas=climaticas,
            geoespacial=geo_normalizado,
            territorial=mapa_normalizado,
            calculado_em_utc=self.agora_utc(),
        )
        score = self._score_legado(
            dataframe_nasa,
            tipo_operacao=cenario.tipo_operacao,
            proximidade_agua=cenario.proximidade_agua_declarada,
            origem_nasa=(nasa.get("dados") or {}).get("origem"),
            nasa_simulada=(
                serie_nasa.qualidade.simulado if serie_nasa is not None else None
            ),
        )
        erros = [item["erro"] for item in fontes.values() if item.get("erro")]
        status = self._status_cenario(fontes)
        total_ms = (self.cronometro() - inicio_total) * 1000
        return para_json_compativel(
            {
                "id_cenario": cenario.id_cenario,
                "tipo": "TESTE_DE_MESA",
                "classificacao": cenario.classificacao,
                "parametros": parametros,
                "referencia": referencia,
                "fontes": fontes,
                "camada_canonica": conjunto,
                "score_legado": score,
                "erros": erros,
                "status_execucao": status.value,
                "duracoes_ms": {
                    "nasa_ms": nasa["duracao_ms"],
                    "openmeteo_ms": openmeteo["duracao_ms"],
                    "inmet_ms": inmet["duracao_ms"],
                    "geoespacial_ms": max(srtm["duracao_ms"], merit["duracao_ms"]),
                    "mapbiomas_ms": mapa["duracao_ms"],
                    "total_ms": round(total_ms, 3),
                },
            }
        )

    def executar(
        self,
        cenarios: list[CenarioValidacao],
        *,
        data_referencia: date,
        ano_mapbiomas: int = ANO_DEFAULT,
    ) -> dict[str, Any]:
        instante = self.agora_utc()
        if instante.tzinfo is None:
            raise ValueError("agora_utc deve retornar datetime com timezone")
        resultados = [
            self.executar_cenario(
                cenario, data_referencia=data_referencia, ano_mapbiomas=ano_mapbiomas
            )
            for cenario in cenarios
        ]
        return para_json_compativel(
            {
                "schema_version": HARNESS_SCHEMA_VERSION,
                "tipo": "VALIDACAO_MULTI_REGIONAL",
                "executado_em_utc": instante.astimezone(timezone.utc),
                "git_commit": _git_commit(),
                "parametros_execucao": {
                    "data_referencia": data_referencia,
                    "ano_mapbiomas": ano_mapbiomas,
                    "execucao": "SEQUENCIAL",
                    "quantidade_cenarios": len(cenarios),
                },
                "resultados": resultados,
                "comparativo": comparar_resultados(resultados),
            }
        )


def _git_commit() -> str | None:
    try:
        processo = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return processo.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


__all__ = [
    "DependenciasValidacao",
    "ExecutorValidacaoMultiregional",
    "FONTES",
    "WARNING_GEOMETRIA_VALIDACAO",
    "dependencias_reais",
]
