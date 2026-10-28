"""Contrato, validacao CSV e indicadores do inventario de maquinarios."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


FUSO_HORARIO_NEGOCIO = ZoneInfo("America/Sao_Paulo")


TipoEquipamento = Literal[
    "TRATOR",
    "COLHEITADEIRA",
    "PULVERIZADOR_AUTOPROPELIDO",
    "PLANTADEIRA",
    "IMPLEMENTO_ARRASTO",
    "PLATAFORMA",
    "UTILITARIO_APOIO",
]
MarcaMaquinario = Literal[
    "JOHN_DEERE",
    "MASSEY_FERGUSON",
    "NEW_HOLLAND",
    "VALTRA",
    "CASE_IH",
    "JACTO",
    "STARA",
    "OUTROS",
]
SeguradoraMaquinario = Literal[
    "MAPFRE",
    "PORTO_SEGURO",
    "ALLIANZ",
    "OUTRA",
]

TIPOS_MOTORIZADOS = {
    "TRATOR",
    "COLHEITADEIRA",
    "PULVERIZADOR_AUTOPROPELIDO",
    "UTILITARIO_APOIO",
}

CABECALHO_CSV_MAQUINARIOS = [
    "tipo_equipamento",
    "marca",
    "marca_outro",
    "modelo",
    "ano_fabricacao",
    "chassi",
    "apelido",
    "horimetro_atual",
    "hodometro_atual",
    "media_horas_dia",
    "possui_seguro",
    "seguradora",
    "seguradora_outro",
    "vencimento_apolice",
]

_ROTULOS_CSV = {
    "TRATOR": "TRATOR",
    "COLHEITADEIRA": "COLHEITADEIRA",
    "PULVERIZADOR AUTOPROPELIDO": "PULVERIZADOR_AUTOPROPELIDO",
    "PULVERIZADOR_AUTOPROPELIDO": "PULVERIZADOR_AUTOPROPELIDO",
    "PLANTADEIRA": "PLANTADEIRA",
    "IMPLEMENTO DE ARRASTO": "IMPLEMENTO_ARRASTO",
    "IMPLEMENTO_ARRASTO": "IMPLEMENTO_ARRASTO",
    "PLATAFORMA": "PLATAFORMA",
    "UTILITARIO DE APOIO": "UTILITARIO_APOIO",
    "UTILITARIO_APOIO": "UTILITARIO_APOIO",
    "JOHN DEERE": "JOHN_DEERE",
    "JOHN_DEERE": "JOHN_DEERE",
    "MASSEY FERGUSON": "MASSEY_FERGUSON",
    "MASSEY_FERGUSON": "MASSEY_FERGUSON",
    "NEW HOLLAND": "NEW_HOLLAND",
    "NEW_HOLLAND": "NEW_HOLLAND",
    "VALTRA": "VALTRA",
    "CASE IH": "CASE_IH",
    "CASE_IH": "CASE_IH",
    "JACTO": "JACTO",
    "STARA": "STARA",
    "OUTROS": "OUTROS",
    "MAPFRE": "MAPFRE",
    "PORTO SEGURO": "PORTO_SEGURO",
    "PORTO_SEGURO": "PORTO_SEGURO",
    "ALLIANZ": "ALLIANZ",
    "OUTRA": "OUTRA",
}


def _texto_opcional(valor: Any) -> str | None:
    texto = " ".join(str(valor or "").strip().split())
    return texto or None


class MaquinarioIn(BaseModel):
    tipo_equipamento: TipoEquipamento
    marca: MarcaMaquinario
    marca_outro: str | None = Field(default=None, min_length=2, max_length=80)
    modelo: str = Field(..., min_length=1, max_length=100)
    ano_fabricacao: int = Field(..., ge=1970)
    chassi: str | None = Field(default=None, min_length=2, max_length=100)
    apelido: str | None = Field(default=None, max_length=80)
    horimetro_atual: float | None = Field(default=None, ge=0, le=10_000_000)
    hodometro_atual: float | None = Field(default=None, ge=0, le=100_000_000)
    media_horas_dia: float | None = Field(default=None, ge=0, le=24)
    possui_seguro: bool = False
    seguradora: SeguradoraMaquinario | None = None
    seguradora_outro: str | None = Field(default=None, min_length=2, max_length=80)
    vencimento_apolice: date | None = None

    @field_validator("modelo")
    @classmethod
    def normalizar_modelo(cls, valor: str) -> str:
        texto = _texto_opcional(valor)
        if not texto:
            raise ValueError("informe o modelo")
        return texto

    @field_validator("marca_outro", "apelido", "seguradora_outro", mode="before")
    @classmethod
    def normalizar_texto_opcional(cls, valor: Any) -> str | None:
        return _texto_opcional(valor)

    @field_validator("chassi", mode="before")
    @classmethod
    def normalizar_chassi(cls, valor: Any) -> str | None:
        texto = _texto_opcional(valor)
        return texto.upper() if texto else None

    @model_validator(mode="after")
    def validar_regras_condicionais(self) -> "MaquinarioIn":
        if self.ano_fabricacao > date.today().year + 1:
            raise ValueError("ano de fabricacao nao pode ser posterior ao proximo ano")
        if self.tipo_equipamento in TIPOS_MOTORIZADOS and self.horimetro_atual is None:
            raise ValueError("horimetro atual e obrigatorio para equipamento motorizado")
        if self.marca == "OUTROS" and not self.marca_outro:
            raise ValueError("informe o fabricante quando a marca for Outros")
        if self.marca != "OUTROS":
            self.marca_outro = None
        if self.possui_seguro:
            if not self.seguradora or not self.vencimento_apolice:
                raise ValueError(
                    "seguradora e vencimento sao obrigatorios para seguro cadastrado"
                )
            if self.seguradora == "OUTRA" and not self.seguradora_outro:
                raise ValueError("informe a seguradora quando a opcao for Outra")
            if self.seguradora != "OUTRA":
                self.seguradora_outro = None
        else:
            self.seguradora = None
            self.seguradora_outro = None
            self.vencimento_apolice = None
        return self

    def para_persistencia(self, origem: Literal["manual", "csv", "semente"]) -> dict[str, Any]:
        dados = self.model_dump(mode="json")
        dados["origem_cadastro"] = origem
        return dados


class ConteudoCsvIn(BaseModel):
    conteudo_csv: str = Field(..., min_length=1, max_length=1_000_000)


def _numero_csv(valor: Any) -> float | None:
    texto = str(valor or "").strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)


def _inteiro_csv(valor: Any) -> int | None:
    numero = _numero_csv(valor)
    if numero is None:
        return None
    if not numero.is_integer():
        raise ValueError("use um numero inteiro")
    return int(numero)


def _booleano_csv(valor: Any) -> bool:
    texto = str(valor or "").strip().upper()
    if texto in {"SIM", "S", "TRUE", "1"}:
        return True
    if texto in {"NAO", "NÃO", "N", "FALSE", "0", ""}:
        return False
    raise ValueError("use SIM ou NAO")


def _codigo_csv(valor: Any) -> str:
    texto = " ".join(str(valor or "").strip().upper().split())
    return _ROTULOS_CSV.get(texto, texto.replace(" ", "_"))


def _erro_validacao(linha: int, exc: ValidationError) -> list[dict[str, Any]]:
    erros = []
    for erro in exc.errors(include_url=False):
        localizacao = erro.get("loc") or ("registro",)
        mensagem = str(erro.get("msg") or "valor invalido")
        if mensagem.startswith("Value error, "):
            mensagem = mensagem[len("Value error, ") :]
        erros.append(
            {
                "linha": linha,
                "campo": str(localizacao[-1]),
                "mensagem": mensagem,
            }
        )
    return erros


def validar_csv_maquinarios(
    conteudo: str,
    *,
    chassis_cadastrados: set[str] | None = None,
) -> tuple[list[MaquinarioIn], list[dict[str, Any]]]:
    texto = str(conteudo or "").lstrip("\ufeff")
    leitor = csv.DictReader(StringIO(texto), delimiter=";")
    cabecalho = [str(item or "").strip() for item in (leitor.fieldnames or [])]
    erros: list[dict[str, Any]] = []
    ausentes = [campo for campo in CABECALHO_CSV_MAQUINARIOS if campo not in cabecalho]
    extras = [campo for campo in cabecalho if campo not in CABECALHO_CSV_MAQUINARIOS]
    if ausentes:
        erros.append(
            {
                "linha": 1,
                "campo": "cabecalho",
                "mensagem": "colunas ausentes: " + ", ".join(ausentes),
            }
        )
    if extras:
        erros.append(
            {
                "linha": 1,
                "campo": "cabecalho",
                "mensagem": "colunas desconhecidas: " + ", ".join(extras),
            }
        )
    if erros:
        return [], erros

    registros: list[MaquinarioIn] = []
    vistos = {" ".join(item.strip().upper().split()) for item in chassis_cadastrados or set()}
    total_linhas = 0
    for numero_linha, linha in enumerate(leitor, start=2):
        if numero_linha > 501:
            erros.append(
                {
                    "linha": numero_linha,
                    "campo": "arquivo",
                    "mensagem": "o limite e de 500 maquinarios por importacao",
                }
            )
            break
        if not any(str(valor or "").strip() for valor in linha.values()):
            continue
        total_linhas += 1
        if None in linha:
            erros.append(
                {
                    "linha": numero_linha,
                    "campo": "arquivo",
                    "mensagem": "a linha possui mais colunas do que o cabecalho",
                }
            )
            continue
        try:
            entrada = {
                **linha,
                "tipo_equipamento": _codigo_csv(linha.get("tipo_equipamento")),
                "marca": _codigo_csv(linha.get("marca")),
                "ano_fabricacao": _inteiro_csv(linha.get("ano_fabricacao")),
                "horimetro_atual": _numero_csv(linha.get("horimetro_atual")),
                "hodometro_atual": _numero_csv(linha.get("hodometro_atual")),
                "media_horas_dia": _numero_csv(linha.get("media_horas_dia")),
                "possui_seguro": _booleano_csv(linha.get("possui_seguro")),
                "seguradora": (
                    _codigo_csv(linha.get("seguradora"))
                    if str(linha.get("seguradora") or "").strip()
                    else None
                ),
                "vencimento_apolice": str(linha.get("vencimento_apolice") or "").strip() or None,
            }
            registro = MaquinarioIn.model_validate(entrada)
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                erros.extend(_erro_validacao(numero_linha, exc))
            else:
                erros.append(
                    {
                        "linha": numero_linha,
                        "campo": "registro",
                        "mensagem": str(exc),
                    }
                )
            continue

        if registro.chassi and registro.chassi in vistos:
            erros.append(
                {
                    "linha": numero_linha,
                    "campo": "chassi",
                    "mensagem": "chassi ja cadastrado nesta fazenda ou repetido no arquivo",
                }
            )
            continue
        if registro.chassi:
            vistos.add(registro.chassi)
        registros.append(registro)

    if total_linhas == 0:
        erros.append(
            {
                "linha": 2,
                "campo": "arquivo",
                "mensagem": "adicione ao menos uma linha de maquinario",
            }
        )
    return registros, erros


def resumo_maquinarios(
    registros: list[dict[str, Any]], *, referencia: date | None = None
) -> dict[str, Any]:
    hoje = referencia or datetime.now(FUSO_HORARIO_NEGOCIO).date()
    limite_30 = hoje + timedelta(days=30)
    limite_60 = hoje + timedelta(days=60)
    limite_90 = hoje + timedelta(days=90)
    total = len(registros)
    segurados = sum(1 for item in registros if bool(item.get("possui_seguro")))
    vencimentos = []
    anos = []
    horimetros = []
    horimetros_motorizados = []
    horas_dia = []
    chassis_informados = 0
    tipos: dict[str, int] = {}
    atualizado_em = None
    for item in registros:
        tipo = str(item.get("tipo_equipamento") or "NAO_INFORMADO")
        tipos[tipo] = tipos.get(tipo, 0) + 1
        if item.get("ano_fabricacao") is not None:
            anos.append(int(item["ano_fabricacao"]))
        if item.get("horimetro_atual") is not None:
            horimetro = float(item["horimetro_atual"])
            horimetros.append(horimetro)
            if tipo in TIPOS_MOTORIZADOS:
                horimetros_motorizados.append(horimetro)
        if item.get("media_horas_dia") is not None:
            horas_dia.append(float(item["media_horas_dia"]))
        if str(item.get("chassi") or "").strip():
            chassis_informados += 1
        if item.get("possui_seguro") and item.get("vencimento_apolice"):
            try:
                vencimentos.append(date.fromisoformat(str(item["vencimento_apolice"])[:10]))
            except ValueError:
                pass
        valor_atualizacao = str(item.get("updated_at") or item.get("created_at") or "")
        if valor_atualizacao and (atualizado_em is None or valor_atualizacao > atualizado_em):
            atualizado_em = valor_atualizacao

    idades = [max(0, hoje.year - ano) for ano in anos]
    seguros_vigentes = sum(1 for valor in vencimentos if valor >= hoje)
    return {
        "disponivel": True,
        "total": total,
        "segurados": segurados,
        "sem_seguro": total - segurados,
        "percentual_segurado": round((segurados / total) * 100) if total else 0,
        "seguros_vigentes": seguros_vigentes,
        "percentual_seguro_vigente": (
            round((seguros_vigentes / total) * 100) if total else 0
        ),
        "vencendo_30_dias": sum(1 for valor in vencimentos if hoje <= valor <= limite_30),
        "vencendo_60_dias": sum(1 for valor in vencimentos if hoje <= valor <= limite_60),
        "vencendo_90_dias": sum(1 for valor in vencimentos if hoje <= valor <= limite_90),
        "seguros_vencidos": sum(1 for valor in vencimentos if valor < hoje),
        "proximo_vencimento": min((valor for valor in vencimentos if valor >= hoje), default=None),
        "idade_media_anos": (
            round(sum(idades) / len(idades), 1)
            if idades
            else None
        ),
        "faixas_idade": {
            "ate_3_anos": sum(1 for idade in idades if idade <= 3),
            "de_4_a_7_anos": sum(1 for idade in idades if 4 <= idade <= 7),
            "8_anos_ou_mais": sum(1 for idade in idades if idade >= 8),
        },
        "horimetro_total_horas": round(sum(horimetros), 1),
        "horimetros_informados": len(horimetros),
        "horimetro_medio_motorizados": (
            round(sum(horimetros_motorizados) / len(horimetros_motorizados), 1)
            if horimetros_motorizados
            else None
        ),
        "motorizados": sum(tipos.get(tipo, 0) for tipo in TIPOS_MOTORIZADOS),
        "horimetros_motorizados_informados": len(horimetros_motorizados),
        "horas_dia_estimadas": round(sum(horas_dia), 1),
        "horas_dia_informadas": len(horas_dia),
        "horas_dia_media_declarada": (
            round(sum(horas_dia) / len(horas_dia), 1) if horas_dia else None
        ),
        "chassis_informados": chassis_informados,
        "percentual_chassi_informado": (
            round((chassis_informados / total) * 100) if total else 0
        ),
        "tipos_distintos": len(tipos),
        "por_tipo": dict(sorted(tipos.items())),
        "atualizado_em": atualizado_em,
    }


def modelo_csv_maquinarios() -> bytes:
    buffer = StringIO(newline="")
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(CABECALHO_CSV_MAQUINARIOS)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


__all__ = [
    "CABECALHO_CSV_MAQUINARIOS",
    "ConteudoCsvIn",
    "MaquinarioIn",
    "modelo_csv_maquinarios",
    "resumo_maquinarios",
    "validar_csv_maquinarios",
]
