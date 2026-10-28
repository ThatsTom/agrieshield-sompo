import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FazendaSearch, filtrarFazendas } from "./FazendaSearch";

const fazendas = [
  { id: "1", nome_fazenda: "Fazenda São José", numero_apolice: "ABC-10", cep: "78000-000", cidade: "Cuiabá", uf: "MT", tipo_operacao: "campo", status_geoespacial: "SUCESSO" },
  { id: "2", nome_fazenda: "Estância Norte", numero_apolice: "XYZ-20", cep: "79000-000", cidade: "Campo Grande", uf: "MS", tipo_operacao: "transporte", status_geoespacial: "PENDENTE" },
];

afterEach(cleanup);

describe("busca inteligente de fazendas", () => {
  it("ignora acentos e pesquisa referências cadastrais", () => {
    expect(filtrarFazendas(fazendas, { consulta: "sao jose" })).toHaveLength(1);
    expect(filtrarFazendas(fazendas, { consulta: "XYZ-20" })[0].id).toBe("2");
    expect(filtrarFazendas(fazendas, { consulta: "campo grande MS" })[0].id).toBe("2");
  });

  it("combina operação, UF e contexto territorial", () => {
    expect(filtrarFazendas(fazendas, { operacao: "campo", uf: "MT", contexto: "pronto" }).map((f) => f.id)).toEqual(["1"]);
    expect(filtrarFazendas(fazendas, { operacao: "transporte", contexto: "pronto" })).toHaveLength(0);
  });

  it("seleciona o primeiro resultado com Enter", () => {
    const onSelect = vi.fn();
    render(<FazendaSearch fazendas={fazendas} selected="1" onSelect={onSelect} />);
    const input = screen.getByRole("combobox", { name: "Buscar propriedade" });
    fireEvent.change(input, { target: { value: "XYZ-20" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("2");
  });

  it("remove o filtro de operação e preserva a busca de campo e transporte", () => {
    render(<FazendaSearch fazendas={fazendas} onSelect={vi.fn()} />);
    expect(screen.queryByRole("combobox", { name: "Filtrar por operação" })).not.toBeInTheDocument();
    expect(screen.queryByText("Todas as operações")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Filtrar por UF" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Filtrar por contexto territorial" })).toBeInTheDocument();

    fireEvent.focus(screen.getByRole("combobox", { name: "Buscar propriedade" }));
    expect(screen.getByRole("option", { name: /Fazenda São José/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Estância Norte/ })).toBeInTheDocument();
  });

  it("mantém os filtros de UF e contexto funcionando após remover operação", () => {
    render(<FazendaSearch fazendas={fazendas} onSelect={vi.fn()} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Filtrar por UF" }), { target: { value: "MS" } });
    expect(screen.getByRole("option", { name: /Estância Norte/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Fazenda São José/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Filtrar por contexto territorial" }), { target: { value: "pronto" } });
    expect(screen.getByText("Nenhuma propriedade encontrada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Limpar busca e filtros" }));
    expect(screen.getByRole("option", { name: /Fazenda São José/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Estância Norte/ })).toBeInTheDocument();
  });
});
