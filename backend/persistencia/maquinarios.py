"""Persistencia do inventario de maquinarios por fazenda.

O acesso ao Supabase acontece exclusivamente no backend. Em desenvolvimento
sem banco configurado, uma memoria de processo mantem o fluxo funcional sem
criar arquivos paralelos ao cadastro principal.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from threading import Lock
from typing import Any, Iterable, Mapping

from backend.persistencia.supabase_rest import cliente_supabase, supabase_configurado


TABELA_MAQUINARIOS = "agrishield_maquinarios"
_MEMORIA: list[dict[str, Any]] = []
_MEMORIA_LOCK = Lock()
_PROXIMO_ID = 1


def _normalizar_chassi(valor: Any) -> str | None:
    texto = " ".join(str(valor or "").strip().upper().split())
    return texto or None


def listar_maquinarios(id_fazenda: str | int) -> list[dict[str, Any]]:
    id_numero = int(id_fazenda)
    if supabase_configurado():
        return cliente_supabase().selecionar(
            TABELA_MAQUINARIOS,
            filtros={
                "id_fazenda": f"eq.{id_numero}",
                "ativo": "eq.true",
            },
            ordem="created_at.desc,id_maquinario.desc",
        )
    with _MEMORIA_LOCK:
        registros = [
            deepcopy(item)
            for item in _MEMORIA
            if item["id_fazenda"] == id_numero and item.get("ativo", True)
        ]
    return sorted(registros, key=lambda item: int(item["id_maquinario"]), reverse=True)


def listar_totais_por_fazenda() -> dict[str, int]:
    if not supabase_configurado():
        with _MEMORIA_LOCK:
            contagem = Counter(
                str(item["id_fazenda"])
                for item in _MEMORIA
                if item.get("ativo", True)
            )
        return dict(contagem)

    cliente = cliente_supabase()
    contagem: Counter[str] = Counter()
    deslocamento = 0
    pagina = 1000
    while True:
        linhas = cliente.selecionar(
            TABELA_MAQUINARIOS,
            colunas="id_fazenda",
            filtros={"ativo": "eq.true"},
            limite=pagina,
            deslocamento=deslocamento,
        )
        contagem.update(str(item["id_fazenda"]) for item in linhas)
        if len(linhas) < pagina:
            break
        deslocamento += pagina
    return dict(contagem)


def chassis_existentes(id_fazenda: str | int) -> set[str]:
    return {
        chassi
        for item in listar_maquinarios(id_fazenda)
        if (chassi := _normalizar_chassi(item.get("chassi")))
    }


def cadastrar_maquinarios(
    id_fazenda: str | int,
    registros: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    global _PROXIMO_ID
    id_numero = int(id_fazenda)
    linhas = []
    for registro in registros:
        linha = dict(registro)
        linha["id_fazenda"] = id_numero
        linha["chassi"] = _normalizar_chassi(linha.get("chassi"))
        linhas.append(linha)
    if not linhas:
        return []

    if supabase_configurado():
        return cliente_supabase().inserir_varios(TABELA_MAQUINARIOS, linhas)

    with _MEMORIA_LOCK:
        salvos = []
        for linha in linhas:
            salvo = {
                **linha,
                "id_maquinario": _PROXIMO_ID,
                "ativo": True,
            }
            _PROXIMO_ID += 1
            _MEMORIA.append(salvo)
            salvos.append(deepcopy(salvo))
    return salvos


def cadastrar_maquinario(
    id_fazenda: str | int, registro: Mapping[str, Any]
) -> dict[str, Any]:
    return cadastrar_maquinarios(id_fazenda, [registro])[0]


__all__ = [
    "TABELA_MAQUINARIOS",
    "cadastrar_maquinario",
    "cadastrar_maquinarios",
    "chassis_existentes",
    "listar_maquinarios",
    "listar_totais_por_fazenda",
]
