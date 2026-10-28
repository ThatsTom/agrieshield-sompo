import { useEffect, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "../components/ConceptHelp";
import { FazendaSearch } from "../components/FazendaSearch";
import { buscarExposicaoMaquinario } from "../api/exposicao";

const formatoScore = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const formatoData = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });
const formatarScore = (valor) => formatoScore.format(valor);
const formatarData = (valor) =>
  valor ? formatoData.format(new Date(`${valor}T00:00:00Z`)) : "—";
const nomesPerigos = {
  EXPOSICAO_HIDRICA: "Exposição Hídrica",
  TRAFEGABILIDADE: "Trafegabilidade",
  INSTABILIDADE: "Instabilidade",
  INCENDIO: "Incêndio / Propagação de Fogo",
  TEMPESTADES: "Tempestades Severas",
};
const classificacoes = {
  NORMAL: { rotulo: "NORMAL", cor: "var(--eq-normal)" },
  ATENCAO: { rotulo: "ATENÇÃO", cor: "var(--eq-atencao)" },
  ALERTA: { rotulo: "ALERTA", cor: "var(--eq-alerta)" },
  CRITICO: { rotulo: "CRÍTICO", cor: "var(--eq-critico)" },
};

function ScoreExposicao({ exposicao, carregando, erro, f, onNavigate }) {
  const publicavel = Boolean(exposicao?.score_publicavel && exposicao.score_atual != null);
  const pct = publicavel
      ? Math.max(0, Math.min(1, exposicao.score_atual / 100))
      : 0,
    dash = 182 * pct;
  const classificacao = classificacoes[exposicao?.classificacao_atual];
  return (
    <div className="card dashboard-card">
      <h3>
        Score de Exposição do Maquinário <ConceptHelp conceito="score_exposicao" />
      </h3>
      <div className="gauge-wrap">
        <div
          className="gauge"
          role="img"
          aria-label={publicavel
            ? `Score de exposição ${formatarScore(exposicao.score_atual)} de 100, classificação ${classificacao?.rotulo}`
            : "Score de exposição indisponível"}
        >
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
            <b>{publicavel ? formatarScore(exposicao.score_atual) : "—"}</b>
            <span>{publicavel ? "/100" : "Indisponível"}</span>
          </div>
        </div>
        <div className="op-meta">
          <div
            className="cond"
            style={{ color: classificacao?.cor }}
          >
            <Icon name="warning" size={15} />
            {carregando
              ? "Carregando exposição..."
              : publicavel
                ? classificacao?.rotulo
                : "Score indisponível"}
          </div>
          <div>
            <b>{f?.nome_fazenda || exposicao?.fazenda?.nome}</b>
          </div>
          <div>Apólice: {f?.numero_apolice || "—"}</div>
          <div>
            {f?.cidade || exposicao?.fazenda?.cidade} / {f?.uf || exposicao?.fazenda?.uf}
          </div>
          <div>Período analisado: últimos 90 dias</div>
          {publicavel && exposicao.perigo_dominante && (
            <div>Perigo dominante: {nomesPerigos[exposicao.perigo_dominante]}</div>
          )}
          {erro && <div role="alert">{erro}</div>}
        </div>
      </div>
      <div className="card-foot split-foot">
        <span className="badge">
          ● {exposicao?.qualidade_dados?.fonte_meteorologica || "—"} · Referência: {formatarData(exposicao?.data_referencia)}
        </span>
        <button className="text-link" onClick={() => onNavigate("operacoes")}>
          Ver detalhamento em Operações <Icon name="arrow" size={13} />
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
        Distribuição Operacional (30 dias){" "}
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
function Fatores({ exposicao, onNavigate }) {
  const perigos = (exposicao?.score_publicavel ? exposicao.perigos : [])
    .filter((perigo) => perigo.participa_score && perigo.contribuicao != null)
    .sort((a, b) => b.contribuicao - a.contribuicao)
    .slice(0, 3);
  return (
    <div className="card dashboard-card">
      <h3>
        Principais Contribuições ao Score <ConceptHelp conceito="contribuicao" />
      </h3>
      {perigos.length ? (
        perigos.map((perigo) => (
          <div className="factor" key={perigo.perigo}>
            <div className="fic"><Icon name="shield" size={17} /></div>
            <div>
              <div className="fn">{nomesPerigos[perigo.perigo]}</div>
              <div className="fd">Peso no índice: {formatarScore(perigo.peso * 100)}%</div>
            </div>
            <div className="fright">
              <div>{formatarScore(perigo.contribuicao)} pontos</div>
              <div className="bar">
                <i style={{ width: `${Math.max(0, Math.min(100, perigo.contribuicao))}%`, background: classificacoes[perigo.classificacao]?.cor }} />
              </div>
            </div>
          </div>
        ))
      ) : (
        <p className="loading">Contribuições indisponíveis.</p>
      )}
      <div className="card-foot">
        <button className="text-link" onClick={() => onNavigate("operacoes")}>
          Ver composição em Operações <Icon name="arrow" size={13} />
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
  const [exposicao, setExposicao] = useState({
    id: null,
    carregando: true,
    dados: null,
    erro: "",
  });
  const [atualizacao, setAtualizacao] = useState(0);
  useEffect(() => {
    if (!selected) return;
    let ativo = true;
    const controller = new AbortController();
    setExposicao({
      id: String(selected),
      carregando: true,
      dados: null,
      erro: "",
    });
    buscarExposicaoMaquinario(selected, undefined, "NASA_POWER", controller.signal)
      .then((dados) => {
        if (ativo) {
          setExposicao({ id: String(selected), carregando: false, dados, erro: "" });
        }
      })
      .catch((erro) => {
        if (ativo && erro?.name !== "AbortError") {
          setExposicao({
            id: String(selected),
            carregando: false,
            dados: null,
            erro: erro?.message || "Não foi possível carregar a exposição.",
          });
        }
      });
    return () => {
      ativo = false;
      controller.abort();
    };
  }, [selected, atualizacao]);
  const exposicaoSelecionada = exposicao.id === String(selected)
    ? exposicao
    : { carregando: true, dados: null, erro: "" };
  const s = dashboard?.score,
    alertas = dashboard?.alertas || [];
  return (
    <>
      <PageHeader
        title="Olá, Analista!"
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
          <span>Janela do score <ConceptHelp conceito="score_exposicao" /></span>
          <b>90 dias</b>
          <small>Exposição do maquinário</small>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => {
            onRefresh?.();
            setAtualizacao((valor) => valor + 1);
            showToast("Atualizando leituras da propriedade...");
          }}
        >
          <Icon name="refresh" size={16} /> Atualizar leitura
        </button>
      </div>
      <div className="grid dashboard-grid">
        <ScoreExposicao
          exposicao={exposicaoSelecionada.dados}
          carregando={exposicaoSelecionada.carregando}
          erro={exposicaoSelecionada.erro}
          f={fazenda}
          onNavigate={onNavigate}
        />
        <Fatores exposicao={exposicaoSelecionada.dados} onNavigate={onNavigate} />
        {s ? (
          <>
            <Distribuicao d={s.distribuicao_30d} onNavigate={onNavigate} />
            <Alertas itens={alertas} onNavigate={onNavigate} />
            <Recomenda onNavigate={onNavigate} />
            <Insights onNavigate={onNavigate} />
          </>
        ) : (
          <div className="loading-panel">
            <span className="spinner" />
            Gerando indicadores operacionais pela API...
          </div>
        )}
      </div>
      <div className="footer-note">
        Exposição: {formatarData(exposicaoSelecionada.dados?.data_referencia)} · Indicadores operacionais: {formatarData(s?.data_referencia)} · As informações apresentadas não substituem a análise técnica do analista.
      </div>
    </>
  );
}
