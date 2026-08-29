import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "../components/ConceptHelp";
import { FazendaSearch } from "../components/FazendaSearch";
import { dataBr, numero } from "../utils/format";
const ordem = { Alta: 0, Média: 1, Baixa: 2 };
const cls = (s) =>
  String(s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
export function AlertasPage({
  fazendas,
  selected,
  setSelected,
  dashboard,
  fazenda,
}) {
  const alertas = [...(dashboard?.alertas || [])].sort(
      (a, b) => (ordem[a.severidade] ?? 9) - (ordem[b.severidade] ?? 9),
    ),
    previsao = dashboard?.previsao_5d || [],
    altas = alertas.filter((a) => a.severidade === "Alta").length;
  return (
    <>
      <PageHeader
        eyebrow="Monitoramento"
        title="Alertas"
        subtitle="Priorize eventos meteorológicos e operacionais da propriedade selecionada."
      />
      <div className="filters">
        <FazendaSearch
          fazendas={fazendas}
          selected={selected}
          onSelect={setSelected}
          label="Localizar propriedade"
        />
        <div className="filter-summary">
          <span>{alertas.length} <ConceptHelp conceito="alertas_ativos" /></span>
          <small>alertas ativos</small>
        </div>
        <div className="filter-summary danger">
          <span>{altas} <ConceptHelp conceito="severidade_alerta" /></span>
          <small>alta severidade</small>
        </div>
      </div>
      <div className="alerts-layout">
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>Fila de atenção</span>
               <h2>{fazenda?.nome_fazenda}</h2>
            </div>
            <span className="badge red">{alertas.length} ativo(s)</span>
          </div>
          <div className="alert-list-page">
            {alertas.length ? (
              alertas.map((a, i) => (
                <article
                  className={`alert-row severity-${cls(a.severidade)}`}
                  key={`${a.tipo}-${i}`}
                >
                  <div className="alert-icon">
                    <Icon name="warning" />
                  </div>
                  <div className="alert-main">
                    <div className="alert-title-row">
                      <b>{a.tipo}</b>
                      <span
                        className={`severity-badge severity-${cls(a.severidade)}`}
                      >
                        {a.severidade}
                      </span>
                    </div>
                    <p>{a.detalhe}</p>
                    <small>{a.data || "Período atual"}</small>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state">
                <Icon name="check" size={24} />
                <b>Sem alertas ativos</b>
                <span>Nenhum evento foi publicado para a leitura atual.</span>
              </div>
            )}
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>Previsão</span>
              <h2>
                Próximos dias <ConceptHelp conceito="previsao_meteorologica" />
              </h2>
            </div>
            <Icon name="cloud" />
          </div>
          <div className="forecast-list">
            {previsao.length ? (
              previsao.slice(0, 5).map((dia, i) => (
                <article key={dia.data || i}>
                  <div>
                    <b>{dataBr(dia.data)}</b>
                    <small>
                      {dia.descricao ||
                        dia.condicao ||
                        "Previsão meteorológica"}
                    </small>
                  </div>
                  <div className="forecast-values">
                    <span>
                      <small>Chuva</small>
                      <b>{numero(dia.precipitacao_mm, 1)} mm</b>
                    </span>
                    {dia.probabilidade_precipitacao_pct != null && (
                      <span>
                        <small>Prob.</small>
                        <b>{numero(dia.probabilidade_precipitacao_pct, 0)}%</b>
                      </span>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-state inline-empty">
                <Icon name="cloud" size={23} />
                <div>
                  <b>Previsão não retornada</b>
                  <span>
                    A API não publicou dias de previsão nesta consulta.
                  </span>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
      <div className="notice-card">
        <Icon name="info" />
        <div>
          <b>Como interpretar os alertas</b>
          <p>
            A severidade auxilia na priorização operacional. A decisão de
            subscrição deve considerar o conjunto de dados e a análise técnica.
          </p>
        </div>
      </div>
    </>
  );
}
