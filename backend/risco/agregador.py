"""Composição pura de features já normalizadas, sem busca ou pontuação."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .modelos import (
    AgregacaoTemporal,
    AnaliseGeoespacialNormalizada,
    AnaliseTerritorialNormalizada,
    CadastroNormalizado,
    ConjuntoFeatures,
    FEATURES_VERSION,
    FeatureNeutra,
    FonteDado,
    GrupoFeatures,
    LinhagemFeature,
    NaturezaDado,
    QualidadeDado,
    ReferenciaTemporal,
    StatusQualidade,
)


def _ausente(motivo: str) -> GrupoFeatures:
    return GrupoFeatures(
        qualidade=QualidadeDado(
            status=StatusQualidade.AUSENTE,
            flags=("FONTE_AUSENTE",),
        ),
        contexto={"motivo": motivo},
    )


def _linhagem(
    *,
    algoritmo: str,
    fonte: FonteDado,
    natureza: NaturezaDado,
    entrada: str,
) -> LinhagemFeature:
    return LinhagemFeature(
        algoritmo=algoritmo,
        versao=FEATURES_VERSION,
        fonte=fonte,
        natureza=natureza,
        janela="nao_temporal",
        entradas=(entrada,),
    )


def _grupo_geoespacial(
    analise: AnaliseGeoespacialNormalizada | None,
) -> GrupoFeatures:
    if analise is None:
        return _ausente("analise_geoespacial_nao_fornecida")
    atributos = (
        analise.declividade_media_graus,
        analise.posicao_topografica_relativa_m,
        analise.distancia_drenagem_m,
        analise.area_drenagem_montante_km2,
    )
    features = tuple(
        FeatureNeutra(
            nome=atributo.variavel,
            valor=atributo.valor,
            unidade=atributo.unidade,
            fonte=atributo.fonte,
            natureza=NaturezaDado.ESTRUTURAL,
            qualidade=atributo.qualidade,
            linhagem=_linhagem(
                algoritmo=analise.algorithm_version,
                fonte=atributo.fonte,
                natureza=NaturezaDado.ESTRUTURAL,
                entrada=atributo.variavel,
            ),
            metadados={
                "dataset": atributo.dataset,
                "banda": atributo.banda,
                "resolucao_m": atributo.resolucao_m,
                "metodologia": atributo.metodologia,
            },
        )
        for atributo in atributos
    )
    return GrupoFeatures(
        features=features,
        qualidade=analise.qualidade,
        contexto={
            "referencia": analise.referencia.model_dump(mode="json"),
            "parametros": analise.parametros.model_dump(mode="json"),
            "qualidade_fonte": analise.qualidade_contexto,
            "fontes": list(analise.fontes),
            "schema_version": analise.schema_version,
            "algorithm_version": analise.algorithm_version,
            "status_fonte": analise.status_fonte,
            "calculado_em_utc": (
                analise.calculado_em_utc.isoformat()
                if analise.calculado_em_utc
                else None
            ),
        },
    )


def _grupo_territorial(
    analise: AnaliseTerritorialNormalizada | None,
) -> GrupoFeatures:
    if analise is None:
        return _ausente("analise_mapbiomas_nao_fornecida")
    valores: tuple[tuple[str, Any, str | None], ...] = (
        ("classe_predominante_codigo", analise.classe_predominante_codigo, None),
        ("classe_predominante_nome", analise.classe_predominante_nome, None),
        ("agricultura_pct", analise.agricultura_pct, "%"),
        ("pastagem_pct", analise.pastagem_pct, "%"),
        ("vegetacao_nativa_pct", analise.vegetacao_nativa_pct, "%"),
        ("agua_pct", analise.agua_pct, "%"),
        ("outros_pct", analise.outros_pct, "%"),
        (
            "cobertura_valida_pct",
            analise.qualidade_territorial.cobertura_valida_pct,
            "%",
        ),
    )
    features = tuple(
        FeatureNeutra(
            nome=nome,
            valor=valor,
            unidade=unidade,
            fonte=FonteDado.MAPBIOMAS,
            natureza=NaturezaDado.ESTRUTURAL,
            referencia_temporal=ReferenciaTemporal(
                inicio=datetime(analise.ano_referencia, 1, 1).date(),
                fim=datetime(analise.ano_referencia, 12, 31).date(),
                timezone=None,
                agregacao=AgregacaoTemporal.ANUAL,
            ),
            qualidade=analise.qualidade,
            linhagem=_linhagem(
                algoritmo=analise.algorithm_version,
                fonte=FonteDado.MAPBIOMAS,
                natureza=NaturezaDado.ESTRUTURAL,
                entrada=nome,
            ),
        )
        for nome, valor, unidade in valores
    )
    return GrupoFeatures(
        features=features,
        qualidade=analise.qualidade,
        contexto={
            "referencia": analise.referencia.model_dump(mode="json"),
            "geometria": analise.geometria.model_dump(mode="json"),
            "ano_referencia": analise.ano_referencia,
            "asset_id": analise.asset_id,
            "colecao": analise.colecao,
            "asset_version": analise.asset_version,
            "banda": analise.banda,
            "legend_version": analise.legend_version,
            "schema_version": analise.schema_version,
            "algorithm_version": analise.algorithm_version,
            "fingerprint": analise.fingerprint,
            "distribuicao_bruta": [
                item.model_dump(mode="json") for item in analise.distribuicao_bruta
            ],
            "qualidade_territorial": analise.qualidade_territorial.model_dump(
                mode="json"
            ),
            "calculado_em_utc": analise.calculado_em_utc.isoformat(),
        },
    )


def _grupo_operacional(cadastro: CadastroNormalizado) -> GrupoFeatures:
    valores: tuple[tuple[str, Any, str | None], ...] = (
        ("tipo_operacao", cadastro.tipo_operacao, None),
        ("proximidade_agua_declarada", cadastro.proximidade_agua_declarada, None),
        ("area_ha", cadastro.area_ha, "ha"),
    )
    features = tuple(
        FeatureNeutra(
            nome=nome,
            valor=valor,
            unidade=unidade,
            fonte=FonteDado.CADASTRO,
            natureza=NaturezaDado.CADASTRAL,
            qualidade=QualidadeDado(
                status=(
                    StatusQualidade.DISPONIVEL
                    if valor is not None
                    else StatusQualidade.AUSENTE
                )
            ),
            linhagem=_linhagem(
                algoritmo="normalizacao_cadastro",
                fonte=FonteDado.CADASTRO,
                natureza=NaturezaDado.CADASTRAL,
                entrada=nome,
            ),
        )
        for nome, valor, unidade in valores
    )
    status = (
        StatusQualidade.DISPONIVEL
        if all(item.valor is not None for item in features)
        else StatusQualidade.PARCIAL
    )
    return GrupoFeatures(
        features=features,
        qualidade=QualidadeDado(status=status),
        contexto={
            "latitude": cadastro.latitude,
            "longitude": cadastro.longitude,
            "nome": cadastro.nome,
            "numero_apolice": cadastro.numero_apolice,
            "cep": cadastro.cep,
            "cidade": cadastro.cidade,
            "uf": cadastro.uf,
        },
    )


def _qualidade_global(grupos: tuple[GrupoFeatures, ...]) -> QualidadeDado:
    status_grupos = [grupo.qualidade.status for grupo in grupos]
    if all(status == StatusQualidade.DISPONIVEL for status in status_grupos):
        status = StatusQualidade.DISPONIVEL
    elif all(status == StatusQualidade.AUSENTE for status in status_grupos):
        status = StatusQualidade.AUSENTE
    elif any(status == StatusQualidade.INVALIDO for status in status_grupos):
        status = StatusQualidade.INVALIDO
    else:
        status = StatusQualidade.PARCIAL
    return QualidadeDado(
        status=status,
        simulado=any(grupo.qualidade.simulado for grupo in grupos),
        cobertura_pct=None,
        flags=tuple(
            dict.fromkeys(flag for grupo in grupos for flag in grupo.qualidade.flags)
        ),
    )


def agregar_features(
    *,
    cadastro: CadastroNormalizado,
    climaticas: GrupoFeatures | None = None,
    geoespacial: AnaliseGeoespacialNormalizada | None = None,
    territorial: AnaliseTerritorialNormalizada | None = None,
    calculado_em_utc: datetime | None = None,
) -> ConjuntoFeatures:
    """Compõe grupos independentes; uma fonte ausente não destrói o conjunto."""
    climaticas_grupo = climaticas or _ausente("features_climaticas_nao_fornecidas")
    geo_grupo = _grupo_geoespacial(geoespacial)
    territorial_grupo = _grupo_territorial(territorial)
    operacional_grupo = _grupo_operacional(cadastro)
    grupos = (climaticas_grupo, geo_grupo, territorial_grupo, operacional_grupo)
    instante = calculado_em_utc or datetime.now(timezone.utc)
    if instante.tzinfo is None:
        raise ValueError("calculado_em_utc deve conter timezone")
    return ConjuntoFeatures(
        id_fazenda=cadastro.id_fazenda,
        calculado_em_utc=instante.astimezone(timezone.utc),
        versao=FEATURES_VERSION,
        climaticas=climaticas_grupo,
        geoespaciais_hidrologicas=geo_grupo,
        territoriais=territorial_grupo,
        operacionais=operacional_grupo,
        qualidade_global=_qualidade_global(grupos),
    )


__all__ = ["agregar_features"]
