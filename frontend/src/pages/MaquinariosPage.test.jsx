import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MaquinariosPage } from "./MaquinariosPage";

const api = vi.hoisted(() => ({
  listar: vi.fn(),
  cadastrar: vi.fn(),
  validar: vi.fn(),
  importar: vi.fn(),
  baixar: vi.fn(),
}));

vi.mock("../api/maquinarios", () => ({
  listarMaquinarios: api.listar,
  cadastrarMaquinario: api.cadastrar,
  validarCsvMaquinarios: api.validar,
  importarCsvMaquinarios: api.importar,
  baixarModeloMaquinarios: api.baixar,
}));

const fazenda = {
  id: "5",
  id_fazenda: "5",
  nome_fazenda: "Embrapa Acre",
  numero_apolice: "69900-970",
  apolices: ["69900-970"],
  cidade: "Rio Branco",
  uf: "AC",
  arquivada: false,
};

beforeEach(() => {
  api.listar.mockReset().mockResolvedValue({
    maquinarios: [
      {
        id_maquinario: 1,
        tipo_equipamento: "TRATOR",
        marca: "JOHN_DEERE",
        modelo: "7230J",
        ano_fabricacao: 2022,
        chassi: "DEMO-01",
        horimetro_atual: 1250.5,
        possui_seguro: true,
        seguradora: "SOMPO",
        vencimento_apolice: "2027-11-15",
      },
    ],
    resumo: {
      total: 1,
      segurados: 1,
      sem_seguro: 0,
      percentual_segurado: 100,
      vencendo_90_dias: 0,
    },
  });
  api.cadastrar.mockReset().mockResolvedValue({ id_maquinario: 2 });
  api.validar.mockReset();
  api.importar.mockReset();
  api.baixar.mockReset();
});

afterEach(cleanup);

describe("MaquinariosPage", () => {
  it("consulta somente a frota da fazenda recebida", async () => {
    render(<MaquinariosPage fazenda={fazenda} />);

    expect(await screen.findByText(/7230J/)).toBeInTheDocument();
    expect(screen.getAllByText("Embrapa Acre").length).toBeGreaterThan(0);
    expect(api.listar).toHaveBeenCalledWith("5");
  });

  it("cadastra um equipamento individual sem valores demonstrativos padrão", async () => {
    const showToast = vi.fn();
    render(
      <MaquinariosPage
        fazenda={fazenda}
        showToast={showToast}
        onAtualizado={vi.fn()}
        onDirtyChange={vi.fn()}
      />,
    );
    await screen.findByText(/7230J/);
    fireEvent.click(screen.getByRole("tab", { name: "Cadastro individual" }));

    expect(screen.getByLabelText(/Modelo/)).toHaveValue("");
    fireEvent.change(screen.getByLabelText(/Tipo de equipamento/), { target: { value: "TRATOR" } });
    fireEvent.change(screen.getByLabelText(/Marca \/ fabricante/), { target: { value: "VALTRA" } });
    fireEvent.change(screen.getByLabelText(/Modelo/), { target: { value: "BH 224" } });
    fireEvent.change(screen.getByLabelText(/Ano de fabricação/), { target: { value: "2024" } });
    fireEvent.change(screen.getByLabelText(/Horímetro atual/), { target: { value: "120.5" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar maquinário/ }));

    await waitFor(() => expect(api.cadastrar).toHaveBeenCalledTimes(1));
    expect(api.cadastrar).toHaveBeenCalledWith(
      "5",
      expect.objectContaining({
        tipo_equipamento: "TRATOR",
        marca: "VALTRA",
        modelo: "BH 224",
        ano_fabricacao: 2024,
        horimetro_atual: 120.5,
        possui_seguro: false,
      }),
    );
    expect(showToast).toHaveBeenCalledWith(
      "Maquinário cadastrado e vinculado à fazenda.",
    );
  });

  it("mantém fazenda arquivada em modo somente consulta", async () => {
    render(<MaquinariosPage fazenda={{ ...fazenda, arquivada: true }} />);

    await screen.findByText(/7230J/);
    expect(screen.getByText(/somente consulta/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Cadastro individual" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Importar CSV" })).not.toBeInTheDocument();
  });
});
