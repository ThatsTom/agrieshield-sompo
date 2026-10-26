import { baixarArquivoAutenticado, fetchJSON } from "./core";

const rotaFazenda = (idFazenda) =>
  `/api/fazendas/${encodeURIComponent(String(idFazenda))}/maquinarios`;

export function listarMaquinarios(idFazenda) {
  return fetchJSON(rotaFazenda(idFazenda));
}

export function cadastrarMaquinario(idFazenda, dados) {
  return fetchJSON(rotaFazenda(idFazenda), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
  });
}

export function validarCsvMaquinarios(idFazenda, conteudoCsv) {
  return fetchJSON(`${rotaFazenda(idFazenda)}/importacoes/validar`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conteudo_csv: conteudoCsv }),
  });
}

export function importarCsvMaquinarios(idFazenda, conteudoCsv) {
  return fetchJSON(`${rotaFazenda(idFazenda)}/importacoes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conteudo_csv: conteudoCsv }),
  });
}

export function baixarModeloMaquinarios() {
  return baixarArquivoAutenticado(
    "/api/maquinarios/modelo.csv",
    "modelo-maquinarios-agrishield.csv",
  );
}
