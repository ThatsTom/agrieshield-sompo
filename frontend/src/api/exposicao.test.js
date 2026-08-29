import { afterEach, describe, expect, it, vi } from "vitest";
import { buscarExposicaoMaquinario, mensagemErroExposicao } from "./exposicao";
import { fixtureExposicao } from "../test/fixtureExposicao";
describe("cliente de exposição", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("usa somente o endpoint oficial com NASA default e sem data", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => fixtureExposicao });
    vi.stubGlobal("fetch", fetch);
    const dto = await buscarExposicaoMaquinario("fazenda 1");
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/exposicao/fazenda%201?fonte=NASA_POWER",
    );
    expect(dto.score_atual).toBe(0);
    expect(dto.perigos).toHaveLength(5);
    expect(dto.exposicao_hidrica.janela_atual.indice).toBe(
      dto.perigos[0].indice,
    );
    expect(Object.keys(dto.detalhes_perigos)).toEqual([
      "trafegabilidade",
      "incendio",
      "instabilidade",
      "tempestades",
    ]);
    expect(dto.detalhes_perigos.incendio.dia_maior_indice.indice_diario).toBe(
      23.456,
    );
  });
  it("inclui data opcional sem alterar valor", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => fixtureExposicao });
    vi.stubGlobal("fetch", fetch);
    await buscarExposicaoMaquinario(1, "2026-07-31");
    expect(fetch.mock.calls[0][0]).toContain(
      "fonte=NASA_POWER&data_referencia=2026-07-31",
    );
  });
  it.each([
    [404, "Fazenda não encontrada."],
    [422, "Dados necessários para a avaliação ainda não estão disponíveis."],
    [503, "Fonte de dados temporariamente indisponível."],
    [500, "Não foi possível carregar"],
  ])("mapeia erro %s", (status, texto) =>
    expect(mensagemErroExposicao(status)).toContain(texto),
  );
});

it("preserva o diagnostico estruturado devolvido pelo backend", async () => {
  const fetch = vi.fn().mockResolvedValue({
    ok: false,
    status: 422,
    json: async () => ({
      detail: {
        codigo: "CONTEXTO_TERRITORIAL_INDISPONIVEL",
        mensagem: "Contexto territorial normalizado indisponivel",
      },
    }),
  });
  vi.stubGlobal("fetch", fetch);
  await expect(buscarExposicaoMaquinario(1)).rejects.toMatchObject({
    status: 422,
    codigo: "CONTEXTO_TERRITORIAL_INDISPONIVEL",
    message: "Contexto territorial normalizado indisponivel",
  });
});
