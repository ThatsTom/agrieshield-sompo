import { useEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { numero } from "../utils/format";

export function prepararMapaGeoespacial(geo, fazenda) {
  const latitude = Number(geo?.latitude_referencia ?? fazenda?.latitude);
  const longitude = Number(geo?.longitude_referencia ?? fazenda?.longitude);
  const poligono = (fazenda?.poligono || [])
    .map(([lon, lat]) => [Number(lat), Number(lon)])
    .filter(([lat, lon]) => Number.isFinite(lat) && Number.isFinite(lon));
  const drenagem = geo?.qualidade?.pixel_drenagem;

  return {
    latitude,
    longitude,
    valido:
      Number.isFinite(latitude) &&
      Number.isFinite(longitude) &&
      (latitude !== 0 || longitude !== 0),
    raioAnaliseM: Number(geo?.raio_analise_m) || 1000,
    raioEquivalenteM: Number(geo?.raio_equivalente_m) || null,
    raioDrenagemM: Number(geo?.raio_busca_drenagem_m) || null,
    poligono,
    drenagem:
      drenagem && Number.isFinite(Number(drenagem.latitude)) && Number.isFinite(Number(drenagem.longitude))
        ? [Number(drenagem.latitude), Number(drenagem.longitude)]
        : null,
  };
}

export function GeoAnalysisMap({ geo, fazenda }) {
  const elemento = useRef(null);
  const mapa = useRef(null);
  const dados = useMemo(
    () => prepararMapaGeoespacial(geo, fazenda),
    [geo, fazenda],
  );

  useEffect(() => {
    if (!dados.valido || !elemento.current) return undefined;

    const instancia = L.map(elemento.current, {
      scrollWheelZoom: true,
      zoomControl: true,
    }).setView([dados.latitude, dados.longitude], 14);
    mapa.current = instancia;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instancia);
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(instancia);

    const camadasParaEnquadrar = [];
    const areaAnalise = L.circle([dados.latitude, dados.longitude], {
      radius: dados.raioAnaliseM,
      color: "#d71920",
      weight: 2,
      dashArray: "7 5",
      fillColor: "#d71920",
      fillOpacity: 0.09,
    })
      .addTo(instancia)
      .bindTooltip(`Área analisada: raio de ${numero(dados.raioAnaliseM, 0)} m`);
    camadasParaEnquadrar.push(areaAnalise);

    const sede = L.circleMarker([dados.latitude, dados.longitude], {
      radius: 7,
      color: "#fff",
      weight: 3,
      fillColor: "#17243b",
      fillOpacity: 1,
    })
      .addTo(instancia)
      .bindTooltip("Sede", {
        permanent: true,
        direction: "top",
        className: "geo-map-fixed-label geo-map-headquarters-label",
        offset: [0, -8],
      });
    camadasParaEnquadrar.push(sede);

    if (dados.poligono.length >= 3) {
      const perimetro = L.polygon(dados.poligono, {
        color: "#2563c9",
        weight: 2,
        fillColor: "#2563c9",
        fillOpacity: 0.12,
      })
        .addTo(instancia)
        .bindTooltip("Perímetro cadastrado da fazenda");
      camadasParaEnquadrar.push(perimetro);
    } else if (dados.raioEquivalenteM) {
      const equivalente = L.circle([dados.latitude, dados.longitude], {
        radius: dados.raioEquivalenteM,
        color: "#238f53",
        weight: 2,
        fillOpacity: 0,
      })
        .addTo(instancia)
        .bindTooltip("Círculo equivalente estimado pela área cadastrada");
      camadasParaEnquadrar.push(equivalente);
    }

    if (dados.drenagem) {
      const pontoDrenagem = L.circleMarker(dados.drenagem, {
        radius: 7,
        color: "#fff",
        weight: 3,
        fillColor: "#00a6c8",
        fillOpacity: 1,
      })
        .addTo(instancia)
        .bindTooltip("Drenagem MERIT", {
          permanent: true,
          direction: "top",
          className: "geo-map-fixed-label geo-map-drainage-label",
          offset: [0, -8],
        });
      camadasParaEnquadrar.push(pontoDrenagem);
    }

    const grupo = L.featureGroup(camadasParaEnquadrar);
    if (grupo.getBounds().isValid()) {
      instancia.fitBounds(grupo.getBounds().pad(0.18), { maxZoom: 16 });
    }
    window.setTimeout(() => instancia.invalidateSize(), 0);

    return () => {
      instancia.remove();
      if (mapa.current === instancia) mapa.current = null;
    };
  }, [dados]);

  if (!dados.valido) {
    return <div className="geo-map-empty">Coordenadas indisponíveis para o mapa.</div>;
  }

  return (
    <div className="geo-analysis-map-card">
      <div
        ref={elemento}
        className="geo-map-canvas"
        aria-label="Mapa da área de análise geoespacial"
        role="region"
      />
      <div className="geo-map-legend">
        <span><i className="legend-analysis" /> Área efetivamente analisada ({numero(dados.raioAnaliseM, 0)} m)</span>
        <span><i className="legend-property" /> {dados.poligono.length >= 3 ? "Perímetro cadastrado" : "Área equivalente estimada"}</span>
        <span><i className="legend-center" /> Sede / referência</span>
        {dados.drenagem && <span><i className="legend-drainage" /> Drenagem MERIT</span>}
      </div>
      <div className="geo-map-note">
        <b>Escopo da leitura:</b> SRTM no entorno de {numero(dados.raioAnaliseM, 0)} m.
        {dados.raioDrenagemM && <> Busca de drenagem MERIT limitada a {numero(dados.raioDrenagemM / 1000, 0)} km.</>}
        {dados.drenagem && (
          <> Ponto MERIT lido em <b>{dados.drenagem[0].toFixed(6)}, {dados.drenagem[1].toFixed(6)}</b>; o marcador acompanha essas coordenadas durante zoom e deslocamento.</>
        )}
        {dados.poligono.length >= 3 && <> O polígono azul é referência cadastral e ainda não substitui o círculo vermelho no processamento atual.</>}
      </div>
    </div>
  );
}
