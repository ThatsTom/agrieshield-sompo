import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplicacaoPerigoIA } from "./ExplicacaoPerigoIA";

const { fetchJSON } = vi.hoisted(() => ({ fetchJSON: vi.fn() }));
vi.mock("../api/core", () => ({ fetchJSON }));
const avaliacao = { data_referencia: "2026-10-27", fonte_meteorologica: "NASA_POWER" };
function resposta(perigo, nomePerigo) {
  return {
    modelo: "modelo-configurado",
    calculo: {
      fazenda: "Fazenda Pampa Sul", perigo, nome_perigo: nomePerigo,
      data_referencia: "2026-10-27", fonte_meteorologica: "NASA_POWER",
      disponibilidade_diaria: { motivo: "Último cálculo disponível em 21/10/2026, seis dias antes da referência." },
      dia: { data: "2026-10-21", indice_diario: 0 },
      dados_utilizados: [{ rotulo: "Precipitação do dia", valor: 0, unidade: "mm" }],
      etapas: [{ titulo: "Resultado diário", formula: "Índice diário ≈ 0,00 × 1,00 = 0,00", resultado: 0 }],
      janela_90d: {
        inicio: "2026-07-30", fim: "2026-10-27", dias_disponiveis: 84, dias_esperados: 90,
        dias_relevantes: 0, eventos: 0, indice: 0,
        pesos: { severidade: .4, frequencia: .3, duracao: .2, recorrencia: .1 },
        componentes: { severidade: 0, frequencia: 0, duracao: 0, recorrencia: 0 },
      },
      limitacoes: ["Metodologia experimental."],
    },
    explicacao: {
      resumo: `Explicação de ${nomePerigo}.`, leitura_dados: "Dados usados.",
      leitura_calculo: "Como os componentes participam.", leitura_janela: "Leitura histórica.",
      limitacoes: "Não é probabilidade de sinistro.",
    },
  };
}
afterEach(() => { cleanup(); fetchJSON.mockReset(); });

describe("explicação dos outros quatro perigos", () => {
  it.each([
    ["INCENDIO", "Incêndio / Propagação de Fogo"],
    ["INSTABILIDADE", "Instabilidade"],
    ["TRAFEGABILIDADE", "Trafegabilidade"],
    ["TEMPESTADES", "Tempestades Severas"],
  ])("consulta e mostra exclusivamente o cálculo de %s", async (perigo, nomePerigo) => {
    fetchJSON.mockResolvedValue(resposta(perigo, nomePerigo));
    render(<ExplicacaoPerigoIA idFazenda="8" avaliacao={avaliacao} perigo={perigo} nomePerigo={nomePerigo} />);
    expect(fetchJSON).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    expect(await screen.findByText(`Explicação de ${nomePerigo}.`)).toBeVisible();
    const url = new URL(fetchJSON.mock.calls[0][0], "http://localhost");
    expect(url.pathname).toBe("/api/v1/exposicao/8/explicacao-perigo-ia");
    expect(url.searchParams.get("perigo")).toBe(perigo);
    expect(url.searchParams.get("fonte")).toBe("NASA_POWER");
    expect(url.searchParams.get("data_referencia")).toBe("2026-10-27");
    expect(screen.getByRole("heading", { name: "1. Dados utilizados em 21/10/2026" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "2. Cálculo diário: 0,00 / 100" })).toBeVisible();
    expect(screen.getByText("0,00 mm")).toBeVisible();
    expect(screen.getByText("Índice diário ≈ 0,00 × 1,00 = 0,00")).toBeVisible();
    expect(document.body.textContent).toContain("84 de 90 dias disponíveis");
    expect(document.body.textContent).toContain("seis dias antes da referência");
  });

  it("explica a ausência sem apresentar uma equação diária ou agregada incompleta", async () => {
    const retorno = resposta("INSTABILIDADE", "Instabilidade");
    retorno.calculo.dia = { data: "2026-10-27", indice_diario: null };
    retorno.calculo.dados_utilizados[0].valor = null;
    retorno.calculo.etapas = [];
    retorno.calculo.janela_90d.indice = null;
    retorno.calculo.disponibilidade_diaria.motivo = "Faltam dados de declividade.";
    fetchJSON.mockResolvedValue(retorno);
    render(<ExplicacaoPerigoIA idFazenda="8" avaliacao={avaliacao} perigo="INSTABILIDADE" nomePerigo="Instabilidade" />);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    expect(await screen.findByRole("heading", { name: "2. Cálculo diário: dados insuficientes" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Faltam dados de declividade.");
    expect(document.querySelectorAll(".hydric-ai-formula")).toHaveLength(0);
    expect(document.body.textContent).not.toContain("indisponível / 100");
  });
});
