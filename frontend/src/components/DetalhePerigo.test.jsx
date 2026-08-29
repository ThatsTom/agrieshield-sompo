import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { DetalhePerigo } from "./DetalhePerigo";
import { fixtureExposicao } from "../test/fixtureExposicao";

const resumo = (perigo) =>
  fixtureExposicao.perigos.find((item) => item.perigo === perigo);
const detalhe = (perigo) =>
  ({
    TRAFEGABILIDADE: fixtureExposicao.detalhes_perigos.trafegabilidade,
    INCENDIO: fixtureExposicao.detalhes_perigos.incendio,
    INSTABILIDADE: fixtureExposicao.detalhes_perigos.instabilidade,
    TEMPESTADES: fixtureExposicao.detalhes_perigos.tempestades,
  })[perigo];

afterEach(cleanup);

describe("detalhamento reutilizável dos perigos", () => {
  it("expõe Incêndio / Propagação de Fogo com dados e intermediários do DTO", () => {
    render(
      <DetalhePerigo
        resumo={resumo("INCENDIO")}
        detalhe={detalhe("INCENDIO")}
      />,
    );
    const painel = screen
      .getByText("Incêndio / Propagação de Fogo")
      .closest("details");
    fireEvent.click(painel.querySelector(":scope > summary"));
    expect(painel).toHaveAttribute("open");
    expect(painel).toHaveTextContent("24/07/2026");
    expect(painel).toHaveTextContent("Temperatura máxima30,00 °C");
    expect(painel).toHaveTextContent("Umidade relativa média60,00%");
    expect(painel).toHaveTextContent("Vento médio diário2,00 m/s");
    expect(painel).toHaveTextContent("Dias desde chuva4 dia(s)");
    expect(painel).toHaveTextContent("Componente de temperatura0,60 / 1,00");
    expect(painel).toHaveTextContent("Índice base24,66 / 100");
    expect(painel).toHaveTextContent("Multiplicador de secura1,05×");
    expect(painel).toHaveTextContent("Índice diário23,46 / 100");
    expect(painel).toHaveTextContent(
      "Não detecta foco de incêndio e não representa probabilidade de sinistro",
    );
  });
  it("distingue o cálculo diário dos componentes da agregação de 90 dias", () => {
    render(
      <DetalhePerigo
        resumo={resumo("TEMPESTADES")}
        detalhe={{
          ...detalhe("TEMPESTADES"),
          agregacao_90d: {
            ...detalhe("TEMPESTADES").agregacao_90d,
            severidade: 33,
            frequencia: 40,
            duracao: 28.57,
            recorrencia: 20,
            indice_agregado: 31.71,
            classificacao: "ATENCAO",
          },
        }}
      />,
    );
    const painel = screen.getByText("Tempestades Severas").closest("details");
    expect(painel).toHaveTextContent(
      "Cálculo diário — dia de maior índice disponível",
    );
    expect(painel).toHaveTextContent("Índice diário16,00 / 100");
    expect(painel).toHaveTextContent("Agregação histórica de 90 dias");
    expect(painel).toHaveTextContent("Severidade33,00 / 100");
    expect(painel).toHaveTextContent("Frequência40,00 / 100");
    expect(painel).toHaveTextContent("Duração28,57 / 100");
    expect(painel).toHaveTextContent("Recorrência20,00 / 100");
    expect(painel).toHaveTextContent("Índice agregado final31,71 / 100");
  });
  it("explica Instabilidade sem transformar contexto topográfico em componente", () => {
    render(
      <DetalhePerigo
        resumo={resumo("INSTABILIDADE")}
        detalhe={detalhe("INSTABILIDADE")}
      />,
    );
    const painel = screen.getByText("Instabilidade").closest("details");
    expect(painel).toHaveTextContent("Declividade média SRTM7,70°");
    expect(painel).toHaveTextContent("Suscetibilidade topográfica25,80 / 100");
    expect(painel).toHaveTextContent(
      "Condição hídrica meteorológica interna50,00 / 100",
    );
    expect(painel).toHaveTextContent("Fator de ativação0,65 / 1,00");
    expect(painel).toHaveTextContent("posição topográfica relativa -1,46 m");
    expect(painel).toHaveTextContent(
      "não participa da fórmula de Instabilidade",
    );
    expect(painel).not.toHaveTextContent("MERIT");
  });
  it("usa Fator combinado vento–chuva e declara ausências metodológicas", () => {
    render(
      <DetalhePerigo
        resumo={resumo("TEMPESTADES")}
        detalhe={detalhe("TEMPESTADES")}
      />,
    );
    const painel = screen.getByText("Tempestades Severas").closest("details");
    expect(painel).toHaveTextContent("Vento médio diário2,00 m/s");
    expect(painel).toHaveTextContent("Precipitação diária10,00 mm");
    expect(painel).toHaveTextContent("Fator combinado vento–chuva0,80 / 1,00");
    expect(painel).toHaveTextContent("granizo, raios, rajadas");
    expect(painel).not.toHaveTextContent("fator de amplificação");
  });
  it("reflete proveniência Open-Meteo sem chamar vento de rajada", () => {
    const open = {
      ...detalhe("INCENDIO"),
      proveniencia: {
        ...detalhe("INCENDIO").proveniencia,
        fonte_meteorologica: "OPEN_METEO",
        dataset_meteorologico: "ERA5-Land",
        parametro_vento: "wind_speed_10m_mean",
        altura_vento_m: 10,
      },
    };
    render(<DetalhePerigo resumo={resumo("INCENDIO")} detalhe={open} />);
    const painel = screen
      .getByText("Incêndio / Propagação de Fogo")
      .closest("details");
    expect(painel).toHaveTextContent("Fonte meteorológicaOPEN_METEO");
    expect(painel).toHaveTextContent("Variável de ventowind_speed_10m_mean");
    expect(painel).toHaveTextContent(
      "Medição do ventoVento médio diário a 10,00 m",
    );
    expect(painel).not.toHaveTextContent("rajada");
  });
  it("não fabrica zero quando o maior dia está indisponível", () => {
    const semDia = {
      ...detalhe("INCENDIO"),
      dia_maior_indice: null,
      agregacao_90d: {
        ...detalhe("INCENDIO").agregacao_90d,
        indice_agregado: null,
        classificacao: null,
      },
    };
    const semResumo = {
      ...resumo("INCENDIO"),
      indice: null,
      classificacao: null,
      contribuicao: null,
    };
    render(<DetalhePerigo resumo={semResumo} detalhe={semDia} />);
    const painel = screen
      .getByText("Incêndio / Propagação de Fogo")
      .closest("details");
    expect(painel).toHaveTextContent(
      "Nenhum índice diário disponível na janela atual",
    );
    expect(painel).toHaveTextContent("Índice agregado finalNão disponível");
    expect(painel).not.toHaveTextContent("Índice agregado final0,00");
  });
  it("expõe Trafegabilidade com resultado, cálculo diário, pesos aplicados, limiar e proveniência do DTO, sem recalcular nada", () => {
    render(
      <DetalhePerigo
        resumo={resumo("TRAFEGABILIDADE")}
        detalhe={detalhe("TRAFEGABILIDADE")}
      />,
    );
    const painel = screen.getByText("Trafegabilidade").closest("details");
    expect(painel).not.toHaveAttribute("open");
    fireEvent.click(painel.querySelector(":scope > summary"));
    expect(painel).toHaveAttribute("open");
    expect(painel).toHaveTextContent(
      "Condições meteorológicas que podem dificultar a circulação e operação de máquinas.",
    );
    expect(painel).toHaveTextContent("Índice agregado0,00 / 100");
    expect(painel).toHaveTextContent("ClassificaçãoNORMAL");
    expect(painel).toHaveTextContent("Contribuição para o score0,00 pts");
    expect(painel).toHaveTextContent("Peso no índice25,00%");
    expect(painel).toHaveTextContent("21/07/2026");
    expect(painel).toHaveTextContent("Índice diário52,36 / 100");
    expect(painel).toHaveTextContent("Precipitação do dia40,00 mm");
    expect(painel).toHaveTextContent(
      "Precipitação acumulada recente / 3 dias60,00 mm",
    );
    expect(painel).toHaveTextContent(
      "Dias secos desde a última chuva relevante0 dia(s)",
    );
    expect(painel).toHaveTextContent("Componente do dia44,69 / 100");
    expect(painel).toHaveTextContent("Componente acumulado59,18 / 100");
    expect(painel).toHaveTextContent("Recuperação / secagem59,18 / 100");
    expect(painel).toHaveTextContent("Pesos aplicados");
    expect(painel).toHaveTextContent("Condição do dia35,00%");
    expect(painel).toHaveTextContent("Acúmulo recente45,00%");
    expect(painel).toHaveTextContent("Limiar de dia relevante25,00");
    expect(painel).toHaveTextContent(
      "A Trafegabilidade representa uma condição ambiental favorável ou desfavorável à operação de máquinas e não uma medição direta da condição física do solo.",
    );
    expect(painel).toHaveTextContent(
      "Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
    );
    expect(painel).not.toHaveTextContent("probabilidade de sinistro");
    expect(painel).not.toHaveTextContent("probabilidade de atolamento");
    expect(painel).not.toHaveTextContent("impossibilidade de circulação");
    expect(painel).not.toHaveTextContent("umidade real do solo");
  });
});
