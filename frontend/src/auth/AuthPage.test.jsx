import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { signInWithOtp, verifyOtp } = vi.hoisted(() => ({
  signInWithOtp: vi.fn(),
  verifyOtp: vi.fn(),
}));

vi.mock("./supabase", () => ({
  supabase: { auth: { signInWithOtp, verifyOtp } },
}));
vi.mock("./AuthProvider", () => ({
  useAuth: () => ({ motivoSaida: "", limparMotivoSaida: vi.fn() }),
}));

import { AuthPage } from "./AuthPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("autenticação por e-mail", () => {
  it("envia metadados no cadastro e orienta a confirmação pelo link", async () => {
    signInWithOtp.mockResolvedValue({ error: null });
    verifyOtp.mockResolvedValue({ error: null });
    render(<AuthPage />);

    fireEvent.click(screen.getByRole("tab", { name: "Criar conta" }));
    fireEvent.change(screen.getByLabelText("Nome completo"), {
      target: { value: "Pessoa Teste" },
    });
    fireEvent.change(screen.getByLabelText("Função"), {
      target: { value: "Consultor de riscos" },
    });
    fireEvent.change(screen.getByLabelText("E-mail corporativo"), {
      target: { value: "Pessoa@Empresa.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Enviar confirmação/ }));

    await waitFor(() => expect(signInWithOtp).toHaveBeenCalledWith({
      email: "pessoa@empresa.com",
      options: expect.objectContaining({
        shouldCreateUser: true,
        data: {
          nome_completo: "Pessoa Teste",
          funcao: "Consultor de riscos",
          origem_aplicacao: "agrishield",
        },
      }),
    }));

    expect(await screen.findByText("Verifique seu e-mail")).toBeInTheDocument();
    expect(screen.getByText(/link de confirmação para/)).toHaveTextContent(
      "pessoa@empresa.com",
    );
    expect(
      screen.getByText(/aguarde a aprovação do administrador/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Código de seis dígitos"),
    ).not.toBeInTheDocument();
    expect(verifyOtp).not.toHaveBeenCalled();
  });

  it("mantém o código de seis dígitos para contas já cadastradas", async () => {
    signInWithOtp.mockResolvedValue({ error: null });
    verifyOtp.mockResolvedValue({ error: null });
    render(<AuthPage />);

    fireEvent.change(screen.getByLabelText("E-mail corporativo"), {
      target: { value: "Pessoa@Empresa.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Receber código/ }));

    const campoCodigo = await screen.findByLabelText("Código de seis dígitos");
    fireEvent.change(campoCodigo, { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /Confirmar e continuar/ }));
    await waitFor(() => expect(verifyOtp).toHaveBeenCalledWith({
      email: "pessoa@empresa.com",
      token: "123456",
      type: "email",
    }));
  });

  it("explica o limite global de e-mails e bloqueia novas tentativas", async () => {
    signInWithOtp.mockResolvedValue({
      error: {
        code: "over_email_send_rate_limit",
        message: "email rate limit exceeded",
      },
    });
    render(<AuthPage />);

    fireEvent.change(screen.getByLabelText("E-mail corporativo"), {
      target: { value: "pessoa@empresa.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Receber código/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "o código não foi enviado",
    );
    expect(
      screen.getByRole("button", { name: /Tente novamente em/ }),
    ).toBeDisabled();
  });
});
