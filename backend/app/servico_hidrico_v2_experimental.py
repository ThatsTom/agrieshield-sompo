"""Camada fina de comparação Hídrico v1 × V2, isolada do endpoint oficial."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import Field

from backend.app.servico_avaliacao_exposicao import ServicoAvaliacaoExposicao
from backend.exposicao.avaliacao_exposicao import (
    executar_avaliacao_exposicao_maquinario,
)
from backend.exposicao.hidrico_v2_experimental import (
    LIMITACOES_METODOLOGICAS,
    METODOLOGIA_HIDRICO_V2,
    ContextoTerritorialHidricoV2,
    agregar_hidrico_v2_experimental,
    calcular_hidrico_v2_diario,
    calcular_score_paralelo,
    calcular_t3,
)
from backend.exposicao.politica import (
    ClassificacaoIndice,
    criar_politica_agrishield_equip_v1,
)
from backend.risco.modelos import FonteDado, ModeloDominio


DISCLAIMER = (
    "Resultado experimental para comparação metodológica. Não representa "
    "probabilidade atuarial de sinistro e não substitui o Hídrico v1 oficial."
)
AVISOS = tuple(
    dict.fromkeys(
        (
            *LIMITACOES_METODOLOGICAS,
            "As normalizações não são parâmetros hidrológicos oficiais.",
            "Hídrico v1 continua sendo a metodologia oficial da política atual.",
        )
    )
)


class StatusExperimental(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"


class TerritorioHidricoV2Dto(ModeloDominio):
    distancia_drenagem_m: float
    area_drenagem_montante_km2: float
    posicao_topografica_relativa_m: float
    d2: float = Field(ge=0, le=100)
    a2: float = Field(ge=0, le=100)
    p2: float = Field(ge=0, le=100)
    t3: float = Field(ge=0, le=100)


class JanelaHidricoV2Dto(ModeloDominio):
    hidrico_v1_90d: float | None = None
    classificacao_v1: ClassificacaoIndice | None = None
    hidrico_v2_90d: float | None = None
    classificacao_v2: ClassificacaoIndice | None = None
    delta_hidrico: float | None = None
    score_v1: float | None = None
    score_v2_experimental: float | None = None
    delta_score: float | None = None
    classificacao_score_v1: ClassificacaoIndice | None = None
    classificacao_score_v2: ClassificacaoIndice | None = None


class DiaRelevanteHidricoV2Dto(ModeloDominio):
    data: date
    janela: str
    h1: float | None = None
    g3: float | None = None
    incremento_territorial: float | None = None
    h2: float | None = None
    classe_h1: ClassificacaoIndice | None = None
    classe_h2: ClassificacaoIndice | None = None


class ItemProvenienciaHidricoV2Dto(ModeloDominio):
    fonte: str
    papel: tuple[str, ...]
    utilizada: bool


class ResultadoInterfaceHidricoV2Dto(ModeloDominio):
    id_fazenda: str
    nome_fazenda: str
    data_referencia: date
    fonte_meteorologica: FonteDado
    status: StatusExperimental = StatusExperimental.EXPERIMENTAL
    metodologia: str = METODOLOGIA_HIDRICO_V2
    territorio: TerritorioHidricoV2Dto
    janela_anterior: JanelaHidricoV2Dto
    janela_atual: JanelaHidricoV2Dto
    dias_relevantes: tuple[DiaRelevanteHidricoV2Dto, ...]
    proveniencia: tuple[ItemProvenienciaHidricoV2Dto, ...]
    avisos_metodologicos: tuple[str, ...] = AVISOS
    disclaimer: str = DISCLAIMER


def _valor(atributo) -> float | None:
    return atributo.valor


class ServicoHidricoV2Experimental:
    def __init__(self, servico_v1: ServicoAvaliacaoExposicao) -> None:
        self._servico_v1 = servico_v1

    def avaliar(
        self,
        id_fazenda: str,
        data_referencia: date,
        *,
        fonte: FonteDado = FonteDado.NASA_POWER,
        detalhe_completo: bool = False,
    ) -> ResultadoInterfaceHidricoV2Dto:
        insumos = self._servico_v1.obter_insumos_avaliacao(
            id_fazenda, data_referencia, fonte=fonte
        )
        politica = criar_politica_agrishield_equip_v1()
        avaliacao = executar_avaliacao_exposicao_maquinario(
            insumos.serie, insumos.contexto_territorial, politica
        )
        geo = insumos.contexto_territorial
        contexto = ContextoTerritorialHidricoV2(
            distancia_drenagem_m=_valor(geo.distancia_drenagem_m),
            area_drenagem_montante_km2=_valor(geo.area_drenagem_montante_km2),
            posicao_topografica_relativa_m=_valor(geo.posicao_topografica_relativa_m),
        )
        susc = calcular_t3(contexto)
        if susc.t3 is None:
            # Mantém a semântica tipada já usada pelo provedor oficial.
            from backend.app.servico_avaliacao_exposicao import (
                ContextoTerritorialIndisponivel,
            )

            raise ContextoTerritorialIndisponivel(str(id_fazenda))
        por_data_h1 = {
            x.data: x.indice_hidrico_meteorologico
            for validacao in (avaliacao.validacao_anterior, avaliacao.validacao_atual)
            for x in validacao.exposicao_hidrica.condicoes_hidricas
        }
        resultados = []
        for feature in avaliacao.features_compartilhadas.dias:
            if feature.data not in por_data_h1:
                continue
            resultados.append(
                calcular_hidrico_v2_diario(
                    data=feature.data,
                    h1_meteorologico=por_data_h1[feature.data],
                    acumulado_3d=feature.acumulado_3d,
                    contexto=contexto,
                    politica=politica,
                )
            )
        anterior = tuple(
            x
            for x in resultados
            if avaliacao.janela_anterior.inicio
            <= x.data
            <= avaliacao.janela_anterior.fim
        )
        atual = tuple(
            x
            for x in resultados
            if avaliacao.janela_atual.inicio <= x.data <= avaliacao.janela_atual.fim
        )

        def janela(itens, periodo, score_v1):
            agregado = agregar_hidrico_v2_experimental(itens, periodo, politica)
            score_base = None
            if (
                score_v1.score is not None
                and agregado.indice_hidrico_v1_90d is not None
                and agregado.indice_hidrico_v2_90d is not None
            ):
                score_base = min(
                    100.0,
                    max(
                        0.0,
                        score_v1.score
                        - 0.4
                        * (
                            agregado.indice_hidrico_v2_90d
                            - agregado.indice_hidrico_v1_90d
                        ),
                    ),
                )
            score = calcular_score_paralelo(
                score_v1=score_base,
                indice_hidrico_v1_90d=agregado.indice_hidrico_v1_90d,
                indice_hidrico_v2_90d=agregado.indice_hidrico_v2_90d,
                politica=politica,
            )
            return JanelaHidricoV2Dto(
                hidrico_v1_90d=agregado.indice_hidrico_v1_90d,
                classificacao_v1=agregado.classificacao_hidrica_v1_90d,
                hidrico_v2_90d=agregado.indice_hidrico_v2_90d,
                classificacao_v2=agregado.classificacao_hidrica_v2_90d,
                delta_hidrico=agregado.delta_hidrico_90d,
                score_v1=score.score_v1,
                score_v2_experimental=score.score_v2_experimental,
                delta_score=score.delta_score,
                classificacao_score_v1=score.classificacao_v1,
                classificacao_score_v2=score.classificacao_v2_experimental,
            )

        relevantes = []
        for nome, itens in (("ANTERIOR", anterior), ("ATUAL", atual)):
            for x in itens:
                if detalhe_completo or (
                    (x.h1_meteorologico is not None and x.h1_meteorologico >= 20)
                    or (x.h2_final is not None and x.h2_final >= 20)
                    or x.classificacao_h1 != x.classificacao_h2
                    or (
                        x.incremento_territorial is not None
                        and x.incremento_territorial >= 5
                    )
                ):
                    relevantes.append(
                        DiaRelevanteHidricoV2Dto(
                            data=x.data,
                            janela=nome,
                            h1=x.h1_meteorologico,
                            g3=x.g3,
                            incremento_territorial=x.incremento_territorial,
                            h2=x.h2_final,
                            classe_h1=x.classificacao_h1,
                            classe_h2=x.classificacao_h2,
                        )
                    )
        return ResultadoInterfaceHidricoV2Dto(
            id_fazenda=str(id_fazenda),
            nome_fazenda=str(
                insumos.fazenda.get("nome_fazenda")
                or insumos.fazenda.get("nome")
                or id_fazenda
            ),
            data_referencia=data_referencia,
            fonte_meteorologica=fonte,
            territorio=TerritorioHidricoV2Dto(
                distancia_drenagem_m=contexto.distancia_drenagem_m,
                area_drenagem_montante_km2=contexto.area_drenagem_montante_km2,
                posicao_topografica_relativa_m=contexto.posicao_topografica_relativa_m,
                d2=susc.d2,
                a2=susc.a2,
                p2=susc.p2,
                t3=susc.t3,
            ),
            janela_anterior=janela(
                anterior, avaliacao.janela_anterior, avaliacao.score_anterior
            ),
            janela_atual=janela(atual, avaliacao.janela_atual, avaliacao.score_atual),
            dias_relevantes=tuple(relevantes),
            proveniencia=(
                ItemProvenienciaHidricoV2Dto(
                    fonte=fonte.value, papel=("METEOROLOGIA",), utilizada=True
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="MERIT_HYDRO",
                    papel=("DISTANCIA_DRENAGEM", "AREA_MONTANTE"),
                    utilizada=True,
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="SRTM",
                    papel=("POSICAO_TOPOGRAFICA_RELATIVA",),
                    utilizada=True,
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="DECLIVIDADE",
                    papel=("NAO_UTILIZADA_NO_HIDRICO_V2",),
                    utilizada=False,
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="MAPBIOMAS", papel=("NAO_UTILIZADO",), utilizada=False
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="INMET", papel=("NAO_UTILIZADO",), utilizada=False
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="TRAFEGABILIDADE", papel=("NAO_ALTERADA",), utilizada=False
                ),
                ItemProvenienciaHidricoV2Dto(
                    fonte="INSTABILIDADE",
                    papel=("CONTINUA_BASEADA_NO_HIDRICO_V1",),
                    utilizada=False,
                ),
            ),
        )


__all__ = ["ResultadoInterfaceHidricoV2Dto", "ServicoHidricoV2Experimental"]
