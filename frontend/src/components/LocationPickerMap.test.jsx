import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

const leafletState = vi.hoisted(() => ({
  mapHandlers: {},
  markerHandlers: {},
  mapInstance: null,
  markerInstance: null,
}));

vi.mock("leaflet", () => {
  const map = vi.fn(() => {
    const instance = {
      setView: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      remove: vi.fn(),
      invalidateSize: vi.fn(),
      getZoom: vi.fn(() => 12),
      getCenter: vi.fn(() => ({ lat: -15.1, lng: -47.2 })),
    };
    instance.setView.mockImplementation(() => instance);
    instance.on.mockImplementation((event, handler) => {
      leafletState.mapHandlers[event] = handler;
      return instance;
    });
    instance.off.mockImplementation(() => instance);
    leafletState.mapInstance = instance;
    return instance;
  });

  const marker = vi.fn((latLng) => {
    let current = { lat: latLng[0], lng: latLng[1] };
    const instance = {
      addTo: vi.fn(),
      bindTooltip: vi.fn(),
      on: vi.fn(),
      getLatLng: vi.fn(() => current),
      setLatLng: vi.fn(),
      remove: vi.fn(),
      dragging: {
        enable: vi.fn(),
        disable: vi.fn(),
      },
      setMockLatLng(lat, lng) {
        current = { lat, lng };
      },
    };
    instance.addTo.mockImplementation(() => instance);
    instance.bindTooltip.mockImplementation(() => instance);
    instance.on.mockImplementation((event, handler) => {
      leafletState.markerHandlers[event] = handler;
      return instance;
    });
    instance.setLatLng.mockImplementation((next) => {
      current = { lat: next[0], lng: next[1] };
      return instance;
    });
    leafletState.markerInstance = instance;
    return instance;
  });

  return {
    default: {
      map,
      marker,
      tileLayer: vi.fn(() => ({ addTo: vi.fn() })),
      control: {
        scale: vi.fn(() => ({ addTo: vi.fn() })),
      },
      divIcon: vi.fn((config) => config),
    },
  };
});

import L from "leaflet";
import { LocationPickerMap, normalizarPontoMapa } from "./LocationPickerMap";

beforeEach(() => {
  Object.keys(leafletState.mapHandlers).forEach((key) => {
    delete leafletState.mapHandlers[key];
  });
  Object.keys(leafletState.markerHandlers).forEach((key) => {
    delete leafletState.markerHandlers[key];
  });
  leafletState.mapInstance = null;
  leafletState.markerInstance = null;
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("normalizarPontoMapa", () => {
  it("aceita somente pares válidos e diferentes de zero", () => {
    expect(normalizarPontoMapa("-23.5", "-46.6")).toEqual({
      latitude: -23.5,
      longitude: -46.6,
    });
    expect(normalizarPontoMapa("", "-46.6")).toBeNull();
    expect(normalizarPontoMapa(-91, -46.6)).toBeNull();
    expect(normalizarPontoMapa(-23.5, 181)).toBeNull();
    expect(normalizarPontoMapa(0, 0)).toBeNull();
  });
});

describe("LocationPickerMap", () => {
  it("permite escolher o ponto por clique e pelo centro do mapa", () => {
    const onChange = vi.fn();
    render(
      <LocationPickerMap
        latitude=""
        longitude=""
        onChange={onChange}
        onClear={vi.fn()}
      />,
    );

    expect(L.map).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ scrollWheelZoom: true, zoomControl: true }),
    );

    act(() => {
      leafletState.mapHandlers.click({ latlng: { lat: -12.5, lng: -55.7 } });
    });
    expect(onChange).toHaveBeenCalledWith(-12.5, -55.7);

    fireEvent.click(screen.getByRole("button", { name: "Fixar pino no centro" }));
    expect(onChange).toHaveBeenLastCalledWith(-15.1, -47.2);
  });

  it("cria um pino arrastável e envia a posição final", () => {
    const onChange = vi.fn();
    render(
      <LocationPickerMap
        latitude={-23.5}
        longitude={-46.6}
        onChange={onChange}
        onClear={vi.fn()}
      />,
    );

    expect(L.marker).toHaveBeenCalledWith(
      [-23.5, -46.6],
      expect.objectContaining({ draggable: true, keyboard: false }),
    );
    leafletState.markerInstance.setMockLatLng(-23.6, -46.7);
    act(() => {
      leafletState.markerHandlers.dragend();
    });
    expect(onChange).toHaveBeenCalledWith(-23.6, -46.7);
  });

  it("sincroniza coordenadas externas sem recriar o mapa", () => {
    const tela = render(
      <LocationPickerMap
        latitude={-23.5}
        longitude={-46.6}
        onChange={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const primeiroMarcador = leafletState.markerInstance;

    tela.rerender(
      <LocationPickerMap
        latitude={-22.9}
        longitude={-43.2}
        onChange={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    expect(L.map).toHaveBeenCalledTimes(1);
    expect(primeiroMarcador.setLatLng).toHaveBeenCalledWith([-22.9, -43.2]);
  });

  it("bloqueia clique e arraste enquanto está desabilitado", () => {
    const onChange = vi.fn();
    const tela = render(
      <LocationPickerMap
        latitude={-23.5}
        longitude={-46.6}
        onChange={onChange}
        onClear={vi.fn()}
      />,
    );

    tela.rerender(
      <LocationPickerMap
        latitude={-23.5}
        longitude={-46.6}
        onChange={onChange}
        onClear={vi.fn()}
        disabled
      />,
    );
    expect(leafletState.markerInstance.dragging.disable).toHaveBeenCalled();

    act(() => {
      leafletState.mapHandlers.click({ latlng: { lat: -12.5, lng: -55.7 } });
      leafletState.markerInstance.setMockLatLng(-23.6, -46.7);
      leafletState.markerHandlers.dragend();
    });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Fixar pino no centro" })).toBeDisabled();
  });

  it("remove o pino e libera o mapa ao limpar as coordenadas", () => {
    const tela = render(
      <LocationPickerMap
        latitude={-23.5}
        longitude={-46.6}
        onChange={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const marcador = leafletState.markerInstance;

    tela.rerender(
      <LocationPickerMap
        latitude=""
        longitude=""
        onChange={vi.fn()}
        onClear={vi.fn()}
      />,
    );

    expect(marcador.remove).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Remover pino" })).not.toBeInTheDocument();
  });

  it("limpa os eventos e a instância do mapa ao desmontar", () => {
    const tela = render(
      <LocationPickerMap
        latitude=""
        longitude=""
        onChange={vi.fn()}
        onClear={vi.fn()}
      />,
    );
    const mapa = leafletState.mapInstance;
    const clique = leafletState.mapHandlers.click;

    tela.unmount();

    expect(mapa.off).toHaveBeenCalledWith("click", clique);
    expect(mapa.remove).toHaveBeenCalled();
  });
});
