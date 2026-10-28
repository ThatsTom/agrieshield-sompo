import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplicacaoCalculoIA } from "./ExplicacaoCalculoIA";

const { fetchJSON } = vi.hoisted(() => ({ fetchJSON: vi.fn() }));
vi.mock("../api/core", () => ({ fetchJSON }));
const avaliacao = { data_referencia: "2026-10-27", fonte_meteorologica: "NASA_POWER" };
const props = { idFazenda: "8", avaliacao, nomePerigo: "Exposição Hídrica" };
const relatorio = (dados) => <p>{dados.texto}</p>;

afterEach(() => {
  cleanup();
  fetchJSON.mockReset();
});

describe("exibição da explicação com IA", () => {
  it("recolhe e reabre o relatório já gerado sem nova chamada à IA", async () => {
    fetchJSON.mockResolvedValue({ texto: "Relatório já gerado." });
    render(<ExplicacaoCalculoIA {...props}>{relatorio}</ExplicacaoCalculoIA>);
    expect(fetchJSON).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    expect(await screen.findByText("Relatório já gerado.")).toBeVisible();
    const recolher = screen.getByRole("button", { name: "Recolher explicação" });
    expect(recolher).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById(recolher.getAttribute("aria-controls"))).toBeVisible();

    fireEvent.click(recolher);
    expect(screen.getByText("Relatório já gerado.")).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Mostrar explicação novamente" }));
    expect(screen.getByText("Relatório já gerado.")).toBeVisible();
    expect(fetchJSON).toHaveBeenCalledTimes(1);
  });

  it("preserva o relatório quando uma nova geração falha", async () => {
    fetchJSON.mockResolvedValueOnce({ texto: "Relatório original." }).mockRejectedValueOnce(new Error("IA temporariamente indisponível."));
    render(<ExplicacaoCalculoIA {...props}>{relatorio}</ExplicacaoCalculoIA>);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    expect(await screen.findByText("Relatório original.")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Gerar nova explicação" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("IA temporariamente indisponível.");
    expect(screen.getByText("Relatório original.")).toBeVisible();
    expect(fetchJSON).toHaveBeenCalledTimes(2);
  });

  it.each([
    { idFazenda: "9" },
    { avaliacao: { ...avaliacao, data_referencia: "2026-10-26" } },
    { avaliacao: { ...avaliacao, fonte_meteorologica: "OPEN_METEO" } },
    { perigo: "INCENDIO", nomePerigo: "Incêndio" },
  ])("descarta o relatório anterior ao mudar o contexto: %j", async (novoContexto) => {
    fetchJSON.mockResolvedValue({ texto: "Relatório do contexto anterior." });
    const { rerender } = render(<ExplicacaoCalculoIA {...props}>{relatorio}</ExplicacaoCalculoIA>);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    expect(await screen.findByText("Relatório do contexto anterior.")).toBeVisible();
    rerender(<ExplicacaoCalculoIA {...props} {...novoContexto}>{relatorio}</ExplicacaoCalculoIA>);
    expect(screen.queryByText("Relatório do contexto anterior.")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deixe a IA te explicar" })).toBeInTheDocument();
    expect(fetchJSON).toHaveBeenCalledTimes(1);
  });

  it("cancela uma geração antiga ao trocar de fazenda", async () => {
    let concluir;
    fetchJSON.mockImplementation(() => new Promise((resolve) => { concluir = resolve; }));
    const { rerender } = render(<ExplicacaoCalculoIA {...props}>{relatorio}</ExplicacaoCalculoIA>);
    fireEvent.click(screen.getByRole("button", { name: "Deixe a IA te explicar" }));
    const signal = fetchJSON.mock.calls[0][1].signal;
    rerender(<ExplicacaoCalculoIA {...props} idFazenda="9">{relatorio}</ExplicacaoCalculoIA>);
    expect(signal.aborted).toBe(true);
    await act(async () => { concluir({ texto: "Relatório da fazenda anterior." }); });
    expect(screen.queryByText("Relatório da fazenda anterior.")).not.toBeInTheDocument();
  });
});
