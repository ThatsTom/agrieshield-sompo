"""Contratos pequenos do harness observacional de validação multi-regional."""

from __future__ import annotations

from enum import Enum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


HARNESS_SCHEMA_VERSION = "validacao-multiregional-v1"


class ModoCenario(str, Enum):
    CEP = "CEP"
    COORDENADA = "COORDENADA"


class StatusFonte(str, Enum):
    SUCESSO = "SUCESSO"
    PARCIAL = "PARCIAL"
    AUSENTE = "AUSENTE"
    ERRO = "ERRO"
    NAO_EXECUTADO = "NAO_EXECUTADO"


class CenarioValidacao(BaseModel):
    """Fixture técnico; nunca representa cadastro ou limite fundiário real."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id_cenario: str = Field(min_length=1)
    nome: str = Field(min_length=1)
    modo: ModoCenario
    classificacao: str
    uf: str = Field(min_length=2, max_length=2)
    regiao: str = Field(min_length=1)
    cep: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    area_ha: float = Field(gt=0)
    tipo_operacao: str = "campo"
    proximidade_agua_declarada: bool | None = None
    tags: tuple[str, ...] = ()
    observacao: str = "Cenário técnico de validação; não representa propriedade real."

    @model_validator(mode="after")
    def validar_modo(self) -> "CenarioValidacao":
        if self.modo == ModoCenario.CEP:
            if not str(self.cep or "").strip():
                raise ValueError("cenário CEP exige cep")
            if self.latitude is not None or self.longitude is not None:
                raise ValueError("cenário CEP não deve fixar coordenadas")
        else:
            if self.latitude is None or self.longitude is None:
                raise ValueError("cenário COORDENADA exige latitude e longitude")
            if self.cep is not None:
                raise ValueError("cenário COORDENADA não utiliza CEP")
            if self.classificacao != "PONTO_RURAL_DE_VALIDACAO":
                raise ValueError("cenário COORDENADA deve ser PONTO_RURAL_DE_VALIDACAO")
        return self


def carregar_cenarios(caminho: str | Path) -> list[CenarioValidacao]:
    payload: Any = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("arquivo de cenários deve conter uma lista não vazia")
    cenarios = [CenarioValidacao.model_validate(item) for item in payload]
    identificadores = [cenario.id_cenario for cenario in cenarios]
    if len(identificadores) != len(set(identificadores)):
        raise ValueError("id_cenario duplicado")
    return cenarios


__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "CenarioValidacao",
    "ModoCenario",
    "StatusFonte",
    "carregar_cenarios",
]
