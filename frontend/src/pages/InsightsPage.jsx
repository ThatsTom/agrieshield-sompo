import { useMemo } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "../components/ConceptHelp";
import { numero } from "../utils/format";
export function InsightsPage({ fazendas, dashboard }) {
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
  return (
    <>
      <PageHeader
        eyebrow="Análise"
        title="Insights"
        subtitle="Leituras rápidas do portfólio cadastrado e da condição operacional selecionada."
      />
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
              <header>
                <span>Campo</span>
                <b>{r.campo}</b>
              </header>
              <i>
                <span
                  style={{
                    width: `${r.total ? (r.campo / r.total) * 100 : 0}%`,
                  }}
                />
              </i>
            </div>
            <div>
              <header>
                <span>Transporte</span>
                <b>{r.transporte}</b>
              </header>
              <i>
                <span
                  style={{
                    width: `${r.total ? (r.transporte / r.total) * 100 : 0}%`,
                  }}
                />
              </i>
            </div>
            <div>
              <header>
                <span>Contexto territorial pronto</span>
                <b>{r.geo}</b>
              </header>
              <i>
                <span
                  style={{ width: `${r.total ? (r.geo / r.total) * 100 : 0}%` }}
                />
              </i>
            </div>
          </div>
          <div className="panel-foot-note">
            Estados presentes: {r.ufs.join(", ") || "—"}
          </div>
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
              <div className="ideal" style={{ flex: d.ideais || 0 }}>
                <b>{d.ideais || 0}</b>
                <span>Ideais</span>
              </div>
              <div className="attention" style={{ flex: d.atencao || 0 }}>
                <b>{d.atencao || 0}</b>
                <span>Atenção</span>
              </div>
              <div className="restriction" style={{ flex: d.restricao || 0 }}>
                <b>{d.restricao || 0}</b>
                <span>Restrição</span>
              </div>
            </div>
          ) : (
            <div className="empty-state inline-empty">
              <Icon name="chart" size={22} />
              <div>
                <b>Sem distribuição disponível</b>
                <span>Selecione uma fazenda com score calculado.</span>
              </div>
            </div>
          )}
          <div className="panel-foot-note">
            Score atual: <b>{dashboard?.score?.score ?? "—"}/100</b> ·{" "}
            {dashboard?.score?.condicao_atual || "sem leitura"}
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
                  <div className="driver-rank">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <div>
                    <b>{f.fator}</b>
                    <p>{f.detalhe}</p>
                  </div>
                  <div className="driver-impact">
                    <span>{f.impacto}</span>
                    {f.pontos != null && <b>{numero(f.pontos, 0)} pts</b>}
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <Icon name="trend" size={24} />
                <b>Sem fatores publicados</b>
                <span>
                  A API ainda não retornou fatores de risco para a leitura
                  atual.
                </span>
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
