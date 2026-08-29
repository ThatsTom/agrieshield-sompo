"""Cliente estrito do produto diário NASA POWER para séries históricas."""

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


ENDPOINT_NASA_POWER_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/point"
DATASET_NASA_POWER_DAILY = "NASA POWER Daily Point"
PARAMETROS_NASA_POWER = (
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "RH2M",
    "ALLSKY_SFC_SW_DWN",
    "WS2M",
)
MAPEAMENTO_REGISTRO = MappingProxyType(
    {
        "PRECTOTCORR": "precipitacao_mm",
        "T2M": "temperatura_media_c",
        "T2M_MAX": "temperatura_maxima_c",
        "T2M_MIN": "temperatura_minima_c",
        "RH2M": "umidade_media_pct",
        "WS2M": "velocidade_vento_media_m_s",
    }
)
SENTINELA_NASA = -999.0
TIMEOUT_PADRAO = (5.0, 30.0)


class ErroNasaPowerHistorico(RuntimeError):
    """Erro de domínio base do cliente histórico NASA POWER."""


class ErroParametroNasaPower(ErroNasaPowerHistorico):
    """Entrada local inválida antes da chamada externa."""


class ErroTransporteNasaPower(ErroNasaPowerHistorico):
    """Falha de rede ou timeout ao consultar a fonte."""


class ErroHttpNasaPower(ErroNasaPowerHistorico):
    """Resposta HTTP sem sucesso, sem exposição do corpo externo."""

    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"NASA POWER respondeu com HTTP {status_code}")


class ErroContratoNasaPower(ErroNasaPowerHistorico):
    """Resposta não corresponde ao contrato esperado da fonte."""


class TransporteHttp(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _validar_coordenadas(latitude: float, longitude: float) -> tuple[float, float]:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        raise ErroParametroNasaPower("latitude e longitude devem ser numéricas")
    try:
        latitude_normalizada = float(latitude)
        longitude_normalizada = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ErroParametroNasaPower(
            "latitude e longitude devem ser numéricas"
        ) from exc
    if not isfinite(latitude_normalizada) or not -90 <= latitude_normalizada <= 90:
        raise ErroParametroNasaPower("latitude fora do domínio permitido")
    if not isfinite(longitude_normalizada) or not -180 <= longitude_normalizada <= 180:
        raise ErroParametroNasaPower("longitude fora do domínio permitido")
    return latitude_normalizada, longitude_normalizada


def _validar_timeout(
    timeout: float | tuple[float, float]
) -> float | tuple[float, float]:
    valores = timeout if isinstance(timeout, tuple) else (timeout,)
    if len(valores) not in (1, 2):
        raise ErroParametroNasaPower("timeout deve ser escalar ou par conexão/leitura")
    if any(isinstance(valor, bool) for valor in valores):
        raise ErroParametroNasaPower("timeout deve ser numérico")
    try:
        normalizados = tuple(float(valor) for valor in valores)
    except (TypeError, ValueError) as exc:
        raise ErroParametroNasaPower("timeout deve ser numérico") from exc
    if any(not isfinite(valor) or valor <= 0 for valor in normalizados):
        raise ErroParametroNasaPower("timeout deve conter valores positivos e finitos")
    return normalizados[0] if len(normalizados) == 1 else normalizados


def _converter_valor(parametro: str, data_chave: str, valor: Any) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroContratoNasaPower(
            f"valor não numérico para {parametro} em {data_chave}"
        )
    valor_float = float(valor)
    if not isfinite(valor_float):
        raise ErroContratoNasaPower(
            f"valor não finito para {parametro} em {data_chave}"
        )
    if valor_float == SENTINELA_NASA:
        return None
    return valor_float


def _extrair_parametros(
    resposta: Any, janela: JanelaHistorica
) -> tuple[dict[str, dict[str, Any]], tuple[str, ...]]:
    if not isinstance(resposta, dict):
        raise ErroContratoNasaPower("resposta JSON deve ser um objeto")
    propriedades = resposta.get("properties")
    if not isinstance(propriedades, dict):
        raise ErroContratoNasaPower("resposta sem objeto properties")
    parametros = propriedades.get("parameter")
    if not isinstance(parametros, dict) or not parametros:
        raise ErroContratoNasaPower("resposta sem parâmetros meteorológicos")

    retornados = tuple(sorted(str(nome) for nome in parametros))
    parametros_validados: dict[str, dict[str, Any]] = {}
    for nome in PARAMETROS_NASA_POWER:
        if nome not in parametros:
            continue
        serie = parametros[nome]
        if not isinstance(serie, dict):
            raise ErroContratoNasaPower(f"série do parâmetro {nome} deve ser um objeto")
        for data_chave in serie:
            if (
                not isinstance(data_chave, str)
                or len(data_chave) != 8
                or not data_chave.isdigit()
            ):
                raise ErroContratoNasaPower(f"data inválida no parâmetro {nome}")
            try:
                data_valor = datetime.strptime(data_chave, "%Y%m%d").date()
            except ValueError as exc:
                raise ErroContratoNasaPower(
                    f"data inválida no parâmetro {nome}: {data_chave}"
                ) from exc
            if data_valor < janela.inicio or data_valor > janela.fim:
                raise ErroContratoNasaPower(
                    f"data fora da janela no parâmetro {nome}: {data_chave}"
                )
        parametros_validados[nome] = serie
    return parametros_validados, retornados


def _construir_registros(
    parametros: dict[str, dict[str, Any]], janela: JanelaHistorica
) -> tuple[RegistroMeteorologicoDiario, ...]:
    registros: list[RegistroMeteorologicoDiario] = []
    dia = janela.inicio
    while dia <= janela.fim:
        data_chave = dia.strftime("%Y%m%d")
        valores: dict[str, float | None] = {}
        flags: list[str] = []
        for parametro, campo in MAPEAMENTO_REGISTRO.items():
            serie_parametro = parametros.get(parametro, {})
            valor_bruto = serie_parametro.get(data_chave)
            valor = _converter_valor(parametro, data_chave, valor_bruto)
            valores[campo] = valor
            if valor_bruto is not None and valor is None:
                flags.append(f"SENTINELA_NASA:{parametro}")
        try:
            registros.append(
                RegistroMeteorologicoDiario(
                    data=dia,
                    **valores,
                    flags_qualidade=tuple(flags),
                )
            )
        except ValidationError as exc:
            raise ErroContratoNasaPower(
                f"valores meteorológicos inválidos em {data_chave}"
            ) from exc
        dia += timedelta(days=1)
    return tuple(registros)


class ClienteNasaPowerHistorico:
    """Consulta uma janela completa em uma única requisição, sem fallback.

    O período solicitado nunca muda. O período efetivo da série é o envelope
    entre o primeiro e o último dia com ao menos um valor suportado válido;
    lacunas internas e finais continuam preservadas nos registros e na qualidade.
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
            raise ErroParametroNasaPower("janela deve ser uma JanelaHistorica válida")
        if janela.dias_esperados not in {90, 180, 187}:
            raise ErroParametroNasaPower(
                "cliente suporta janelas de 90, 180 ou 187 dias"
            )

        parametros_requisicao = {
            "parameters": ",".join(PARAMETROS_NASA_POWER),
            "community": "AG",
            "longitude": longitude,
            "latitude": latitude,
            "start": janela.inicio.strftime("%Y%m%d"),
            "end": janela.fim.strftime("%Y%m%d"),
            "format": "JSON",
            "time-standard": "LST",
        }
        try:
            resposta_http = self._transporte.get(
                ENDPOINT_NASA_POWER_DAILY,
                params=parametros_requisicao,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise ErroTransporteNasaPower("timeout ao consultar NASA POWER") from exc
        except requests.RequestException as exc:
            raise ErroTransporteNasaPower(
                "falha de rede ao consultar NASA POWER"
            ) from exc

        status_code = getattr(resposta_http, "status_code", None)
        if status_code != 200:
            if not isinstance(status_code, int):
                raise ErroContratoNasaPower("resposta HTTP sem status_code válido")
            raise ErroHttpNasaPower(status_code)
        try:
            resposta_json = resposta_http.json()
        except (TypeError, ValueError) as exc:
            raise ErroContratoNasaPower(
                "resposta da NASA POWER não contém JSON válido"
            ) from exc

        parametros, parametros_retornados = _extrair_parametros(resposta_json, janela)
        registros = _construir_registros(parametros, janela)
        coletado_em_utc = self._relogio_utc()
        if (
            not isinstance(coletado_em_utc, datetime)
            or coletado_em_utc.tzinfo is None
            or coletado_em_utc.utcoffset() is None
        ):
            raise ErroParametroNasaPower(
                "relógio UTC deve retornar datetime com timezone"
            )

        return SerieHistoricaFonte.criar(
            id_fazenda=id_fazenda,
            fonte=FonteDado.NASA_POWER,
            tipo_produto=TipoProdutoHistorico.HISTORICO_REGIONAL,
            dataset=DATASET_NASA_POWER_DAILY,
            periodo_solicitado=janela,
            referencia_temporal=ReferenciaTemporalHistorica(
                tipo=TipoReferenciaTemporal.LOCAL_SOLAR_TIME,
                descricao=(
                    "NASA POWER Daily em Local Solar Time (LST), solicitado "
                    "explicitamente e preservado sem conversão para timezone civil"
                ),
            ),
            registros=registros,
            coletado_em_utc=coletado_em_utc,
            metadados_origem={
                "endpoint": ENDPOINT_NASA_POWER_DAILY,
                "community": "AG",
                "formato": "JSON",
                "time_standard": "LST",
                "latitude": latitude,
                "longitude": longitude,
                "parametros_solicitados": PARAMETROS_NASA_POWER,
                "parametros_retornados": parametros_retornados,
                "inicio_solicitado": parametros_requisicao["start"],
                "fim_solicitado": parametros_requisicao["end"],
                "dias_solicitados": janela.dias_esperados,
                "vento": {
                    "parametro_fonte": "WS2M",
                    "variavel_canonica": "velocidade_vento_media_m_s",
                    "unidade": "m/s",
                    "altura_m": 2,
                    "agregacao_temporal": "media_diaria",
                    "referencia_temporal": "LST",
                },
            },
        )


def consultar_nasa_power_historico(
    latitude: float,
    longitude: float,
    janela: JanelaHistorica,
    *,
    id_fazenda: str | None = None,
    transporte: TransporteHttp | None = None,
    timeout: float | tuple[float, float] = TIMEOUT_PADRAO,
) -> SerieHistoricaFonte:
    """Fachada funcional sem estado compartilhado entre chamadas."""

    cliente = ClienteNasaPowerHistorico(transporte=transporte, timeout=timeout)
    return cliente.consultar(
        latitude,
        longitude,
        janela,
        id_fazenda=id_fazenda,
    )


__all__ = [
    "DATASET_NASA_POWER_DAILY",
    "ENDPOINT_NASA_POWER_DAILY",
    "MAPEAMENTO_REGISTRO",
    "PARAMETROS_NASA_POWER",
    "ClienteNasaPowerHistorico",
    "ErroContratoNasaPower",
    "ErroHttpNasaPower",
    "ErroNasaPowerHistorico",
    "ErroParametroNasaPower",
    "ErroTransporteNasaPower",
    "consultar_nasa_power_historico",
]
