import type {
  FonteMeteorologica,
  ResultadoApresentacaoExposicaoMaquinario,
} from "../types/exposicao";
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
export function mensagemErroExposicao(status: number): string {
  if (status === 404) return "Fazenda não encontrada.";
  if (status === 422)
    return "Dados necessários para a avaliação ainda não estão disponíveis.";
  if (status === 503) return "Fonte de dados temporariamente indisponível.";
  return "Não foi possível carregar a exposição do maquinário.";
}
export class ErroApiExposicao extends Error {
  status: number;
  codigo?: string;
  constructor(status: number, mensagem?: string, codigo?: string) {
    super(mensagem || mensagemErroExposicao(status));
    this.name = "ErroApiExposicao";
    this.status = status;
    this.codigo = codigo;
  }
}

async function lerDetalheErro(
  resposta: Response,
): Promise<{ mensagem?: string; codigo?: string }> {
  try {
    const corpo = await resposta.json();
    const detalhe = corpo?.detail;
    if (typeof detalhe === "string") return { mensagem: detalhe };
    if (detalhe && typeof detalhe === "object")
      return {
        mensagem:
          typeof detalhe.mensagem === "string" ? detalhe.mensagem : undefined,
        codigo: typeof detalhe.codigo === "string" ? detalhe.codigo : undefined,
      };
  } catch {
    // Mantem a mensagem segura por status quando o corpo nao for JSON valido.
  }
  return {};
}

export async function buscarExposicaoMaquinario(
  idFazenda: string | number,
  dataReferencia?: string,
  fonte: FonteMeteorologica = "NASA_POWER",
  signal?: AbortSignal,
): Promise<ResultadoApresentacaoExposicaoMaquinario> {
  const params = new URLSearchParams({ fonte });
  if (dataReferencia) params.set("data_referencia", dataReferencia);
  const url = `${API_URL}/api/v1/exposicao/${encodeURIComponent(String(idFazenda))}?${params}`;
  const resposta = signal ? await fetch(url, { signal }) : await fetch(url);
  if (!resposta.ok) {
    const detalhe = await lerDetalheErro(resposta);
    throw new ErroApiExposicao(
      resposta.status,
      detalhe.mensagem,
      detalhe.codigo,
    );
  }
  return (await resposta.json()) as ResultadoApresentacaoExposicaoMaquinario;
}
