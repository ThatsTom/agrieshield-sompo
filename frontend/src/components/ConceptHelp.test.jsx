import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ConceptHelp } from "./ConceptHelp";
import { conceitos } from "../content/conceitos";

afterEach(cleanup);
describe("ajuda contextual de conceitos", () => {
  it("mostra contexto resumido ao passar o mouse", () => {
    render(<ConceptHelp conceito="score_exposicao" />);
    const abrir = screen.getByRole("button", {
      name: "Ajuda: Score de Exposição",
    });
    fireEvent.mouseEnter(abrir.parentElement);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Índice consolidado de exposição",
    );
    fireEvent.mouseLeave(abrir.parentElement);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
  it("renderiza ícone, abre modal acessível e fecha pelo botão", () => {
    render(<ConceptHelp conceito="score_exposicao" />);
    const abrir = screen.getByRole("button", {
      name: "Ajuda: Score de Exposição",
    });
    fireEvent.click(abrir);
    const modal = screen.getByRole("dialog", { name: "Score de Exposição" });
    expect(modal).toHaveAttribute("aria-modal", "true");
    expect(modal).toHaveTextContent("Escala de 0 a 100");
    expect(modal).toHaveTextContent(
      "Não representa probabilidade atuarial de sinistro",
    );
    fireEvent.click(screen.getByRole("button", { name: "Fechar ajuda" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("fecha com Escape", () => {
    render(<ConceptHelp conceito="hidrico" />);
    fireEvent.click(screen.getByRole("button", { name: /Ajuda/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent(
      "suscetibilidade territorial",
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it.each([
    ["hidrico", "mesma agregação de 90 dias"],
    ["trafegabilidade", "metodologia meteorológica própria"],
    ["merit_distancia", "contexto hidrológico raster"],
    ["merit_area", "Área de contribuição hidrológica"],
    ["srtm", "Expressa em graus"],
    ["posicao_topografica", "Não representa profundidade de inundação"],
    ["open_meteo", "sem mistura de fontes"],
    ["peso_indice", "Peso único configurado"],
  ])("apresenta o conceito %s", (conceito, trecho) => {
    render(<ConceptHelp conceito={conceito} />);
    fireEvent.click(screen.getByRole("button", { name: /Ajuda/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent(trecho);
  });
  it("mantém o catálogo independente de fazendas", () => {
    expect(JSON.stringify(conceitos)).not.toMatch(
      /Boa Esperança|Embrapa|Santa Luzia|Três Rios/,
    );
  });
});
