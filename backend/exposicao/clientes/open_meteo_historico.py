"""Cliente isolado do Open-Meteo Historical com dataset ERA5-Land fixo."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from math import isfinite
from types import MappingProxyType
from typing import Any, Callable, Protocol

import requests
from pydantic import ValidationError

from backend.exposicao.modelos import (
    JanelaHistorica,
    ReferenciaTemporalHistorica,
    RegistroMeteorologicoDiario,
    SerieHistoricaFonte,
    TipoProdutoHistorico,
    TipoReferenciaTemporal,
)
from backend.risco.modelos import FonteDado


ENDPOINT_OPEN_METEO_HISTORICAL = "https://archive-api.open-meteo.com/v1/archive"
DATASET_OPEN_METEO_HISTORICAL = "ERA5-Land"
MODELO_OPEN_METEO_HISTORICAL = "era5_land"
TIMEZONE_OPEN_METEO_HISTORICAL = "UTC"
VARIAVEIS_DIARIAS_OPEN_METEO = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "relative_humidity_2m_mean",
    "wind_speed_10m_mean",
)
MAPEAMENTO_REGISTRO = MappingProxyType(
    {
        "precipitation_sum": "precipitacao_mm",
        "temperature_2m_mean": "temperatura_media_c",
        "temperature_2m_max": "temperatura_maxima_c",
        "temperature_2m_min": "temperatura_minima_c",
        "relative_humidity_2m_mean": "umidade_media_pct",
        "wind_speed_10m_mean": "velocidade_vento_media_m_s",
    }
)
UNIDADES_ESPERADAS = MappingProxyType(
    {
        "time": "iso8601",
        "temperature_2m_mean": "°C",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_sum": "mm",
        "relative_humidity_2m_mean": "%",
        "wind_speed_10m_mean": "m/s",
    }
)
TIMEOUT_PADRAO = (5.0, 30.0)


class ErroOpenMeteoHistorico(RuntimeError):
    """Erro de domínio base do cliente Open-Meteo Historical."""


class ErroParametroOpenMeteoHistorico(ErroOpenMeteoHistorico):
    """Entrada ou configuração local inválida."""


class ErroTransporteOpenMeteoHistorico(ErroOpenMeteoHistorico):
    """Falha de rede ou timeout ao consultar a fonte."""


class ErroHttpOpenMeteoHistorico(ErroOpenMeteoHistorico):
    """Resposta HTTP sem sucesso, sem exposição do corpo externo."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"Open-Meteo Historical respondeu com HTTP {status_code}")


class ErroContratoOpenMeteoHistorico(ErroOpenMeteoHistorico):
    """Resposta incompatível com o contrato histórico solicitado."""


class TransporteHttp(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _validar_coordenadas(latitude: float, longitude: float) -> tuple[float, float]:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ErroParametroOpenMeteoHistorico(
            "latitude e longitude devem ser numéricas"
        )
    try:
        latitude_normalizada = float(latitude)
        longitude_normalizada = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ErroParametroOpenMeteoHistorico(
            "latitude e longitude devem ser numéricas"
        ) from exc
    if not isfinite(latitude_normalizada) or not -90 <= latitude_normalizada <= 90:
        raise ErroParametroOpenMeteoHistorico("latitude fora do domínio permitido")
    if not isfinite(longitude_normalizada) or not -180 <= longitude_normalizada <= 180:
        raise ErroParametroOpenMeteoHistorico("longitude fora do domínio permitido")
    return latitude_normalizada, longitude_normalizada


def _validar_timeout(
    timeout: float | tuple[float, float]
) -> float | tuple[float, float]:
    valores = timeout if isinstance(timeout, tuple) else (timeout,)
    if len(valores) not in (1, 2):
        raise ErroParametroOpenMeteoHistorico(
            "timeout deve ser escalar ou par conexão/leitura"
        )
    if any(isinstance(valor, bool) for valor in valores):
        raise ErroParametroOpenMeteoHistorico("timeout deve ser numérico")
    try:
        normalizados = tuple(float(valor) for valor in valores)
    except (TypeError, ValueError) as exc:
        raise ErroParametroOpenMeteoHistorico("timeout deve ser numérico") from exc
    if any(not isfinite(valor) or valor <= 0 for valor in normalizados):
        raise ErroParametroOpenMeteoHistorico(
            "timeout deve conter valores positivos e finitos"
        )
    return normalizados[0] if len(normalizados) == 1 else normalizados


def _converter_valor(variavel: str, data_valor: date, valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroContratoOpenMeteoHistorico(
            f"valor não numérico para {variavel} em {data_valor.isoformat()}"
        )
    numero = float(valor)
    if not isfinite(numero):
        raise ErroContratoOpenMeteoHistorico(
            f"valor não finito para {variavel} em {data_valor.isoformat()}"
        )
    return numero


def _validar_timezone(payload: dict[str, Any]) -> tuple[str, int]:
    timezone_resposta = payload.get("timezone")
    if timezone_resposta not in {"UTC", "GMT"}:
        raise ErroContratoOpenMeteoHistorico(
            "timezone da resposta incompatível com UTC solicitado"
        )
    offset = payload.get("utc_offset_seconds")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset != 0:
        raise ErroContratoOpenMeteoHistorico(
            "utc_offset_seconds incompatível com UTC solicitado"
        )
    return timezone_resposta, offset


def _validar_unidades(payload: dict[str, Any]) -> dict[str, str]:
    unidades = payload.get("daily_units")
    if not isinstance(unidades, dict):
        raise ErroContratoOpenMeteoHistorico("daily_units ausente ou inválido")
    normalizadas: dict[str, str] = {}
    for variavel, esperada in UNIDADES_ESPERADAS.items():
        recebida = unidades.get(variavel)
        if recebida != esperada:
            raise ErroContratoOpenMeteoHistorico(
                f"unidade incompatível para {variavel}"
            )
        normalizadas[variavel] = recebida
    return normalizadas


def _extrair_dados_diarios(
    payload: Any,
    janela: JanelaHistorica,
) -> tuple[dict[date, dict[str, float | None]], dict[str, str], str, int]:
    if not isinstance(payload, dict):
        raise ErroContratoOpenMeteoHistorico("resposta JSON deve ser um objeto")
    timezone_resposta, offset = _validar_timezone(payload)
    unidades = _validar_unidades(payload)
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise ErroContratoOpenMeteoHistorico("daily ausente ou inválido")

    datas_brutas = daily.get("time")
    if not isinstance(datas_brutas, list) or not datas_brutas:
        raise ErroContratoOpenMeteoHistorico("daily.time ausente, vazio ou inválido")
    tamanho = len(datas_brutas)
    arrays: dict[str, list[Any]] = {}
    for variavel in VARIAVEIS_DIARIAS_OPEN_METEO:
        valores = daily.get(variavel)
        if not isinstance(valores, list):
            raise ErroContratoOpenMeteoHistorico(
                f"daily.{variavel} ausente ou inválido"
            )
        if len(valores) != tamanho:
            raise ErroContratoOpenMeteoHistorico(
                f"daily.{variavel} possui tamanho incompatível com daily.time"
            )
        arrays[variavel] = valores

    datas: list[date] = []
    for data_bruta in datas_brutas:
        if (
            not isinstance(data_bruta, str)
            or len(data_bruta) != 10
            or data_bruta[4:5] != "-"
            or data_bruta[7:8] != "-"
        ):
            raise ErroContratoOpenMeteoHistorico("daily.time contém data inválida")
        try:
            data_convertida = date.fromisoformat(data_bruta)
        except ValueError as exc:
            raise ErroContratoOpenMeteoHistorico(
                f"data diária inválida: {data_bruta}"
            ) from exc
        if data_convertida < janela.inicio or data_convertida > janela.fim:
            raise ErroContratoOpenMeteoHistorico(
                f"data diária fora da janela: {data_bruta}"
            )
        datas.append(data_convertida)
    if len(datas) != len(set(datas)):
        raise ErroContratoOpenMeteoHistorico("daily.time contém datas duplicadas")

    por_data: dict[date, dict[str, float | None]] = {}
    for indice, data_valor in enumerate(datas):
        por_data[data_valor] = {
            variavel: _converter_valor(variavel, data_valor, valores[indice])
            for variavel, valores in arrays.items()
        }
    return por_data, unidades, timezone_resposta, offset


def _construir_registros(
    dados_por_data: dict[date, dict[str, float | None]],
    janela: JanelaHistorica,
) -> tuple[RegistroMeteorologicoDiario, ...]:
    registros: list[RegistroMeteorologicoDiario] = []
    dia = janela.inicio
    while dia <= janela.fim:
        dados_dia = dados_por_data.get(dia, {})
        valores = {
            campo: dados_dia.get(variavel)
            for variavel, campo in MAPEAMENTO_REGISTRO.items()
        }
        try:
            registros.append(RegistroMeteorologicoDiario(data=dia, **valores))
        except ValidationError as exc:
            raise ErroContratoOpenMeteoHistorico(
                f"valores meteorológicos inválidos em {dia.isoformat()}"
            ) from exc
        dia += timedelta(days=1)
    return tuple(registros)


class ClienteOpenMeteoHistorico:
    """Consulta ERA5-Land em uma única requisição, sem Forecast ou fallback.

    O período solicitado permanece fixo. O período efetivo é o envelope da
    primeira à última data com algum valor suportado válido; gaps não são
    eliminados nem preenchidos.
    """

    def __init__(
        self,
        *,
        transporte: TransporteHttp | None = None,
        timeout: float | tuple[float, float] = TIMEOUT_PADRAO,
        relogio_utc: Callable[[], datetime] = _agora_utc,
    ):
        self._transporte = transporte if transporte is not None else requests
        self._timeout = _validar_timeout(timeout)
        self._relogio_utc = relogio_utc

    def consultar(
        self,
        latitude: float,
        longitude: float,
        janela: JanelaHistorica,
        *,
        id_fazenda: str | None = None,
    ) -> SerieHistoricaFonte:
        latitude, longitude = _validar_coordenadas(latitude, longitude)
        if not isinstance(janela, JanelaHistorica):
            raise ErroParametroOpenMeteoHistorico(
                "janela deve ser uma JanelaHistorica válida"
            )
        if janela.dias_esperados not in {90, 180, 187}:
            raise ErroParametroOpenMeteoHistorico(
                "cliente suporta janelas de 90, 180 ou 187 dias"
            )

        parametros_requisicao = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": janela.inicio.isoformat(),
            "end_date": janela.fim.isoformat(),
            "daily": ",".join(VARIAVEIS_DIARIAS_OPEN_METEO),
            "models": MODELO_OPEN_METEO_HISTORICAL,
            "timezone": TIMEZONE_OPEN_METEO_HISTORICAL,
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "wind_speed_unit": "ms",
            "timeformat": "iso8601",
        }
        try:
            resposta_http = self._transporte.get(
                ENDPOINT_OPEN_METEO_HISTORICAL,
                params=parametros_requisicao,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise ErroTransporteOpenMeteoHistorico(
                "timeout ao consultar Open-Meteo Historical"
            ) from exc
        except requests.RequestException as exc:
            raise ErroTransporteOpenMeteoHistorico(
                "falha de rede ao consultar Open-Meteo Historical"
            ) from exc

        status_code = getattr(resposta_http, "status_code", None)
        if status_code != 200:
            if not isinstance(status_code, int):
                raise ErroContratoOpenMeteoHistorico(
                    "resposta HTTP sem status_code válido"
                )
            raise ErroHttpOpenMeteoHistorico(status_code)
        try:
            payload = resposta_http.json()
        except (TypeError, ValueError) as exc:
            raise ErroContratoOpenMeteoHistorico(
                "resposta do Open-Meteo Historical não contém JSON válido"
            ) from exc

        dados, unidades, timezone_resposta, offset = _extrair_dados_diarios(
            payload, janela
        )
        registros = _construir_registros(dados, janela)
        coletado_em_utc = self._relogio_utc()
        if (
            not isinstance(coletado_em_utc, datetime)
            or coletado_em_utc.tzinfo is None
            or coletado_em_utc.utcoffset() is None
        ):
            raise ErroParametroOpenMeteoHistorico(
                "relógio UTC deve retornar datetime com timezone"
            )

        return SerieHistoricaFonte.criar(
            id_fazenda=id_fazenda,
            fonte=FonteDado.OPEN_METEO,
            tipo_produto=TipoProdutoHistorico.REANALISE_MODELADA,
            dataset=DATASET_OPEN_METEO_HISTORICAL,
            periodo_solicitado=janela,
            referencia_temporal=ReferenciaTemporalHistorica(
                tipo=TipoReferenciaTemporal.UTC,
                timezone="UTC",
                descricao=(
                    "Agregações diárias ERA5-Land solicitadas em UTC; sem "
                    "conversão ou reconciliação com dias NASA POWER LST"
                ),
            ),
            registros=registros,
            coletado_em_utc=coletado_em_utc,
            metadados_origem={
                "endpoint": ENDPOINT_OPEN_METEO_HISTORICAL,
                "dataset": DATASET_OPEN_METEO_HISTORICAL,
                "modelo_api": MODELO_OPEN_METEO_HISTORICAL,
                "latitude": latitude,
                "longitude": longitude,
                "variaveis_solicitadas": VARIAVEIS_DIARIAS_OPEN_METEO,
                "unidades": unidades,
                "timezone_solicitado": TIMEZONE_OPEN_METEO_HISTORICAL,
                "timezone_resposta": timezone_resposta,
                "utc_offset_seconds": offset,
                "inicio_solicitado": parametros_requisicao["start_date"],
                "fim_solicitado": parametros_requisicao["end_date"],
                "dias_solicitados": janela.dias_esperados,
                "vento": {
                    "parametro_fonte": "wind_speed_10m_mean",
                    "variavel_canonica": "velocidade_vento_media_m_s",
                    "unidade": "m/s",
                    "altura_m": 10,
                    "agregacao_temporal": "media_diaria",
                    "referencia_temporal": "UTC",
                },
            },
        )


def consultar_open_meteo_historico(
    latitude: float,
    longitude: float,
    janela: JanelaHistorica,
    *,
    id_fazenda: str | None = None,
    transporte: TransporteHttp | None = None,
    timeout: float | tuple[float, float] = TIMEOUT_PADRAO,
) -> SerieHistoricaFonte:
    """Fachada funcional estrita, sem estado compartilhado entre chamadas."""

    cliente = ClienteOpenMeteoHistorico(
        transporte=transporte,
        timeout=timeout,
    )
    return cliente.consultar(
        latitude,
        longitude,
        janela,
        id_fazenda=id_fazenda,
    )


__all__ = [
    "DATASET_OPEN_METEO_HISTORICAL",
    "ENDPOINT_OPEN_METEO_HISTORICAL",
    "MAPEAMENTO_REGISTRO",
    "MODELO_OPEN_METEO_HISTORICAL",
    "TIMEZONE_OPEN_METEO_HISTORICAL",
    "UNIDADES_ESPERADAS",
    "VARIAVEIS_DIARIAS_OPEN_METEO",
    "ClienteOpenMeteoHistorico",
    "ErroContratoOpenMeteoHistorico",
    "ErroHttpOpenMeteoHistorico",
    "ErroOpenMeteoHistorico",
    "ErroParametroOpenMeteoHistorico",
    "ErroTransporteOpenMeteoHistorico",
    "consultar_open_meteo_historico",
]
