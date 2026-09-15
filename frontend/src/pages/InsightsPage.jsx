import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { FazendaSearch } from "../components/FazendaSearch";
import { ConceptHelp } from "../components/ConceptHelp";
import { fetchJSON } from "../api/core";
import { numero } from "../utils/format";

const ROTULOS_PRIORIDADE = {
  imediata: "Ação imediata",
  hoje: "Ainda hoje",
  proximos_dias: "Próximos dias",
  monitorar: "Monitorar",
};

const ROTULOS_ATENCAO = {
  baixo: "Baixa atenção",
  moderado: "Atenção moderada",
  alto: "Alta atenção",
  critico: "Atenção crítica",
};

function formatarData(valor) {
  if (!valor) return "";
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return "";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(data);
}

function formatarDiaPrevisao(valor) {
  if (!valor) return { semana: "Dia", data: "—" };
  const data = new Date(`${String(valor).slice(0, 10)}T12:00:00`);
  if (Number.isNaN(data.getTime())) {
    return { semana: "Dia", data: String(valor) };
  }
  return {
    semana: new Intl.DateTimeFormat("pt-BR", { weekday: "short" })
      .format(data)
      .replace(".", ""),
    data: new Intl.DateTimeFormat("pt-BR", {
      day: "2-digit",
      month: "2-digit",
    }).format(data),
  };
}

function classeDiaPrevisao(dia) {
  const chuva = Number(dia?.precipitacao_mm);
  const probabilidade = Number(dia?.prob_precip_pct);
  if (chuva >= 20 || probabilidade >= 70) return "is-alert";
  if (chuva >= 5 || probabilidade >= 40) return "is-attention";
  return "is-stable";
}

function PrevisaoSeteDias({ dashboard, fazenda }) {
  const dias = dashboard?.previsao_7d || [];
  const oficial = dashboard?.origem_previsao === "api_open_meteo";
  const chuvaValida = dias
    .map((dia) => Number(dia.precipitacao_mm))
    .filter(Number.isFinite);
  const probabilidadeValida = dias
    .map((dia) => Number(dia.prob_precip_pct))
    .filter(Number.isFinite);
  const temperaturaValida = dias
    .map((dia) => Number(dia.temp_max_c))
    .filter(Number.isFinite);
  const chuvaAcumulada = chuvaValida.reduce((total, valor) => total + valor, 0);
  const maiorProbabilidade = probabilidadeValida.length
    ? Math.max(...probabilidadeValida)
    : null;
  const maiorTemperatura = temperaturaValida.length
    ? Math.max(...temperaturaValida)
    : null;

  return (
    <section className="weather-insights-card" aria-labelledby="weather-insights-title">
      <header className="weather-insights-head">
        <div className="weather-insights-heading">
          <span className="weather-insights-symbol">
            <Icon name="cloud" size={20} />
          </span>
          <div>
            <span>Open-Meteo · janela operacional</span>
            <h2 id="weather-insights-title">Previsão dos próximos 7 dias</h2>
            <p>
              Condições previstas para {fazenda?.nome_fazenda || "a propriedade selecionada"},
              com foco em chuva e temperatura máxima.
            </p>
          </div>
        </div>
        <div className="weather-source-status">
          <span className={oficial ? "is-live" : ""}>
            {oficial ? "Dados oficiais disponíveis" : "Fonte indisponível"}
          </span>
          {dashboard?.previsao_atualizada_em && (
            <small>Atualizada em {formatarData(dashboard.previsao_atualizada_em)}</small>
          )}
        </div>
      </header>

      {!dashboard ? (
        <div className="weather-insights-state" role="status">
          <span className="ai-loading-dot is-active" />
          <div>
            <b>Consultando a previsão meteorológica</b>
            <p>A leitura será exibida assim que os dados da fazenda carregarem.</p>
          </div>
        </div>
      ) : oficial && dias.length === 7 ? (
        <div className="weather-insights-content">
          <div className="weather-summary" aria-label="Resumo da previsão de sete dias">
            <div>
              <span>Chuva acumulada</span>
              <b>{chuvaValida.length ? `${numero(chuvaAcumulada, 1)} mm` : "—"}</b>
            </div>
            <div>
              <span>Maior probabilidade</span>
              <b>{maiorProbabilidade == null ? "—" : `${numero(maiorProbabilidade, 0)}%`}</b>
            </div>
            <div>
              <span>Máxima do período</span>
              <b>{maiorTemperatura == null ? "—" : `${numero(maiorTemperatura, 1)}°C`}</b>
            </div>
          </div>
          <div className="weather-days" role="list" aria-label="Previsão diária">
            {dias.map((dia, indice) => {
              const rotulo = formatarDiaPrevisao(dia.data);
              return (
                <article
                  className={classeDiaPrevisao(dia)}
                  key={dia.data || indice}
                  role="listitem"
                >
                  <header>
                    <span>{rotulo.semana}</span>
                    <b>{rotulo.data}</b>
                  </header>
                  <div className="weather-day-temperature">
                    <Icon name="cloud" size={18} />
                    <strong>{dia.temp_max_c == null ? "—" : `${numero(dia.temp_max_c, 1)}°`}</strong>
                  </div>
                  <dl>
                    <div>
                      <dt>Chuva</dt>
                      <dd>{dia.precipitacao_mm == null ? "—" : `${numero(dia.precipitacao_mm, 1)} mm`}</dd>
                    </div>
                    <div>
                      <dt>Prob.</dt>
                      <dd>{dia.prob_precip_pct == null ? "—" : `${numero(dia.prob_precip_pct, 0)}%`}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}
          </div>
          <footer className="weather-insights-footer">
            <span>Previsões podem mudar; confirme as condições antes de orientar a operação.</span>
            <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
              Fonte: Open-Meteo
            </a>
          </footer>
        </div>
      ) : (
        <div className="weather-insights-state is-unavailable" role="status">
          <Icon name="info" size={19} />
          <div>
            <b>Previsão de 7 dias temporariamente indisponível</b>
            <p>Os demais Insights continuam disponíveis sem usar dados meteorológicos simulados.</p>
          </div>
        </div>
      )}
    </section>
  );
}

function PainelInsightsIA({ selected, fazenda, dashboard }) {
  const [resultado, setResultado] = useState(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const requisicaoAtual = useRef(0);

  const carregar = useCallback(
    async (forcar = false) => {
      if (!selected) return;
      const numeroRequisicao = ++requisicaoAtual.current;
      setCarregando(true);
      setErro("");
      try {
        const dados = await fetchJSON(
          `/api/fazendas/${selected}/insights-ia`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ forcar }),
          },
        );
        if (numeroRequisicao === requisicaoAtual.current) setResultado(dados);
      } catch (exc) {
        if (numeroRequisicao === requisicaoAtual.current) {
          setErro(
            exc?.message ||
              "Não foi possível gerar o briefing inteligente neste momento.",
          );
        }
      } finally {
        if (numeroRequisicao === requisicaoAtual.current) setCarregando(false);
      }
    },
    [selected],
  );

  useEffect(() => {
    setResultado(null);
    setErro("");
    if (selected && dashboard) carregar(false);
    return () => {
      requisicaoAtual.current += 1;
    };
  }, [selected, dashboard, carregar]);

  const insight = resultado?.insight;
  const nivel = insight?.nivel_atencao || "moderado";

  return (
    <section className="ai-insights-card" aria-labelledby="ai-insights-title">
      <header className="ai-insights-head">
        <div className="ai-insights-heading">
          <span className="ai-insights-symbol">
            <Icon name="trend" size={19} />
          </span>
          <div>
            <span>Assistente de decisão · GPT-4o mini</span>
            <h2 id="ai-insights-title">
              Briefing prático de {fazenda?.nome_fazenda || "risco rural"}
            </h2>
            <p>
              O score, os alertas e o contexto territorial foram traduzidos em
              pontos de conversa e próximos passos.
            </p>
          </div>
        </div>
        <button
          className="btn btn-ghost ai-refresh-button"
          type="button"
          disabled={carregando || !dashboard}
          onClick={() => carregar(true)}
        >
          <Icon name="refresh" size={15} />
          {carregando ? "Analisando..." : "Atualizar análise"}
        </button>
      </header>

      {!dashboard && (
        <div className="ai-insights-state" role="status">
          <span className="ai-loading-dot" />
          <div>
            <b>Preparando os dados da fazenda</b>
            <p>O briefing será criado assim que a leitura operacional carregar.</p>
          </div>
        </div>
      )}

      {carregando && !insight && (
        <div className="ai-insights-state" role="status">
          <span className="ai-loading-dot is-active" />
          <div>
            <b>Transformando os dados em ações práticas</b>
            <p>Isso pode levar alguns segundos na primeira análise.</p>
          </div>
        </div>
      )}

      {erro && (
        <div className="ai-insights-error" role="alert">
          <Icon name="warning" size={18} />
          <div>
            <b>A análise por IA não está disponível</b>
            <p>{erro}</p>
          </div>
          {!resultado && (
            <button type="button" onClick={() => carregar(false)}>
              Tentar novamente
            </button>
          )}
        </div>
      )}

      {insight && (
        <div className="ai-insights-content">
          <div className="ai-summary-grid">
            <div>
              <span className="ai-section-label">Resumo executivo</span>
              <h3>{insight.resumo_executivo}</h3>
              <p>{insight.leitura_principal}</p>
            </div>
            <aside className={`ai-attention-level is-${nivel}`}>
              <small>Nível de atenção sugerido</small>
              <b>{ROTULOS_ATENCAO[nivel] || nivel}</b>
              <span>Baseado na leitura disponível, não em probabilidade de sinistro.</span>
            </aside>
          </div>

          <div className="ai-insights-layout">
            <div className="ai-priorities">
              <div className="ai-section-title">
                <span className="ai-section-label">Plano de conversa</span>
                <h3>Prioridades para o consultor</h3>
              </div>
              {(insight.prioridades || []).map((item, indice) => (
                <article key={`${item.titulo}-${indice}`}>
                  <div className="ai-priority-rank">
                    {String(indice + 1).padStart(2, "0")}
                  </div>
                  <div>
                    <span className={`ai-priority-tag is-${item.prioridade}`}>
                      {ROTULOS_PRIORIDADE[item.prioridade] || item.prioridade}
                    </span>
                    <h4>{item.titulo}</h4>
                    <p>{item.motivo}</p>
                    <div className="ai-recommended-action">
                      <Icon name="arrow" size={14} />
                      <span>
                        <b>Próximo passo:</b> {item.acao_recomendada}
                      </span>
                    </div>
                    <small>
                      <b>Evidência usada:</b> {item.dado_base}
                    </small>
                  </div>
                </article>
              ))}
            </div>

            <aside className="ai-support-column">
              <section>
                <div className="ai-support-icon is-positive">
                  <Icon name="check" size={15} />
                </div>
                <div>
                  <h3>Sinais positivos</h3>
                  <ul>
                    {(insight.pontos_positivos || []).map((item, indice) => (
                      <li key={`${item}-${indice}`}>{item}</li>
                    ))}
                  </ul>
                </div>
              </section>
              <section>
                <div className="ai-support-icon is-question">
                  <Icon name="info" size={15} />
                </div>
                <div>
                  <h3>Perguntas para validar</h3>
                  <ol>
                    {(insight.perguntas_consultor || []).map((item, indice) => (
                      <li key={`${item}-${indice}`}>{item}</li>
                    ))}
                  </ol>
                </div>
              </section>
            </aside>
          </div>

          <div className="ai-limitations">
            <Icon name="shield" size={16} />
            <p>
              <b>Limites da leitura:</b>{" "}
              {(insight.limitacoes || []).join(" · ")}
            </p>
          </div>
          <footer className="ai-insights-footer">
            <span>
              Análise assistida por IA; confirme os dados antes de orientar o segurado.
            </span>
            <span>
              {resultado.cache ? "Leitura reaproveitada" : "Nova leitura"}
              {formatarData(resultado.gerado_em)
                ? ` · ${formatarData(resultado.gerado_em)}`
                : ""}
            </span>
          </footer>
        </div>
      )}
    </section>
  );
}

export function InsightsPage({ fazendas, dashboard, selected, setSelected, fazenda }) {
  const r = useMemo(() => {
    const total = fazendas.length,
      campo = fazendas.filter((f) => f.tipo_operacao === "campo").length,
      geo = fazendas.filter(
        (f) => String(f.status_geoespacial).toUpperCase() === "SUCESSO",
      ).length;
    return {
      total,
      campo,
      transporte: total - campo,
      agua: fazendas.filter((f) => f.proximidade_agua).length,
      geo,
      ufs: [...new Set(fazendas.map((f) => f.uf).filter(Boolean))],
    };
  }, [fazendas]);
  const fatores = dashboard?.score?.fatores_risco || [],
    d = dashboard?.score?.distribuicao_30d || {},
    totalDias = d.total || 0;
  const indiceSelecionado = fazendas.findIndex(
    (item) => String(item.id) === String(selected),
  );
  const moverSelecao = (direcao) => {
    if (!fazendas.length || !setSelected) return;
    const base = indiceSelecionado >= 0 ? indiceSelecionado : 0;
    const proximo = (base + direcao + fazendas.length) % fazendas.length;
    setSelected(String(fazendas[proximo].id));
  };
  return (
    <>
      <PageHeader
        eyebrow="Análise"
        title="Insights"
        subtitle="Um briefing inteligente para orientar a conversa, apoiado pelos indicadores calculados da fazenda e do portfólio."
      />

      <section className="filters insights-farm-toolbar" aria-label="Fazenda analisada">
        <FazendaSearch
          fazendas={fazendas}
          selected={selected}
          onSelect={(id) => setSelected?.(id)}
          label="Analisar fazenda"
          showFilters={false}
        />
        <div className="insights-farm-summary" aria-live="polite">
          <span className="farm-summary-icon"><Icon name="map" size={17} /></span>
          <span>
            <small>Leitura em foco</small>
            <b>{fazenda?.nome_fazenda || "Nenhuma fazenda selecionada"}</b>
            <em>{fazenda ? `${fazenda.cidade || "Localidade não informada"} / ${fazenda.uf || "—"}` : "Selecione uma propriedade"}</em>
          </span>
        </div>
        {fazendas.length > 1 && (
          <div className="farm-stepper" aria-label="Navegação rápida entre fazendas">
            <button type="button" onClick={() => moverSelecao(-1)} aria-label="Fazenda anterior">
              <Icon name="chevron" size={17} />
            </button>
            <span>{Math.max(indiceSelecionado + 1, 1)} de {fazendas.length}</span>
            <button type="button" onClick={() => moverSelecao(1)} aria-label="Próxima fazenda">
              <Icon name="chevron" size={17} />
            </button>
          </div>
        )}
      </section>

      <PainelInsightsIA
        selected={selected}
        fazenda={fazenda}
        dashboard={dashboard}
      />

      <PrevisaoSeteDias dashboard={dashboard} fazenda={fazenda} />

      <div className="kpi-grid">
        <div className="kpi-card">
          <Icon name="users" />
          <span>Portfólio <ConceptHelp conceito="cadastro_operacional" /></span>
          <b>{r.total}</b>
          <small>propriedades cadastradas</small>
        </div>
        <div className="kpi-card">
          <Icon name="map" />
          <span>Cobertura territorial <ConceptHelp conceito="cobertura_territorial" /></span>
          <b>{r.total ? Math.round((r.geo / r.total) * 100) : 0}%</b>
          <small>{r.geo} contexto(s) pronto(s)</small>
        </div>
        <div className="kpi-card">
          <Icon name="activity" />
          <span>Operação em campo <ConceptHelp conceito="tipo_operacao" /></span>
          <b>{r.campo}</b>
          <small>{r.transporte} em transporte</small>
        </div>
        <div className="kpi-card">
          <Icon name="cloud" />
          <span>Proximidade de água <ConceptHelp conceito="proximidade_agua_cadastral" /></span>
          <b>{r.agua}</b>
          <small>cadastros sinalizados</small>
        </div>
      </div>
      <div className="insights-grid">
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>Portfólio</span>
              <h2>Distribuição cadastral <ConceptHelp conceito="cadastro_operacional" /></h2>
            </div>
          </div>
          <div className="bar-insights">
            <div>
              <header><span>Campo</span><b>{r.campo}</b></header>
              <i><span style={{ width: `${r.total ? (r.campo / r.total) * 100 : 0}%` }} /></i>
            </div>
            <div>
              <header><span>Transporte</span><b>{r.transporte}</b></header>
              <i><span style={{ width: `${r.total ? (r.transporte / r.total) * 100 : 0}%` }} /></i>
            </div>
            <div>
              <header><span>Contexto territorial pronto</span><b>{r.geo}</b></header>
              <i><span style={{ width: `${r.total ? (r.geo / r.total) * 100 : 0}%` }} /></i>
            </div>
          </div>
          <div className="panel-foot-note">Estados presentes: {r.ufs.join(", ") || "—"}</div>
        </section>
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>Janela atual</span>
              <h2>Condição nos últimos 30 dias <ConceptHelp conceito="distribuicao_condicoes" /></h2>
            </div>
          </div>
          {totalDias ? (
            <div className="condition-bars">
              <div className="ideal" style={{ flex: d.ideais || 0 }}><b>{d.ideais || 0}</b><span>Ideais</span></div>
              <div className="attention" style={{ flex: d.atencao || 0 }}><b>{d.atencao || 0}</b><span>Atenção</span></div>
              <div className="restriction" style={{ flex: d.restricao || 0 }}><b>{d.restricao || 0}</b><span>Restrição</span></div>
            </div>
          ) : (
            <div className="empty-state inline-empty">
              <Icon name="chart" size={22} />
              <div><b>Sem distribuição disponível</b><span>Selecione uma fazenda com score calculado.</span></div>
            </div>
          )}
          <div className="panel-foot-note">
            Score atual: <b>{dashboard?.score?.score ?? "—"}/100</b> · {dashboard?.score?.condicao_atual || "sem leitura"}
          </div>
        </section>
        <section className="panel-card wide">
          <div className="panel-head">
            <div>
              <span>Drivers do risco</span>
              <h2>Fatores que mais pesam na leitura atual <ConceptHelp conceito="fatores_risco" /></h2>
            </div>
          </div>
          <div className="driver-list">
            {fatores.length ? (
              fatores.map((f, i) => (
                <article key={`${f.fator}-${i}`}>
                  <div className="driver-rank">{String(i + 1).padStart(2, "0")}</div>
                  <div><b>{f.fator}</b><p>{f.detalhe}</p></div>
                  <div className="driver-impact"><span>{f.impacto}</span>{f.pontos != null && <b>{numero(f.pontos, 0)} pts</b>}</div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <Icon name="trend" size={24} />
                <b>Sem fatores publicados</b>
                <span>A API ainda não retornou fatores de risco para a leitura atual.</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
