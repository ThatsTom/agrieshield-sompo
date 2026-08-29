import { describe, expect, it } from "vitest";
import { prepararMapaGeoespacial } from "./GeoAnalysisMap";

describe("mapa geoespacial", () => {
  it("distingue raio analisado, polígono cadastrado e drenagem", () => {
    const dados = prepararMapaGeoespacial(
      {
        latitude_referencia: -12.545,
        longitude_referencia: -55.721,
        raio_analise_m: 1000,
        raio_busca_drenagem_m: 50000,
        qualidade: { pixel_drenagem: { latitude: -12.53, longitude: -55.70 } },
      },
      {
        poligono: [[-55.72, -12.54], [-55.71, -12.55], [-55.73, -12.56]],
      },
    );
    expect(dados.valido).toBe(true);
    expect(dados.raioAnaliseM).toBe(1000);
    expect(dados.raioDrenagemM).toBe(50000);
    expect(dados.poligono[0]).toEqual([-12.54, -55.72]);
    expect(dados.drenagem).toEqual([-12.53, -55.7]);
  });

  it("usa coordenada cadastral e reconhece ausência de localização", () => {
    expect(prepararMapaGeoespacial(null, { latitude: -23, longitude: -51 }).valido).toBe(true);
    expect(prepararMapaGeoespacial(null, { latitude: 0, longitude: 0 }).valido).toBe(false);
  });

  it("preserva as coordenadas exatas da drenagem para ancoragem no mapa", () => {
    const dados = prepararMapaGeoespacial(
      {
        latitude_referencia: -23,
        longitude_referencia: -51,
        qualidade: { pixel_drenagem: { latitude: "-22.998765", longitude: "-50.991234" } },
      },
      {},
    );

    expect(dados.drenagem).toEqual([-22.998765, -50.991234]);
  });
});
