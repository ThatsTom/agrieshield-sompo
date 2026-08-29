import { describe, expect, it } from "vitest";
import {
  formatarCep,
  montarPayloadFazenda,
  parsePoligonoTexto,
  validarCoordenadas,
} from "./fazenda";

const base = {
  nome_fazenda: "Fazenda Rural",
  numero_apolice: "123",
  cep: "86000-000",
  area_ha: "321.5",
  logradouro: "Rodovia Carlos João Strass",
  numero_km: "km 14",
  complemento: "Distrito de Warta",
  cidade: "Londrina",
  uf: "PR",
  referencia_acesso: "Entrada pela estrada municipal",
  latitude: "",
  longitude: "",
};

describe("cadastro rural", () => {
  it("formata o CEP sem aceitar caracteres extras", () => {
    expect(formatarCep("86085981")).toBe("86085-981");
    expect(formatarCep("86.085-981abc9")).toBe("86085-981");
  });
  it("converte vértices latitude/longitude para GeoJSON", () => {
    expect(parsePoligonoTexto("-12.5, -55.7\n-12.6, -55.7\n-12.6, -55.8"))
      .toEqual([[-55.7, -12.5], [-55.7, -12.6], [-55.8, -12.6]]);
  });
  it("rejeita polígono incompleto", () => {
    expect(() => parsePoligonoTexto("-12,-55\n-13,-55")).toThrow(
      "ao menos 3 vértices",
    );
  });
  it("mantém coordenadas opcionais e área em hectares", () => {
    const payload = montarPayloadFazenda(base);
    expect(payload).not.toHaveProperty("latitude");
    expect(payload).not.toHaveProperty("longitude");
    expect(payload.area_ha).toBe(321.5);
  });
  it("prioriza e converte o par manual sem alterar os campos rurais", () => {
    const payload = montarPayloadFazenda({
      ...base,
      latitude: "-23.5505",
      longitude: "-46.6333",
    });
    expect(payload.latitude).toBe(-23.5505);
    expect(payload.longitude).toBe(-46.6333);
    expect(payload.numero_km).toBe("km 14");
    expect(payload.referencia_acesso).toBe("Entrada pela estrada municipal");
  });
  it.each([
    ["-12", "", "Informe latitude e longitude juntas."],
    ["", "-55", "Informe latitude e longitude juntas."],
    ["-91", "-55", "Latitude deve estar entre -90 e 90."],
    ["-12", "181", "Longitude deve estar entre -180 e 180."],
    ["0", "0", "As coordenadas 0,0 não identificam uma localização válida."],
  ])("rejeita coordenadas inválidas", (lat, lon, mensagem) =>
    expect(validarCoordenadas(lat, lon)).toBe(mensagem),
  );
});
