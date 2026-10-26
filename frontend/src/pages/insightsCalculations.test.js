import { describe, expect, it } from "vitest";
import {
  avaliarDiaPrevisao,
  calcularComparativoPortfolio,
  calcularQualidadeDados,
  construirRadarOperacional,
  resumirJanelaOperacional,
} from "./insightsCalculations";

describe("cálculos determinísticos dos Insights", () => {
  it("classifica previsão sem chamar a condição de recomendação garantida", () => {
    expect(avaliarDiaPrevisao({ precipitacao_mm: 1, prob_precip_pct: 20, temp_max_c: 30 }).status).toBe("menor_sinal_chuva");
    expect(avaliarDiaPrevisao({ precipitacao_mm: 6, prob_precip_pct: 45, temp_max_c: 31 }).status).toBe("atencao");
    expect(avaliarDiaPrevisao({ precipitacao_mm: 22, prob_precip_pct: 80, temp_max_c: 29 }).status).toBe("restricao");
  });

  it("encontra a maior sequência com menor sinal de chuva", () => {
    const resumo = resumirJanelaOperacional([
      { data: "2026-09-28", precipitacao_mm: 0, prob_precip_pct: 10, temp_max_c: 30 },
      { data: "2026-09-29", precipitacao_mm: 1, prob_precip_pct: 20, temp_max_c: 31 },
      { data: "2026-09-30", precipitacao_mm: 8, prob_precip_pct: 50, temp_max_c: 32 },
    ]);
    expect(resumo.contagem.menor_sinal_chuva).toBe(2);
    expect(resumo.melhor_sequencia).toEqual({
      inicio: "2026-09-28",
      fim: "2026-09-29",
      total_dias: 2,
    });
  });

  it("expõe lacunas de dados sem chamá-las de precisão estatística", () => {
    const qualidade = calcularQualidadeDados({
      fazenda: { nome_fazenda: "Teste", uf: "MT", tipo_operacao: "campo" },
      dashboard: {
        score: { score: 70 },
        origem_previsao: "fallback_simulado",
        previsao_7d: [],
        maquinarios_resumo: { disponivel: true, total: 0 },
      },
    });
    expect(qualidade.percentual).toBeLessThan(60);
    expect(qualidade.itens.find((item) => item.id === "clima").status).toBe("atencao");
  });

  it("prioriza seguro vencido com evidência concreta", () => {
    const qualidade = { percentual: 100, itens: [] };
    const radar = construirRadarOperacional({
      qualidade,
      dashboard: {
        score: { score: 80, condicao_atual: "Ideais", fatores_risco: [] },
        alertas: [],
        previsao_7d: [],
        maquinarios_resumo: {
          disponivel: true,
          total: 2,
          seguros_vencidos: 1,
          sem_seguro: 0,
          vencendo_90_dias: 0,
        },
      },
    });
    expect(radar[0]).toMatchObject({ id: "seguro", prioridade: "imediata" });
    expect(radar[0].evidencia).toContain("1 seguro cadastrado vencido");
  });

  it("compara apenas fazendas da mesma operação e exige coorte mínima", () => {
    const resultado = calcularComparativoPortfolio({
      fazenda: { id: "1", tipo_operacao: "campo", area_ha: 100 },
      totalFrota: 4,
      fazendas: [
        { id: "1", tipo_operacao: "campo", area_ha: 100, total_maquinarios: 4, status_geoespacial: "SUCESSO" },
        { id: "2", tipo_operacao: "campo", area_ha: 200, total_maquinarios: 8, status_geoespacial: "PENDENTE" },
        { id: "3", tipo_operacao: "transporte", area_ha: 900, total_maquinarios: 20, status_geoespacial: "SUCESSO" },
      ],
    });
    expect(resultado).toMatchObject({ suficiente: true, base: 2, area_mediana_ha: 150, frota_mediana: 6 });
  });

  it("exclui contagens de frota indisponíveis da mediana", () => {
    const resultado = calcularComparativoPortfolio({
      fazenda: { id: "1", tipo_operacao: "campo", area_ha: 100 },
      totalFrota: 4,
      fazendas: [
        { id: "1", tipo_operacao: "campo", total_maquinarios: 4 },
        { id: "2", tipo_operacao: "campo", total_maquinarios: 0, total_maquinarios_disponivel: false },
        { id: "3", tipo_operacao: "campo", total_maquinarios: 8, total_maquinarios_disponivel: true },
      ],
    });
    expect(resultado).toMatchObject({ frota_mediana: 6, frota_base: 2 });
  });
});
