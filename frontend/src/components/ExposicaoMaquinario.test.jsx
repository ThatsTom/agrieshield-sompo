import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExposicaoMaquinario } from "./ExposicaoMaquinario";
import { fixtureExposicao } from "../test/fixtureExposicao";

const renderizar = (
  patch = {},
  buscar,
  fazenda = { nome_fazenda: "Fallback", tipo_operacao: "campo" },
) =>
  render(
    <ExposicaoMaquinario
      idFazenda="1"
      fazenda={fazenda}
      buscar={
        buscar || (() => Promise.resolve({ ...fixtureExposicao, ...patch }))
      }
    />,
  );

afterEach(cleanup);

describe("dashboard de exposição", () => {
  it("exibe score e comparação publicados", async () => {
    renderizar();
    await screen.findByText("Exposição de Maquinário Agrícola");
    const t = document.body.textContent;
    expect(t).toContain("17,17");
    expect(t).toContain("0,00");
    expect(t).toContain("-17,17 pontos");
    expect(t).toContain("-100%");
    expect(screen.getAllByText("NORMAL").length).toBeGreaterThan(1);
  });
  it("renderiza identificação, localização, SRTM e MERIT do endpoint", async () => {
    renderizar();
    await screen.findByText("Contexto territorial");
    const t = document.body.textContent;
    expect(t).toContain("Fazenda Boa Esperança");
    expect(t).toContain("Sorriso / MT");
    expect(t).toContain("250,00 ha");
    expect(t).toContain("Declividade média3,22°");
    expect(
      screen
        .getByRole("button", {
          name: "Ajuda: SRTM — Posição topográfica relativa",
        })
        .closest("div"),
    ).toHaveTextContent("-1,46 m");
    expect(t).toContain("Distância à drenagem2,00 km");
    expect(
      screen
        .getByRole("button", { name: "Ajuda: MERIT — Área montante" })
        .closest("div"),
    ).toHaveTextContent("850,33 km²");
  });
  it("preserva missing territorial sem fabricar zero", async () => {
    const ausente = {
      proximidade_drenagem: null,
      relevancia_area_montante: null,
      posicao_topografica: null,
      suscetibilidade_territorial: null,
    };
    renderizar({
      contexto_territorial: {
        declividade_media_graus: null,
        posicao_topografica_relativa_m: null,
        distancia_drenagem_m: null,
        area_montante_km2: null,
      },
      exposicao_hidrica: { ...fixtureExposicao.exposicao_hidrica, ...ausente },
      fazenda: { ...fixtureExposicao.fazenda, area_ha: null },
    });
    await screen.findByText("Contexto territorial");
    expect(screen.getAllByText("Não disponível").length).toBeGreaterThanOrEqual(
      8,
    );
    expect(document.body.textContent).not.toContain("0,00 km²");
  });
  it("marca NASA POWER, Open-Meteo, SRTM e MERIT conforme o uso real", async () => {
    renderizar();
    await screen.findByText("Fontes e indicadores");
    const t = document.body.textContent;
    expect(t).toContain("USADANASA POWER");
    expect(t).toContain("DISPONÍVELOpen-Meteo");
    expect(t).toContain(
      "Fonte meteorológica alternativa. Não utilizada nesta avaliação.",
    );
    expect(t).toContain("USADASRTM");
    expect(t).toContain("USADAMERIT Hydro");
    expect(t).toContain("DISPONÍVELMapBiomas");
    expect(t).toContain("NÃO UTILIZADOINMET");
    expect(screen.getAllByText("Contribui para o score oficial")).toHaveLength(
      3,
    );
  });
  it("apresenta corretamente Open-Meteo usada e NASA POWER alternativa", async () => {
    const fontes_avaliacao = fixtureExposicao.fontes_avaliacao.map((x) =>
      x.fonte === "OPEN_METEO"
        ? {
            ...x,
            status: "USADA",
            contribui_score: true,
            descricao: "Meteorologia histórica usada nesta avaliação.",
          }
        : x.fonte === "NASA_POWER"
          ? {
              ...x,
              status: "DISPONIVEL",
              contribui_score: false,
              descricao:
                "Fonte meteorológica alternativa. Não utilizada nesta avaliação.",
            }
          : x,
    );
    renderizar({ fonte_meteorologica: "OPEN_METEO", fontes_avaliacao });
    await screen.findByText("Fontes e indicadores");
    const t = document.body.textContent;
    expect(t).toContain("USADAOpen-Meteo");
    expect(t).toContain("DISPONÍVELNASA POWER");
  });
  it("exibe Trafegabilidade participando normalmente do score com peso configurado", async () => {
    renderizar();
    await screen.findByText("Exposição de Maquinário Agrícola");
    const titulo = screen.getByRole("heading", {
      level: 4,
      name: /^Trafegabilidade/,
    });
    const card = titulo.closest("section");
    expect(card).toHaveTextContent("Peso no índice25%");
    expect(card).toHaveTextContent("Participa do scoreSim");
    expect(card).not.toHaveTextContent("Indicador informativo");
    expect(document.body.textContent).not.toContain("Peso nominal");
    expect(document.body.textContent).not.toContain("Peso efetivo");
  });
  it("faz card, score e timeline usarem a mesma Exposição Hídrica", async () => {
    const evento = {
      perigo: "EXPOSICAO_HIDRICA",
      inicio: "2026-07-20",
      fim: "2026-07-22",
      duracao_dias: 3,
      severidade: 55,
      classificacao_maxima: "ALERTA",
      indice_maximo: 60,
      indice_medio: 55,
      metodologia_perigo: "EXPOSICAO_HIDRICA_TERRITORIAL",
    };
    const perigos = fixtureExposicao.perigos.map((p) =>
      p.perigo === "EXPOSICAO_HIDRICA"
        ? { ...p, indice: 50, classificacao: "ALERTA", contribuicao: 20 }
        : p,
    );
    const exposicao_hidrica = {
      ...fixtureExposicao.exposicao_hidrica,
      janela_atual: {
        ...fixtureExposicao.exposicao_hidrica.janela_atual,
        indice: 50,
        classificacao: "ALERTA",
        quantidade_dias_relevantes: 3,
        quantidade_eventos: 1,
      },
    };
    renderizar({
      perigos,
      exposicao_hidrica,
      timeline_eventos: [evento],
      score_atual: 20,
      classificacao_atual: "NORMAL",
      perigos_dominantes: ["EXPOSICAO_HIDRICA"],
      perigo_dominante: "EXPOSICAO_HIDRICA",
    });
    await screen.findByLabelText("Detalhamento da Exposição Hídrica");
    const card = screen
      .getByRole("heading", { level: 4, name: /Exposição Hídrica/ })
      .closest("section");
    expect(card).toHaveTextContent("Índice50,00");
    expect(card).toHaveTextContent("Contribuição oficial20,00 pts");
    expect(
      screen.getByLabelText("Detalhamento da Exposição Hídrica"),
    ).toHaveTextContent("Exposição hídrica atual50,00");
    expect(
      screen.getByLabelText("Exposição Hídrica: 1 eventos"),
    ).toBeInTheDocument();
    expect(document.querySelector(".equip-condition-gauge")).toHaveTextContent("20,00");
  });
  it("explica os componentes territoriais com valores do DTO", async () => {
    renderizar();
    const detalhe = await screen.findByLabelText(
      "Detalhamento da Exposição Hídrica",
    );
    expect(detalhe).toHaveTextContent("Proximidade da drenagem48,28 / 100");
    expect(detalhe).toHaveTextContent(
      "Relevância da drenagem pela área montante55,58 / 100",
    );
    expect(detalhe).toHaveTextContent(
      "Posição topográfica relativa65,84 / 100",
    );
    expect(detalhe).toHaveTextContent("Suscetibilidade territorial55,24 / 100");
    expect(detalhe).toHaveTextContent("Janela atual");
    expect(detalhe).toHaveTextContent("Janela anterior");
  });
  it("unifica Exposição Hídrica, Trafegabilidade e os três perigos em uma única seção Detalhamento dos perigos, na ordem correta", async () => {
    renderizar();
    await screen.findByLabelText("Detalhamento da Exposição Hídrica");
    const secao = screen
      .getByText("Detalhamento dos perigos")
      .closest("section.hazard-details");
    expect(secao).toBeInTheDocument();
    expect(document.querySelectorAll("section.hazard-details")).toHaveLength(1);
    const hidrico = screen.getByLabelText("Detalhamento da Exposição Hídrica");
    expect(secao).toContainElement(hidrico);
    expect(secao).toHaveTextContent("Trafegabilidade");
    expect(secao).toHaveTextContent("Incêndio / Propagação de Fogo");
    expect(secao).toHaveTextContent("Instabilidade");
    expect(secao).toHaveTextContent("Tempestades Severas");
    expect(hidrico).toHaveTextContent("Componentes territoriais");
    expect(document.querySelectorAll(".hazard-detail")).toHaveLength(5);
    const titulos = [
      ...secao.querySelectorAll(
        ".hazard-detail>summary h3, [aria-label='Detalhamento da Exposição Hídrica']>summary h3",
      ),
    ].map((x) => x.textContent.replace(/\s*\?\s*$/, "").trim());
    expect(titulos[0]).toBe("Exposição Hídrica");
    expect(titulos[1]).toBe("Trafegabilidade");
    expect(titulos[2]).toBe("Incêndio / Propagação de Fogo");
    expect(titulos[3]).toBe("Instabilidade");
    expect(titulos[4]).toBe("Tempestades Severas");
  });
  it("Exposição Hídrica inicia expandida e os demais perigos, incluindo Trafegabilidade, iniciam recolhidos", async () => {
    renderizar();
    const hidrico = await screen.findByLabelText(
      "Detalhamento da Exposição Hídrica",
    );
    expect(hidrico).toHaveAttribute("open");
    const trafegabilidade = screen
      .getByRole("heading", { level: 3, name: "Trafegabilidade" })
      .closest("details");
    const incendio = screen
      .getByRole("heading", { level: 3, name: "Incêndio / Propagação de Fogo" })
      .closest("details");
    const instabilidade = screen
      .getByRole("heading", { level: 3, name: "Instabilidade" })
      .closest("details");
    const tempestades = screen
      .getByRole("heading", { level: 3, name: "Tempestades Severas" })
      .closest("details");
    expect(trafegabilidade).not.toHaveAttribute("open");
    expect(incendio).not.toHaveAttribute("open");
    expect(instabilidade).not.toHaveAttribute("open");
    expect(tempestades).not.toHaveAttribute("open");
  });
  it("não dispara nenhuma nova chamada de API ao unificar as seções", async () => {
    const buscar = vi.fn().mockResolvedValue(fixtureExposicao);
    renderizar({}, buscar);
    await screen.findByLabelText("Detalhamento da Exposição Hídrica");
    expect(buscar).toHaveBeenCalledTimes(1);
  });
  it("não apresenta nomenclatura legada de versão hídrica", async () => {
    renderizar();
    await screen.findByLabelText("Detalhamento da Exposição Hídrica");
    expect(document.body.textContent).not.toMatch(
      /\b(?:H1|H2|hidrico[ -]?v1|hidrico[ -]?v2)\b/i,
    );
  });
  it("usa a palavra experimental apenas no aviso metodológico da Trafegabilidade, não como nomenclatura de versão", async () => {
    renderizar();
    const trafegabilidade = await screen.findByRole("heading", {
      level: 3,
      name: "Trafegabilidade",
    });
    const detalhe = trafegabilidade.closest("details");
    expect(detalhe).toHaveTextContent(
      "Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
    );
    const foraDoDetalhe = document.body.textContent.replace(
      detalhe.textContent,
      "",
    );
    expect(foraDoDetalhe).not.toMatch(/experimental/i);
  });
  it("linha do tempo de Trafegabilidade usa eventos da metodologia própria, na posição correta e sem chamada extra à API", async () => {
    const evento = (perigo, inicio, fim, duracao_dias) => ({
      perigo,
      inicio,
      fim,
      duracao_dias,
      severidade: 33,
      classificacao_maxima: "ATENCAO",
      indice_maximo: 35,
      indice_medio: 30,
      metodologia_perigo:
        "COMPOSICAO_METEOROLOGICA_PROPRIA_DIA_ACUMULADO_RECUPERACAO_V1",
    });
    const timeline_eventos = [
      evento("TRAFEGABILIDADE", "2026-06-01", "2026-06-03", 3),
      evento("TRAFEGABILIDADE", "2026-07-10", "2026-07-10", 1),
    ];
    const buscar = vi
      .fn()
      .mockResolvedValue({ ...fixtureExposicao, timeline_eventos });
    renderizar({}, buscar);
    await screen.findByLabelText("Trafegabilidade: 2 eventos");
    expect(buscar).toHaveBeenCalledTimes(1);
    const raias = [...document.querySelectorAll(".timeline-lane")];
    const rotulos = raias.map((l) => l.querySelector("b").textContent);
    expect(rotulos).toEqual([
      "Exposição Hídrica",
      "Trafegabilidade",
      "Instabilidade",
      "Incêndio / Propagação de Fogo",
      "Tempestades Severas",
    ]);
    const laneTrafegabilidade = raias[1];
    expect(laneTrafegabilidade).toHaveTextContent(
      "Chuva do dia, acúmulo recente e recuperação/secagem",
    );
    expect(laneTrafegabilidade.querySelectorAll(".lane-event")).toHaveLength(2);
    expect(
      document.querySelectorAll(
        "[aria-label='Exposição Hídrica: 0 eventos'], [aria-label='Instabilidade: 0 eventos']",
      ).length,
    ).toBe(2);
  });
  it("mantém a raia de Trafegabilidade visível, sem intervalos e sem erro quando não há dias relevantes na janela", async () => {
    renderizar();
    await screen.findByLabelText("Trafegabilidade: 0 eventos");
    const lane = document.querySelector(
      "[aria-label='Trafegabilidade: 0 eventos']",
    );
    expect(lane).toBeInTheDocument();
    expect(lane.querySelectorAll(".lane-event")).toHaveLength(0);
    expect(
      screen.getByText(/Nenhum evento relevante identificado na janela atual/),
    ).toBeInTheDocument();
  });
  it("posiciona eventos pela data e representa duração proporcional", async () => {
    const evento = (perigo, inicio, fim, duracao_dias) => ({
      perigo,
      inicio,
      fim,
      duracao_dias,
      severidade: 33,
      classificacao_maxima: "ATENCAO",
      indice_maximo: 35,
      indice_medio: 30,
      metodologia_perigo: "PERIGO_ATUAL",
    });
    const timeline_eventos = [
      evento("INCENDIO", "2026-05-03", "2026-05-03", 1),
      evento("INCENDIO", "2026-06-15", "2026-06-15", 1),
      evento("INCENDIO", "2026-07-20", "2026-07-25", 6),
      evento("TEMPESTADES", "2026-06-10", "2026-06-10", 1),
      evento("TEMPESTADES", "2026-07-31", "2026-07-31", 1),
    ];
    renderizar({ timeline_eventos });
    await screen.findByLabelText("Incêndio / Propagação de Fogo: 3 eventos");
    const incendio = [
      ...screen
        .getByLabelText("Incêndio / Propagação de Fogo: 3 eventos")
        .querySelectorAll(".lane-event"),
    ];
    const tempestades = [
      ...screen
        .getByLabelText("Tempestades Severas: 2 eventos")
        .querySelectorAll(".lane-event"),
    ];
    expect(incendio).toHaveLength(3);
    expect(tempestades).toHaveLength(2);
    expect(incendio[0]).toHaveStyle({
      left: "0%",
      width: "1.1111111111111112%",
    });
    expect(new Set(incendio.map((x) => x.style.left)).size).toBe(3);
    expect(parseFloat(incendio[2].style.width)).toBeGreaterThan(
      parseFloat(incendio[0].style.width),
    );
    expect(parseFloat(tempestades[1].style.left)).toBeGreaterThan(98);
  });
  it("permite filtrar, selecionar e ler os riscos do período com datas e métricas", async () => {
    const timeline_eventos = [
      {
        perigo: "INCENDIO",
        inicio: "2026-06-15",
        fim: "2026-06-15",
        duracao_dias: 1,
        severidade: 33,
        classificacao_maxima: "ATENCAO",
        indice_maximo: 35,
        indice_medio: 30,
        metodologia_perigo: "PERIGO_ATUAL",
      },
      {
        perigo: "EXPOSICAO_HIDRICA",
        inicio: "2026-07-20",
        fim: "2026-07-22",
        duracao_dias: 3,
        severidade: 55,
        classificacao_maxima: "ALERTA",
        indice_maximo: 60,
        indice_medio: 55,
        metodologia_perigo: "EXPOSICAO_HIDRICA_TERRITORIAL",
      },
    ];
    renderizar({ timeline_eventos });

    const resumo = await screen.findByLabelText("Resumo dos riscos no período");
    expect(resumo).toHaveTextContent("Eventos identificados2");
    expect(resumo).toHaveTextContent("Perigos com evento2 de 5");
    expect(resumo).toHaveTextContent("Dias sinalizados4 de 90");
    expect(document.querySelectorAll(".timeline-axis span")).toHaveLength(6);

    const detalhe = screen.getByLabelText("Detalhes do evento selecionado");
    expect(detalhe).toHaveTextContent("Exposição Hídrica");
    expect(detalhe).toHaveTextContent("Início20/07/2026");
    expect(detalhe).toHaveTextContent("Índice máximo60,00 / 100");

    fireEvent.click(
      screen.getByRole("button", {
        name: /Incêndio \/ Propagação de Fogo, 15\/06\/2026 a 15\/06\/2026/,
      }),
    );
    expect(detalhe).toHaveTextContent("Incêndio / Propagação de Fogo");
    expect(detalhe).toHaveTextContent("Severidade33,00 / 100");

    fireEvent.click(
      screen.getByRole("button", { name: /Incêndio \/ Propagação de Fogo 1$/ }),
    );
    expect(document.querySelectorAll(".timeline-lane")).toHaveLength(1);
    expect(screen.getByLabelText("Riscos identificados no período")).toHaveTextContent(
      "1 resultado(s)",
    );
  });
  it("apresenta o score no padrão semicircular da condição operacional", async () => {
    renderizar();
    await screen.findByText("Score de Exposição do Maquinário");
    const medidor = document.querySelector(".equip-condition-gauge");
    expect(medidor).toHaveClass("gauge", "equip-condition-gauge");
    expect(medidor).toHaveAttribute("role", "img");
    expect(medidor).toHaveAccessibleName(/Score de exposição 0,00 de 100/);
    expect(medidor.querySelectorAll("path")).toHaveLength(2);
    const card = medidor.closest("article");
    expect(card).toHaveTextContent("Período analisado: últimos 90 dias");
    expect(card).toHaveTextContent("Referência: 31/07/2026");
  });
  it("exibe loading e erro", async () => {
    renderizar({}, () => new Promise(() => {}));
    expect(
      screen.getByText("Carregando avaliação de exposição..."),
    ).toBeInTheDocument();
    cleanup();
    renderizar({}, () => Promise.reject(new Error("Fazenda não encontrada.")));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Fazenda não encontrada.",
    );
  });
});
