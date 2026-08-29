"""Smoke test local do contexto territorial exigido pela exposicao v1."""

from __future__ import annotations

from backend.app.provedor_contexto_territorial_persistido import (
    ProvedorContextoTerritorialPersistido,
)
from backend.etl.repositorio_fazendas_geoespaciais import (
    buscar_registro_geoespacial,
    listar_registros_geoespaciais,
)


def verificar_contexto_local() -> str:
    provedor = ProvedorContextoTerritorialPersistido()
    for item in listar_registros_geoespaciais():
        id_fazenda = str(item.get("id_fazenda") or "").strip()
        if not id_fazenda:
            continue
        registro = buscar_registro_geoespacial(id_fazenda)
        if not registro or registro.get("status") not in {"sucesso", "parcial"}:
            continue
        provedor.obter(
            id_fazenda=id_fazenda,
            latitude=float(registro["latitude_referencia"]),
            longitude=float(registro["longitude_referencia"]),
        )
        return id_fazenda
    raise RuntimeError("nenhum contexto territorial utilizavel foi encontrado")


if __name__ == "__main__":
    try:
        fazenda_validada = verificar_contexto_local()
    except Exception as exc:
        raise SystemExit(f"[FALHA] contexto territorial: {exc}") from exc
    print(f"[OK] contexto territorial da exposicao: fazenda {fazenda_validada}")
