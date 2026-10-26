# =============================================================================
# AgriShield — Etapa 1: cadastro de fazendas e base estática de coordenadas
#
# Responsabilidades:
#   1) Criar data/base_coordenadas_cep.csv, usada para resolver CEP -> lat/long.
#   2) Criar data/fazendas.csv, usado para armazenar as fazendas cadastradas.
#   3) Listar e adicionar fazendas para a API FastAPI e para os testes isolados.
# =============================================================================

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.persistencia.supabase_rest import (
    cliente_supabase,
    supabase_configurado,
)

PASTA_DADOS = Path(__file__).resolve().parent.parent / "data"
PASTA_DADOS.mkdir(parents=True, exist_ok=True)

ARQUIVO_COORDENADAS = PASTA_DADOS / "base_coordenadas_cep.csv"
ARQUIVO_FAZENDAS = PASTA_DADOS / "fazendas.csv"
TABELA_FAZENDAS = "agrishield_fazendas"
TABELA_COORDENADAS = "agrishield_coordenadas_cep"

COLUNAS_COORDENADAS = [
    "cep",
    "logradouro",
    "bairro",
    "cidade",
    "uf",
    "latitude",
    "longitude",
    "fonte",
]

COLUNAS_FAZENDAS = [
    "id_fazenda",
    "nome_fazenda",
    "numero_apolice",
    "apolices_json",
    "arquivada",
    "cep",
    "logradouro",
    "numero_km",
    "complemento",
    "bairro",
    "cidade",
    "uf",
    "referencia_acesso",
    "tipo_operacao",
    "proximidade_agua",
    "latitude",
    "longitude",
    "area_ha",
    "poligono_geojson",
]

COORDENADAS_EXEMPLO = [
    {
        "cep": "78890000",
        "logradouro": "Rodovia MT-242, Km 12",
        "bairro": "Zona Rural",
        "cidade": "Sorriso",
        "uf": "MT",
        "latitude": "-12.5450",
        "longitude": "-55.7210",
        "fonte": "base_estatica_demo",
    },
    {
        "cep": "78550000",
        "logradouro": "Estrada da Produção, s/n",
        "bairro": "Zona Rural",
        "cidade": "Sinop",
        "uf": "MT",
        "latitude": "-11.8644",
        "longitude": "-55.5025",
        "fonte": "base_estatica_demo",
    },
    {
        "cep": "78700000",
        "logradouro": "Rod. BR-070, Km 45",
        "bairro": "Zona Rural",
        "cidade": "Rondonópolis",
        "uf": "MT",
        "latitude": "-16.4708",
        "longitude": "-54.6356",
        "fonte": "base_estatica_demo",
    },
    {
        "cep": "78600000",
        "logradouro": "Rodovia BR-158, Km 20",
        "bairro": "Zona Rural",
        "cidade": "Barra do Garças",
        "uf": "MT",
        "latitude": "-15.8900",
        "longitude": "-52.2567",
        "fonte": "base_estatica_demo",
    },
    {
        "cep": "78455000",
        "logradouro": "Estrada Rural, s/n",
        "bairro": "Zona Rural",
        "cidade": "Lucas do Rio Verde",
        "uf": "MT",
        "latitude": "-13.0588",
        "longitude": "-55.9042",
        "fonte": "base_estatica_demo",
    },
]

FAZENDAS_EXEMPLO = [
    {
        "id_fazenda": "1",
        "nome_fazenda": "Fazenda Boa Esperança",
        "numero_apolice": "1234567890",
        "cep": "78890-000",
        "logradouro": "Rodovia MT-242, Km 12",
        "bairro": "Zona Rural",
        "cidade": "Sorriso",
        "uf": "MT",
        "tipo_operacao": "campo",
        "proximidade_agua": "True",
        "latitude": "-12.5450",
        "longitude": "-55.7210",
    },
    {
        "id_fazenda": "2",
        "nome_fazenda": "Fazenda Santa Luzia",
        "numero_apolice": "2233445566",
        "cep": "78550-000",
        "logradouro": "Estrada da Produção, s/n",
        "bairro": "Zona Rural",
        "cidade": "Sinop",
        "uf": "MT",
        "tipo_operacao": "transporte",
        "proximidade_agua": "False",
        "latitude": "-11.8644",
        "longitude": "-55.5025",
    },
    {
        "id_fazenda": "3",
        "nome_fazenda": "Fazenda Três Rios",
        "numero_apolice": "9988776655",
        "cep": "78700-000",
        "logradouro": "Rod. BR-070, Km 45",
        "bairro": "Zona Rural",
        "cidade": "Rondonópolis",
        "uf": "MT",
        "tipo_operacao": "campo",
        "proximidade_agua": "True",
        "latitude": "-16.4708",
        "longitude": "-54.6356",
    },
]


def normalizar_cep(cep: str) -> str:
    return "".join(c for c in str(cep or "") if c.isdigit())


def bool_str(valor) -> str:
    if isinstance(valor, bool):
        return "True" if valor else "False"
    return (
        "True"
        if str(valor).strip().lower() in {"true", "1", "sim", "s", "yes"}
        else "False"
    )


def criar_base_coordenadas_se_nao_existir() -> None:
    """Cria a base estática de CEP/latitude/longitude usada no protótipo."""
    if ARQUIVO_COORDENADAS.exists():
        return
    with open(ARQUIVO_COORDENADAS, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS_COORDENADAS, delimiter=";")
        writer.writeheader()
        writer.writerows(COORDENADAS_EXEMPLO)


def resolver_cep_base_estatica(cep: str) -> Optional[Dict[str, str]]:
    """Procura o CEP na base estática; se não achar, tenta pelo prefixo inicial."""
    cep_limpo = normalizar_cep(cep)
    if not cep_limpo:
        return None

    if supabase_configurado():
        linhas = cliente_supabase().selecionar(
            TABELA_COORDENADAS,
            filtros={"cep": f"eq.{cep_limpo}"},
            limite=1,
        )
        if linhas:
            retorno = {
                chave: "" if valor is None else str(valor)
                for chave, valor in linhas[0].items()
                if chave in COLUNAS_COORDENADAS
            }
            retorno["origem"] = "base_estatica"
            return retorno
        return None

    criar_base_coordenadas_se_nao_existir()

    with open(ARQUIVO_COORDENADAS, "r", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))

    for row in linhas:
        if normalizar_cep(row.get("cep")) == cep_limpo:
            row["origem"] = "base_estatica"
            return row

    # fallback por prefixo para manter a demo funcional com CEPs parecidos da região
    for tamanho in (5, 3):
        prefixo = cep_limpo[:tamanho]
        for row in linhas:
            if normalizar_cep(row.get("cep", ""))[:tamanho] == prefixo:
                retorno = dict(row)
                retorno["cep"] = cep
                retorno["origem"] = "base_estatica_prefixo"
                return retorno
    return None


def criar_base_se_nao_existir() -> None:
    """Cria o CSV de fazendas com exemplos para a demonstração."""
    if supabase_configurado():
        return
    criar_base_coordenadas_se_nao_existir()
    if ARQUIVO_FAZENDAS.exists():
        _migrar_schema_fazendas()
        return
    with open(ARQUIVO_FAZENDAS, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS_FAZENDAS, delimiter=";")
        writer.writeheader()
        writer.writerows(FAZENDAS_EXEMPLO)


def _migrar_schema_fazendas() -> None:
    """Acrescenta colunas novas sem invalidar registros de versões anteriores."""
    with open(ARQUIVO_FAZENDAS, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        colunas_atuais = reader.fieldnames or []
        if all(coluna in colunas_atuais for coluna in COLUNAS_FAZENDAS):
            return
        linhas = list(reader)

    temporario = ARQUIVO_FAZENDAS.with_suffix(".csv.tmp")
    try:
        with open(temporario, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUNAS_FAZENDAS, delimiter=";")
            writer.writeheader()
            writer.writerows(
                {col: linha.get(col, "") for col in COLUNAS_FAZENDAS}
                for linha in linhas
            )
        os.replace(temporario, ARQUIVO_FAZENDAS)
    finally:
        if temporario.exists():
            temporario.unlink()


def listar_fazendas() -> List[Dict[str, str]]:
    if supabase_configurado():
        linhas = cliente_supabase().selecionar(
            TABELA_FAZENDAS,
            ordem="id_fazenda.asc",
        )
        return [_linha_do_supabase(item) for item in linhas]
    criar_base_se_nao_existir()
    with open(ARQUIVO_FAZENDAS, "r", encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    for linha in linhas:
        linha.setdefault("area_ha", "")
    return linhas


def buscar_fazenda(id_fazenda: str) -> Optional[Dict[str, str]]:
    for fazenda in listar_fazendas():
        if str(fazenda.get("id_fazenda")) == str(id_fazenda):
            return fazenda
    return None


def adicionar_fazenda(dados: Dict[str, str]) -> Dict[str, str]:
    """Adiciona uma fazenda ao CSV, preservando o contrato de colunas da aplicação."""
    if supabase_configurado():
        salvo = cliente_supabase().inserir(
            TABELA_FAZENDAS,
            _linha_para_supabase(dados, incluir_id=False),
        )
        return _linha_do_supabase(salvo)
    criar_base_se_nao_existir()
    fazendas = listar_fazendas()
    novo_id = str(max([int(f["id_fazenda"]) for f in fazendas], default=0) + 1)
    dados = dict(dados)
    dados["id_fazenda"] = novo_id
    dados["proximidade_agua"] = bool_str(dados.get("proximidade_agua"))
    dados["tipo_operacao"] = str(dados.get("tipo_operacao") or "campo").lower()
    dados["cep"] = dados.get("cep", "")
    dados["arquivada"] = bool_str(dados.get("arquivada", False))
    dados["apolices_json"] = _normalizar_apolices_json(dados)

    linha = {col: dados.get(col, "") for col in COLUNAS_FAZENDAS}
    with open(ARQUIVO_FAZENDAS, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUNAS_FAZENDAS, delimiter=";")
        writer.writerow(linha)
    return linha


def _normalizar_apolices_json(dados: Dict[str, str]) -> str:
    bruto = dados.get("apolices_json")
    if isinstance(bruto, list):
        valores = bruto
    else:
        try:
            valores = json.loads(str(bruto)) if bruto else []
        except (TypeError, ValueError, json.JSONDecodeError):
            valores = []
    principal = str(dados.get("numero_apolice") or "").strip()
    unicas = []
    for valor in ([principal] if principal else []) + list(valores):
        numero = str(valor or "").strip()
        if numero and numero not in unicas:
            unicas.append(numero)
    return json.dumps(unicas, ensure_ascii=False)


def _json_opcional(valor: Any, padrao: Any) -> Any:
    if valor in (None, ""):
        return padrao
    if isinstance(valor, (dict, list)):
        return valor
    try:
        return json.loads(str(valor))
    except (TypeError, ValueError, json.JSONDecodeError):
        return padrao


def _float_opcional(valor: Any) -> float | None:
    if valor in (None, ""):
        return None
    return float(valor)


def _linha_para_supabase(
    dados: Dict[str, Any], *, incluir_id: bool = True
) -> Dict[str, Any]:
    apolices_json = _normalizar_apolices_json(dados)
    linha: Dict[str, Any] = {
        "nome_fazenda": str(dados.get("nome_fazenda") or "").strip(),
        "numero_apolice": str(dados.get("numero_apolice") or "").strip(),
        "apolices": _json_opcional(apolices_json, []),
        "arquivada": bool_str(dados.get("arquivada", False)) == "True",
        "cep": str(dados.get("cep") or "").strip(),
        "logradouro": str(dados.get("logradouro") or ""),
        "numero_km": str(dados.get("numero_km") or ""),
        "complemento": str(dados.get("complemento") or ""),
        "bairro": str(dados.get("bairro") or ""),
        "cidade": str(dados.get("cidade") or ""),
        "uf": str(dados.get("uf") or "").upper(),
        "referencia_acesso": str(dados.get("referencia_acesso") or ""),
        "tipo_operacao": str(dados.get("tipo_operacao") or "campo").lower(),
        "proximidade_agua": bool_str(dados.get("proximidade_agua")) == "True",
        "latitude": _float_opcional(dados.get("latitude")),
        "longitude": _float_opcional(dados.get("longitude")),
        "area_ha": _float_opcional(dados.get("area_ha")),
        "poligono": _json_opcional(dados.get("poligono_geojson"), None),
    }
    if incluir_id and dados.get("id_fazenda") not in (None, ""):
        linha["id_fazenda"] = int(str(dados["id_fazenda"]))
    return linha


def _linha_do_supabase(dados: Dict[str, Any]) -> Dict[str, str]:
    mapeada: Dict[str, Any] = {
        "id_fazenda": str(dados.get("id_fazenda") or ""),
        "nome_fazenda": dados.get("nome_fazenda") or "",
        "numero_apolice": dados.get("numero_apolice") or "",
        "apolices_json": json.dumps(dados.get("apolices") or [], ensure_ascii=False),
        "arquivada": bool_str(dados.get("arquivada")),
        "cep": dados.get("cep") or "",
        "logradouro": dados.get("logradouro") or "",
        "numero_km": dados.get("numero_km") or "",
        "complemento": dados.get("complemento") or "",
        "bairro": dados.get("bairro") or "",
        "cidade": dados.get("cidade") or "",
        "uf": dados.get("uf") or "",
        "referencia_acesso": dados.get("referencia_acesso") or "",
        "tipo_operacao": dados.get("tipo_operacao") or "campo",
        "proximidade_agua": bool_str(dados.get("proximidade_agua")),
        "latitude": dados.get("latitude"),
        "longitude": dados.get("longitude"),
        "area_ha": dados.get("area_ha"),
        "poligono_geojson": (
            json.dumps(dados.get("poligono"), ensure_ascii=False)
            if dados.get("poligono")
            else ""
        ),
    }
    return {
        coluna: "" if mapeada.get(coluna) is None else str(mapeada.get(coluna, ""))
        for coluna in COLUNAS_FAZENDAS
    }


def atualizar_fazenda(id_fazenda: str, dados: Dict[str, str]) -> Optional[Dict[str, str]]:
    """Atualiza uma fazenda de forma atômica, sem alterar seu identificador."""
    if supabase_configurado():
        salvo = cliente_supabase().atualizar(
            TABELA_FAZENDAS,
            _linha_para_supabase(dados, incluir_id=False),
            filtros={"id_fazenda": f"eq.{int(id_fazenda)}"},
        )
        return _linha_do_supabase(salvo) if salvo else None
    criar_base_se_nao_existir()
    fazendas = listar_fazendas()
    atualizado = None
    linhas = []
    for fazenda in fazendas:
        if str(fazenda.get("id_fazenda")) != str(id_fazenda):
            linhas.append({col: fazenda.get(col, "") for col in COLUNAS_FAZENDAS})
            continue

        mesclado = {**fazenda, **dict(dados), "id_fazenda": str(id_fazenda)}
        mesclado["proximidade_agua"] = bool_str(mesclado.get("proximidade_agua"))
        mesclado["tipo_operacao"] = str(
            mesclado.get("tipo_operacao") or "campo"
        ).lower()
        mesclado["arquivada"] = bool_str(mesclado.get("arquivada", False))
        mesclado["apolices_json"] = _normalizar_apolices_json(mesclado)
        atualizado = {col: mesclado.get(col, "") for col in COLUNAS_FAZENDAS}
        linhas.append(atualizado)

    if atualizado is None:
        return None

    temporario = ARQUIVO_FAZENDAS.with_suffix(".csv.tmp")
    try:
        with open(temporario, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=COLUNAS_FAZENDAS, delimiter=";")
            writer.writeheader()
            writer.writerows(linhas)
        os.replace(temporario, ARQUIVO_FAZENDAS)
    finally:
        if temporario.exists():
            temporario.unlink()
    return atualizado


def definir_arquivamento(id_fazenda: str, arquivada: bool) -> Optional[Dict[str, str]]:
    """Arquiva ou restaura uma fazenda sem apagar seu histórico."""
    if supabase_configurado():
        salvo = cliente_supabase().atualizar(
            TABELA_FAZENDAS,
            {"arquivada": bool_str(arquivada) == "True"},
            filtros={"id_fazenda": f"eq.{int(id_fazenda)}"},
        )
        return _linha_do_supabase(salvo) if salvo else None
    return atualizar_fazenda(id_fazenda, {"arquivada": arquivada})


if __name__ == "__main__":
    criar_base_se_nao_existir()
    print("Base estática de coordenadas:", ARQUIVO_COORDENADAS.resolve())
    print("Base de fazendas:", ARQUIVO_FAZENDAS.resolve())
    print("Fazendas cadastradas:")
    for f in listar_fazendas():
        print(
            f"  [{f['id_fazenda']}] {f['nome_fazenda']} | {f['cidade']}/{f['uf']} | apólice {f['numero_apolice']}"
        )
