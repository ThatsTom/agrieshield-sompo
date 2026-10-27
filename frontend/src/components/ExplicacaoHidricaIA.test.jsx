import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplicacaoHidricaIA } from "./ExplicacaoHidricaIA";

const { fetchJSON } = vi.hoisted(() => ({ fetchJSON: vi.fn() }));
vi.mock("../api/core", () => ({ fetchJSON }));

const avaliacao = {
  data_referencia: "2026-08-30",
  fonte_meteorologica: "NASA_POWER",
};

afterEach(() => {
  cleanup();
  fetchJSON.mockReset();
});

describe("explicação hídrica com IA", () => {
  it("faz a consulta só após o clique e mostra as contas fornecidas pelo motor", async () => {
    fetchJSON.mockResolvedValue({
      modelo: "gpt-4o-mini",
      calculo: {
        fazenda: "Fazenda Pampa Sul",
        data_referencia: "2026-08-30",
        fonte_meteorologica: "NASA_POWER",
        medidas_territorio: { distancia_drenagem_m: 1903.62, area_influencia_drenagem_km2: 10.88, posicao_topografica_relativa_m: -5.7 },
        territorio: {
          proximidade_drenagem: 49.53, relevancia_area_influencia: 0,
          posicao_topografica: 72.36, indice: 37.9,
          pesos: { proximidade: .4, area: .35, posicao: .25 },
          parametros_normalizacao: { mediana_distancia_m: 1868.12, area_log_min: 2.53, area_log_max: 10.06, mediana_posicao_m: 7.65, iqr_posicao_m: 13.87 },
        },
        meteorologia_dia: {
          data: "2026-08-30", chuva_hoje_mm: .4, chuva_d1_d3_mm: 13.75,
          chuva_d4_d7_mm: .59, chuva_3d_mm: 10.68, curva_chuva: [{ mm: 0, indice: 0 }, { mm: 20, indice: 25 }],
          chuva_hoje_normalizada: .5, chuva_d1_d3_normalizada: 17.19,
          chuva_d4_d7_normalizada: .74, pesos_antecedente: { d1_d3: .7, d4_d7: .3 },
          multiplicador_persistencia: 1.2, antecedente_normalizado: 14.7,
          pesos_base: { hoje: .7, antecedente: .3 }, base: 4.76,
          ativacao_chuva_3d: .1335, fator_incremento: .3,
          incremento_territorial: 1.52, indice_diario: 6.28,
        },
        janela_90d: {
          inicio: "2026-06-02", fim: "2026-08-30", dias_disponiveis: 90,
          dias_esperados: 90, dias_relevantes: 2, eventos: 1,
          componentes: { severidade: 10, frequencia: 13, duracao: 14, recorrencia: 20 },
          pesos: { severidade: .4, frequencia: .3, duracao: .2, recorrencia: .1 },
          indice: 12.7,
        },
        limitacao_geografica: "O cálculo usa o ponto cadastrado, não o polígono da fazenda.",
      },
      explicacao: {
        resumo: "Resumo da fazenda.", leitura_territorial: "Leitura territorial.",
        leitura_meteorologica: "Leitura meteorológica.", leitura_janela: "Leitura da janela.",
        limitacoes: "Conferir o cadastro.",
      },
    });
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    expect(fetchJSON).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Explicar este cálculo com IA" }));

    expect(await screen.findByText("Resumo da fazenda.")).toBeInTheDocument();
    expect(fetchJSON.mock.calls[0][0]).toContain("/api/v1/exposicao/8/explicacao-hidrica-ia?data_referencia=2026-08-30&fonte=NASA_POWER");
    expect(document.body.textContent).toContain("37,90");
    expect(document.body.textContent).toContain("6,28");
    expect(document.body.textContent).toContain("12,70");
  });

  it("mostra a falha da IA sem fabricar uma conta", async () => {
    fetchJSON.mockRejectedValue(new Error("Serviço temporariamente indisponível."));
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Explicar este cálculo com IA" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Serviço temporariamente indisponível.");
    expect(screen.queryByText("Como chegamos ao valor")).not.toBeInTheDocument();
  });
});
