"""DTO neutro de apresentacao da avaliacao AGRISHIELD-EQUIP para o MVP."""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import Field, model_validator

from backend.exposicao.avaliacao_exposicao import (
    ResultadoAvaliacaoExposicaoMaquinario,
)
from backend.exposicao.comparacao_score import DirecaoVariacaoScore
from backend.exposicao.modelos import JanelaHistorica
from backend.exposicao.politica import ClassificacaoIndice, PerigoExposicao
from backend.exposicao.score_exposicao import (
    MotivoIndisponibilidadeScore,
    TipoNaoContribuicaoScore,
)
from backend.risco.modelos import FonteDado, ModeloDominio


APRESENTACAO_EXPOSICAO_VERSION = "exposicao-apresentacao-mvp-v1"
METODOLOGIA_APRESENTACAO_EXPOSICAO = "APRESENTACAO_EXPOSICAO_MAQUINARIO_MVP_V1"


class EstadoPerigoApresentacao(str, Enum):
    PARTICIPANTE_ELEGIVEL = "PARTICIPANTE_ELEGIVEL"
    INATIVO_NA_CONFIGURACAO = "INATIVO_NA_CONFIGURACAO"
    DADO_INSUFICIENTE = "DADO_INSUFICIENTE"


class ResumoPerigoApresentacao(ModeloDominio):
    perigo: PerigoExposicao
    indice: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None
    participa_score: bool
    elegivel: bool
    peso: float = Field(ge=0, le=1)
    contribuicao: float | None = Field(default=None, ge=0, le=100)
    cobertura_percentual: float = Field(ge=0, le=100)
    qualidade_suficiente: bool
    estado: EstadoPerigoApresentacao
    motivo_nao_contribuicao: TipoNaoContribuicaoScore | None = None
    motivos_indisponibilidade: tuple[MotivoIndisponibilidadeScore, ...] = ()
    metodologia: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_estado(self) -> "ResumoPerigoApresentacao":
        if self.participa_score and self.elegivel:
            esperado = EstadoPerigoApresentacao.PARTICIPANTE_ELEGIVEL
        elif self.participa_score:
            esperado = EstadoPerigoApresentacao.DADO_INSUFICIENTE
        else:
            esperado = EstadoPerigoApresentacao.INATIVO_NA_CONFIGURACAO
        if self.estado != esperado:
            raise ValueError("estado do perigo incoerente")
        if not self.participa_score:
            if self.peso != 0 or self.contribuicao != 0:
                raise ValueError("perigo excluido exige peso e contribuicao zero")
        elif self.elegivel:
            if (
                self.indice is None
                or self.classificacao is None
                or self.contribuicao is None
            ):
                raise ValueError("perigo elegivel exige resultado completo")
            if not self.qualidade_suficiente:
                raise ValueError("perigo elegivel exige qualidade suficiente")
        else:
            if self.contribuicao is not None or not self.motivos_indisponibilidade:
                raise ValueError(
                    "perigo indisponivel exige diagnostico sem contribuicao"
                )
        return self


class EventoTimelineApresentacao(ModeloDominio):
    perigo: PerigoExposicao
    inicio: date
    fim: date
    duracao_dias: int = Field(gt=0)
    severidade: float = Field(ge=0, le=100)
    classificacao_maxima: ClassificacaoIndice
    indice_maximo: float = Field(ge=0, le=100)
    indice_medio: float = Field(ge=0, le=100)
    metodologia_perigo: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_periodo(self) -> "EventoTimelineApresentacao":
        if self.duracao_dias != (self.fim - self.inicio).days + 1:
            raise ValueError("duracao do evento incoerente")
        return self


class CoberturaPerigoApresentacao(ModeloDominio):
    perigo: PerigoExposicao
    cobertura_percentual: float = Field(ge=0, le=100)
    qualidade_suficiente: bool


class ResumoQualidadeDados(ModeloDominio):
    conceito: str = "COBERTURA_E_QUALIDADE_DOS_DADOS"
    coberturas_por_perigo: tuple[CoberturaPerigoApresentacao, ...] = Field(
        min_length=5,
        max_length=5,
    )
    warmup_completo: bool
    dias_contexto_esperados: int = Field(ge=0)
    dias_contexto_disponiveis: int = Field(ge=0)
    quantidade_gaps: int = Field(ge=0)
    dias_com_dados_ausentes: int = Field(ge=0)
    fonte_meteorologica: FonteDado
    periodo_aquisicao: JanelaHistorica

    @model_validator(mode="after")
    def validar_resumo(self) -> "ResumoQualidadeDados":
        if tuple(item.perigo for item in self.coberturas_por_perigo) != tuple(
            PerigoExposicao
        ):
            raise ValueError("qualidade deve conter os cinco perigos em ordem")
        if self.dias_contexto_disponiveis > self.dias_contexto_esperados:
            raise ValueError("contexto disponivel excede o esperado")
        if self.warmup_completo != (
            self.dias_contexto_disponiveis == self.dias_contexto_esperados
        ):
            raise ValueError("estado do warm-up incoerente")
        if self.dias_com_dados_ausentes > self.periodo_aquisicao.dias_esperados:
            raise ValueError("dias ausentes excedem o periodo")
        return self


class FazendaApresentacao(ModeloDominio):
    nome: str
    cidade: str | None = None
    uf: str | None = None
    area_ha: float | None = Field(default=None, gt=0)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class ContextoTerritorialApresentacao(ModeloDominio):
    declividade_media_graus: float | None = None
    posicao_topografica_relativa_m: float | None = None
    distancia_drenagem_m: float | None = Field(default=None, ge=0)
    area_montante_km2: float | None = Field(default=None, ge=0)


class ResumoJanelaHidricaApresentacao(ModeloDominio):
    inicio: date
    fim: date
    indice: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None
    quantidade_dias_relevantes: int = Field(ge=0)
    quantidade_eventos: int = Field(ge=0)
    cobertura_percentual: float = Field(ge=0, le=100)


class DetalheExposicaoHidricaApresentacao(ModeloDominio):
    proximidade_drenagem: float | None = Field(default=None, ge=0, le=100)
    relevancia_area_montante: float | None = Field(default=None, ge=0, le=100)
    posicao_topografica: float | None = Field(default=None, ge=0, le=100)
    suscetibilidade_territorial: float | None = Field(default=None, ge=0, le=100)
    janela_anterior: ResumoJanelaHidricaApresentacao
    janela_atual: ResumoJanelaHidricaApresentacao
    metodologia: str = Field(min_length=1)
    calibrado_contra_sinistros: bool = False


class ComponentesAgregacao90dApresentacao(ModeloDominio):
    inicio: date
    fim: date
    severidade: float = Field(ge=0, le=100)
    frequencia: float = Field(ge=0, le=100)
    duracao: float = Field(ge=0, le=100)
    recorrencia: float = Field(ge=0, le=100)
    indice_agregado: float | None = Field(default=None, ge=0, le=100)
    classificacao: ClassificacaoIndice | None = None
    quantidade_dias_relevantes: int = Field(ge=0)
    quantidade_eventos: int = Field(ge=0)
    maior_duracao_evento: int = Field(ge=0)
    cobertura_percentual: float = Field(ge=0, le=100)


class ProvenienciaCalculoApresentacao(ModeloDominio):
    fonte_meteorologica: FonteDado
    dataset_meteorologico: str = Field(min_length=1)
    parametro_vento: str | None = None
    altura_vento_m: float | None = Field(default=None, ge=0)
    unidade_vento: str | None = None
    agregacao_temporal_vento: str | None = None


class DiaDestaqueIncendioApresentacao(ModeloDominio):
    data: date
    temperatura_maxima_c: float | None = None
    umidade_relativa_media_pct: float | None = Field(default=None, ge=0, le=100)
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)
    dias_desde_ultima_chuva: int | None = Field(default=None, ge=0)
    componente_temperatura: float | None = Field(default=None, ge=0, le=1)
    componente_baixa_umidade: float | None = Field(default=None, ge=0, le=1)
    componente_vento: float | None = Field(default=None, ge=0, le=1)
    indice_base: float | None = Field(default=None, ge=0, le=100)
    multiplicador_secura: float | None = Field(default=None, gt=0)
    indice_diario: float = Field(ge=0, le=100)
    motivo: str = Field(min_length=1)


class DetalheIncendioApresentacao(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.INCENDIO
    dia_maior_indice: DiaDestaqueIncendioApresentacao | None = None
    agregacao_90d: ComponentesAgregacao90dApresentacao
    proveniencia: ProvenienciaCalculoApresentacao
    metodologia: str = Field(min_length=1)


class DiaDestaqueInstabilidadeApresentacao(ModeloDominio):
    data: date
    declividade_media_graus: float | None = Field(default=None, ge=0)
    suscetibilidade_topografica: float | None = Field(default=None, ge=0, le=100)
    condicao_hidrica_meteorologica: float | None = Field(default=None, ge=0, le=100)
    fator_ativacao: float | None = Field(default=None, ge=0, le=1)
    indice_diario: float = Field(ge=0, le=100)
    motivo: str = Field(min_length=1)


class DetalheInstabilidadeApresentacao(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.INSTABILIDADE
    dia_maior_indice: DiaDestaqueInstabilidadeApresentacao | None = None
    agregacao_90d: ComponentesAgregacao90dApresentacao
    proveniencia: ProvenienciaCalculoApresentacao
    fonte_declividade: FonteDado
    dataset_declividade: str = Field(min_length=1)
    posicao_topografica_relativa_m: float | None = None
    posicao_topografica_participa_formula: bool = False
    metodologia: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_posicao_como_evidencia(self) -> "DetalheInstabilidadeApresentacao":
        if self.posicao_topografica_participa_formula:
            raise ValueError("posicao topografica nao participa da Instabilidade atual")
        return self


class DiaDestaqueTempestadesApresentacao(ModeloDominio):
    data: date
    velocidade_vento_media_m_s: float | None = Field(default=None, ge=0)
    precipitacao_diaria_mm: float | None = Field(default=None, ge=0)
    componente_vento: float | None = Field(default=None, ge=0, le=1)
    componente_chuva: float | None = Field(default=None, ge=0, le=1)
    indice_vento: float | None = Field(default=None, ge=0, le=100)
    fator_combinado_vento_chuva: float | None = Field(default=None, ge=0, le=1)
    indice_diario: float = Field(ge=0, le=100)
    motivo: str = Field(min_length=1)


class DetalheTempestadesApresentacao(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.TEMPESTADES
    dia_maior_indice: DiaDestaqueTempestadesApresentacao | None = None
    agregacao_90d: ComponentesAgregacao90dApresentacao
    proveniencia: ProvenienciaCalculoApresentacao
    metodologia: str = Field(min_length=1)


class DiaDestaqueTrafegabilidadeApresentacao(ModeloDominio):
    data: date
    precipitacao_d0: float | None = Field(default=None, ge=0)
    acumulado_3d: float | None = Field(default=None, ge=0)
    dias_desde_ultima_chuva_relevante: int | None = Field(default=None, ge=0)
    componente_dia: float | None = Field(default=None, ge=0, le=100)
    componente_acumulado: float | None = Field(default=None, ge=0, le=100)
    componente_recuperacao: float | None = Field(default=None, ge=0, le=100)
    indice_diario: float = Field(ge=0, le=100)


class DetalheTrafegabilidadeApresentacao(ModeloDominio):
    perigo: PerigoExposicao = PerigoExposicao.TRAFEGABILIDADE
    dia_maior_indice: DiaDestaqueTrafegabilidadeApresentacao | None = None
    agregacao_90d: ComponentesAgregacao90dApresentacao
    proveniencia: ProvenienciaCalculoApresentacao
    peso_dia: float = Field(ge=0, le=1)
    peso_acumulado: float = Field(ge=0, le=1)
    peso_recuperacao: float = Field(ge=0, le=1)
    limiar_relevancia: float = Field(ge=0, le=100)
    metodologia: str = Field(min_length=1)
    aviso_metodologia: str = Field(min_length=1)


class DetalhesPerigosApresentacao(ModeloDominio):
    trafegabilidade: DetalheTrafegabilidadeApresentacao
    incendio: DetalheIncendioApresentacao
    instabilidade: DetalheInstabilidadeApresentacao
    tempestades: DetalheTempestadesApresentacao

    @model_validator(mode="after")
    def validar_perigos(self) -> "DetalhesPerigosApresentacao":
        if (
            self.trafegabilidade.perigo != PerigoExposicao.TRAFEGABILIDADE
            or self.incendio.perigo != PerigoExposicao.INCENDIO
            or self.instabilidade.perigo != PerigoExposicao.INSTABILIDADE
            or self.tempestades.perigo != PerigoExposicao.TEMPESTADES
        ):
            raise ValueError("detalhes devem preservar a identidade dos perigos")
        return self


class FonteAvaliacaoApresentacao(ModeloDominio):
    fonte: str
    nome_exibicao: str
    status: str
    categoria: str
    contribui_score: bool
    indicadores: tuple[str, ...]
    descricao: str


class IntegracaoApresentacao(ModeloDominio):
    fonte: str
    nome_exibicao: str
    status: str
    contribui_score: bool = False
    descricao: str


class ResultadoApresentacaoExposicaoMaquinario(ModeloDominio):
    id_fazenda: str | None = None
    politica_id: str = Field(min_length=1)
    metodologia: str = Field(default=METODOLOGIA_APRESENTACAO_EXPOSICAO, min_length=1)
    metodologia_score: str = Field(min_length=1)
    metodologia_comparacao: str = Field(min_length=1)
    data_referencia: date
    fonte_meteorologica: FonteDado
    fazenda: FazendaApresentacao | None = None
    contexto_territorial: ContextoTerritorialApresentacao | None = None
    exposicao_hidrica: DetalheExposicaoHidricaApresentacao
    detalhes_perigos: DetalhesPerigosApresentacao | None = None
    fontes_avaliacao: tuple[FonteAvaliacaoApresentacao, ...] = ()
    integracoes: tuple[IntegracaoApresentacao, ...] = ()
    score_atual: float | None = Field(default=None, ge=0, le=100)
    classificacao_atual: ClassificacaoIndice | None = None
    score_anterior: float | None = Field(default=None, ge=0, le=100)
    classificacao_anterior: ClassificacaoIndice | None = None
    variacao_pontos: float | None = Field(default=None, ge=-100, le=100)
    variacao_percentual: float | None = None
    direcao_variacao: DirecaoVariacaoScore | None = None
    perigo_dominante: PerigoExposicao | None = None
    perigos_dominantes: tuple[PerigoExposicao, ...] = ()
    perigos: tuple[ResumoPerigoApresentacao, ...] = Field(min_length=5, max_length=5)
    timeline_eventos: tuple[EventoTimelineApresentacao, ...]
    qualidade_dados: ResumoQualidadeDados
    score_anterior_publicavel: bool
    score_publicavel: bool
    comparacao_publicavel: bool
    avaliacao_publicavel: bool
    avisos_metodologicos: tuple[str, ...]
    disclaimer: str = Field(min_length=1)
    disclaimer_comparacao: str = Field(min_length=1)
    versao: str = Field(default=APRESENTACAO_EXPOSICAO_VERSION, min_length=1)

    @model_validator(mode="after")
    def validar_apresentacao(self) -> "ResultadoApresentacaoExposicaoMaquinario":
        if tuple(item.perigo for item in self.perigos) != tuple(PerigoExposicao):
            raise ValueError("apresentacao deve conter os cinco perigos em ordem")
        resumo_hidrico = self.perigos[0]
        if resumo_hidrico.perigo != PerigoExposicao.EXPOSICAO_HIDRICA:
            raise ValueError("primeiro perigo deve ser Exposição Hídrica")
        if (
            self.exposicao_hidrica.janela_atual.indice != resumo_hidrico.indice
            or self.exposicao_hidrica.janela_atual.classificacao
            != resumo_hidrico.classificacao
        ):
            raise ValueError("card hídrico deve usar a agregação oficial atual")
        eventos_hidricos = tuple(
            item
            for item in self.timeline_eventos
            if item.perigo == PerigoExposicao.EXPOSICAO_HIDRICA
        )
        if (
            len(eventos_hidricos)
            != self.exposicao_hidrica.janela_atual.quantidade_eventos
        ):
            raise ValueError(
                "timeline hídrica deve usar os eventos da agregação oficial"
            )
        if self.detalhes_perigos is not None:
            resumos = {item.perigo: item for item in self.perigos}
            detalhes = (
                self.detalhes_perigos.trafegabilidade,
                self.detalhes_perigos.instabilidade,
                self.detalhes_perigos.incendio,
                self.detalhes_perigos.tempestades,
            )
            for detalhe in detalhes:
                resumo = resumos[detalhe.perigo]
                if (
                    detalhe.agregacao_90d.indice_agregado != resumo.indice
                    or detalhe.agregacao_90d.classificacao != resumo.classificacao
                ):
                    raise ValueError(
                        "detalhamento deve preservar o agregado oficial do perigo"
                    )
        if tuple(sorted(set(self.avisos_metodologicos))) != self.avisos_metodologicos:
            raise ValueError("avisos devem estar deduplicados e ordenados")
        ordem = {perigo: indice for indice, perigo in enumerate(PerigoExposicao)}
        if (
            tuple(
                sorted(
                    self.timeline_eventos,
                    key=lambda item: (item.inicio, ordem[item.perigo], item.fim),
                )
            )
            != self.timeline_eventos
        ):
            raise ValueError("timeline deve possuir ordem deterministica")

        dominantes = _selecionar_dominantes(self.perigos, self.score_publicavel)
        if self.perigos_dominantes != dominantes:
            raise ValueError("perigos dominantes incoerentes")
        dominante_unico = dominantes[0] if len(dominantes) == 1 else None
        if self.perigo_dominante != dominante_unico:
            raise ValueError("perigo dominante unico incoerente")
        if self.score_publicavel:
            if self.score_atual is None or self.classificacao_atual is None:
                raise ValueError("score atual publicavel exige valor e classificacao")
        elif self.score_atual is not None or self.classificacao_atual is not None:
            raise ValueError("score atual indisponivel nao pode ser apresentado")
        if self.score_anterior_publicavel:
            if self.score_anterior is None or self.classificacao_anterior is None:
                raise ValueError("score anterior publicavel exige resultado")
        elif self.score_anterior is not None or self.classificacao_anterior is not None:
            raise ValueError("score anterior indisponivel nao pode ser apresentado")
        if not self.comparacao_publicavel and any(
            item is not None
            for item in (
                self.variacao_pontos,
                self.variacao_percentual,
                self.direcao_variacao,
            )
        ):
            raise ValueError("comparacao indisponivel nao publica variacao")
        return self


def _resultados_atuais(avaliacao: ResultadoAvaliacaoExposicaoMaquinario):
    validacao = avaliacao.validacao_atual
    return (
        validacao.exposicao_hidrica,
        validacao.trafegabilidade,
        validacao.instabilidade,
        validacao.propagacao_fogo,
        validacao.tempestade,
    )


def _estado_perigo(participa: bool, elegivel: bool) -> EstadoPerigoApresentacao:
    if participa and elegivel:
        return EstadoPerigoApresentacao.PARTICIPANTE_ELEGIVEL
    if participa:
        return EstadoPerigoApresentacao.DADO_INSUFICIENTE
    return EstadoPerigoApresentacao.INATIVO_NA_CONFIGURACAO


def _selecionar_dominantes(
    perigos: tuple[ResumoPerigoApresentacao, ...],
    score_publicavel: bool,
) -> tuple[PerigoExposicao, ...]:
    if not score_publicavel:
        return ()
    candidatos = tuple(
        item
        for item in perigos
        if item.participa_score and item.elegivel and item.contribuicao is not None
    )
    if not candidatos:
        return ()
    maior = max(
        item.contribuicao for item in candidatos if item.contribuicao is not None
    )
    return tuple(item.perigo for item in candidatos if item.contribuicao == maior)


def _dias_com_gaps(avaliacao: ResultadoAvaliacaoExposicaoMaquinario) -> int:
    datas: set[date] = set()
    for gap in avaliacao.qualidade_aquisicao.gaps:
        for deslocamento in range(gap.duracao_dias):
            datas.add(gap.inicio + timedelta(days=deslocamento))
    return len(datas)


def _resumo_janela_hidrica(resultado) -> ResumoJanelaHidricaApresentacao:
    agregado = resultado.agregacao_90d
    return ResumoJanelaHidricaApresentacao(
        inicio=agregado.inicio,
        fim=agregado.fim,
        indice=agregado.indice_agregado,
        classificacao=agregado.classificacao_agregada,
        quantidade_dias_relevantes=agregado.quantidade_dias_relevantes,
        quantidade_eventos=agregado.quantidade_eventos,
        cobertura_percentual=agregado.cobertura_percentual,
    )


def _componentes_agregacao(resultado) -> ComponentesAgregacao90dApresentacao:
    agregado = resultado.agregacao_90d
    return ComponentesAgregacao90dApresentacao(
        inicio=agregado.inicio,
        fim=agregado.fim,
        severidade=agregado.severidade_score,
        frequencia=agregado.frequencia_score,
        duracao=agregado.duracao_score,
        recorrencia=agregado.recorrencia_score,
        indice_agregado=agregado.indice_agregado,
        classificacao=agregado.classificacao_agregada,
        quantidade_dias_relevantes=agregado.quantidade_dias_relevantes,
        quantidade_eventos=agregado.quantidade_eventos,
        maior_duracao_evento=agregado.maior_duracao_evento,
        cobertura_percentual=agregado.cobertura_percentual,
    )


def _maior_dia_disponivel(itens, campo_indice: str):
    disponiveis = tuple(
        item for item in itens if getattr(item, campo_indice) is not None
    )
    if not disponiveis:
        return None
    return max(
        disponiveis,
        key=lambda item: (getattr(item, campo_indice), item.data),
    )


def _proveniencia_calculo(resultado) -> ProvenienciaCalculoApresentacao:
    vento = resultado.proveniencia_vento
    return ProvenienciaCalculoApresentacao(
        fonte_meteorologica=resultado.fonte,
        dataset_meteorologico=resultado.dataset,
        parametro_vento=vento.get("parametro_fonte"),
        altura_vento_m=vento.get("altura_m"),
        unidade_vento=vento.get("unidade"),
        agregacao_temporal_vento=vento.get("agregacao_temporal"),
    )


def _detalhes_perigos(
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario,
) -> DetalhesPerigosApresentacao:
    validacao = avaliacao.validacao_atual

    trafegabilidade = validacao.trafegabilidade
    trafegabilidade_dia = _maior_dia_disponivel(
        trafegabilidade.trafegabilidade_diaria,
        "indice_trafegabilidade",
    )
    detalhe_trafegabilidade_dia = None
    if trafegabilidade_dia is not None:
        detalhe_trafegabilidade_dia = DiaDestaqueTrafegabilidadeApresentacao(
            data=trafegabilidade_dia.data,
            precipitacao_d0=trafegabilidade_dia.precipitacao_d0,
            acumulado_3d=trafegabilidade_dia.acumulado_3d,
            dias_desde_ultima_chuva_relevante=(
                trafegabilidade_dia.dias_desde_ultima_chuva_relevante
            ),
            componente_dia=trafegabilidade_dia.componente_dia,
            componente_acumulado=trafegabilidade_dia.componente_acumulado,
            componente_recuperacao=trafegabilidade_dia.componente_recuperacao,
            indice_diario=trafegabilidade_dia.indice_trafegabilidade,
        )
    proveniencia_trafegabilidade = ProvenienciaCalculoApresentacao(
        fonte_meteorologica=validacao.fonte_meteorologica,
        dataset_meteorologico=validacao.dataset,
    )

    fogo = validacao.propagacao_fogo
    fogo_dia = _maior_dia_disponivel(
        fogo.propagacao_fogo_diaria,
        "indice_exposicao_propagacao_fogo",
    )
    detalhe_fogo_dia = None
    if fogo_dia is not None:
        detalhe_fogo_dia = DiaDestaqueIncendioApresentacao(
            data=fogo_dia.data,
            temperatura_maxima_c=fogo_dia.temperatura_maxima_c,
            umidade_relativa_media_pct=fogo_dia.umidade_relativa_media_pct,
            velocidade_vento_media_m_s=fogo_dia.velocidade_vento_media_m_s,
            dias_desde_ultima_chuva=fogo_dia.dias_desde_ultima_chuva_relevante,
            componente_temperatura=fogo_dia.componente_temperatura,
            componente_baixa_umidade=fogo_dia.componente_baixa_umidade,
            componente_vento=fogo_dia.componente_vento,
            indice_base=fogo_dia.indice_fogo_base,
            multiplicador_secura=fogo_dia.multiplicador_secura,
            indice_diario=fogo_dia.indice_exposicao_propagacao_fogo,
            motivo=fogo_dia.motivo,
        )

    instabilidade = validacao.instabilidade
    instabilidade_dia = _maior_dia_disponivel(
        instabilidade.instabilidades_diarias,
        "indice_exposicao_instabilidade",
    )
    detalhe_instabilidade_dia = None
    if instabilidade_dia is not None:
        detalhe_instabilidade_dia = DiaDestaqueInstabilidadeApresentacao(
            data=instabilidade_dia.data,
            declividade_media_graus=instabilidade_dia.declividade_media_graus,
            suscetibilidade_topografica=(
                instabilidade_dia.indice_suscetibilidade_topografica
            ),
            condicao_hidrica_meteorologica=(instabilidade_dia.indice_condicao_hidrica),
            fator_ativacao=instabilidade_dia.fator_ativacao_hidrica,
            indice_diario=instabilidade_dia.indice_exposicao_instabilidade,
            motivo=instabilidade_dia.motivo,
        )

    tempestades = validacao.tempestade
    tempestades_dia = _maior_dia_disponivel(
        tempestades.tempestades_diarias,
        "indice_exposicao_tempestade",
    )
    detalhe_tempestades_dia = None
    if tempestades_dia is not None:
        detalhe_tempestades_dia = DiaDestaqueTempestadesApresentacao(
            data=tempestades_dia.data,
            velocidade_vento_media_m_s=(tempestades_dia.velocidade_vento_media_m_s),
            precipitacao_diaria_mm=tempestades_dia.precipitacao_d0,
            componente_vento=tempestades_dia.componente_vento,
            componente_chuva=tempestades_dia.componente_chuva,
            indice_vento=tempestades_dia.indice_vento,
            fator_combinado_vento_chuva=(tempestades_dia.fator_amplificacao_chuva),
            indice_diario=tempestades_dia.indice_exposicao_tempestade,
            motivo=tempestades_dia.motivo,
        )

    declividade = instabilidade.suscetibilidade_topografica.declividade_media
    posicao = instabilidade.suscetibilidade_topografica.posicao_topografica_relativa
    proveniencia_instabilidade = ProvenienciaCalculoApresentacao(
        fonte_meteorologica=validacao.fonte_meteorologica,
        dataset_meteorologico=validacao.dataset,
    )
    return DetalhesPerigosApresentacao(
        trafegabilidade=DetalheTrafegabilidadeApresentacao(
            dia_maior_indice=detalhe_trafegabilidade_dia,
            agregacao_90d=_componentes_agregacao(trafegabilidade),
            proveniencia=proveniencia_trafegabilidade,
            peso_dia=trafegabilidade.parametros_trafegabilidade.peso_dia,
            peso_acumulado=trafegabilidade.parametros_trafegabilidade.peso_acumulado,
            peso_recuperacao=(
                trafegabilidade.parametros_trafegabilidade.peso_recuperacao
            ),
            limiar_relevancia=(
                trafegabilidade.parametros_trafegabilidade.limiar_relevancia
            ),
            metodologia=trafegabilidade.metodologia,
            aviso_metodologia=trafegabilidade.aviso_metodologia,
        ),
        incendio=DetalheIncendioApresentacao(
            dia_maior_indice=detalhe_fogo_dia,
            agregacao_90d=_componentes_agregacao(fogo),
            proveniencia=_proveniencia_calculo(fogo),
            metodologia=fogo.metodologia,
        ),
        instabilidade=DetalheInstabilidadeApresentacao(
            dia_maior_indice=detalhe_instabilidade_dia,
            agregacao_90d=_componentes_agregacao(instabilidade),
            proveniencia=proveniencia_instabilidade,
            fonte_declividade=declividade.fonte,
            dataset_declividade=declividade.dataset,
            posicao_topografica_relativa_m=posicao.valor,
            metodologia=instabilidade.metodologia,
        ),
        tempestades=DetalheTempestadesApresentacao(
            dia_maior_indice=detalhe_tempestades_dia,
            agregacao_90d=_componentes_agregacao(tempestades),
            proveniencia=_proveniencia_calculo(tempestades),
            metodologia=tempestades.metodologia,
        ),
    )


def criar_apresentacao_exposicao_maquinario(
    avaliacao: ResultadoAvaliacaoExposicaoMaquinario,
) -> ResultadoApresentacaoExposicaoMaquinario:
    """Resume uma avaliacao pronta sem executar qualquer regra de risco."""

    if not isinstance(avaliacao, ResultadoAvaliacaoExposicaoMaquinario):
        raise TypeError("avaliacao deve ser ResultadoAvaliacaoExposicaoMaquinario")
    avaliacao = ResultadoAvaliacaoExposicaoMaquinario.model_validate(
        avaliacao.model_dump()
    )
    resultados = _resultados_atuais(avaliacao)
    contribuicoes = avaliacao.score_atual.contribuicoes
    perigos = tuple(
        ResumoPerigoApresentacao(
            perigo=contribuicao.perigo,
            indice=contribuicao.indice_perigo,
            classificacao=contribuicao.classificacao_perigo,
            participa_score=contribuicao.participa_score,
            elegivel=contribuicao.elegivel,
            peso=contribuicao.peso,
            contribuicao=contribuicao.contribuicao,
            cobertura_percentual=contribuicao.cobertura_percentual,
            qualidade_suficiente=contribuicao.qualidade_suficiente,
            estado=_estado_perigo(
                contribuicao.participa_score,
                contribuicao.elegivel,
            ),
            motivo_nao_contribuicao=contribuicao.tipo_nao_contribuicao,
            motivos_indisponibilidade=contribuicao.motivos_indisponibilidade,
            metodologia=resultado.metodologia,
        )
        for resultado, contribuicao in zip(resultados, contribuicoes)
    )
    ordem = {perigo: indice for indice, perigo in enumerate(PerigoExposicao)}
    timeline = tuple(
        sorted(
            (
                EventoTimelineApresentacao(
                    perigo=resultado.perigo,
                    inicio=evento.inicio,
                    fim=evento.fim,
                    duracao_dias=evento.duracao_dias,
                    severidade=evento.severidade_evento,
                    classificacao_maxima=evento.classificacao_maxima,
                    indice_maximo=evento.indice_maximo,
                    indice_medio=evento.indice_medio,
                    metodologia_perigo=resultado.metodologia,
                )
                for resultado in resultados
                for evento in resultado.agregacao_90d.eventos
            ),
            key=lambda item: (item.inicio, ordem[item.perigo], item.fim),
        )
    )
    dominantes = _selecionar_dominantes(
        perigos,
        avaliacao.score_atual.score_publicavel,
    )
    qualidade = ResumoQualidadeDados(
        coberturas_por_perigo=tuple(
            CoberturaPerigoApresentacao(
                perigo=item.perigo,
                cobertura_percentual=item.cobertura_percentual,
                qualidade_suficiente=item.qualidade_suficiente,
            )
            for item in perigos
        ),
        warmup_completo=avaliacao.warmup_completo,
        dias_contexto_esperados=avaliacao.dias_contexto_esperados,
        dias_contexto_disponiveis=avaliacao.dias_contexto_disponiveis,
        quantidade_gaps=len(avaliacao.qualidade_aquisicao.gaps),
        dias_com_dados_ausentes=_dias_com_gaps(avaliacao),
        fonte_meteorologica=avaliacao.fonte_meteorologica,
        periodo_aquisicao=avaliacao.periodo_aquisicao,
    )
    score_atual_publicavel = avaliacao.score_atual.score_publicavel
    score_anterior_publicavel = avaliacao.score_anterior.score_publicavel
    comparacao_publicavel = avaliacao.comparacao.comparacao_publicavel
    hidrico_atual = avaliacao.validacao_atual.exposicao_hidrica
    hidrico_anterior = avaliacao.validacao_anterior.exposicao_hidrica
    suscetibilidade = hidrico_atual.suscetibilidade_territorial
    return ResultadoApresentacaoExposicaoMaquinario(
        id_fazenda=avaliacao.id_fazenda,
        politica_id=avaliacao.politica_id,
        metodologia_score=avaliacao.score_atual.metodologia,
        metodologia_comparacao=avaliacao.comparacao.metodologia,
        data_referencia=avaliacao.data_referencia,
        fonte_meteorologica=avaliacao.fonte_meteorologica,
        exposicao_hidrica=DetalheExposicaoHidricaApresentacao(
            proximidade_drenagem=suscetibilidade.proximidade_drenagem,
            relevancia_area_montante=suscetibilidade.relevancia_area_montante,
            posicao_topografica=suscetibilidade.posicao_topografica,
            suscetibilidade_territorial=suscetibilidade.indice,
            janela_anterior=_resumo_janela_hidrica(hidrico_anterior),
            janela_atual=_resumo_janela_hidrica(hidrico_atual),
            metodologia=hidrico_atual.metodologia,
        ),
        detalhes_perigos=_detalhes_perigos(avaliacao),
        score_atual=(avaliacao.score_atual.score if score_atual_publicavel else None),
        classificacao_atual=(
            avaliacao.score_atual.classificacao if score_atual_publicavel else None
        ),
        score_anterior=(
            avaliacao.score_anterior.score if score_anterior_publicavel else None
        ),
        classificacao_anterior=(
            avaliacao.score_anterior.classificacao
            if score_anterior_publicavel
            else None
        ),
        variacao_pontos=avaliacao.comparacao.variacao_pontos,
        variacao_percentual=avaliacao.comparacao.variacao_percentual,
        direcao_variacao=avaliacao.comparacao.direcao,
        perigo_dominante=(dominantes[0] if len(dominantes) == 1 else None),
        perigos_dominantes=dominantes,
        perigos=perigos,
        timeline_eventos=timeline,
        qualidade_dados=qualidade,
        score_anterior_publicavel=score_anterior_publicavel,
        score_publicavel=score_atual_publicavel,
        comparacao_publicavel=comparacao_publicavel,
        avaliacao_publicavel=avaliacao.avaliacao_publicavel,
        avisos_metodologicos=tuple(sorted(set(avaliacao.avisos_metodologicos))),
        disclaimer=avaliacao.score_atual.disclaimer,
        disclaimer_comparacao=avaliacao.comparacao.disclaimer,
    )


__all__ = [
    "APRESENTACAO_EXPOSICAO_VERSION",
    "METODOLOGIA_APRESENTACAO_EXPOSICAO",
    "CoberturaPerigoApresentacao",
    "EstadoPerigoApresentacao",
    "EventoTimelineApresentacao",
    "FazendaApresentacao",
    "ContextoTerritorialApresentacao",
    "ComponentesAgregacao90dApresentacao",
    "DetalheIncendioApresentacao",
    "DetalheInstabilidadeApresentacao",
    "DetalheTempestadesApresentacao",
    "DetalheTrafegabilidadeApresentacao",
    "DetalhesPerigosApresentacao",
    "DetalheExposicaoHidricaApresentacao",
    "DiaDestaqueIncendioApresentacao",
    "DiaDestaqueInstabilidadeApresentacao",
    "DiaDestaqueTempestadesApresentacao",
    "DiaDestaqueTrafegabilidadeApresentacao",
    "FonteAvaliacaoApresentacao",
    "IntegracaoApresentacao",
    "ProvenienciaCalculoApresentacao",
    "ResultadoApresentacaoExposicaoMaquinario",
    "ResumoJanelaHidricaApresentacao",
    "ResumoPerigoApresentacao",
    "ResumoQualidadeDados",
    "criar_apresentacao_exposicao_maquinario",
]
