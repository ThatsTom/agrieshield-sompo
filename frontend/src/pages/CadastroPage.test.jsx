import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const locationPickerMockState = vi.hoisted(() => ({
  onChange: null,
  onClear: null,
}));

vi.mock("../components/LocationPickerMap", () => ({
  LocationPickerMap: ({
    latitude,
    longitude,
    onChange,
    onClear,
    disabled,
  }) => {
    locationPickerMockState.onChange = onChange;
    locationPickerMockState.onClear = onClear;
    return (
      <div data-testid="location-picker" data-disabled={String(disabled)}>
        <button
          type="button"
          onClick={() => onChange(-23.12345678, -46.98765432)}
          disabled={disabled}
        >
          Simular clique no mapa
        </button>
        <button type="button" onClick={onClear} disabled={disabled}>
          Simular remoção do pino
        </button>
        <span>{`${latitude ?? ""},${longitude ?? ""}`}</span>
      </div>
    );
  },
}));

import { CadastroPage } from "./CadastroPage";

function respostaJson(payload, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => payload,
  };
}

function renderCadastro(fazenda) {
  return render(
    <CadastroPage
      fazenda={fazenda}
      setPage={vi.fn()}
      carregarFazendas={vi.fn().mockResolvedValue([])}
      showToast={vi.fn()}
      setSelected={vi.fn()}
      onDirtyChange={vi.fn()}
    />,
  );
}

function preencherEnderecoParaLocalizar() {
  fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "04236310" } });
  fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
    target: { value: "Rua Maria Santíssima" },
  });
  fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
  fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
  fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
  fireEvent.blur(screen.getByLabelText("Número ou Km"));
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CadastroPage — localização automática", () => {
  it("preenche e remove as coordenadas pelo pino do mapa", () => {
    vi.stubGlobal("fetch", vi.fn());
    renderCadastro();

    fireEvent.click(screen.getByRole("button", { name: "Simular clique no mapa" }));

    expect(screen.getByLabelText("Latitude")).toHaveValue(-23.1234568);
    expect(screen.getByLabelText("Longitude")).toHaveValue(-46.9876543);
    expect(screen.getByText(/Coordenadas definidas pelo pino no mapa/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Localizar pelo endereço" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Simular remoção do pino" }));

    expect(screen.getByLabelText("Latitude")).toHaveValue(null);
    expect(screen.getByLabelText("Longitude")).toHaveValue(null);
    expect(screen.getByRole("button", { name: "Localizar pelo endereço" })).toBeEnabled();
  });

  it("usa CEP e Número/Km para sugerir o par de coordenadas", async () => {
    const fetchMock = vi.fn(async (url, options) => {
      if (String(url).endsWith("/api/cep/01001000")) {
        return respostaJson({
          cep: "01001-000",
          logradouro: "Praça da Sé",
          bairro: "Sé",
          cidade: "São Paulo",
          uf: "SP",
          latitude: null,
          longitude: null,
        });
      }
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        expect(options.method).toBe("POST");
        expect(JSON.parse(options.body)).toMatchObject({
          cep: "01001000",
          logradouro: "Praça da Sé",
          numero_km: "100",
          cidade: "São Paulo",
          uf: "SP",
        });
        return respostaJson({
          encontrado: true,
          latitude: -23.55052,
          longitude: -46.633308,
          precisao: "numero",
          aviso: "Número confirmado; revise o ponto no mapa.",
          atribuicao: "© OpenStreetMap contributors",
        });
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByLabelText("CEP"), {
      target: { value: "01001000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));

    await waitFor(() => expect(screen.getByLabelText("Cidade")).toHaveValue("São Paulo"));
    fireEvent.change(screen.getByLabelText("Número ou Km"), {
      target: { value: "100" },
    });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toHaveValue(-23.55052);
      expect(screen.getByLabelText("Longitude")).toHaveValue(-46.633308);
    });
    expect(screen.getByText(/Número confirmado; revise o ponto no mapa/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).includes("/api/cep/"))).toHaveLength(1);

    fireEvent.change(screen.getByLabelText("Latitude"), {
      target: { value: "-23.6" },
    });
    expect(screen.getByLabelText("Latitude")).toHaveValue(-23.6);
    expect(screen.getByLabelText("Longitude")).toHaveValue(null);
    expect(screen.getByText(/Coordenadas ajustadas manualmente/)).toBeInTheDocument();
  });

  it("exige confirmação antes de salvar uma coordenada aproximada", async () => {
    const fetchMock = vi.fn(async (url) => {
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        return respostaJson({
          encontrado: true,
          latitude: -23.6098639,
          longitude: -46.5952919,
          precisao: "logradouro",
          requer_confirmacao: true,
          aviso: "Ponto aproximado pelo logradouro; confirme no mapa.",
          atribuicao: "© OpenStreetMap contributors",
        });
      }
      if (String(url).includes("/api/cep/")) {
        return respostaJson({
          cep: "04236-310",
          logradouro: "Rua Maria Santíssima",
          cidade: "São Paulo",
          uf: "SP",
        });
      }
      if (String(url).endsWith("/api/fazendas")) {
        return respostaJson({ id: 42, latitude: -23.6098639, longitude: -46.5952919 });
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda confirmação" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "100" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-200" },
    });
    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Confirmar este ponto" })).toBeEnabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));

    await waitFor(() => {
      expect(screen.getByText(/A sugestão é aproximada/)).toBeInTheDocument();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
      .toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Confirmar este ponto" }));
    expect(screen.queryByRole("button", { name: "Confirmar este ponto" }))
      .not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
        .toBe(true);
    });
  });

  it("preserva a confirmação quando uma nova consulta da sugestão aproximada falha", async () => {
    let consultasGeocodificacao = 0;
    const fetchMock = vi.fn(async (url) => {
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        consultasGeocodificacao += 1;
        if (consultasGeocodificacao === 1) {
          return respostaJson({
            encontrado: true,
            latitude: -23.6098639,
            longitude: -46.5952919,
            precisao: "logradouro",
            requer_confirmacao: true,
            aviso: "Ponto aproximado; confirme no mapa.",
          });
        }
        return respostaJson(
          { detail: "Serviço de localização temporariamente indisponível." },
          { ok: false, status: 502 },
        );
      }
      if (String(url).includes("/api/cep/")) {
        return respostaJson({
          cep: "04236-310",
          logradouro: "Rua Maria Santíssima",
          cidade: "São Paulo",
          uf: "SP",
        });
      }
      if (String(url).endsWith("/api/fazendas")) {
        return respostaJson({ id: 42 });
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda confirmação preservada" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "100" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-201" },
    });
    preencherEnderecoParaLocalizar();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Confirmar este ponto" })).toBeEnabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Localizar pelo endereço" }));
    await waitFor(() => expect(consultasGeocodificacao).toBe(2));
    expect(screen.getByRole("button", { name: "Confirmar este ponto" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));
    await waitFor(() => {
      expect(screen.getByText(/A sugestão é aproximada/)).toBeInTheDocument();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
      .toBe(false);
  });

  it("exige confirmação para coordenadas de referência devolvidas pelo CEP", async () => {
    const fetchMock = vi.fn(async (url) => {
      if (String(url).endsWith("/api/cep/78890000")) {
        return respostaJson({
          cep: "78890-000",
          logradouro: "Rodovia MT-242",
          cidade: "Sorriso",
          uf: "MT",
          latitude: -12.545,
          longitude: -55.721,
        });
      }
      if (String(url).endsWith("/api/fazendas")) {
        return respostaJson({ id: 43 });
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda referência CEP" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "100" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-202" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "78890000" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toHaveValue(-12.545);
      expect(screen.getByLabelText("Longitude")).toHaveValue(-55.721);
    });
    expect(screen.getByRole("button", { name: "Confirmar este ponto" })).toBeEnabled();
    expect(screen.getByText(/Endereço preenchido pelo ViaCEP; coordenadas de referência/))
      .toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Complemento"), {
      target: { value: "Galpão principal" },
    });
    expect(screen.getByRole("button", { name: "Confirmar este ponto" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));
    await waitFor(() => {
      expect(screen.getByText(/A sugestão é aproximada/)).toBeInTheDocument();
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
      .toBe(false);
  });

  it("explica quando os provedores não retornam coordenadas compatíveis", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaJson({
      encontrado: false,
      latitude: null,
      longitude: null,
      motivo: "sem_coordenadas_compativeis",
      aviso: "Não encontramos coordenadas compatíveis com este endereço. Posicione o pino no mapa.",
    })));
    renderCadastro();

    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByText(/Não encontramos coordenadas compatíveis/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Latitude")).toHaveValue(null);
    expect(screen.getByLabelText("Longitude")).toHaveValue(null);
  });

  it("não transforma coordenadas nulas de uma resposta inconsistente em zero", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaJson({
      encontrado: true,
      latitude: null,
      longitude: null,
      aviso: "Resposta sem coordenadas válidas.",
    })));
    renderCadastro();

    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByText(/Resposta sem coordenadas válidas/)).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Latitude")).toHaveValue(null);
    expect(screen.getByLabelText("Longitude")).toHaveValue(null);
  });

  it("trata uma resposta 200 malformada sem expor erro técnico", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaJson(null)));
    renderCadastro();

    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByText(/Endereço não localizado automaticamente/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Cannot read properties/)).not.toBeInTheDocument();
  });

  it("mantém uma mensagem amigável quando a rede falha", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new Error("Failed to fetch");
    }));
    renderCadastro();

    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByText(/A localização automática está indisponível/))
        .toBeInTheDocument();
    });
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();
  });

  it("mostra o motivo devolvido pelo backend quando os provedores estão indisponíveis", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => respostaJson(
      { detail: "Não foi possível consultar a localização automática agora." },
      { ok: false, status: 502 },
    )));
    renderCadastro();

    preencherEnderecoParaLocalizar();

    await waitFor(() => {
      expect(screen.getByText(/Não foi possível consultar a localização automática agora/))
        .toBeInTheDocument();
    });
    expect(screen.getByText(/Posicione o pino no mapa ou tente novamente/)).toBeInTheDocument();
  });

  it("ignora resposta atrasada de um CEP que já foi substituído", async () => {
    vi.useFakeTimers();
    let resolverPrimeiro;
    let resolverSegundo;
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => new Promise((resolve) => { resolverPrimeiro = resolve; }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolverSegundo = resolve; }));
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "70040900" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));

    await act(async () => {
      resolverSegundo(respostaJson({
        cep: "70040-900",
        logradouro: "Praça dos Três Poderes",
        cidade: "Brasília",
        uf: "DF",
      }));
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Cidade")).toHaveValue("Brasília");

    await act(async () => {
      resolverPrimeiro(respostaJson({
        cep: "01001-000",
        logradouro: "Praça da Sé",
        cidade: "São Paulo",
        uf: "SP",
      }));
      await Promise.resolve();
    });
    expect(screen.getByLabelText("CEP")).toHaveValue("70040-900");
    expect(screen.getByLabelText("Cidade")).toHaveValue("Brasília");
  });

  it("descarta endereço e número antigos mesmo em trocas rápidas de CEP", async () => {
    const fetchMock = vi.fn(async (url) => {
      if (String(url).endsWith("/api/cep/01001000")) {
        return respostaJson({
          cep: "01001-000",
          logradouro: "Praça da Sé",
          cidade: "São Paulo",
          uf: "SP",
        });
      }
      if (String(url).endsWith("/api/cep/30140071")) {
        return respostaJson({
          cep: "30140-071",
          logradouro: "Avenida Afonso Pena",
          cidade: "Belo Horizonte",
          uf: "MG",
        });
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));
    await waitFor(() => expect(screen.getByLabelText("Cidade")).toHaveValue("São Paulo"));

    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Endereço ajustado manualmente" },
    });
    fireEvent.change(screen.getByLabelText("Número ou Km"), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "70040900" } });
    expect(screen.getByLabelText("Número ou Km")).toHaveValue("");

    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Endereço temporário do CEP intermediário" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "30140071" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Logradouro ou rodovia"))
        .toHaveValue("Avenida Afonso Pena");
      expect(screen.getByLabelText("Cidade")).toHaveValue("Belo Horizonte");
      expect(screen.getByLabelText("Estado ou UF")).toHaveValue("MG");
    });
  });

  it("não deixa uma sugestão pendente sobrescrever coordenadas manuais", async () => {
    vi.useFakeTimers();
    let resolverGeocodificacao;
    const fetchMock = vi.fn(
      () => new Promise((resolve) => { resolverGeocodificacao = resolve; }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Praça da Sé" },
    });
    fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
    fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));

    await act(async () => { await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText("Latitude"), { target: { value: "-22.9" } });
    fireEvent.change(screen.getByLabelText("Longitude"), { target: { value: "-43.2" } });

    await act(async () => {
      resolverGeocodificacao(respostaJson({
        encontrado: true,
        latitude: -23.55052,
        longitude: -46.633308,
      }));
      await Promise.resolve();
    });

    expect(screen.getByLabelText("Latitude")).toHaveValue(-22.9);
    expect(screen.getByLabelText("Longitude")).toHaveValue(-43.2);
    expect(screen.getByText(/Coordenadas ajustadas manualmente/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Localizar pelo endereço" })).toBeDisabled();
  });

  it("não deixa uma sugestão pendente sobrescrever o pino colocado no mapa", async () => {
    let resolverGeocodificacao;
    const fetchMock = vi.fn(
      () => new Promise((resolve) => { resolverGeocodificacao = resolve; }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Praça da Sé" },
    });
    fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
    fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));

    await act(async () => { await Promise.resolve(); });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Simular clique no mapa" }));

    await act(async () => {
      resolverGeocodificacao(respostaJson({
        encontrado: true,
        latitude: -23.55052,
        longitude: -46.633308,
      }));
      await Promise.resolve();
    });

    expect(screen.getByLabelText("Latitude")).toHaveValue(-23.1234568);
    expect(screen.getByLabelText("Longitude")).toHaveValue(-46.9876543);
    expect(screen.getByText(/Coordenadas definidas pelo pino no mapa/)).toBeInTheDocument();
  });

  it("aguarda a geocodificação pendente antes de salvar a fazenda", async () => {
    let resolverGeocodificacao;
    const fetchMock = vi.fn((url) => {
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        return new Promise((resolve) => { resolverGeocodificacao = resolve; });
      }
      if (String(url).endsWith("/api/fazendas")) {
        return Promise.resolve(respostaJson({ id: 42, latitude: 0, longitude: 0 }));
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda teste" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "150" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-100" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Praça da Sé" },
    });
    fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
    fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));

    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
      .toBe(false);

    await act(async () => {
      resolverGeocodificacao(respostaJson({
        encontrado: true,
        latitude: -23.55052,
        longitude: -46.633308,
        precisao: "numero",
      }));
      await Promise.resolve();
    });

    await waitFor(() => {
      const chamadaSalvar = fetchMock.mock.calls.find(
        ([url]) => String(url).endsWith("/api/fazendas"),
      );
      expect(chamadaSalvar).toBeTruthy();
      expect(JSON.parse(chamadaSalvar[1].body)).toMatchObject({
        latitude: -23.55052,
        longitude: -46.633308,
      });
    });
  });

  it("ignora uma consulta de CEP atrasada quando o salvamento já começou", async () => {
    let resolverCep;
    let resolverGeocodificacao;
    const fetchMock = vi.fn((url) => {
      if (String(url).endsWith("/api/cep/01001000")) {
        return new Promise((resolve) => { resolverCep = resolve; });
      }
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        return new Promise((resolve) => { resolverGeocodificacao = resolve; });
      }
      if (String(url).endsWith("/api/fazendas")) {
        return Promise.resolve(respostaJson({ id: 42, latitude: 0, longitude: 0 }));
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda manual" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "150" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-100" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.click(screen.getByRole("button", { name: "Buscar CEP" }));
    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Endereço informado manualmente" },
    });
    fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
    fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));

    await act(async () => {
      resolverCep(respostaJson({
        cep: "01001-000",
        logradouro: "Praça da Sé",
        cidade: "São Paulo",
        uf: "SP",
      }));
      await Promise.resolve();
    });
    expect(screen.getByLabelText("Logradouro ou rodovia"))
      .toHaveValue("Endereço informado manualmente");

    await act(async () => {
      resolverGeocodificacao(respostaJson({
        encontrado: true,
        latitude: -23.55052,
        longitude: -46.633308,
      }));
      await Promise.resolve();
    });

    await waitFor(() => {
      const chamadaSalvar = fetchMock.mock.calls.find(
        ([url]) => String(url).endsWith("/api/fazendas"),
      );
      expect(chamadaSalvar).toBeTruthy();
      expect(JSON.parse(chamadaSalvar[1].body)).toMatchObject({
        logradouro: "Endereço informado manualmente",
        latitude: -23.55052,
        longitude: -46.633308,
      });
    });
    expect(fetchMock.mock.calls.filter(
      ([url]) => String(url).endsWith("/api/geocodificacao/endereco"),
    )).toHaveLength(1);
  });

  it("bloqueia edição e não salva após desmontar durante a localização", async () => {
    const fetchMock = vi.fn((url) => {
      if (String(url).endsWith("/api/geocodificacao/endereco")) {
        return new Promise(() => {});
      }
      if (String(url).endsWith("/api/fazendas")) {
        return Promise.resolve(respostaJson({ id: 42, latitude: 0, longitude: 0 }));
      }
      throw new Error(`URL inesperada: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const tela = renderCadastro();

    fireEvent.change(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança"), {
      target: { value: "Fazenda cancelada" },
    });
    fireEvent.change(screen.getByPlaceholderText("250"), { target: { value: "150" } });
    fireEvent.change(screen.getByPlaceholderText("1234567890"), {
      target: { value: "AP-100" },
    });
    fireEvent.change(screen.getByLabelText("CEP"), { target: { value: "01001000" } });
    fireEvent.change(screen.getByLabelText("Logradouro ou rodovia"), {
      target: { value: "Praça da Sé" },
    });
    fireEvent.change(screen.getByLabelText("Cidade"), { target: { value: "São Paulo" } });
    fireEvent.change(screen.getByLabelText("Estado ou UF"), { target: { value: "SP" } });
    fireEvent.change(screen.getByLabelText("Número ou Km"), { target: { value: "100" } });
    fireEvent.blur(screen.getByLabelText("Número ou Km"));
    fireEvent.click(screen.getByRole("button", { name: "Salvar fazenda" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Ex.: Fazenda Boa Esperança")).toBeDisabled();
      expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
      expect(screen.getByRole("button", { name: /Voltar/ })).toBeDisabled();
    });

    tela.unmount();
    await act(async () => { await Promise.resolve(); });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/api/fazendas")))
      .toBe(false);
  });

  it("ignora eventos atrasados do mapa depois que o salvamento começa", async () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro({
      id: "9",
      nome_fazenda: "Fazenda existente",
      numero_apolice: "123",
      area_ha: 100,
      cep: "01001-000",
      logradouro: "Praça da Sé",
      numero_km: "100",
      bairro: "Sé",
      cidade: "São Paulo",
      uf: "SP",
      latitude: -23.55052,
      longitude: -46.633308,
      tipo_operacao: "campo",
      proximidade_agua: false,
    });

    fireEvent.click(screen.getByRole("button", { name: "Salvar alterações" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    act(() => {
      locationPickerMockState.onChange(-12.5, -55.7);
      locationPickerMockState.onClear();
    });

    expect(screen.getByLabelText("Latitude")).toHaveValue(-23.55052);
    expect(screen.getByLabelText("Longitude")).toHaveValue(-46.633308);
  });

  it("não consulta nem altera automaticamente uma fazenda existente ao montar", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderCadastro({
      id: "9",
      nome_fazenda: "Fazenda existente",
      numero_apolice: "123",
      area_ha: 100,
      cep: "01001-000",
      logradouro: "Praça da Sé",
      numero_km: "100",
      bairro: "Sé",
      cidade: "São Paulo",
      uf: "SP",
      latitude: -23.55052,
      longitude: -46.633308,
      tipo_operacao: "campo",
      proximidade_agua: false,
    });

    await act(async () => {
      vi.advanceTimersByTime(1000);
      await Promise.resolve();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Latitude")).toHaveValue(-23.55052);
    expect(screen.getByRole("button", { name: "Localizar pelo endereço" })).toBeDisabled();
  });
});
