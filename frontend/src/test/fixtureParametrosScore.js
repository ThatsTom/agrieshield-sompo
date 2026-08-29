const ATUALIZADO_EM = "2026-08-16T12:00:00+00:00";

const item = (grupo, indicador, parametro, valor, tipo) => ({
  grupo,
  indicador,
  parametro,
  valor_atual: valor,
  valor_padrao: valor,
  tipo,
  atualizado_em: ATUALIZADO_EM,
});

export const PARAMETROS_MODELO_PADRAO = [
  ["SCORE", "EXPOSICAO_HIDRICA", "peso", 0.3, "percentual"],
  ["SCORE", "TRAFEGABILIDADE", "peso", 0.25, "percentual"],
  ["SCORE", "INSTABILIDADE", "peso", 0.2, "percentual"],
  ["SCORE", "INCENDIO", "peso", 0.15, "percentual"],
  ["SCORE", "TEMPESTADES", "peso", 0.1, "percentual"],
  ["EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem", 0.4, "percentual"],
  ["EXPOSICAO_HIDRICA", "T3", "relevancia_area_montante", 0.35, "percentual"],
  ["EXPOSICAO_HIDRICA", "T3", "posicao_topografica", 0.25, "percentual"],
  ["INSTABILIDADE", "ATIVACAO", "normal", 0.0, "fator"],
  ["INSTABILIDADE", "ATIVACAO", "atencao", 0.35, "fator"],
  ["INSTABILIDADE", "ATIVACAO", "alerta", 0.65, "fator"],
  ["INSTABILIDADE", "ATIVACAO", "critico", 1.0, "fator"],
  ["INCENDIO", "SECURA", "0_1_dia", 0.9, "fator"],
  ["INCENDIO", "SECURA", "2_3_dias", 1.0, "fator"],
  ["INCENDIO", "SECURA", "4_6_dias", 1.05, "fator"],
  ["INCENDIO", "SECURA", "7_mais_dias", 1.1, "fator"],
  ["TEMPESTADES", "VENTO_CHUVA", "base", 0.75, "fator"],
  ["TEMPESTADES", "VENTO_CHUVA", "influencia_chuva", 0.25, "fator"],
  ["TRAFEGABILIDADE", "COMPOSICAO", "peso_dia", 0.35, "percentual"],
  ["TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado", 0.45, "percentual"],
  ["TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao", 0.2, "percentual"],
  ["TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia", 25, "fator"],
];

export const fixtureParametrosScore = {
  parametros: PARAMETROS_MODELO_PADRAO.map(
    ([grupo, indicador, parametro, valor, tipo]) =>
      item(grupo, indicador, parametro, valor, tipo),
  ),
};
