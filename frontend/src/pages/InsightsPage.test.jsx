import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InsightsPage } from "./InsightsPage";

const insight = {
  resumo_executivo: "A operação requer acompanhamento preventivo.",
  nivel_atencao: "moderado",
  leitura_principal: "Há chuva prevista e o acesso deve ser confirmado.",
  prioridades: [
    {
      titulo: "Confirmar acesso",
      prioridade: "hoje",
      motivo: "A chuva pode afetar a operação.",
      acao_recomendada: "Validar a rota com o responsável local.",
      dado_base: "Previsão de chuva para amanhã.",
    },
  ],
  perguntas_consultor: ["Há uma rota alternativa?"],
  pontos_positivos: ["O contexto territorial está disponível."],
  limitacoes: ["A previsão pode mudar."],
};

const dashboard = {
  score: {
    score: 70,
    condicao_atual: "Atenção",
    distribuicao_30d: { total: 30, ideais: 20, atencao: 8, restricao: 2 },
    fatores_risco: [],
  },
  origem_previsao: "api_open_meteo",
  previsao_atualizada_em: "2026-09-15T12:00:00Z",
  previsao_7d: [
    { data: "2026-09-15", precipitacao_mm: 0, prob_precip_pct: 10, temp_max_c: 30 },
    { data: "2026-09-16", precipitacao_mm: 1, prob_precip_pct: 20, temp_max_c: 31 },
    { data: "2026-09-17", precipitacao_mm: 2, prob_precip_pct: 30, temp_max_c: 32 },
    { data: "2026-09-18", precipitacao_mm: 3, prob_precip_pct: 40, temp_max_c: 33 },
    { data: "2026-09-19", precipitacao_mm: 4, prob_precip_pct: 50, temp_max_c: 34 },
    { data: "2026-09-20", precipitacao_mm: 5, prob_precip_pct: 70, temp_max_c: 35 },
    { data: "2026-09-21", precipitacao_mm: 6, prob_precip_pct: 80, temp_max_c: 34 },
  ],
  maquinarios_resumo: {
    disponivel: true,
    total: 4,
    segurados: 2,
    seguros_vigentes: 1,
    seguros_vencidos: 1,
    sem_seguro: 2,
    percentual_segurado: 50,
    vencendo_90_dias: 1,
    proximo_vencimento: "2026-11-15",
    idade_media_anos: 4.5,
    horimetro_total_horas: 3930.5,
    horimetros_informados: 3,
    horas_dia_estimadas: 21.5,
    horas_dia_informadas: 3,
    por_tipo: { TRATOR: 1, COLHEITADEIRA: 1, PLANTADEIRA: 2 },
    atualizado_em: "2026-09-15T12:00:00Z",
  },
};

const fazenda = {
  id: "1",
  nome_fazenda: "Fazenda Horizonte",
  tipo_operacao: "campo",
  uf: "MT",
  cidade: "Sorriso",
  area_ha: 120,
  proximidade_agua: true,
  status_geoespacial: "SUCESSO",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("InsightsPage", () => {
  it("gera e apresenta um briefing prático ao abrir a página", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        modelo: "gpt-4o-mini",
        gerado_em: "2026-09-09T12:00:00Z",
        cache: false,
        insight,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <InsightsPage
        fazendas={[fazenda]}
        dashboard={dashboard}
        selected="1"
        fazenda={fazenda}
      />,
    );

    expect(await screen.findByText("Confirmar acesso")).toBeInTheDocument();
    expect(screen.getByText("Radar para tomada de decisão")).toBeInTheDocument();
    expect(screen.getByText("Conferir seguros cadastrados vencidos")).toBeInTheDocument();
    expect(screen.getByText("Próximo passo:")).toBeInTheDocument();
    expect(screen.getByText(/Previsão de chuva para amanhã/)).toBeInTheDocument();
    expect(screen.getByText("Perguntas para validar")).toBeInTheDocument();
    expect(screen.getByText("Previsão dos próximos 7 dias")).toBeInTheDocument();
    expect(screen.getByText("21 mm")).toBeInTheDocument();
    expect(screen.getByText("Maquinário de Fazenda Horizonte")).toBeInTheDocument();
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
    expect(screen.getByText("21,5 h/dia")).toBeInTheDocument();
    expect(screen.getByText("3.930,5 h")).toBeInTheDocument();
    expect(screen.getByText("Cobertura dos dados e contexto cadastral")).toBeInTheDocument();
    expect(screen.queryByText(/Insights 2\.0/i)).not.toBeInTheDocument();
    const previsaoDiaria = screen.getByRole("list", { name: "Previsão diária" });
    expect(within(previsaoDiaria).getAllByRole("listitem")).toHaveLength(7);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/fazendas/1/insights-ia",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("solicita uma nova leitura quando o consultor atualiza", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cache: false, insight }),
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <InsightsPage
        fazendas={[fazenda]}
        dashboard={dashboard}
        selected="1"
        fazenda={fazenda}
      />,
    );
    await screen.findByText("Confirmar acesso");

    fireEvent.click(screen.getByRole("button", { name: "Atualizar análise" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][1].body).toBe(JSON.stringify({ forcar: true }));
  });

  it("mantém os indicadores determinísticos quando a IA falha", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: "Configure OPENAI_API_KEY no backend." }),
      }),
    );
    render(
      <InsightsPage
        fazendas={[fazenda]}
        dashboard={dashboard}
        selected="1"
        fazenda={fazenda}
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("OPENAI_API_KEY");
    expect(screen.getAllByText("70/100").length).toBeGreaterThan(0);
    expect(screen.getByText("Distribuição cadastral")).toBeInTheDocument();
  });

  it("permite alternar rapidamente a fazenda analisada", () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cache: true, insight }),
    }));
    const setSelected = vi.fn();
    const outraFazenda = {
      ...fazenda,
      id: "2",
      nome_fazenda: "Fazenda Aurora",
      cidade: "Sorriso",
    };
    render(
      <InsightsPage
        fazendas={[fazenda, outraFazenda]}
        dashboard={dashboard}
        selected="1"
        setSelected={setSelected}
        fazenda={fazenda}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Próxima fazenda" }));
    expect(setSelected).toHaveBeenCalledWith("2");
  });

  it("não converte valores climáticos ausentes em zero ou condição estável", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cache: true, insight }),
    }));
    const parcial = {
      ...dashboard,
      previsao_7d: Array.from({ length: 7 }, (_, indice) => ({
        data: `2026-09-${String(15 + indice).padStart(2, "0")}`,
        precipitacao_mm: null,
        prob_precip_pct: null,
        temp_max_c: null,
      })),
    };

    render(
      <InsightsPage
        fazendas={[fazenda]}
        dashboard={parcial}
        selected="1"
        fazenda={fazenda}
      />,
    );

    expect(await screen.findByText("Confirmar acesso")).toBeInTheDocument();
    expect(screen.getAllByText("Dados incompletos")).toHaveLength(7);
    expect(screen.getByText("Nenhuma sequência identificada")).toBeInTheDocument();
    expect(screen.queryByText("0 mm")).not.toBeInTheDocument();
    expect(screen.getByText("Previsão parcial")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Previsão diária com rolagem horizontal" })).toHaveAttribute("tabindex", "0");
  });

  it("não apresenta uma soma parcial de chuva como acumulado de sete dias", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ cache: true, insight }),
    }));
    const parcial = {
      ...dashboard,
      previsao_7d: dashboard.previsao_7d.map((dia, indice) => (
        indice === 6 ? { ...dia, precipitacao_mm: null } : dia
      )),
    };

    render(
      <InsightsPage
        fazendas={[fazenda]}
        dashboard={parcial}
        selected="1"
        fazenda={fazenda}
      />,
    );

    expect(await screen.findByText("Confirmar acesso")).toBeInTheDocument();
    expect(screen.getByText("Previsão parcial")).toBeInTheDocument();
    expect(screen.getByText("6 de 7 dias com valor")).toBeInTheDocument();
    expect(screen.queryByText("15 mm")).not.toBeInTheDocument();
  });
});
