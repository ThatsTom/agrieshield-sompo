import { afterEach, describe, expect, it, vi } from "vitest";

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));

vi.mock("../auth/supabase", () => ({
  supabase: { auth: { getSession } },
}));

import { fetchAutenticado, fetchJSON } from "./core";

describe("cliente HTTP autenticado", () => {
  afterEach(() => {
    getSession.mockReset();
    vi.unstubAllGlobals();
  });

  it("encaminha o token da sessão Supabase no cabeçalho Authorization", async () => {
    getSession.mockResolvedValue({
      data: { session: { access_token: "token-da-sessao" } },
    });
    const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200 });
    vi.stubGlobal("fetch", fetch);

    await fetchAutenticado("/api/v1/parametros-score");

    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:8000/api/v1/parametros-score");
    expect(options.headers.get("Authorization")).toBe(
      "Bearer token-da-sessao",
    );
  });

  it("identifica separadamente a mensagem pública devolvida pela API", async () => {
    getSession.mockResolvedValue({ data: { session: null } });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ detail: "Serviço temporariamente indisponível." }),
    }));

    await expect(fetchJSON("/api/geocodificacao/endereco")).rejects.toMatchObject({
      message: "Serviço temporariamente indisponível.",
      publicMessage: "Serviço temporariamente indisponível.",
      status: 502,
    });
  });
});
