export function validarCoordenadas(latitude, longitude) {
  const latVazia = String(latitude ?? "").trim() === "";
  const lonVazia = String(longitude ?? "").trim() === "";
  if (latVazia && lonVazia) return null;
  if (latVazia || lonVazia) return "Informe latitude e longitude juntas.";
  const lat = Number(latitude),
    lon = Number(longitude);
  if (!Number.isFinite(lat) || lat < -90 || lat > 90)
    return "Latitude deve estar entre -90 e 90.";
  if (!Number.isFinite(lon) || lon < -180 || lon > 180)
    return "Longitude deve estar entre -180 e 180.";
  if (lat === 0 && lon === 0)
    return "As coordenadas 0,0 não identificam uma localização válida.";
  return null;
}

export function montarPayloadFazenda(form) {
  const erro = validarCoordenadas(form.latitude, form.longitude);
  if (erro) throw new Error(erro);
  const {
    apolices_adicionais = [],
    poligono_texto = "",
    ...campos
  } = form;
  const payload = { ...campos, area_ha: Number(form.area_ha) };
  payload.apolices = [form.numero_apolice, ...apolices_adicionais]
    .map((numero) => String(numero || "").trim())
    .filter((numero, indice, todos) => numero && todos.indexOf(numero) === indice);
  payload.poligono = parsePoligonoTexto(poligono_texto);
  if (String(form.latitude ?? "").trim() === "") {
    delete payload.latitude;
    delete payload.longitude;
  } else {
    payload.latitude = Number(form.latitude);
    payload.longitude = Number(form.longitude);
  }
  return payload;
}

export function parsePoligonoTexto(texto) {
  const linhas = String(texto || "")
    .split(/\r?\n/)
    .map((linha) => linha.trim())
    .filter(Boolean);
  if (!linhas.length) return [];
  if (linhas.length < 3)
    throw new Error("O polígono deve possuir ao menos 3 vértices.");
  return linhas.map((linha, indice) => {
    const partes = linha.split(/[;,\s]+/).filter(Boolean);
    if (partes.length !== 2)
      throw new Error(`Vértice ${indice + 1}: use latitude, longitude.`);
    const latitude = Number(partes[0]);
    const longitude = Number(partes[1]);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90)
      throw new Error(`Vértice ${indice + 1}: latitude inválida.`);
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180)
      throw new Error(`Vértice ${indice + 1}: longitude inválida.`);
    return [longitude, latitude];
  });
}

export function formatarCep(valor) {
  const digitos = String(valor ?? "").replace(/\D/g, "").slice(0, 8);
  return digitos.length > 5
    ? `${digitos.slice(0, 5)}-${digitos.slice(5)}`
    : digitos;
}
