import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { normalizarBusca } from "../components/FazendaSearch";
import { API_URL, fetchJSON } from "../api/core";
import {
  obterStatusGeoespacial,
  permiteReprocessarGeoespacial,
} from "../cadastro/statusGeoespacial";
const cor = (c) =>
  c === "RESTRIÇÃO"
    ? "var(--red)"
    : c === "ATENÇÃO"
      ? "var(--amber)"
      : "var(--green)";
const formatarData = (valor) => {
  if (!valor) return "Data indisponível";
  const [ano, mes, dia] = String(valor).slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : String(valor);
};
const origemScore = (origem) =>
  origem === "nasa_power"
    ? "NASA real"
    : origem === "simulado"
      ? "Simulado"
      : "Origem pendente";
function Status({ status }) {
  const v = obterStatusGeoespacial(status);
  return (
    <span className={`geo-status ${v.classe}`}>
      <b>{v.icone}</b>
      {v.texto}
    </span>
  );
}
export function ClientesPage({
  fazendas,
  scorePreview,
  setPage,
  setSelected,
  carregarFazendas,
  showToast,
  onNovaFazenda,
  onEditarFazenda,
  carregando = false,
}) {
  const [q, setQ] = useState(""),
    [op, setOp] = useState("todos"),
    [uf, setUf] = useState("todas"),
    [geo, setGeo] = useState("todos"),
    [agua, setAgua] = useState("todos"),
    [condicao, setCondicao] = useState("todas"),
    [arquivo, setArquivo] = useState("ativos"),
    [ordem, setOrdem] = useState("nome"),
    [reprocessando, setReprocessando] = useState(""),
    [jobs, setJobs] = useState({}),
    [arquivando, setArquivando] = useState("");
  const acompanhando = useRef(new Set());
  const ufs = useMemo(
    () => [...new Set(fazendas.map((f) => f.uf).filter(Boolean))].sort(),
    [fazendas],
  );
  const filtradas = useMemo(
    () => {
      const termos = normalizarBusca(q).split(/\s+/).filter(Boolean);
      return fazendas
        .filter((f) => {
          const texto = normalizarBusca(
            [f.nome_fazenda, ...(f.apolices || []), f.id_fazenda, f.id, f.cep, f.cidade, f.uf].join(" "),
          );
          const statusGeo = String(f.status_geoespacial || "PENDENTE").toUpperCase();
          const statusCondicao = normalizarBusca(scorePreview[f.id]?.condicao_atual);
          return (
            termos.every((termo) => texto.includes(termo)) &&
            (op === "todos" || f.tipo_operacao === op) &&
            (uf === "todas" || f.uf === uf) &&
            (geo === "todos" ||
              (geo === "pronto" && statusGeo === "SUCESSO") ||
              (geo === "pendente" && statusGeo !== "SUCESSO")) &&
            (agua === "todos" ||
              (agua === "sim" && Boolean(f.proximidade_agua)) ||
              (agua === "nao" && !f.proximidade_agua)) &&
            (condicao === "todas" || statusCondicao === condicao)
            && (arquivo === "todos" || (arquivo === "arquivados" ? f.arquivada : !f.arquivada))
          );
        })
        .sort((a, b) => {
          if (ordem === "score")
            return (scorePreview[b.id]?.score ?? -1) - (scorePreview[a.id]?.score ?? -1);
          if (ordem === "cidade")
            return String(a.cidade).localeCompare(String(b.cidade), "pt-BR");
          return String(a.nome_fazenda).localeCompare(String(b.nome_fazenda), "pt-BR");
        });
    },
    [fazendas, scorePreview, q, op, uf, geo, agua, condicao, arquivo, ordem],
  );
  const limparFiltros = () => {
    setQ("");
    setOp("todos");
    setUf("todas");
    setGeo("todos");
    setAgua("todos");
    setCondicao("todas");
    setArquivo("ativos");
    setOrdem("nome");
  };
  const filtrosAtivos = [q, op !== "todos", uf !== "todas", geo !== "todos", agua !== "todos", condicao !== "todas", arquivo !== "ativos"].filter(Boolean).length;

  async function acompanharClima(id) {
    if (acompanhando.current.has(id)) return;
    acompanhando.current.add(id);
    try {
      for (let tentativa = 0; tentativa < 300; tentativa += 1) {
        const job = await fetchJSON(`/api/fazendas/${id}/clima/status`);
        setJobs((prev) => ({ ...prev, [id]: job }));
        if (["concluido", "erro", "nao_iniciado"].includes(job.status)) {
          if (job.status === "concluido") {
            await carregarFazendas();
            showToast("Condição climática atualizada.");
          } else if (job.status === "erro") {
            showToast(job.mensagem || "Falha no processamento climático.");
          }
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (erro) {
      showToast(erro.message || "Não foi possível acompanhar o processamento.");
    } finally {
      acompanhando.current.delete(id);
    }
  }

  useEffect(() => {
    let ativo = true;
    Promise.all(
      fazendas.filter((f) => !f.arquivada).map(async (f) => {
        try {
          const job = await fetchJSON(`/api/fazendas/${f.id}/clima/status`);
          if (!ativo) return;
          setJobs((prev) => ({ ...prev, [f.id]: job }));
          if (["aguardando", "processando"].includes(job.status))
            acompanharClima(String(f.id));
        } catch { /* status é complementar */ }
      }),
    );
    return () => { ativo = false; };
  }, [fazendas]);

  async function processarClima(ev, f) {
    ev.stopPropagation();
    const id = String(f.id);
    try {
      const job = await fetchJSON(`/api/fazendas/${id}/clima/processar`, {
        method: "POST",
      });
      setJobs((prev) => ({ ...prev, [id]: job }));
      showToast("Processamento climático iniciado em segundo plano.");
      acompanharClima(id);
    } catch (erro) {
      showToast(erro.message || "Não foi possível iniciar o processamento.");
    }
  }

  async function alternarArquivamento(ev, f) {
    ev.stopPropagation();
    if (!f.arquivada && !window.confirm(
      `Arquivar "${f.nome_fazenda}"? O histórico será preservado.`,
    )) return;
    const id = String(f.id);
    setArquivando(id);
    try {
      await fetchJSON(`/api/fazendas/${id}/arquivamento`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ arquivada: !f.arquivada }),
      });
      await carregarFazendas();
      showToast(f.arquivada ? "Fazenda restaurada." : "Fazenda arquivada sem excluir dados.");
    } catch (erro) {
      showToast(erro.message || "Não foi possível alterar o arquivamento.");
    } finally {
      setArquivando("");
    }
  }
  async function retry(ev, f) {
    ev.stopPropagation();
    const id = String(f.id);
    setReprocessando(id);
    try {
      const r = await fetchJSON(`/api/fazendas/${id}/geoespacial/recalcular`, {
        method: "POST",
      });
      await carregarFazendas();
      showToast(
        r.status === "sucesso"
          ? "Contexto territorial processado com sucesso."
          : "O contexto territorial continua indisponível.",
      );
    } catch {
      showToast("Não foi possível reprocessar o contexto territorial.");
    } finally {
      setReprocessando("");
    }
  }
  return (
    <>
      <PageHeader
        title="Clientes e Apólices"
        subtitle="Fazendas cadastradas e suas operações seguradas."
        actions={
          <button className="btn btn-red" onClick={onNovaFazenda}>
            <Icon name="plus" size={16} /> Nova fazenda
          </button>
        }
      />
      <div className="filters list-toolbar portfolio-toolbar">
        <div className="search">
          <span>
            <Icon name="search" size={17} />
          </span>
          <input
            placeholder="Nome, apólice, ID, CEP, cidade ou UF"
            aria-label="Buscar fazendas"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <div className="portfolio-filter-grid">
        <div className="field compact-field">
          <label>Operação</label>
          <select value={op} onChange={(e) => setOp(e.target.value)}>
            <option value="todos">Todas</option>
            <option value="campo">Campo</option>
            <option value="transporte">Transporte</option>
          </select>
        </div>
        <div className="field compact-field">
          <label>UF</label>
          <select value={uf} onChange={(e) => setUf(e.target.value)}>
            <option value="todas">Todas</option>
            {ufs.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="field compact-field">
          <label>Território</label>
          <select value={geo} onChange={(e) => setGeo(e.target.value)}>
            <option value="todos">Todos</option>
            <option value="pronto">Pronto</option>
            <option value="pendente">Pendente</option>
          </select>
        </div>
        <div className="field compact-field">
          <label>Proximidade de água</label>
          <select value={agua} onChange={(e) => setAgua(e.target.value)}>
            <option value="todos">Todas</option>
            <option value="sim">Sinalizada</option>
            <option value="nao">Não sinalizada</option>
          </select>
        </div>
        <div className="field compact-field">
          <label>Condição</label>
          <select value={condicao} onChange={(e) => setCondicao(e.target.value)}>
            <option value="todas">Todas</option>
            <option value="ideais">Ideal</option>
            <option value="atencao">Atenção</option>
            <option value="restricao">Restrição</option>
          </select>
        </div>
        <div className="field compact-field">
          <label>Ordenar</label>
          <select value={ordem} onChange={(e) => setOrdem(e.target.value)}>
            <option value="nome">Nome A–Z</option>
            <option value="score">Maior score</option>
            <option value="cidade">Cidade A–Z</option>
          </select>
        </div>
        <div className="field compact-field">
          <label>Cadastro</label>
          <select value={arquivo} onChange={(e) => setArquivo(e.target.value)}>
            <option value="ativos">Ativas</option>
            <option value="arquivados">Arquivadas</option>
            <option value="todos">Todas</option>
          </select>
        </div>
        </div>
        <div className="portfolio-filter-footer">
          <span><b>{filtradas.length}</b> de {fazendas.length} propriedade(s)</span>
          {filtrosAtivos > 0 && (
            <button type="button" className="filter-clear" onClick={limparFiltros}>
              Limpar {filtrosAtivos} filtro(s)
            </button>
          )}
        </div>
      </div>
      <div className="table-shell">
        <table className="portfolio-table">
          <thead>
            <tr>
              <th>Fazenda</th>
              <th>Apólice</th>
              <th>Localização</th>
              <th>Operação</th>
              <th>Contexto territorial</th>
              <th>Condição atual</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {carregando && Array.from({ length: 4 }, (_, indice) => (
              <tr className="skeleton-row" key={`skeleton-${indice}`}>
                {Array.from({ length: 7 }, (__, coluna) => (
                  <td key={coluna}><span className="skeleton-line" /></td>
                ))}
              </tr>
            ))}
            {!carregando && filtradas.map((f) => {
              const s = scorePreview[f.id],
                pode = permiteReprocessarGeoespacial(f.status_geoespacial),
                job = jobs[f.id],
                processando = ["aguardando", "processando"].includes(job?.status);
              return (
                <tr
                  className={`${f.arquivada ? "is-archived" : "clickable"}`}
                  key={f.id}
                  onClick={() => {
                    if (f.arquivada) return;
                    setSelected(String(f.id));
                    setPage("operacoes");
                  }}
                >
                  <td data-label="Fazenda">
                    <b>{f.nome_fazenda}</b>
                    <small className="table-sub">
                      ID {f.id_fazenda || f.id}
                    </small>
                  </td>
                  <td data-label="Apólices">
                    <div className="policy-badges">
                      {(f.apolices || [f.numero_apolice]).map((numero) => (
                        <span className="policy-badge" key={numero}>
                          {numero}
                          <a
                            href={`${API_URL}/api/fazendas/${f.id}/relatorio.pdf?apolice=${encodeURIComponent(numero)}`}
                            onClick={(event) => event.stopPropagation()}
                            title={`Exportar relatório da apólice ${numero}`}
                            aria-label={`Exportar PDF da apólice ${numero}`}
                          >PDF</a>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td data-label="Localização">
                    {f.cidade} / {f.uf}
                    <small className="table-sub">CEP {f.cep}</small>
                  </td>
                  <td data-label="Operação">
                    <span
                      className={
                        f.tipo_operacao === "campo"
                          ? "badge green"
                          : "badge blue"
                      }
                    >
                      {f.tipo_operacao}
                    </span>
                    {f.proximidade_agua && (
                      <span className="badge water">água</span>
                    )}
                  </td>
                  <td data-label="Contexto territorial">
                    <Status status={f.status_geoespacial} />
                    {pode && (
                      <button
                        className="geo-retry"
                        type="button"
                        disabled={reprocessando === String(f.id)}
                        onClick={(e) => retry(e, f)}
                      >
                        {reprocessando === String(f.id)
                          ? "Reprocessando…"
                          : "Reprocessar"}
                      </button>
                    )}
                  </td>
                  <td data-label="Condição atual">
                    {s ? (
                      <>
                        <b style={{ color: cor(s.condicao_atual) }}>
                          {s.score}/100
                        </b>
                        <small
                          className="table-sub"
                          style={{ color: cor(s.condicao_atual) }}
                        >
                          {s.condicao_atual}
                        </small>
                        <small className="condition-meta">
                          Atualizado em {formatarData(s.data_referencia)}
                        </small>
                        <small className={`score-source ${s.origem_dados === "simulado" ? "is-simulated" : ""}`}>
                          {origemScore(s.origem_dados)}
                        </small>
                      </>
                    ) : (
                      <span className="soft-text">Aguardando leitura</span>
                    )}
                    {!f.arquivada && (
                      <button
                        className="climate-run"
                        type="button"
                        disabled={processando}
                        onClick={(event) => processarClima(event, f)}
                      >
                        {processando ? job.mensagem : "Atualizar clima"}
                      </button>
                    )}
                    {processando && (
                      <div className="job-progress" aria-label={`Progresso ${job.progresso || 0}%`}>
                        <span style={{ width: `${job.progresso || 0}%` }} />
                        <small>{job.progresso || 0}%</small>
                      </div>
                    )}
                  </td>
                  <td className="row-action" data-label="Ação">
                    {!f.arquivada && (
                      <button
                        type="button"
                        className="row-edit"
                        onClick={(event) => {
                          event.stopPropagation();
                          onEditarFazenda(f);
                        }}
                      >Editar</button>
                    )}
                    <button
                      type="button"
                      className="row-archive"
                      disabled={arquivando === String(f.id)}
                      onClick={(event) => alternarArquivamento(event, f)}
                    >
                      {f.arquivada ? "Restaurar" : "Arquivar"}
                    </button>
                    {!f.arquivada && <span>Ver <Icon name="arrow" size={14} /></span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!carregando && !filtradas.length && (
          <div className="empty-state">
            <Icon name="search" size={24} />
            <b>Nenhuma fazenda encontrada</b>
            <span>Ajuste a busca ou o filtro de operação.</span>
          </div>
        )}
      </div>
      <div className="footer-note">
        {filtradas.length} de {fazendas.length} fazenda(s) exibida(s).
      </div>
    </>
  );
}
