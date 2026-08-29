export const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export async function fetchJSON(path, options) {
  const response = await fetch(`${API_URL}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : "";
    throw new Error(detail || `Erro ${response.status} em ${path}`);
  }
  return response.json();
}
