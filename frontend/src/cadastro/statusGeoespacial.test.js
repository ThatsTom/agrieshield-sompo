import { describe, expect, it } from "vitest";
import {
  obterStatusGeoespacial,
  permiteReprocessarGeoespacial,
} from "./statusGeoespacial";

describe("status geoespacial", () => {
  it.each([
    ["SUCESSO", "Pronto", false],
    ["PENDENTE", "Pendente", true],
    ["ERRO", "Erro", true],
    ["PROCESSANDO", "Processando", false],
  ])("apresenta %s e controla retry", (status, rotulo, retry) => {
    expect(obterStatusGeoespacial(status).curto).toBe(rotulo);
    expect(permiteReprocessarGeoespacial(status)).toBe(retry);
  });

  it("trata status ausente ou desconhecido como pendente", () => {
    expect(obterStatusGeoespacial().curto).toBe("Pendente");
    expect(obterStatusGeoespacial("inexistente").curto).toBe("Pendente");
    expect(permiteReprocessarGeoespacial()).toBe(true);
  });
});
