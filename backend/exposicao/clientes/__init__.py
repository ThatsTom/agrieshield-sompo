"""Clientes estritos das fontes da camada de exposição histórica."""

from .open_meteo_historico import (
    ClienteOpenMeteoHistorico,
    ErroContratoOpenMeteoHistorico,
    ErroHttpOpenMeteoHistorico,
    ErroOpenMeteoHistorico,
    ErroParametroOpenMeteoHistorico,
    ErroTransporteOpenMeteoHistorico,
    consultar_open_meteo_historico,
)
from .nasa_power_historico import (
    ClienteNasaPowerHistorico,
    ErroContratoNasaPower,
    ErroHttpNasaPower,
    ErroNasaPowerHistorico,
    ErroParametroNasaPower,
    ErroTransporteNasaPower,
    consultar_nasa_power_historico,
)

__all__ = [
    "ClienteOpenMeteoHistorico",
    "ClienteNasaPowerHistorico",
    "ErroContratoOpenMeteoHistorico",
    "ErroContratoNasaPower",
    "ErroHttpOpenMeteoHistorico",
    "ErroHttpNasaPower",
    "ErroOpenMeteoHistorico",
    "ErroNasaPowerHistorico",
    "ErroParametroOpenMeteoHistorico",
    "ErroParametroNasaPower",
    "ErroTransporteOpenMeteoHistorico",
    "ErroTransporteNasaPower",
    "consultar_open_meteo_historico",
    "consultar_nasa_power_historico",
]
