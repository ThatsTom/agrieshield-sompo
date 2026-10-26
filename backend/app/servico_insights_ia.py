"""Gera um briefing operacional estruturado com o GPT-4o mini.

A chave da OpenAI e lida somente no backend. O modulo nao registra prompts,
respostas ou credenciais e pede que a API nao armazene a resposta.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
import requests


MODELO_OPENAI_INSIGHTS = "gpt-4o-mini"
VERSAO_PROMPT_INSIGHTS = "2026-09-28.2"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class ErroConfiguracaoOpenAI(RuntimeError):
    """A integracao nao possui a configuracao minima necessaria."""


class ErroServicoOpenAI(RuntimeError):
    """Falha segura e apresentavel ao consultar ou validar a resposta da IA."""


class PrioridadeInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    prioridade: Literal["imediata", "hoje", "proximos_dias", "monitorar"]
    motivo: str
    acao_recomendada: str
    dado_base: str


class InsightGerado(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resumo_executivo: str
    nivel_atencao: Literal["baixo", "moderado", "alto", "critico"]
    leitura_principal: str
    prioridades: list[PrioridadeInsight] = Field(max_length=5)
    perguntas_consultor: list[str] = Field(max_length=3)
    pontos_positivos: list[str] = Field(max_length=4)
    limitacoes: list[str] = Field(min_length=1, max_length=5)


@dataclass(frozen=True)
class ResultadoInsightIA:
    insight: dict[str, Any]
    uso: dict[str, Any]


INSTRUCOES = """
Voce e um analista de risco rural que prepara briefings para consultores de
seguros. Responda em portugues do Brasil, com linguagem clara, objetiva e
pratica. Use exclusivamente os dados fornecidos. Nao invente clima, perdas,
probabilidades, valores financeiros, coberturas ou diagnosticos. Nao altere o
score calculado pela aplicacao. Diferencie fatos observados de limitacoes dos
dados. Priorize medidas que o consultor pode verificar, comunicar ou orientar,
sem prometer reducao de risco. Cada recomendacao deve citar em `dado_base` o
dado concreto que a sustenta. Quando houver relacao sustentada pelos dados,
cruze clima, leitura calculada, territorio, frota e situacao cadastral do
seguro; nao force conexoes. Entregue ate 5 prioridades, somente quando houver
evidencia suficiente; a lista pode ter menos itens ou ficar vazia. Entregue ate
3 perguntas para o consultor, ate 4 pontos positivos e ao menos uma limitacao.
Esta analise apoia, mas nao substitui avaliacao tecnica, vistoria ou regras da
apolice. Seguro cadastrado nao significa necessariamente seguro vigente. Dados
de maquinario sao cadastrais e descritivos. Nao infira falha, necessidade de
manutencao, disponibilidade ou probabilidade de sinistro apenas por idade ou
horimetro. A previsao diaria sem vento e condicao do solo pode indicar somente
um periodo candidato a validacao local, nunca uma janela operacional garantida.
""".strip()


def _normalizar_json(valor: Any) -> Any:
    """Remove tipos e numeros que nao pertencem ao JSON estrito."""

    if isinstance(valor, dict):
        return {str(chave): _normalizar_json(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_normalizar_json(item) for item in valor]
    if isinstance(valor, float) and not math.isfinite(valor):
        return None
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return str(valor)


def contexto_canonico(contexto: dict[str, Any]) -> dict[str, Any]:
    return _normalizar_json(contexto)


def gerar_hash_contexto(contexto: dict[str, Any]) -> str:
    envelope = {
        "versao_prompt": VERSAO_PROMPT_INSIGHTS,
        "modelo": MODELO_OPENAI_INSIGHTS,
        "contexto": contexto_canonico(contexto),
    }
    serializado = json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


def _extrair_texto(resposta: dict[str, Any]) -> str:
    texto_direto = resposta.get("output_text")
    if isinstance(texto_direto, str) and texto_direto.strip():
        return texto_direto

    for item in resposta.get("output") or []:
        if not isinstance(item, dict):
            continue
        for conteudo in item.get("content") or []:
            if not isinstance(conteudo, dict):
                continue
            texto = conteudo.get("text")
            if isinstance(texto, str) and texto.strip():
                return texto
    raise ErroServicoOpenAI("A OpenAI nao retornou uma analise utilizavel.")


def _mensagem_por_status(status: int | None) -> str:
    if status == 401:
        return "A chave da OpenAI configurada no backend não foi aceita."
    if status == 429:
        return "O limite de uso da OpenAI foi atingido. Tente novamente mais tarde."
    if status is not None and status >= 500:
        return "A OpenAI esta temporariamente indisponivel. Tente novamente."
    return "Nao foi possivel gerar a analise inteligente neste momento."


def gerar_insight_ia(
    contexto: dict[str, Any],
    *,
    chave_api: str | None = None,
    timeout: tuple[int, int] = (5, 55),
) -> ResultadoInsightIA:
    chave = str(chave_api or os.getenv("OPENAI_API_KEY") or "").strip()
    if not chave:
        raise ErroConfiguracaoOpenAI(
            "Configure OPENAI_API_KEY no ambiente do backend para ativar a analise inteligente."
        )

    contexto_seguro = contexto_canonico(contexto)
    payload = {
        "model": MODELO_OPENAI_INSIGHTS,
        "store": False,
        "instructions": INSTRUCOES,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Prepare o briefing a partir deste contexto:\n"
                        + json.dumps(
                            contexto_seguro,
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        ),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "agrishield_insights",
                "strict": True,
                "schema": InsightGerado.model_json_schema(),
            }
        },
        "temperature": 0.2,
        "max_output_tokens": 1800,
    }

    resposta = None
    for tentativa in range(2):
        try:
            resposta_http = requests.post(
                OPENAI_RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {chave}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            resposta_http.raise_for_status()
            resposta = resposta_http.json()
            break
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            temporario = status is None or status == 429 or status >= 500
            if tentativa == 0 and temporario:
                time.sleep(0.6)
                continue
            raise ErroServicoOpenAI(_mensagem_por_status(status)) from exc
        except ValueError as exc:
            raise ErroServicoOpenAI("A OpenAI retornou uma resposta inválida.") from exc

    if resposta is None:
        raise ErroServicoOpenAI("Não foi possível obter uma resposta da OpenAI.")

    try:
        bruto = json.loads(_extrair_texto(resposta))
        insight = InsightGerado.model_validate(bruto).model_dump()
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ErroServicoOpenAI(
            "A analise gerada nao passou pela validacao de seguranca. Tente novamente."
        ) from exc

    uso = resposta.get("usage")
    return ResultadoInsightIA(
        insight=insight,
        uso=dict(uso) if isinstance(uso, dict) else {},
    )


__all__ = [
    "ErroConfiguracaoOpenAI",
    "ErroServicoOpenAI",
    "InsightGerado",
    "MODELO_OPENAI_INSIGHTS",
    "ResultadoInsightIA",
    "contexto_canonico",
    "gerar_hash_contexto",
    "gerar_insight_ia",
]
