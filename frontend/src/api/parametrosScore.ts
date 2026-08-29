import type {
  ConfiguracaoParametrosModeloApresentacao,
  ErroGrupoParametrosModelo,
  ParametrosModeloIn,
} from "../types/parametrosScore";
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export class ErroApiParametrosScore extends Error {
  status: number;
  erros: ErroGrupoParametrosModelo[];
  constructor(
    status: number,
    mensagem: string,
    erros: ErroGrupoParametrosModelo[] = [],
  ) {
    super(mensagem);
    this.name = "ErroApiParametrosScore";
    this.status = status;
    this.erros = erros;
  }
}

async function tratarResposta(
  resposta: Response,
): Promise<ConfiguracaoParametrosModeloApresentacao> {
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    if (Array.isArray(corpo?.detail)) {
      const erros = corpo.detail as ErroGrupoParametrosModelo[];
      const mensagem =
        erros.map((e) => e.mensagem).join(" ") ||
        "Não foi possível salvar os parâmetros do modelo.";
      throw new ErroApiParametrosScore(resposta.status, mensagem, erros);
    }
    const mensagem =
      typeof corpo?.detail === "string"
        ? corpo.detail
        : "Não foi possível salvar os parâmetros do modelo.";
    throw new ErroApiParametrosScore(resposta.status, mensagem);
  }
  return (await resposta.json()) as ConfiguracaoParametrosModeloApresentacao;
}

export async function buscarParametrosScore(): Promise<ConfiguracaoParametrosModeloApresentacao> {
  const resposta = await fetch(`${API_URL}/api/v1/parametros-score`);
  return tratarResposta(resposta);
}

export async function salvarParametrosScore(
  entrada: ParametrosModeloIn,
): Promise<ConfiguracaoParametrosModeloApresentacao> {
  const resposta = await fetch(`${API_URL}/api/v1/parametros-score`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entrada),
  });
  return tratarResposta(resposta);
}
