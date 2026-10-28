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

function respostaCalculavel() {
  return {
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
          ativacao_chuva_3d: .1335, chuva_3d_normalizada: 13.35, fator_incremento: .3,
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
  };
}

describe("explicação hídrica com IA", () => {
  it("faz a consulta só após o clique e mostra as contas fornecidas pelo motor", async () => {
    fetchJSON.mockResolvedValue(respostaCalculavel());
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    expect(fetchJSON).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByText("Resumo da fazenda.")).toBeInTheDocument();
    expect(fetchJSON.mock.calls[0][0]).toContain("/api/v1/exposicao/8/explicacao-hidrica-ia?data_referencia=2026-08-30&fonte=NASA_POWER");
    expect(document.body.textContent).toContain("37,90");
    expect(document.body.textContent).toContain("6,28");
    expect(document.body.textContent).toContain("12,70");
  });

  it("identifica a data efetiva quando os dias finais ainda não têm cálculo", async () => {
    const resposta = respostaCalculavel();
    resposta.calculo.meteorologia_dia.data = "2026-08-24";
    resposta.calculo.disponibilidade_diaria = {
      disponivel: true,
      data_calculo: "2026-08-24",
      data_referencia: "2026-08-30",
      dias_defasagem: 6,
      entradas_ausentes_referencia: ["chuva do dia", "chuva acumulada em 3 dias"],
      motivo: "A data de referência não tem todos os dados necessários para o cálculo diário. O exemplo usa 24/08/2026, 6 dias antes da referência.",
    };
    fetchJSON.mockResolvedValue(resposta);
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByRole("heading", { name: "3. Resultado em 24/08/2026: 6,28 / 100" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("24/08/2026, 6 dias antes da referência");
    expect(document.body.textContent).toContain("Período: 02/06/2026 a 30/08/2026");
  });

  it("explica a falta de entradas sem montar equações com valores ausentes", async () => {
    const resposta = respostaCalculavel();
    resposta.calculo.meteorologia_dia = { data: "2026-08-30", base: null, indice_diario: null };
    resposta.calculo.disponibilidade_diaria = {
      disponivel: false, data_calculo: null, dias_defasagem: null,
      entradas_ausentes_referencia: ["chuva do dia", "chuva acumulada em 3 dias"],
      motivo: "Nenhum dia da janela reúne as entradas necessárias ao cálculo diário.",
    };
    fetchJSON.mockResolvedValue(resposta);
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByRole("heading", { name: "3. Resultado em 30/08/2026: cálculo indisponível" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Nenhum dia da janela");
    expect(document.body.textContent).toContain("Entradas ausentes na referência: chuva do dia; chuva acumulada em 3 dias.");
    expect(document.body.textContent).not.toContain("H_base ≈");
    expect(document.body.textContent).not.toContain("Incremento ≈");
    expect(document.body.textContent).not.toContain("g3 =");
    expect(document.body.textContent).not.toContain("indisponível / 100");
    expect(document.body.textContent).toContain("37,90");
    expect(document.body.textContent).toContain("12,70");
  });

  it("exibe o cálculo quando o resultado e a chuva são zero", async () => {
    const resposta = respostaCalculavel();
    Object.assign(resposta.calculo.meteorologia_dia, {
      base: 0, indice_diario: 0, chuva_3d_mm: 0, chuva_3d_normalizada: 0,
      ativacao_chuva_3d: 0, incremento_territorial: 0,
    });
    fetchJSON.mockResolvedValue(resposta);
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByRole("heading", { name: "3. Resultado em 30/08/2026: 0,00 / 100" })).toBeInTheDocument();
    expect(document.body.textContent).toContain("g3 = 0,00 ÷ 100 = 0,0000");
    expect(document.body.textContent).toContain("Incremento ≈ 0,30 × 0,0000 × 37,90 = 0,00");
  });

  it("omite também as contas de território e da janela quando não há indicador", async () => {
    const resposta = respostaCalculavel();
    resposta.calculo.territorio.indice = null;
    resposta.calculo.janela_90d.indice = null;
    resposta.calculo.meteorologia_dia = { data: "2026-08-30", base: null, indice_diario: null };
    fetchJSON.mockResolvedValue(resposta);
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByRole("heading", { name: "1. Território: dados insuficientes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "4. Valor exibido para a janela de 90 dias: dados insuficientes" })).toBeInTheDocument();
    expect(document.querySelectorAll(".hydric-ai-formula")).toHaveLength(0);
    expect(document.body.textContent).not.toContain("indisponível / 100");
  });

  it("mostra a falha da IA sem fabricar uma conta", async () => {
    fetchJSON.mockRejectedValue(new Error("Serviço temporariamente indisponível."));
    render(<ExplicacaoHidricaIA idFazenda="8" avaliacao={avaliacao} />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Serviço temporariamente indisponível.");
    expect(screen.queryByText("Como chegamos ao valor")).not.toBeInTheDocument();
  });
});
