export const numero = (value, digits = 1) => {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return new Intl.NumberFormat("pt-BR", {
    maximumFractionDigits: digits,
  }).format(parsed);
};
export const dataBr = (value) => {
  if (!value) return "—";
  const normalized = String(value).slice(0, 10);
  const date = new Date(`${normalized}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(date);
};
export const tituloOperacao = (value) =>
  value === "transporte" ? "Transporte" : "Campo";
