const STATUS_GEOESPACIAL = {
  SUCESSO: {
    texto: "Contexto territorial pronto",
    curto: "Pronto",
    icone: "✓",
    classe: "success",
  },
  PENDENTE: {
    texto: "Contexto territorial pendente",
    curto: "Pendente",
    icone: "○",
    classe: "pending",
  },
  PROCESSANDO: {
    texto: "Contexto territorial processando",
    curto: "Processando",
    icone: "…",
    classe: "processing",
  },
  ERRO: {
    texto: "Falha no contexto territorial",
    curto: "Erro",
    icone: "!",
    classe: "error",
  },
};

export function obterStatusGeoespacial(status) {
  return (
    STATUS_GEOESPACIAL[String(status || "").toUpperCase()] ||
    STATUS_GEOESPACIAL.PENDENTE
  );
}

export function permiteReprocessarGeoespacial(status) {
  const normalizado = String(status || "PENDENTE").toUpperCase();
  return normalizado === "PENDENTE" || normalizado === "ERRO";
}
