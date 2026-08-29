"""Legenda e agregação territorial adotadas para o MapBiomas Brasil."""

from __future__ import annotations

from typing import Dict, Iterable, Mapping


LEGENDA_VERSION = "mapbiomas-brasil-colecao-10"

NOMES_CLASSES: Dict[int, str] = {
    1: "Floresta",
    3: "Formação Florestal",
    4: "Formação Savânica",
    5: "Mangue",
    6: "Floresta Alagável",
    9: "Silvicultura",
    10: "Formação Natural não Florestal",
    11: "Campo Alagado e Área Pantanosa",
    12: "Formação Campestre",
    13: "Outra Formação não Florestal",
    14: "Agropecuária",
    15: "Pastagem",
    18: "Agricultura",
    19: "Lavoura Temporária",
    20: "Cana",
    21: "Mosaico de Usos",
    22: "Área não Vegetada",
    23: "Praia, Duna e Areal",
    24: "Área Urbanizada",
    25: "Outras Áreas não Vegetadas",
    26: "Corpo d'Água",
    27: "Não Observado",
    29: "Afloramento Rochoso",
    30: "Mineração",
    31: "Aquicultura",
    32: "Apicum",
    33: "Rio, Lago e Oceano",
    35: "Dendê",
    36: "Lavoura Perene",
    39: "Soja",
    40: "Arroz",
    41: "Outras Lavouras Temporárias",
    46: "Café",
    47: "Citrus",
    48: "Outras Lavouras Perenes",
    49: "Restinga Arbórea",
    50: "Restinga Herbácea",
    62: "Algodão",
    75: "Usina Fotovoltaica",
}

CODIGOS_AGRICULTURA = frozenset({18, 19, 20, 35, 36, 39, 40, 41, 46, 47, 48, 62})
CODIGOS_PASTAGEM = frozenset({15})
CODIGOS_VEGETACAO_NATIVA = frozenset({1, 3, 4, 5, 6, 10, 11, 12, 13, 29, 32, 49, 50})

# A aquicultura (31) é uso antrópico, mas pertence oficialmente ao grupo
# Corpo d'Água na legenda MapBiomas adotada.
CODIGOS_AGUA = frozenset({26, 31, 33})
CODIGOS_NAO_OBSERVADOS = frozenset({27})

CATEGORIAS = (
    "agricultura",
    "pastagem",
    "vegetacao_nativa",
    "agua",
    "outros",
)


def nome_classe(codigo: int) -> str:
    """Retorna o nome conhecido sem descartar códigos futuros da coleção."""
    return NOMES_CLASSES.get(int(codigo), f"Código {int(codigo)}")


def categoria_codigo(codigo: int) -> str | None:
    """Classifica um código válido; 27 é deliberadamente não observado."""
    codigo = int(codigo)
    if codigo in CODIGOS_NAO_OBSERVADOS:
        return None
    if codigo in CODIGOS_AGRICULTURA:
        return "agricultura"
    if codigo in CODIGOS_PASTAGEM:
        return "pastagem"
    if codigo in CODIGOS_VEGETACAO_NATIVA:
        return "vegetacao_nativa"
    if codigo in CODIGOS_AGUA:
        return "agua"
    return "outros"


def agregar_areas(distribuicao: Mapping[int, float]) -> Dict[str, float]:
    """Soma áreas válidas por categoria sem ajustar percentuais artificialmente."""
    areas = {categoria: 0.0 for categoria in CATEGORIAS}
    for codigo, area_m2 in distribuicao.items():
        categoria = categoria_codigo(codigo)
        if categoria is not None:
            areas[categoria] += float(area_m2)
    return areas


def codigos_categoria(categoria: str) -> Iterable[int]:
    """Expõe os códigos explícitos para documentação e testes."""
    grupos = {
        "agricultura": CODIGOS_AGRICULTURA,
        "pastagem": CODIGOS_PASTAGEM,
        "vegetacao_nativa": CODIGOS_VEGETACAO_NATIVA,
        "agua": CODIGOS_AGUA,
        "nao_observado": CODIGOS_NAO_OBSERVADOS,
    }
    return grupos.get(categoria, frozenset())


__all__ = [
    "CATEGORIAS",
    "CODIGOS_AGRICULTURA",
    "CODIGOS_AGUA",
    "CODIGOS_NAO_OBSERVADOS",
    "CODIGOS_PASTAGEM",
    "CODIGOS_VEGETACAO_NATIVA",
    "LEGENDA_VERSION",
    "NOMES_CLASSES",
    "agregar_areas",
    "categoria_codigo",
    "codigos_categoria",
    "nome_classe",
]
