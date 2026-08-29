import { useEffect, useId, useMemo, useRef, useState } from "react";
import { obterStatusGeoespacial } from "../cadastro/statusGeoespacial";
import { Icon } from "../layout/Icon";

export const normalizarBusca = (valor) =>
  String(valor ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

const textoFazenda = (fazenda) =>
  [
    fazenda.nome_fazenda,
    fazenda.numero_apolice,
    fazenda.id_fazenda,
    fazenda.id,
    fazenda.cep,
    fazenda.cidade,
    fazenda.uf,
    fazenda.tipo_operacao,
  ]
    .map(normalizarBusca)
    .join(" ");

const pontuar = (fazenda, consulta) => {
  if (!consulta) return 0;
  const nome = normalizarBusca(fazenda.nome_fazenda);
  const apolice = normalizarBusca(fazenda.numero_apolice);
  const id = normalizarBusca(fazenda.id_fazenda || fazenda.id);
  const cidade = normalizarBusca(fazenda.cidade);
  if (nome === consulta) return 120;
  if (apolice === consulta || id === consulta) return 110;
  if (nome.startsWith(consulta)) return 90;
  if (cidade.startsWith(consulta)) return 70;
  return 20;
};

export function filtrarFazendas(
  fazendas,
  { consulta = "", operacao = "todas", uf = "todas", contexto = "todos" },
) {
  const busca = normalizarBusca(consulta);
  const termos = busca.split(/\s+/).filter(Boolean);
  return fazendas
    .filter((fazenda) => {
      const texto = textoFazenda(fazenda);
      const status = String(fazenda.status_geoespacial || "PENDENTE").toUpperCase();
      return (
        termos.every((termo) => texto.includes(termo)) &&
        (operacao === "todas" || fazenda.tipo_operacao === operacao) &&
        (uf === "todas" || fazenda.uf === uf) &&
        (contexto === "todos" ||
          (contexto === "pronto" && status === "SUCESSO") ||
          (contexto === "pendente" && status !== "SUCESSO"))
      );
    })
    .sort(
      (a, b) =>
        pontuar(b, busca) - pontuar(a, busca) ||
        String(a.nome_fazenda).localeCompare(String(b.nome_fazenda), "pt-BR"),
    );
}

export function FazendaSearch({
  fazendas,
  selected,
  onSelect,
  label = "Buscar propriedade",
  showFilters = true,
}) {
  const selecionada = fazendas.find(
    (fazenda) => String(fazenda.id) === String(selected),
  );
  const [consulta, setConsulta] = useState(selecionada?.nome_fazenda || "");
  const [aberto, setAberto] = useState(false);
  const [operacao, setOperacao] = useState("todas");
  const [uf, setUf] = useState("todas");
  const [contexto, setContexto] = useState("todos");
  const raiz = useRef(null);
  const listaId = useId();
  const ufs = useMemo(
    () => [...new Set(fazendas.map((fazenda) => fazenda.uf).filter(Boolean))].sort(),
    [fazendas],
  );
  const resultados = useMemo(
    () =>
      filtrarFazendas(fazendas, { consulta, operacao, uf, contexto }).slice(0, 12),
    [fazendas, consulta, operacao, uf, contexto],
  );

  useEffect(() => {
    if (selecionada) setConsulta(selecionada.nome_fazenda);
  }, [selected, selecionada?.nome_fazenda]);

  useEffect(() => {
    const fechar = (evento) => {
      if (!raiz.current?.contains(evento.target)) setAberto(false);
    };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, []);

  const escolher = (fazenda) => {
    onSelect(String(fazenda.id));
    setConsulta(fazenda.nome_fazenda);
    setAberto(false);
  };

  const limpar = () => {
    setConsulta("");
    setOperacao("todas");
    setUf("todas");
    setContexto("todos");
    setAberto(true);
  };

  const filtrosAtivos =
    operacao !== "todas" || uf !== "todas" || contexto !== "todos";

  return (
    <div className="farm-search" ref={raiz}>
      <label htmlFor={`${listaId}-input`}>{label}</label>
      <div className="farm-search-input">
        <Icon name="search" size={17} />
        <input
          id={`${listaId}-input`}
          role="combobox"
          aria-expanded={aberto}
          aria-controls={listaId}
          aria-autocomplete="list"
          autoComplete="off"
          value={consulta}
          placeholder="Nome, apólice, ID, CEP, cidade ou UF"
          onFocus={() => setAberto(true)}
          onChange={(evento) => {
            setConsulta(evento.target.value);
            setAberto(true);
          }}
          onKeyDown={(evento) => {
            if (evento.key === "Escape") setAberto(false);
            if (evento.key === "Enter" && resultados[0]) {
              evento.preventDefault();
              escolher(resultados[0]);
            }
          }}
        />
        {(consulta || filtrosAtivos) && (
          <button type="button" onClick={limpar} aria-label="Limpar busca e filtros">
            ×
          </button>
        )}
      </div>
      {showFilters && (
        <div className="farm-search-filters" aria-label="Filtros da busca">
          <select value={operacao} onChange={(e) => { setOperacao(e.target.value); setAberto(true); }} aria-label="Filtrar por operação">
            <option value="todas">Todas as operações</option>
            <option value="campo">Campo</option>
            <option value="transporte">Transporte</option>
          </select>
          <select value={uf} onChange={(e) => { setUf(e.target.value); setAberto(true); }} aria-label="Filtrar por UF">
            <option value="todas">Todas as UFs</option>
            {ufs.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <select value={contexto} onChange={(e) => { setContexto(e.target.value); setAberto(true); }} aria-label="Filtrar por contexto territorial">
            <option value="todos">Todo contexto territorial</option>
            <option value="pronto">Contexto pronto</option>
            <option value="pendente">Contexto pendente</option>
          </select>
        </div>
      )}
      {aberto && (
        <div className="farm-search-results" id={listaId} role="listbox">
          <header>
            <span>{resultados.length} resultado(s)</span>
            <small>Enter seleciona a primeira opção</small>
          </header>
          {resultados.length ? resultados.map((fazenda) => {
            const status = obterStatusGeoespacial(fazenda.status_geoespacial);
            const atual = String(fazenda.id) === String(selected);
            return (
              <button
                type="button"
                role="option"
                aria-selected={atual}
                className={atual ? "is-selected" : ""}
                key={fazenda.id}
                onClick={() => escolher(fazenda)}
              >
                <span className="farm-result-icon"><Icon name="map" size={16} /></span>
                <span className="farm-result-main">
                  <b>{fazenda.nome_fazenda}</b>
                  <small>{fazenda.cidade || "Localidade não informada"} / {fazenda.uf || "—"} · Apólice {fazenda.numero_apolice || "—"}</small>
                </span>
                <span className="farm-result-meta">
                  <small>{fazenda.tipo_operacao === "transporte" ? "Transporte" : "Campo"}</small>
                  <b className={status.classe}>{status.curto}</b>
                </span>
              </button>
            );
          }) : (
            <div className="farm-search-empty">
              <Icon name="search" size={20} />
              <b>Nenhuma propriedade encontrada</b>
              <span>Tente parte do nome, apólice, cidade ou remova um filtro.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
