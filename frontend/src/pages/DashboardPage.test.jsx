import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { buscarExposicaoMaquinario } from "../api/exposicao";
import { DEMO_DASH, DEMO_FAZENDAS } from "../demoData";
import { fixtureExposicao } from "../test/fixtureExposicao";
import { DashboardPage } from "./DashboardPage";

vi.mock("../api/exposicao", () => ({
  buscarExposicaoMaquinario: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function mostrarDashboard() {
  render(
    <DashboardPage
      fazendas={DEMO_FAZENDAS}
      selected="1"
      setSelected={vi.fn()}
      dashboard={{ ...DEMO_DASH, score: { ...DEMO_DASH.score, score: 56 } }}
      fazenda={DEMO_FAZENDAS[0]}
      onNavigate={vi.fn()}
      showToast={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
}

describe("score de exposição na Visão Geral", () => {
  it("mostra o score publicado pelo mesmo endpoint de Operações", async () => {
    buscarExposicaoMaquinario.mockResolvedValue({
      ...fixtureExposicao,
      score_atual: 48.21,
      classificacao_atual: "ATENCAO",
      perigo_dominante: "EXPOSICAO_HIDRICA",
      perigos: fixtureExposicao.perigos.map((perigo) => ({
        ...perigo,
        contribuicao: {
          EXPOSICAO_HIDRICA: 20.21,
          TRAFEGABILIDADE: 18,
          INCENDIO: 10,
        }[perigo.perigo] || 0,
      })),
    });
    mostrarDashboard();

    expect(await screen.findByRole("img", {
      name: "Score de exposição 48,21 de 100, classificação ATENÇÃO",
    })).toBeInTheDocument();
    expect(screen.getByRole("heading", {
      name: /Score de Exposição do Maquinário/,
    })).toBeInTheDocument();
    expect(screen.getByText("Perigo dominante: Exposição Hídrica")).toBeInTheDocument();
    expect(screen.getByText("20,21 pontos")).toBeInTheDocument();
    expect(buscarExposicaoMaquinario).toHaveBeenCalledWith(
      "1", undefined, "NASA_POWER", expect.any(AbortSignal),
    );
  });

  it("não reutiliza o 56 operacional quando o score de exposição não é publicável", async () => {
    buscarExposicaoMaquinario.mockResolvedValue({
      ...fixtureExposicao,
      score_atual: null,
      classificacao_atual: null,
      score_publicavel: false,
    });
    mostrarDashboard();

    expect(await screen.findByText("Score indisponível")).toBeInTheDocument();
    expect(screen.getByRole("img", {
      name: "Score de exposição indisponível",
    })).toBeInTheDocument();
    expect(screen.queryByText("56")).not.toBeInTheDocument();
  });
});
