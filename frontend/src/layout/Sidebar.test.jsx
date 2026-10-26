import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

afterEach(cleanup);

describe("navegação responsiva", () => {
  it("abre o menu móvel, identifica a página atual e navega fechando o painel", () => {
    const setPage = vi.fn();
    render(<Sidebar page="insights" setPage={setPage} />);

    fireEvent.click(screen.getByRole("button", { name: "Abrir menu de navegação" }));
    const dialog = screen.getByRole("dialog", { name: "Menu de navegação" });
    expect(dialog).toHaveClass("is-open");
    expect(screen.getAllByText("Insights").length).toBeGreaterThan(0);

    const dashboardButtons = screen.getAllByRole("button", { name: "Visão Geral" });
    fireEvent.click(dashboardButtons.at(-1));
    expect(setPage).toHaveBeenCalledWith("dashboard");
    expect(dialog).not.toHaveClass("is-open");
  });

  it("fecha o menu com Escape e devolve o foco ao botão hambúrguer", async () => {
    render(<Sidebar page="dashboard" setPage={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Abrir menu de navegação" });
    fireEvent.click(trigger);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("exibe identidade real e restringe o gerenciamento ao administrador", () => {
    const props = {
      page: "dashboard",
      setPage: vi.fn(),
      onLogout: vi.fn(),
      perfil: { nome_completo: "Maria Consultora", funcao: "Subscrição rural" },
    };
    const { rerender } = render(<Sidebar {...props} isAdmin={false} />);
    expect(screen.getAllByText("Maria Consultora").length).toBeGreaterThan(0);
    expect(screen.queryByText("Gerenciar Acessos")).not.toBeInTheDocument();

    rerender(<Sidebar {...props} isAdmin />);
    expect(screen.getAllByText("Gerenciar Acessos").length).toBeGreaterThan(0);
  });
});
