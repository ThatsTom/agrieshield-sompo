import { supabase } from "../auth/supabase";

export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function avisarSessaoAusente(response) {
  if (response.status === 401 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("agrishield:unauthorized"));
  }
}

export async function fetchAutenticado(path, options) {
  const headers = new Headers(options?.headers || {});
  if (supabase && !headers.has("Authorization")) {
    const { data } = await supabase.auth.getSession();
    if (data.session?.access_token) {
      headers.set("Authorization", `Bearer ${data.session.access_token}`);
    }
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  avisarSessaoAusente(response);
  return response;
}

export async function fetchJSON(path, options) {
  const response = await fetchAutenticado(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : "";
    const erro = new Error(detail || `Erro ${response.status} em ${path}`);
    erro.status = response.status;
    erro.publicMessage = detail;
    throw erro;
  }
  return response.json();
}

export async function baixarArquivoAutenticado(path, nomeArquivo) {
  const response = await fetchAutenticado(path);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : "";
    throw new Error(detail || `Erro ${response.status} ao baixar o arquivo`);
  }

  const urlTemporaria = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = urlTemporaria;
  link.download = nomeArquivo;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(urlTemporaria);
}
