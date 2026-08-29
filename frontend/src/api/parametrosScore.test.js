import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ErroApiParametrosScore,
  buscarParametrosScore,
  salvarParametrosScore,
} from "./parametrosScore";
import { fixtureParametrosScore } from "../test/fixtureParametrosScore";

describe("cliente de parâmetros do modelo", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("busca a configuração vigente no endpoint oficial", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => fixtureParametrosScore,
    });
    vi.stubGlobal("fetch", fetch);
    const dto = await buscarParametrosScore();
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/parametros-score",
    );
    expect(dto.parametros).toHaveLength(22);
  });

  it("salva via PUT enviando o corpo informado", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => fixtureParametrosScore,
    });
    vi.stubGlobal("fetch", fetch);
    const entrada = {
      parametros: [
        {
          grupo: "SCORE",
          indicador: "EXPOSICAO_HIDRICA",
          parametro: "peso",
          valor: 0.3,
        },
      ],
    };
    await salvarParametrosScore(entrada);
    expect(fetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/parametros-score",
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entrada),
      },
    );
  });

  it("propaga as mensagens de erro por grupo do backend em falha de validação", async () => {
    const detail = [
      { grupo: "SCORE", mensagem: "Os pesos do índice devem totalizar 100%." },
    ];
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail }),
    });
    vi.stubGlobal("fetch", fetch);
    await expect(salvarParametrosScore({ parametros: [] })).rejects.toThrow(
      "Os pesos do índice devem totalizar 100%.",
    );
    try {
      await salvarParametrosScore({ parametros: [] });
    } catch (erro) {
      expect(erro).toBeInstanceOf(ErroApiParametrosScore);
      expect(erro.erros).toEqual(detail);
    }
  });

  it("propaga mensagens de multiplos grupos sem mascarar nenhuma", async () => {
    const detail = [
      { grupo: "SCORE", mensagem: "Os pesos do índice devem totalizar 100%." },
      {
        grupo: "TEMPESTADES",
        mensagem:
          "A base do fator vento–chuva e a influência da chuva das Tempestades Severas devem somar 1,00.",
      },
    ];
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail }),
    });
    vi.stubGlobal("fetch", fetch);
    try {
      await salvarParametrosScore({ parametros: [] });
      throw new Error("deveria ter lancado");
    } catch (erro) {
      expect(erro.erros).toHaveLength(2);
      expect(erro.erros.map((e) => e.grupo)).toEqual(["SCORE", "TEMPESTADES"]);
    }
  });

  it("usa mensagem padrão quando a resposta de erro não tem detail", async () => {
    const fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("sem corpo");
      },
    });
    vi.stubGlobal("fetch", fetch);
    await expect(
      salvarParametrosScore({ parametros: [] }),
    ).rejects.toBeInstanceOf(ErroApiParametrosScore);
  });
});
