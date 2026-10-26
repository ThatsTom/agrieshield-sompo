import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const CENTRO_BRASIL = [-14.235, -51.9253];

export function normalizarPontoMapa(latitude, longitude) {
  if (
    String(latitude ?? "").trim() === ""
    || String(longitude ?? "").trim() === ""
  ) return null;
  const lat = Number(latitude);
  const lon = Number(longitude);
  if (
    !Number.isFinite(lat)
    || !Number.isFinite(lon)
    || lat < -90
    || lat > 90
    || lon < -180
    || lon > 180
    || (lat === 0 && lon === 0)
  ) return null;
  return { latitude: lat, longitude: lon };
}

const ICONE_PINO = L.divIcon({
  className: "farm-location-marker",
  html: '<span class="farm-location-pin" aria-hidden="true"></span>',
  iconSize: [34, 42],
  iconAnchor: [17, 41],
  tooltipAnchor: [0, -34],
});

export function LocationPickerMap({
  latitude,
  longitude,
  onChange,
  onClear,
  disabled = false,
}) {
  const elementoRef = useRef(null);
  const mapaRef = useRef(null);
  const marcadorRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const disabledRef = useRef(disabled);
  const ponto = useMemo(
    () => normalizarPontoMapa(latitude, longitude),
    [latitude, longitude],
  );
  const pontoInicialRef = useRef(ponto);

  useLayoutEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  useLayoutEffect(() => {
    disabledRef.current = disabled;
    const dragging = marcadorRef.current?.dragging;
    if (!dragging) return;
    if (disabled) dragging.disable();
    else dragging.enable();
  }, [disabled]);

  useEffect(() => {
    if (!elementoRef.current) return undefined;
    const inicial = pontoInicialRef.current;
    const instancia = L.map(elementoRef.current, {
      scrollWheelZoom: true,
      zoomControl: true,
      keyboard: true,
    }).setView(
      inicial ? [inicial.latitude, inicial.longitude] : CENTRO_BRASIL,
      inicial ? 15 : 4,
    );
    mapaRef.current = instancia;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instancia);
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(instancia);

    const selecionarPonto = (evento) => {
      if (disabledRef.current || !evento?.latlng) return;
      const selecionado = normalizarPontoMapa(evento.latlng.lat, evento.latlng.lng);
      if (selecionado) {
        onChangeRef.current?.(selecionado.latitude, selecionado.longitude);
      }
    };
    instancia.on("click", selecionarPonto);
    const timer = window.setTimeout(() => instancia.invalidateSize(), 0);

    return () => {
      window.clearTimeout(timer);
      instancia.off("click", selecionarPonto);
      instancia.remove();
      mapaRef.current = null;
      marcadorRef.current = null;
    };
  }, []);

  useEffect(() => {
    const instancia = mapaRef.current;
    if (!instancia) return;
    if (!ponto) {
      if (marcadorRef.current) {
        marcadorRef.current.remove();
        marcadorRef.current = null;
      }
      return;
    }

    const latLng = [ponto.latitude, ponto.longitude];
    if (!marcadorRef.current) {
      const marcador = L.marker(latLng, {
        draggable: !disabledRef.current,
        autoPan: true,
        keyboard: false,
        icon: ICONE_PINO,
        title: "Sede da fazenda",
        alt: "Pino da sede da fazenda",
      })
        .addTo(instancia)
        .bindTooltip("Sede da fazenda · arraste para ajustar", {
          direction: "top",
          offset: [0, -32],
        });
      marcador.on("dragend", () => {
        if (disabledRef.current) return;
        const posicao = marcador.getLatLng();
        const selecionado = normalizarPontoMapa(posicao.lat, posicao.lng);
        if (selecionado) {
          onChangeRef.current?.(selecionado.latitude, selecionado.longitude);
        }
      });
      marcadorRef.current = marcador;
    } else {
      marcadorRef.current.setLatLng(latLng);
    }
    instancia.setView(latLng, Math.max(instancia.getZoom(), 15), {
      animate: false,
    });
  }, [ponto]);

  return (
    <div className={`location-picker${disabled ? " is-disabled" : ""}`}>
      <div className="location-picker-stage">
        <div className="location-picker-instruction" aria-hidden="true">
          Clique ou toque para posicionar · arraste o pino para ajustar
        </div>
        <div
          ref={elementoRef}
          className="location-picker-map"
          role="region"
          aria-label="Mapa para selecionar a sede da fazenda"
          aria-describedby="location-picker-help"
          aria-disabled={disabled}
        />
      </div>
      <div className="location-picker-footer" aria-live="polite">
        <span>
          {ponto
            ? `Pino em ${ponto.latitude.toFixed(7)}, ${ponto.longitude.toFixed(7)}`
            : "Nenhum pino definido. Navegue pelo mapa e clique no local da sede."}
        </span>
        <div className="location-picker-actions">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => {
              const centro = mapaRef.current?.getCenter();
              const selecionado = normalizarPontoMapa(centro?.lat, centro?.lng);
              if (!disabled && selecionado) {
                onChangeRef.current?.(selecionado.latitude, selecionado.longitude);
              }
            }}
            disabled={disabled}
          >
            Fixar pino no centro
          </button>
          {ponto && (
            <button
              type="button"
              className="btn btn-ghost"
              onClick={onClear}
              disabled={disabled}
            >
              Remover pino
            </button>
          )}
        </div>
      </div>
      <p id="location-picker-help" className="location-picker-accessibility-note">
        Pelo teclado, foque o mapa, mova com as setas e use “Fixar pino no centro”.
        Como alternativa, preencha latitude e longitude nos campos acima.
      </p>
    </div>
  );
}
