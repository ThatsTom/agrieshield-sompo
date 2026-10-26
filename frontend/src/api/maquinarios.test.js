import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cadastrarMaquinario,
  importarCsvMaquinarios,
  listarMaquinarios,
  validarCsvMaquinarios,
} from "./maquinarios";

afterEach(() => vi.unstubAllGlobals());

describe("cliente de maquinários", () => {
  it("lista somente pelo identificador da fazenda", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ maquinarios: [], resumo: { total: 0 } }),
    });
    vi.stubGlobal("fetch", fetch);

    await listarMaquinarios("fazenda 5");

    expect(fetch.mock.calls[0][0]).toBe(
      "http://127.0.0.1:8000/api/fazendas/fazenda%205/maquinarios",
    );
  });

  it("envia o cadastro individual como JSON", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id_maquinario: 1 }),
    });
    vi.stubGlobal("fetch", fetch);
    const dados = { tipo_equipamento: "TRATOR", modelo: "7230J" };

    await cadastrarMaquinario(5, dados);

    const [, options] = fetch.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.body).toBe(JSON.stringify(dados));
    expect(options.headers.get("Content-Type")).toBe("application/json");
  });

  it("valida e importa o mesmo conteúdo CSV no escopo da fazenda", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ valido: true, total_validos: 1 }),
    });
    vi.stubGlobal("fetch", fetch);

    await validarCsvMaquinarios(5, "cabecalho\nlinha");
    await importarCsvMaquinarios(5, "cabecalho\nlinha");

    expect(fetch.mock.calls[0][0]).toMatch(/\/importacoes\/validar$/);
    expect(fetch.mock.calls[1][0]).toMatch(/\/importacoes$/);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
      conteudo_csv: "cabecalho\nlinha",
    });
  });
});
