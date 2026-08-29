export type PerigoExposicao =
  | "EXPOSICAO_HIDRICA"
  | "TRAFEGABILIDADE"
  | "INSTABILIDADE"
  | "INCENDIO"
  | "TEMPESTADES";
export type ClassificacaoIndice = "NORMAL" | "ATENCAO" | "ALERTA" | "CRITICO";
export type DirecaoVariacao = "AUMENTO" | "REDUCAO" | "ESTAVEL";
export type FonteMeteorologica = "NASA_POWER" | "OPEN_METEO";
export type EstadoPerigoApresentacao =
  | "PARTICIPANTE_ELEGIVEL"
  | "INATIVO_NA_CONFIGURACAO"
  | "DADO_INSUFICIENTE";
export interface JanelaHistorica {
  inicio: string;
  fim: string;
  dias_esperados: number;
  finalidade: string;
}
export interface ResumoPerigoApresentacao {
  perigo: PerigoExposicao;
  indice: number | null;
  classificacao: ClassificacaoIndice | null;
  participa_score: boolean;
  elegivel: boolean;
  peso: number;
  contribuicao: number | null;
  cobertura_percentual: number;
  qualidade_suficiente: boolean;
  estado: EstadoPerigoApresentacao;
  motivo_nao_contribuicao: string | null;
  motivos_indisponibilidade: string[];
  metodologia: string;
}
export interface EventoTimelineApresentacao {
  perigo: PerigoExposicao;
  inicio: string;
  fim: string;
  duracao_dias: number;
  severidade: number;
  classificacao_maxima: ClassificacaoIndice;
  indice_maximo: number;
  indice_medio: number;
  metodologia_perigo: string;
}
export interface CoberturaPerigoApresentacao {
  perigo: PerigoExposicao;
  cobertura_percentual: number;
  qualidade_suficiente: boolean;
}
export interface ResumoQualidadeDados {
  conceito: "COBERTURA_E_QUALIDADE_DOS_DADOS";
  coberturas_por_perigo: CoberturaPerigoApresentacao[];
  warmup_completo: boolean;
  dias_contexto_esperados: number;
  dias_contexto_disponiveis: number;
  quantidade_gaps: number;
  dias_com_dados_ausentes: number;
  fonte_meteorologica: FonteMeteorologica;
  periodo_aquisicao: JanelaHistorica;
}
export interface FazendaApresentacao {
  nome: string;
  cidade: string | null;
  uf: string | null;
  area_ha: number | null;
  latitude: number | null;
  longitude: number | null;
}
export interface ContextoTerritorialApresentacao {
  declividade_media_graus: number | null;
  posicao_topografica_relativa_m: number | null;
  distancia_drenagem_m: number | null;
  area_montante_km2: number | null;
}
export interface ResumoJanelaHidricaApresentacao {
  inicio: string;
  fim: string;
  indice: number | null;
  classificacao: ClassificacaoIndice | null;
  quantidade_dias_relevantes: number;
  quantidade_eventos: number;
  cobertura_percentual: number;
}
export interface DetalheExposicaoHidricaApresentacao {
  proximidade_drenagem: number | null;
  relevancia_area_montante: number | null;
  posicao_topografica: number | null;
  suscetibilidade_territorial: number | null;
  janela_anterior: ResumoJanelaHidricaApresentacao;
  janela_atual: ResumoJanelaHidricaApresentacao;
  metodologia: string;
  calibrado_contra_sinistros: false;
}
export interface ComponentesAgregacao90dApresentacao {
  inicio: string;
  fim: string;
  severidade: number;
  frequencia: number;
  duracao: number;
  recorrencia: number;
  indice_agregado: number | null;
  classificacao: ClassificacaoIndice | null;
  quantidade_dias_relevantes: number;
  quantidade_eventos: number;
  maior_duracao_evento: number;
  cobertura_percentual: number;
}
export interface ProvenienciaCalculoApresentacao {
  fonte_meteorologica: FonteMeteorologica;
  dataset_meteorologico: string;
  parametro_vento: string | null;
  altura_vento_m: number | null;
  unidade_vento: string | null;
  agregacao_temporal_vento: string | null;
}
export interface DiaDestaqueIncendioApresentacao {
  data: string;
  temperatura_maxima_c: number | null;
  umidade_relativa_media_pct: number | null;
  velocidade_vento_media_m_s: number | null;
  dias_desde_ultima_chuva: number | null;
  componente_temperatura: number | null;
  componente_baixa_umidade: number | null;
  componente_vento: number | null;
  indice_base: number | null;
  multiplicador_secura: number | null;
  indice_diario: number;
  motivo: string;
}
export interface DiaDestaqueInstabilidadeApresentacao {
  data: string;
  declividade_media_graus: number | null;
  suscetibilidade_topografica: number | null;
  condicao_hidrica_meteorologica: number | null;
  fator_ativacao: number | null;
  indice_diario: number;
  motivo: string;
}
export interface DiaDestaqueTempestadesApresentacao {
  data: string;
  velocidade_vento_media_m_s: number | null;
  precipitacao_diaria_mm: number | null;
  componente_vento: number | null;
  componente_chuva: number | null;
  indice_vento: number | null;
  fator_combinado_vento_chuva: number | null;
  indice_diario: number;
  motivo: string;
}
export interface DetalheIncendioApresentacao {
  perigo: "INCENDIO";
  dia_maior_indice: DiaDestaqueIncendioApresentacao | null;
  agregacao_90d: ComponentesAgregacao90dApresentacao;
  proveniencia: ProvenienciaCalculoApresentacao;
  metodologia: string;
}
export interface DetalheInstabilidadeApresentacao {
  perigo: "INSTABILIDADE";
  dia_maior_indice: DiaDestaqueInstabilidadeApresentacao | null;
  agregacao_90d: ComponentesAgregacao90dApresentacao;
  proveniencia: ProvenienciaCalculoApresentacao;
  fonte_declividade: string;
  dataset_declividade: string;
  posicao_topografica_relativa_m: number | null;
  posicao_topografica_participa_formula: false;
  metodologia: string;
}
export interface DetalheTempestadesApresentacao {
  perigo: "TEMPESTADES";
  dia_maior_indice: DiaDestaqueTempestadesApresentacao | null;
  agregacao_90d: ComponentesAgregacao90dApresentacao;
  proveniencia: ProvenienciaCalculoApresentacao;
  metodologia: string;
}
export interface DetalhesPerigosApresentacao {
  incendio: DetalheIncendioApresentacao;
  instabilidade: DetalheInstabilidadeApresentacao;
  tempestades: DetalheTempestadesApresentacao;
}
export interface FonteAvaliacao {
  fonte: string;
  nome_exibicao: string;
  status: "USADA" | "CONTEXTO" | "DISPONIVEL";
  categoria: string;
  contribui_score: boolean;
  indicadores: string[];
  descricao: string;
}
export interface IntegracaoDisponivel {
  fonte: string;
  nome_exibicao: string;
  status: "DISPONIVEL" | "NAO_UTILIZADO";
  contribui_score: false;
  descricao: string;
}
export interface ResultadoApresentacaoExposicaoMaquinario {
  id_fazenda: string | null;
  politica_id: string;
  metodologia: string;
  metodologia_score: string;
  metodologia_comparacao: string;
  data_referencia: string;
  fonte_meteorologica: FonteMeteorologica;
  exposicao_hidrica: DetalheExposicaoHidricaApresentacao;
  detalhes_perigos: DetalhesPerigosApresentacao | null;
  score_atual: number | null;
  classificacao_atual: ClassificacaoIndice | null;
  score_anterior: number | null;
  classificacao_anterior: ClassificacaoIndice | null;
  variacao_pontos: number | null;
  variacao_percentual: number | null;
  direcao_variacao: DirecaoVariacao | null;
  perigo_dominante: PerigoExposicao | null;
  perigos_dominantes: PerigoExposicao[];
  perigos: ResumoPerigoApresentacao[];
  timeline_eventos: EventoTimelineApresentacao[];
  qualidade_dados: ResumoQualidadeDados;
  score_anterior_publicavel: boolean;
  score_publicavel: boolean;
  comparacao_publicavel: boolean;
  avaliacao_publicavel: boolean;
  avisos_metodologicos: string[];
  disclaimer: string;
  disclaimer_comparacao: string;
  versao: string;
}
export interface ResultadoApresentacaoExposicaoMaquinario {
  fazenda: FazendaApresentacao | null;
  contexto_territorial: ContextoTerritorialApresentacao | null;
  fontes_avaliacao: FonteAvaliacao[];
  integracoes: IntegracaoDisponivel[];
}
