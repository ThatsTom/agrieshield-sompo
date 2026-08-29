"""Adapters puros das fontes atuais para os contratos canônicos.

Nenhuma função deste módulo coleta, persiste ou imputa dados. Os payloads são
recebidos por argumento; zeros legítimos são preservados e ausências continuam
como ``None``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any, Mapping

import pandas as pd

from .modelos import (
    AgregacaoTemporal,
    AnaliseGeoespacialNormalizada,
    AnaliseTerritorialNormalizada,
    AtributoGeoespacial,
    CadastroNormalizado,
    ContextoGeometriaTerritorial,
    DadoNormalizado,
    DistribuicaoClasseTerritorial,
    FonteDado,
    NaturezaDado,
    NivelProcessamento,
    ParametrosGeoespaciais,
    QualidadeDado,
    QualidadeTerritorial,
    ReferenciaEspacial,
    ReferenciaTemporal,
    SerieDadosNormalizados,
    StatusQualidade,
)


MAPA_NASA = {
    "temp_media_c": ("temperatura_media_diaria_c", "°C"),
    "temp_maxima_c": ("temperatura_maxima_diaria_c", "°C"),
    "temp_minima_c": ("temperatura_minima_diaria_c", "°C"),
    "precipitacao_mm": ("precipitacao_diaria_mm", "mm/dia"),
    "umidade_relativa_pct": ("umidade_relativa_media_diaria_pct", "%"),
    "radiacao_solar_mj": ("radiacao_solar_diaria_mj_m2", "MJ/m²/dia"),
    "vento_ms": ("vento_medio_diario_m_s", "m/s"),
}

MAPA_INMET = {
    "temperatura_c": ("temperatura_ar_c", "°C"),
    "precipitacao_mm": ("precipitacao_horaria_mm", "mm"),
    "umidade_pct": ("umidade_relativa_pct", "%"),
    "vento_m_s": ("vento_velocidade_m_s", "m/s"),
    "rajada_m_s": ("vento_rajada_m_s", "m/s"),
    "direcao_vento_graus": ("vento_direcao_graus", "graus"),
    "pressao_hpa": ("pressao_atmosferica_hpa", "hPa"),
    "radiacao_kj_m2": ("radiacao_global_kj_m2", "kJ/m²"),
}

MAPA_OPEN_METEO = {
    "precipitacao_mm": ("precipitacao_prevista_diaria_mm", "precipitation_sum"),
    "prob_precip_pct": (
        "probabilidade_precipitacao_maxima_diaria_pct",
        "precipitation_probability_max",
    ),
    "temp_max_c": ("temperatura_maxima_prevista_diaria_c", "temperature_2m_max"),
}


def _valor_opcional(valor: Any) -> float | int | bool | str | None:
    """Converte apenas marcadores de ausência; não usa coerção booleana."""
    try:
        ausente = bool(pd.isna(valor))
    except (TypeError, ValueError):
        ausente = False
    if valor is None or ausente:
        return None
    if hasattr(valor, "item"):
        valor = valor.item()
    return valor


def _datetime_utc(valor: Any, campo: str) -> datetime:
    if isinstance(valor, datetime):
        instante = valor
    elif isinstance(valor, str):
        try:
            instante = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{campo} inválido") from exc
    else:
        raise ValueError(f"{campo} inválido")
    if instante.tzinfo is None:
        raise ValueError(f"{campo} deve conter timezone")
    return instante.astimezone(timezone.utc)


def _status_conjunto(total: int, disponiveis: int) -> StatusQualidade:
    if total == 0 or disponiveis == 0:
        return StatusQualidade.AUSENTE
    if disponiveis < total:
        return StatusQualidade.PARCIAL
    return StatusQualidade.DISPONIVEL


def _bool_declarado(valor: Any) -> bool | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in {"true", "1", "sim"}:
            return True
        if texto in {"false", "0", "não", "nao", ""}:
            return False
    raise ValueError("proximidade_agua deve ser booleana")


def normalizar_cadastro(fazenda: Mapping[str, Any]) -> CadastroNormalizado:
    """Representa o cadastro atual sem alterar sua estrutura persistida."""
    area_bruta = fazenda.get("area_ha")
    area = None if area_bruta in (None, "") else float(area_bruta)
    return CadastroNormalizado(
        id_fazenda=str(fazenda["id_fazenda"]),
        nome=str(fazenda.get("nome_fazenda", "")),
        numero_apolice=str(fazenda.get("numero_apolice", "")),
        cep=str(fazenda.get("cep", "")),
        cidade=str(fazenda.get("cidade", "")),
        uf=str(fazenda.get("uf", "")),
        latitude=float(fazenda["latitude"]),
        longitude=float(fazenda["longitude"]),
        area_ha=area,
        tipo_operacao=str(fazenda.get("tipo_operacao", "")),
        proximidade_agua_declarada=_bool_declarado(fazenda.get("proximidade_agua")),
    )


def normalizar_nasa(
    dataframe: pd.DataFrame,
    origem: str,
    contexto: Mapping[str, Any] | None = None,
) -> SerieDadosNormalizados:
    """Normaliza a série diária da Etapa 2 sem modificar o DataFrame recebido."""
    origem_normalizada = str(origem).strip().lower()
    if origem_normalizada == "nasa_power":
        fonte = FonteDado.NASA_POWER
        simulado = False
        flags: tuple[str, ...] = ()
    elif origem_normalizada == "simulado":
        fonte = FonteDado.SIMULADOR_INTERNO
        simulado = True
        flags = ("DADO_SINTETICO",)
    else:
        raise ValueError("origem NASA desconhecida ou ambígua")

    ausentes = {"data", *MAPA_NASA}.difference(dataframe.columns)
    if ausentes:
        raise ValueError(f"DataFrame NASA sem colunas obrigatórias: {sorted(ausentes)}")

    # ``sort_values`` retorna outro objeto; o input e sua ordem permanecem intactos.
    ordenado = dataframe.sort_values("data", kind="stable")
    dados: list[DadoNormalizado] = []
    disponiveis = 0
    for _, linha in ordenado.iterrows():
        instante = pd.to_datetime(linha["data"], errors="raise")
        dia: date = instante.date()
        referencia = ReferenciaTemporal(
            inicio=dia,
            fim=dia,
            timezone=None,
            agregacao=AgregacaoTemporal.DIARIA,
        )
        for legado, (canonico, unidade) in MAPA_NASA.items():
            valor = _valor_opcional(linha[legado])
            if valor is not None:
                disponiveis += 1
            dados.append(
                DadoNormalizado(
                    variavel=canonico,
                    valor=valor,
                    unidade=unidade,
                    fonte=fonte,
                    natureza=NaturezaDado.HISTORICO,
                    nivel_processamento=NivelProcessamento.NORMALIZADO,
                    referencia_temporal=referencia,
                    qualidade=QualidadeDado(
                        status=(
                            StatusQualidade.DISPONIVEL
                            if valor is not None
                            else StatusQualidade.AUSENTE
                        ),
                        simulado=simulado,
                        flags=flags,
                    ),
                    metadados={"campo_origem": legado},
                )
            )
    total = len(dados)
    return SerieDadosNormalizados(
        id_fazenda=(
            str(contexto["id_fazenda"])
            if contexto and contexto.get("id_fazenda") is not None
            else None
        ),
        fonte=fonte,
        natureza=NaturezaDado.HISTORICO,
        agregacao=AgregacaoTemporal.DIARIA,
        dados=tuple(dados),
        qualidade=QualidadeDado(
            status=_status_conjunto(total, disponiveis),
            simulado=simulado,
            cobertura_pct=(disponiveis * 100.0 / total if total else None),
            flags=flags,
        ),
        contexto={**dict(contexto or {}), "origem_recebida": origem_normalizada},
    )


def normalizar_inmet(resultado: Mapping[str, Any]) -> SerieDadosNormalizados:
    """Normaliza observações horárias de uma única estação INMET."""
    estacao = dict(resultado.get("estacao") or {})
    codigo_esperado = str(estacao.get("codigo") or "").strip().upper()
    if not codigo_esperado:
        raise ValueError("payload INMET sem estação")
    qualidade_fonte = dict(resultado.get("qualidade") or {})
    qualidade_variaveis = qualidade_fonte.get("variaveis") or {}
    dados: list[DadoNormalizado] = []
    disponiveis = 0
    for observacao in resultado.get("observacoes") or []:
        codigo = str(observacao.get("codigo_estacao") or "").strip().upper()
        if codigo != codigo_esperado:
            raise ValueError("payload INMET mistura estações")
        observado = _datetime_utc(
            observacao.get("observado_em_utc"), "observado_em_utc"
        )
        ingerido = _datetime_utc(observacao.get("ingerido_em_utc"), "ingerido_em_utc")
        referencia = ReferenciaTemporal(
            inicio=observado,
            fim=observado,
            timezone="UTC",
            agregacao=AgregacaoTemporal.HORARIA,
        )
        for legado, (canonico, unidade) in MAPA_INMET.items():
            valor = _valor_opcional(observacao.get(legado))
            if valor is not None:
                disponiveis += 1
            disponibilidade = qualidade_variaveis.get(legado) or {}
            cobertura = disponibilidade.get("disponibilidade_pct")
            dados.append(
                DadoNormalizado(
                    variavel=canonico,
                    valor=valor,
                    unidade=unidade,
                    fonte=FonteDado.INMET,
                    natureza=NaturezaDado.OBSERVADO,
                    nivel_processamento=NivelProcessamento.NORMALIZADO,
                    referencia_temporal=referencia,
                    coletado_em_utc=ingerido,
                    qualidade=QualidadeDado(
                        status=(
                            StatusQualidade.DISPONIVEL
                            if valor is not None
                            else StatusQualidade.AUSENTE
                        ),
                        cobertura_pct=cobertura,
                    ),
                    metadados={
                        "campo_origem": legado,
                        "codigo_estacao": codigo,
                        "disponibilidade": dict(disponibilidade),
                    },
                )
            )
    total = len(dados)
    horas_esperadas = qualidade_fonte.get("horas_esperadas")
    horas_observadas = qualidade_fonte.get("horas_observadas")
    cobertura_serie = None
    if horas_esperadas:
        cobertura_serie = min(
            100.0, float(horas_observadas or 0) * 100.0 / float(horas_esperadas)
        )
    return SerieDadosNormalizados(
        id_fazenda=(
            str(resultado["id_fazenda"])
            if resultado.get("id_fazenda") is not None
            else None
        ),
        fonte=FonteDado.INMET,
        natureza=NaturezaDado.OBSERVADO,
        agregacao=AgregacaoTemporal.HORARIA,
        dados=tuple(dados),
        qualidade=QualidadeDado(
            status=_status_conjunto(total, disponiveis),
            cobertura_pct=cobertura_serie,
        ),
        contexto={
            "estacao": estacao,
            "periodo": dict(resultado.get("periodo") or {}),
            "qualidade_fonte": qualidade_fonte,
            "origem": dict(resultado.get("origem") or {}),
        },
    )


def normalizar_open_meteo(
    resultado: Mapping[str, Any],
) -> SerieDadosNormalizados:
    """Normaliza o contrato rico Open-Meteo sem imputar ausências."""
    fonte_bruta = str(resultado.get("fonte") or "")
    simulado = resultado.get("simulado")
    if resultado.get("natureza") != "PREVISTO" or not isinstance(simulado, bool):
        raise ValueError("contrato Open-Meteo sem proveniência válida")
    if fonte_bruta == "OPEN_METEO" and simulado is False:
        fonte = FonteDado.OPEN_METEO
        flags_origem: tuple[str, ...] = ()
    elif fonte_bruta == "SIMULADOR_INTERNO" and simulado is True:
        fonte = FonteDado.SIMULADOR_INTERNO
        flags_origem = ("DADO_SINTETICO",)
    else:
        raise ValueError("fonte e simulação Open-Meteo são incoerentes")

    coletado = _datetime_utc(resultado.get("coletado_em_utc"), "coletado_em_utc")
    requisicao = dict(resultado.get("requisicao") or {})
    resposta = dict(resultado.get("resposta") or {})
    qualidade_fonte = dict(resultado.get("qualidade") or {})
    timezone_dados = resposta.get("timezone") or requisicao.get("timezone_solicitado")
    unidades = dict(resposta.get("unidades") or {})
    flags = tuple(
        dict.fromkeys(
            [
                *flags_origem,
                *(qualidade_fonte.get("flags") or ()),
            ]
        )
    )

    dados: list[DadoNormalizado] = []
    disponiveis = 0
    for dia in resultado.get("dias") or ():
        if not isinstance(dia, Mapping):
            raise ValueError("contrato Open-Meteo contém dia inválido")
        try:
            data_local = date.fromisoformat(str(dia["data_local"]))
        except (KeyError, ValueError) as exc:
            raise ValueError("contrato Open-Meteo contém data inválida") from exc
        referencia = ReferenciaTemporal(
            inicio=data_local,
            fim=data_local,
            timezone=str(timezone_dados) if timezone_dados else None,
            agregacao=AgregacaoTemporal.DIARIA,
        )
        for campo, (variavel, campo_unidade) in MAPA_OPEN_METEO.items():
            valor = _valor_opcional(dia.get(campo))
            if valor is not None:
                disponiveis += 1
            dados.append(
                DadoNormalizado(
                    variavel=variavel,
                    valor=valor,
                    unidade=unidades.get(campo_unidade),
                    fonte=fonte,
                    natureza=NaturezaDado.PREVISTO,
                    nivel_processamento=NivelProcessamento.NORMALIZADO,
                    referencia_temporal=referencia,
                    coletado_em_utc=coletado,
                    qualidade=QualidadeDado(
                        status=(
                            StatusQualidade.DISPONIVEL
                            if valor is not None
                            else StatusQualidade.AUSENTE
                        ),
                        simulado=simulado,
                        flags=flags,
                    ),
                    metadados={"campo_origem": campo},
                )
            )

    total = len(dados)
    status = _status_payload(qualidade_fonte.get("status"))
    if total == 0 and status == StatusQualidade.DISPONIVEL:
        status = StatusQualidade.AUSENTE
    return SerieDadosNormalizados(
        fonte=fonte,
        natureza=NaturezaDado.PREVISTO,
        agregacao=AgregacaoTemporal.DIARIA,
        dados=tuple(dados),
        qualidade=QualidadeDado(
            status=status,
            simulado=simulado,
            flags=flags,
        ),
        contexto={
            "schema_version": resultado.get("schema_version"),
            "requisicao": requisicao,
            "resposta": resposta,
            "qualidade_fonte": qualidade_fonte,
            "erro_origem": resultado.get("erro_origem"),
            "valores_disponiveis": disponiveis,
            "valores_esperados": total,
        },
    )


def _status_payload(valor: str | None) -> StatusQualidade:
    return {
        "sucesso": StatusQualidade.DISPONIVEL,
        "disponivel": StatusQualidade.DISPONIVEL,
        "parcial": StatusQualidade.PARCIAL,
        "erro": StatusQualidade.INVALIDO,
        "indisponivel": StatusQualidade.AUSENTE,
    }.get(str(valor or "").lower(), StatusQualidade.INVALIDO)


def _atributo_geo(
    atributos: Mapping[str, Any],
    chave: str,
    variavel: str,
    unidade: str,
    fonte: FonteDado,
) -> AtributoGeoespacial:
    bruto = dict(atributos.get(chave) or {})
    valor = _valor_opcional(bruto.get("valor"))
    return AtributoGeoespacial(
        variavel=variavel,
        valor=valor,
        unidade=unidade,
        fonte=fonte,
        dataset=str(bruto.get("fonte") or ""),
        banda=str(bruto.get("banda") or ""),
        resolucao_m=float(bruto["resolucao_m"]),
        metodologia=str(bruto.get("metodologia") or ""),
        qualidade=QualidadeDado(status=_status_payload(bruto.get("status"))),
    )


def normalizar_geoespacial(
    resultado: Mapping[str, Any],
    *,
    calculado_em_utc: datetime | None = None,
) -> AnaliseGeoespacialNormalizada:
    """Preserva o contrato estrutural SRTM/MERIT produzido pela Etapa 4."""
    local = resultado.get("localizacao") or {}
    parametros = resultado.get("parametros") or {}
    atributos = resultado.get("atributos") or {}
    contexto = dict(resultado.get("qualidade") or {})
    cobertura = contexto.get("cobertura_srtm_pct")
    calculado = (
        _datetime_utc(calculado_em_utc, "calculado_em_utc")
        if calculado_em_utc is not None
        else None
    )
    return AnaliseGeoespacialNormalizada(
        referencia=ReferenciaEspacial(
            latitude=float(local["latitude"]), longitude=float(local["longitude"])
        ),
        declividade_media_graus=_atributo_geo(
            atributos,
            "declividade_media",
            "declividade_media_graus",
            "graus",
            FonteDado.SRTM,
        ),
        posicao_topografica_relativa_m=_atributo_geo(
            atributos,
            "posicao_topografica_relativa",
            "posicao_topografica_relativa_m",
            "m",
            FonteDado.SRTM,
        ),
        distancia_drenagem_m=_atributo_geo(
            atributos,
            "distancia_drenagem",
            "distancia_drenagem_m",
            "m",
            FonteDado.MERIT_HYDRO,
        ),
        area_drenagem_montante_km2=_atributo_geo(
            atributos,
            "area_drenagem_montante",
            "area_drenagem_montante_km2",
            "km²",
            FonteDado.MERIT_HYDRO,
        ),
        parametros=ParametrosGeoespaciais(
            raio_analise_m=float(parametros["raio_analise_m"]),
            limiar_drenagem_km2=float(parametros["limiar_drenagem_km2"]),
            raio_busca_drenagem_m=float(parametros["raio_busca_drenagem_m"]),
        ),
        qualidade=QualidadeDado(
            status=_status_payload(resultado.get("status")),
            cobertura_pct=cobertura,
            flags=tuple(contexto.get("flags") or ()),
        ),
        qualidade_contexto=contexto,
        fontes=tuple(dict(item) for item in resultado.get("fontes") or ()),
        schema_version=str(resultado.get("schema_version") or ""),
        algorithm_version=str(resultado.get("algorithm_version") or ""),
        calculado_em_utc=calculado,
        status_fonte=str(resultado.get("status") or ""),
    )


def normalizar_mapbiomas(resultado: Mapping[str, Any]) -> AnaliseTerritorialNormalizada:
    """Normaliza a análise territorial sem reduzir seu contexto espacial."""
    ref = resultado.get("referencia") or {}
    mapa = resultado.get("mapbiomas") or {}
    cobertura = resultado.get("cobertura") or {}
    qualidade = resultado.get("qualidade") or {}
    meta = resultado.get("metadados") or {}
    cobertura_pct = float(qualidade["cobertura_valida_pct"])
    return AnaliseTerritorialNormalizada(
        id_fazenda=str(resultado["id_fazenda"]),
        referencia=ReferenciaEspacial(
            latitude=float(ref["latitude"]),
            longitude=float(ref["longitude"]),
            area_ha=float(ref["area_ha"]),
            raio_equivalente_m=float(ref["raio_equivalente_m"]),
        ),
        geometria=ContextoGeometriaTerritorial(
            tipo_geometria=str(ref["tipo_geometria"]),
            metodo_geometria=str(ref["metodo_geometria"]),
            origem_coordenada=str(ref["origem_coordenada"]),
            precisao_espacial=str(ref["precisao_espacial"]),
            warning=str(meta["warning_geometria"]),
        ),
        ano_referencia=int(mapa["ano_referencia"]),
        asset_id=str(mapa["asset_id"]),
        colecao=str(mapa["colecao"]),
        asset_version=str(mapa["asset_version"]),
        banda=str(mapa["banda"]),
        legend_version=str(mapa["versao_legenda"]),
        algorithm_version=str(mapa["algorithm_version"]),
        schema_version=str(meta["schema_version"]),
        fingerprint=str(meta["input_fingerprint"]),
        classe_predominante_codigo=int(cobertura["classe_predominante_codigo"]),
        classe_predominante_nome=str(cobertura["classe_predominante_nome"]),
        agricultura_pct=float(cobertura["agricultura_pct"]),
        pastagem_pct=float(cobertura["pastagem_pct"]),
        vegetacao_nativa_pct=float(cobertura["vegetacao_nativa_pct"]),
        agua_pct=float(cobertura["agua_pct"]),
        outros_pct=float(cobertura["outros_pct"]),
        distribuicao_bruta=tuple(
            DistribuicaoClasseTerritorial(**dict(item))
            for item in resultado.get("distribuicao_bruta") or ()
        ),
        qualidade_territorial=QualidadeTerritorial(**dict(qualidade)),
        qualidade=QualidadeDado(
            status=(
                StatusQualidade.DISPONIVEL
                if math.isclose(cobertura_pct, 100.0)
                else StatusQualidade.PARCIAL
            ),
            cobertura_pct=cobertura_pct,
            flags=(
                ("GEOMETRIA_ESTIMADA",)
                if str(ref.get("tipo_geometria")) == "ESTIMADA"
                else ()
            ),
        ),
        calculado_em_utc=_datetime_utc(meta["calculado_em_utc"], "calculado_em_utc"),
    )


__all__ = [
    "MAPA_INMET",
    "MAPA_NASA",
    "MAPA_OPEN_METEO",
    "normalizar_cadastro",
    "normalizar_geoespacial",
    "normalizar_inmet",
    "normalizar_mapbiomas",
    "normalizar_nasa",
    "normalizar_open_meteo",
]
