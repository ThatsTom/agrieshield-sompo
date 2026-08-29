import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "../components/ConceptHelp";
import { FazendaSearch } from "../components/FazendaSearch";
const corCondicao = (c) =>
  c === "RESTRIÇÃO"
    ? "var(--red)"
    : c === "ATENÇÃO"
      ? "var(--amber)"
      : "var(--green)";
const impacto = (i) =>
  String(i).startsWith("Alto")
    ? { cls: "high", w: "90%", color: "var(--red)" }
    : String(i).startsWith("Médio")
      ? { cls: "med", w: "60%", color: "var(--amber)" }
      : { cls: "low", w: "32%", color: "var(--green)" };
function Condicao({ s, f, onNavigate }) {
  const pct = Math.max(0, Math.min(1, s.score / 100)),
    dash = 182 * pct;
  return (
    <div className="card dashboard-card">
      <h3>
        Condição Operacional Atual <ConceptHelp conceito="condicao_operacional" />
      </h3>
      <div className="gauge-wrap">
        <div className="gauge">
          <svg viewBox="0 0 140 90">
            <path
              d="M12 78 A58 58 0 0 1 128 78"
              fill="none"
              stroke="#eef1f5"
              strokeWidth="13"
              strokeLinecap="round"
            />
            <path
              d="M12 78 A58 58 0 0 1 128 78"
              fill="none"
              stroke="url(#g)"
              strokeWidth="13"
              strokeLinecap="round"
              strokeDasharray={`${dash} 999`}
            />
            <defs>
              <linearGradient id="g" x1="0" x2="1">
                <stop offset="0" stopColor="#21a366" />
                <stop offset=".6" stopColor="#f0a020" />
                <stop offset="1" stopColor="#e0392b" />
              </linearGradient>
            </defs>
          </svg>
          <div className="val">
            <b>{s.score}</b>
            <span>/100</span>
          </div>
        </div>
        <div className="op-meta">
          <div
            className="cond"
            style={{ color: corCondicao(s.condicao_atual) }}
          >
            <Icon name="warning" size={15} />
            {s.condicao_atual}
          </div>
          <div>
            <b>{f?.nome_fazenda || s.fazenda?.nome}</b>
          </div>
          <div>Apólice: {f?.numero_apolice || s.fazenda?.apolice}</div>
          <div>
            {f?.cidade || s.fazenda?.cidade} / {f?.uf || s.fazenda?.uf}
          </div>
          <div>
            Operação:{" "}
            {f?.tipo_operacao === "transporte" ? "Transporte" : "Campo"}
          </div>
        </div>
      </div>
      <div className="card-foot split-foot">
        <span
          className={s.origem_dados === "simulado" ? "badge warn" : "badge"}
        >
          ● {s.origem_dados || "nasa_power"}
        </span>
        <button className="text-link" onClick={() => onNavigate("operacoes")}>
          Ver operação <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
function Distribuicao({ d, onNavigate }) {
  const total = d.total || 1,
    pi = d.ideais / total,
    pa = d.atencao / total,
    pr = d.restricao / total,
    C = 2 * Math.PI * 52;
  return (
    <div className="card dashboard-card">
      <h3>
        Distribuição de Condições (30 dias){" "}
        <ConceptHelp conceito="distribuicao_condicoes" />
      </h3>
      <div className="donut-wrap">
        <svg viewBox="0 0 130 130" className="donut">
          <circle
            cx="65"
            cy="65"
            r="52"
            fill="none"
            stroke="#21a366"
            strokeWidth="20"
            strokeDasharray={`${C * pi} ${C}`}
            transform="rotate(-90 65 65)"
          />
          <circle
            cx="65"
            cy="65"
            r="52"
            fill="none"
            stroke="#f0a020"
            strokeWidth="20"
            strokeDasharray={`${C * pa} ${C}`}
            strokeDashoffset={-C * pi}
            transform="rotate(-90 65 65)"
          />
          <circle
            cx="65"
            cy="65"
            r="52"
            fill="none"
            stroke="#e0392b"
            strokeWidth="20"
            strokeDasharray={`${C * pr} ${C}`}
            strokeDashoffset={-C * (pi + pa)}
            transform="rotate(-90 65 65)"
          />
        </svg>
        <div className="legend">
          <div className="li">
            <span className="dot" style={{ background: "#21a366" }} />
            Ideais{" "}
            <span className="pct">
              {Math.round(pi * 100)}% ({d.ideais})
            </span>
          </div>
          <div className="li">
            <span className="dot" style={{ background: "#f0a020" }} />
            Atenção{" "}
            <span className="pct">
              {Math.round(pa * 100)}% ({d.atencao})
            </span>
          </div>
          <div className="li">
            <span className="dot" style={{ background: "#e0392b" }} />
            Restrição{" "}
            <span className="pct">
              {Math.round(pr * 100)}% ({d.restricao})
            </span>
          </div>
        </div>
      </div>
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("insights")}>
          Ver análise completa <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
function Alertas({ itens, onNavigate }) {
  return (
    <div className="card dashboard-card">
      <h3>
        Alertas Ativos <ConceptHelp conceito="alertas_ativos" />
      </h3>
      {itens.length ? (
        itens.slice(0, 3).map((a, i) => (
          <div className="alert" key={`${a.tipo}-${i}`}>
            <div className="ic">
              <Icon name="warning" size={17} />
            </div>
            <div>
              <div className="tt">{a.tipo}</div>
              <div className="ds">{a.detalhe}</div>
            </div>
            <div className={`sev ${a.severidade === "Alta" ? "high" : "med"}`}>
              {a.severidade}
              <span className="tm">{a.data}</span>
            </div>
          </div>
        ))
      ) : (
        <p className="loading">Sem alertas ativos.</p>
      )}
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("alertas")}>
          Ver todos os alertas <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
function Fatores({ itens, onNavigate }) {
  return (
    <div className="card dashboard-card">
      <h3>
        Principais Fatores de Risco <ConceptHelp conceito="fatores_risco" />
      </h3>
      {(itens || []).slice(0, 3).map((f, i) => {
        const st = impacto(f.impacto);
        return (
          <div className="factor" key={`${f.fator}-${i}`}>
            <div className="fic">
              <Icon name="cloud" size={17} />
            </div>
            <div>
              <div className="fn">{f.fator}</div>
              <div className="fd">{f.detalhe}</div>
            </div>
            <div className="fright">
              <div className={st.cls}>{f.impacto}</div>
              <div className="bar">
                <i style={{ width: st.w, background: st.color }} />
              </div>
            </div>
          </div>
        );
      })}
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("riscos")}>
          Ver modelo de risco <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
function Recomenda({ onNavigate }) {
  return (
    <div className="card dashboard-card">
      <h3>
        Recomendações para a Operação <ConceptHelp conceito="recomendacoes" />
      </h3>
      <div className="rec">
        <div className="ric">
          <Icon name="check" size={17} />
        </div>
        <div>
          <div className="rt">Melhor janela para operação</div>
          <div className="rd">Após redução da chuva prevista</div>
        </div>
        <span className="tag tag-green">Recomendado</span>
      </div>
      <div className="rec">
        <div className="ric">
          <Icon name="warning" size={17} />
        </div>
        <div>
          <div className="rt">Evitar áreas baixas</div>
          <div className="rd">Priorize rotas com melhor drenagem</div>
        </div>
        <span className="tag tag-amber">Atenção</span>
      </div>
      <div className="rec">
        <div className="ric">
          <Icon name="map" size={17} />
        </div>
        <div>
          <div className="rt">Revisar contexto territorial</div>
          <div className="rd">Confirme drenagem e declividade da área</div>
        </div>
        <span className="tag tag-blue">Contexto</span>
      </div>
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("operacoes")}>
          Abrir operação <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
function Insights({ onNavigate }) {
  return (
    <div className="card dashboard-card">
      <h3>
        Insights e Tendências <ConceptHelp conceito="tendencias" />
      </h3>
      <div className="rec">
        <div className="ric">
          <Icon name="trend" size={17} />
        </div>
        <div>
          <div className="rt">Tendência operacional</div>
          <div className="rd">
            Compare os fatores atuais com a janela recente
          </div>
        </div>
      </div>
      <div className="rec">
        <div className="ric">
          <Icon name="cloud" size={17} />
        </div>
        <div>
          <div className="rt">Período mais crítico</div>
          <div className="rd">
            A previsão de chuva ajuda a priorizar inspeções
          </div>
        </div>
      </div>
      <div className="rec">
        <div className="ric">
          <Icon name="shield" size={17} />
        </div>
        <div>
          <div className="rt">Qualidade do contexto</div>
          <div className="rd">
            Dados territoriais aumentam a leitura de exposição
          </div>
        </div>
      </div>
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("insights")}>
          Ver análise completa <Icon name="arrow" size={13} />
        </button>
      </div>
    </div>
  );
}
export function DashboardPage({
  fazendas,
  selected,
  setSelected,
  dashboard,
  fazenda,
  onNavigate,
  showToast,
  onRefresh,
}) {
  const s = dashboard?.score,
    alertas = dashboard?.alertas || [];
  return (
    <>
      <PageHeader
        title="Olá, Analista Sompo!"
        subtitle="Aqui está o panorama das operações e riscos."
        actions={
          <div className="top-actions">
            <button
              className="icon-btn"
              onClick={() => onNavigate("alertas")}
              aria-label="Alertas"
            >
              <Icon name="bell" />
            </button>
            <button
              className="icon-btn"
              onClick={() => onNavigate("dados")}
              aria-label="Dados"
            >
              <Icon name="database" />
            </button>
            <button
              className="icon-btn"
              onClick={() => onNavigate("configuracoes")}
              aria-label="Configurações"
            >
              <Icon name="settings" />
            </button>
          </div>
        }
      />
      <div className="filters dashboard-filters">
        <FazendaSearch
          fazendas={fazendas}
          selected={selected}
          onSelect={setSelected}
          label="Localizar propriedade"
        />
        <div className="reading-window">
          <span>Janela da leitura <ConceptHelp conceito="distribuicao_condicoes" /></span>
          <b>30 dias</b>
          <small>Definida pelo indicador publicado</small>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            onRefresh?.();
            showToast("Leitura da propriedade atualizada.");
          }}
        >
          <Icon name="refresh" size={16} /> Atualizar leitura
        </button>
      </div>
      {!s ? (
        <div className="loading-panel">
          <span className="spinner" />
          Gerando indicadores pela API local...
        </div>
      ) : (
        <div className="grid dashboard-grid">
          <Condicao s={s} f={fazenda} onNavigate={onNavigate} />
          <Distribuicao d={s.distribuicao_30d} onNavigate={onNavigate} />
          <Alertas itens={alertas} onNavigate={onNavigate} />
          <Fatores itens={s.fatores_risco} onNavigate={onNavigate} />
          <Recomenda onNavigate={onNavigate} />
          <Insights onNavigate={onNavigate} />
        </div>
      )}
      <div className="footer-note">
        Dados atualizados em {s?.data_referencia || "—"} · As informações
        apresentadas não substituem a análise técnica do analista.
      </div>
    </>
  );
}
