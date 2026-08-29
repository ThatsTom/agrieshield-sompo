import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErroApiParametrosScore } from "../api/parametrosScore";
import { RiscosScore } from "./RiscosScore";
import { fixtureParametrosScore } from "../test/fixtureParametrosScore";

const renderizar = ({ buscar, salvar, showToast } = {}) =>
  render(
    <RiscosScore
      showToast={showToast || vi.fn()}
      buscar={buscar || (() => Promise.resolve(fixtureParametrosScore))}
      salvar={salvar || vi.fn()}
    />,
  );

afterEach(cleanup);

describe("tela Riscos e Score", () => {
  it("mostra os cinco indicadores com nome e descrição", async () => {
    renderizar();
    await screen.findByText("Indicadores");
    for (const nome of [
      "Exposição Hídrica",
      "Trafegabilidade",
      "Instabilidade",
      "Incêndio / Propagação de Fogo",
      "Tempestades Severas",
    ]) {
      expect(screen.getAllByText(nome).length).toBeGreaterThan(0);
    }
  });

  it("preenche os pesos atuais no topo e mostra o total geral", async () => {
    renderizar();
    const hidrica = await screen.findByLabelText(
      "Peso no índice — Exposição Hídrica",
    );
    expect(hidrica.value).toBe("30");
    expect(
      screen.getByLabelText("Peso no índice — Trafegabilidade").value,
    ).toBe("25");
    expect(screen.getByLabelText("Peso no índice — Instabilidade").value).toBe(
      "20",
    );
    expect(
      screen.getByLabelText("Peso no índice — Incêndio / Propagação de Fogo")
        .value,
    ).toBe("15");
    expect(
      screen.getByLabelText("Peso no índice — Tempestades Severas").value,
    ).toBe("10");
    expect(
      screen.getByText("Total geral").closest(".riscos-peso-total"),
    ).toHaveTextContent("100%");
  });

  it("mostra ajuda de conceito para Peso no índice", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(
      screen.getByRole("button", { name: "Ajuda: Peso no índice" }),
    );
    expect(screen.getByRole("dialog")).toHaveTextContent("Peso no índice");
  });

  it("exibe os parâmetros internos da Exposição Hídrica com total interno", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Exposição Hídrica", { selector: "h3" }));
    expect(screen.getByLabelText("Proximidade da drenagem").value).toBe("40");
    expect(screen.getByLabelText("Relevância da área montante").value).toBe(
      "35",
    );
    expect(screen.getByLabelText("Posição topográfica relativa").value).toBe(
      "25",
    );
    const blocoHidrico = screen
      .getByText("Exposição Hídrica", { selector: "h3" })
      .closest(".riscos-bloco-indicador");
    expect(
      within(blocoHidrico)
        .getByText("Total interno")
        .closest(".riscos-peso-total"),
    ).toHaveTextContent("100%");
  });

  it("exibe os fatores de ativação da Instabilidade como decimais, sem sinal de %", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Instabilidade", { selector: "h3" }));
    expect(screen.getByLabelText("Normal").value).toBe("0");
    expect(screen.getByLabelText("Atenção").value).toBe("0.35");
    expect(screen.getByLabelText("Alerta").value).toBe("0.65");
    expect(screen.getByLabelText("Crítico").value).toBe("1");
    const campo = screen
      .getByLabelText("Atenção")
      .closest(".riscos-peso-campo");
    expect(within(campo).queryByText("%")).not.toBeInTheDocument();
  });

  it("exibe os multiplicadores de secura do Incêndio", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(
      screen.getByText("Incêndio / Propagação de Fogo", { selector: "h3" }),
    );
    expect(screen.getByLabelText("0–1 dia").value).toBe("0.9");
    expect(screen.getByLabelText("2–3 dias").value).toBe("1");
    expect(screen.getByLabelText("4–6 dias").value).toBe("1.05");
    expect(screen.getByLabelText("7+ dias").value).toBe("1.1");
  });

  it("exibe o fator vento-chuva das Tempestades com os rótulos corretos", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(
      screen.getByText("Tempestades Severas", { selector: "h3" }),
    );
    expect(screen.getByLabelText("Base do fator vento–chuva").value).toBe(
      "0.75",
    );
    expect(screen.getByLabelText("Influência da chuva").value).toBe("0.25");
  });

  it("exibe os parâmetros internos da Trafegabilidade (composição + limiar) com total interno", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Trafegabilidade", { selector: "h3" }));
    const bloco = screen
      .getByText("Trafegabilidade", { selector: "h3" })
      .closest(".riscos-bloco-indicador");
    expect(
      within(bloco).queryByText(
        "Sem parâmetros internos configuráveis nesta versão.",
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Condição do dia atual").value).toBe("35");
    expect(screen.getByLabelText("Acúmulo recente").value).toBe("45");
    expect(screen.getByLabelText("Recuperação / secagem").value).toBe("20");
    expect(screen.getByLabelText("Limiar de dia relevante").value).toBe("25");
    expect(
      within(bloco).getByText("Total interno").closest(".riscos-peso-total"),
    ).toHaveTextContent("100%");
    const grid = bloco.querySelector(".riscos-bloco-grid");
    expect(grid).not.toHaveClass("riscos-bloco-grid--somente-explicacao");
    expect(grid.querySelector(".riscos-bloco-config")).toBeInTheDocument();
  });

  it("o limiar de dia relevante da Trafegabilidade não exibe sinal de %", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Trafegabilidade", { selector: "h3" }));
    const campo = screen
      .getByLabelText("Limiar de dia relevante")
      .closest(".riscos-peso-campo");
    expect(within(campo).queryByText("%")).not.toBeInTheDocument();
  });

  it("não altera o layout de dois blocos dos demais indicadores", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Exposição Hídrica", { selector: "h3" }));
    const bloco = screen
      .getByText("Exposição Hídrica", { selector: "h3" })
      .closest(".riscos-bloco-indicador");
    const grid = bloco.querySelector(".riscos-bloco-grid");
    expect(grid).not.toHaveClass("riscos-bloco-grid--somente-explicacao");
    expect(grid.querySelector(".riscos-bloco-config")).toBeInTheDocument();
  });

  it("explica os três componentes da composição interna da Exposição Hídrica", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Exposição Hídrica", { selector: "h3" }));
    const bloco = screen
      .getByText("Exposição Hídrica", { selector: "h3" })
      .closest(".riscos-bloco-indicador");
    const explicacao = within(bloco).getByRole("complementary", {
      name: "Como interpretar a composição interna",
    });
    expect(explicacao).toHaveTextContent("Proximidade da drenagem");
    expect(explicacao).toHaveTextContent("Representa a proximidade da fazenda");
    expect(explicacao).toHaveTextContent("Relevância da área montante");
    expect(explicacao).toHaveTextContent("Representa a dimensão da área");
    expect(explicacao).toHaveTextContent("Posição topográfica relativa");
    expect(explicacao).toHaveTextContent(
      "Compara a elevação do ponto analisado",
    );
    expect(explicacao).toHaveTextContent("Como os parâmetros atuam");
    expect(explicacao).toHaveTextContent("devem totalizar 100%");
  });

  it("explica os fatores de ativação da Instabilidade", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Instabilidade", { selector: "h3" }));
    const explicacao = screen.getByRole("complementary", {
      name: "Como interpretar os fatores de ativação",
    });
    expect(explicacao).toHaveTextContent(
      "A Instabilidade combina a suscetibilidade do terreno",
    );
    expect(explicacao).toHaveTextContent(
      "Sem ativação da suscetibilidade topográfica",
    );
    expect(explicacao).toHaveTextContent("Inicia uma ativação parcial");
    expect(explicacao).toHaveTextContent(
      "Aumenta a influência da suscetibilidade topográfica",
    );
    expect(explicacao).toHaveTextContent(
      "Aplica integralmente a suscetibilidade topográfica",
    );
    expect(explicacao).toHaveTextContent(
      "fatores de ativação, e não percentuais do score",
    );
  });

  it("explica os multiplicadores de secura do Incêndio", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(
      screen.getByText("Incêndio / Propagação de Fogo", { selector: "h3" }),
    );
    const explicacao = screen.getByRole("complementary", {
      name: "Como interpretar os multiplicadores de secura",
    });
    expect(explicacao).toHaveTextContent("0–1 dia sem chuva");
    expect(explicacao).toHaveTextContent("2–3 dias sem chuva");
    expect(explicacao).toHaveTextContent("4–6 dias sem chuva");
    expect(explicacao).toHaveTextContent("7 ou mais dias sem chuva");
    expect(explicacao).toHaveTextContent(
      "multiplicadores aplicados ao índice ambiental de fogo",
    );
  });

  it("explica o fator vento–chuva das Tempestades, incluindo a fórmula", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(
      screen.getByText("Tempestades Severas", { selector: "h3" }),
    );
    const explicacao = screen.getByRole("complementary", {
      name: "Como interpretar o fator vento–chuva",
    });
    expect(explicacao).toHaveTextContent("Base do fator vento–chuva");
    expect(explicacao).toHaveTextContent("Influência da chuva");
    expect(explicacao).toHaveTextContent(
      "Fator = Base + Influência da chuva × Componente de chuva",
    );
    expect(explicacao).toHaveTextContent("devem somar 1,00");
  });

  it("explica a composição interna e o limiar de dia relevante da Trafegabilidade, com aviso experimental", async () => {
    renderizar();
    await screen.findByText("Pesos do índice");
    fireEvent.click(screen.getByText("Trafegabilidade", { selector: "h3" }));
    const bloco = screen
      .getByText("Trafegabilidade", { selector: "h3" })
      .closest(".riscos-bloco-indicador");
    const explicacao = within(bloco).getByRole("complementary", {
      name: "Como interpretar a composição interna",
    });
    expect(explicacao).toHaveTextContent("Condição do dia atual");
    expect(explicacao).toHaveTextContent("Acúmulo recente");
    expect(explicacao).toHaveTextContent("Recuperação / secagem");
    expect(explicacao).toHaveTextContent("Limiar de dia relevante");
    expect(explicacao).toHaveTextContent(
      "participar da identificação de eventos na agregação histórica de 90 dias",
    );
    expect(explicacao).toHaveTextContent(
      "Os três pesos da composição interna devem totalizar 100%",
    );
    expect(explicacao).toHaveTextContent(
      "Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
    );
  });

  it("não realiza nenhuma chamada de API adicional ao exibir as explicações", async () => {
    const buscar = vi.fn().mockResolvedValue(fixtureParametrosScore);
    renderizar({ buscar });
    await screen.findByText("Pesos do índice");
    for (const perigo of [
      "Exposição Hídrica",
      "Instabilidade",
      "Incêndio / Propagação de Fogo",
      "Tempestades Severas",
      "Trafegabilidade",
    ]) {
      fireEvent.click(screen.getByText(perigo, { selector: "h3" }));
    }
    expect(buscar).toHaveBeenCalledTimes(1);
  });

  it("bloqueia o salvamento com peso negativo sem normalizar nada", async () => {
    const salvar = vi.fn();
    renderizar({ salvar });
    const trafegabilidade = await screen.findByLabelText(
      "Peso no índice — Trafegabilidade",
    );
    fireEvent.change(trafegabilidade, { target: { value: "-5" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar parâmetros" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("negativo");
    expect(salvar).not.toHaveBeenCalled();
  });

  it("envia todos os 22 parâmetros ao salvar", async () => {
    const salvar = vi.fn().mockResolvedValue(fixtureParametrosScore);
    const showToast = vi.fn();
    renderizar({ salvar, showToast });
    await screen.findByLabelText("Peso no índice — Exposição Hídrica");
    fireEvent.click(screen.getByRole("button", { name: "Salvar parâmetros" }));
    await vi.waitFor(() => expect(showToast).toHaveBeenCalled());
    expect(salvar).toHaveBeenCalledTimes(1);
    const enviado = salvar.mock.calls[0][0];
    expect(enviado.parametros).toHaveLength(22);
    expect(enviado.parametros).toContainEqual({
      grupo: "SCORE",
      indicador: "EXPOSICAO_HIDRICA",
      parametro: "peso",
      valor: 0.3,
    });
    expect(enviado.parametros).toContainEqual({
      grupo: "TEMPESTADES",
      indicador: "VENTO_CHUVA",
      parametro: "influencia_chuva",
      valor: 0.25,
    });
    expect(enviado.parametros).toContainEqual({
      grupo: "TRAFEGABILIDADE",
      indicador: "COMPOSICAO",
      parametro: "peso_dia",
      valor: 0.35,
    });
    expect(enviado.parametros).toContainEqual({
      grupo: "TRAFEGABILIDADE",
      indicador: "AGREGACAO",
      parametro: "limiar_relevancia",
      valor: 25,
    });
    expect(showToast).toHaveBeenCalledWith(
      "Parâmetros do modelo salvos com sucesso.",
    );
  });

  it("restaurar padrão de um bloco reseta somente aquele indicador, sem salvar automaticamente", async () => {
    const salvar = vi.fn();
    const showToast = vi.fn();
    renderizar({ salvar, showToast });
    await screen.findByLabelText("Peso no índice — Exposição Hídrica");
    fireEvent.click(screen.getByText("Exposição Hídrica", { selector: "h3" }));
    fireEvent.change(screen.getByLabelText("Proximidade da drenagem"), {
      target: { value: "99" },
    });
    fireEvent.click(
      within(
        screen
          .getByLabelText("Proximidade da drenagem")
          .closest(".riscos-bloco-indicador"),
      ).getByRole("button", { name: "Restaurar padrão" }),
    );
    expect(screen.getByLabelText("Proximidade da drenagem").value).toBe("40");
    expect(
      screen.getByLabelText("Peso no índice — Trafegabilidade").value,
    ).toBe("25");
    expect(salvar).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining("Salvar parâmetros"),
    );
  });

  it("restaurar todos os padrões reseta os 22 valores sem salvar automaticamente", async () => {
    const salvar = vi.fn();
    const showToast = vi.fn();
    renderizar({ salvar, showToast });
    const hidrica = await screen.findByLabelText(
      "Peso no índice — Exposição Hídrica",
    );
    fireEvent.change(hidrica, { target: { value: "99" } });
    fireEvent.click(screen.getByText("Instabilidade", { selector: "h3" }));
    fireEvent.change(screen.getByLabelText("Atenção"), {
      target: { value: "0.9" },
    });
    fireEvent.click(screen.getByText("Trafegabilidade", { selector: "h3" }));
    fireEvent.change(screen.getByLabelText("Limiar de dia relevante"), {
      target: { value: "90" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Restaurar todos os padrões" }),
    );
    expect(
      screen.getByLabelText("Peso no índice — Exposição Hídrica").value,
    ).toBe("30");
    expect(screen.getByLabelText("Atenção").value).toBe("0.35");
    expect(screen.getByLabelText("Limiar de dia relevante").value).toBe("25");
    expect(salvar).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining("Salvar parâmetros"),
    );
  });

  it("restaurar padrão do bloco Trafegabilidade reseta composição e limiar, sem salvar automaticamente", async () => {
    const salvar = vi.fn();
    const showToast = vi.fn();
    renderizar({ salvar, showToast });
    await screen.findByLabelText("Peso no índice — Exposição Hídrica");
    fireEvent.click(screen.getByText("Trafegabilidade", { selector: "h3" }));
    fireEvent.change(screen.getByLabelText("Condição do dia atual"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Limiar de dia relevante"), {
      target: { value: "80" },
    });
    fireEvent.click(
      within(
        screen
          .getByLabelText("Condição do dia atual")
          .closest(".riscos-bloco-indicador"),
      ).getByRole("button", { name: "Restaurar padrão" }),
    );
    expect(screen.getByLabelText("Condição do dia atual").value).toBe("35");
    expect(screen.getByLabelText("Limiar de dia relevante").value).toBe("25");
    expect(
      screen.getByLabelText("Peso no índice — Trafegabilidade").value,
    ).toBe("25");
    expect(salvar).not.toHaveBeenCalled();
    expect(showToast).toHaveBeenCalledWith(
      expect.stringContaining("Salvar parâmetros"),
    );
  });

  it("mostra mensagens de erro por grupo do backend sem mascarar nenhuma", async () => {
    const erro = new ErroApiParametrosScore(422, "erro", [
      { grupo: "SCORE", mensagem: "Os pesos do índice devem totalizar 100%." },
      {
        grupo: "TEMPESTADES",
        mensagem:
          "A base do fator vento–chuva e a influência da chuva das Tempestades Severas devem somar 1,00.",
      },
    ]);
    const salvar = vi.fn().mockRejectedValue(erro);
    renderizar({ salvar });
    await screen.findByLabelText("Peso no índice — Exposição Hídrica");
    fireEvent.click(screen.getByRole("button", { name: "Salvar parâmetros" }));
    expect(
      await screen.findByText("Os pesos do índice devem totalizar 100%."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "A base do fator vento–chuva e a influência da chuva das Tempestades Severas devem somar 1,00.",
      ),
    ).toBeInTheDocument();
  });

  it("nunca recalcula ou renormaliza no frontend: envia exatamente o que está nos campos", async () => {
    const salvar = vi.fn().mockResolvedValue(fixtureParametrosScore);
    const showToast = vi.fn();
    renderizar({ salvar, showToast });
    await screen.findByLabelText("Peso no índice — Exposição Hídrica");
    fireEvent.change(
      screen.getByLabelText("Peso no índice — Exposição Hídrica"),
      { target: { value: "40" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Salvar parâmetros" }));
    await vi.waitFor(() => expect(showToast).toHaveBeenCalled());
    const enviado = salvar.mock.calls[0][0];
    expect(enviado.parametros).toContainEqual({
      grupo: "SCORE",
      indicador: "EXPOSICAO_HIDRICA",
      parametro: "peso",
      valor: 0.4,
    });
    const outros = enviado.parametros.filter(
      (p) => !(p.grupo === "SCORE" && p.indicador === "EXPOSICAO_HIDRICA"),
    );
    expect(outros).toEqual(
      fixtureParametrosScore.parametros
        .filter(
          (p) => !(p.grupo === "SCORE" && p.indicador === "EXPOSICAO_HIDRICA"),
        )
        .map((p) => ({
          grupo: p.grupo,
          indicador: p.indicador,
          parametro: p.parametro,
          valor: p.valor_atual,
        })),
    );
  });

  it("exibe erro de carregamento sem travar a tela", async () => {
    renderizar({
      buscar: () =>
        Promise.reject(
          new Error("Não foi possível carregar os parâmetros do modelo."),
        ),
    });
    expect(
      await screen.findByRole("alert", {}, { timeout: 3000 }),
    ).toHaveTextContent("Não foi possível carregar os parâmetros do modelo.");
  });
});
