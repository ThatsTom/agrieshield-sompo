import { useEffect, useMemo, useState } from "react";
import { buscarExposicaoMaquinario } from "../api/exposicao";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "./ConceptHelp";
import { DetalhePerigo } from "./DetalhePerigo";
import { conceitoDaFonte, conceitoDoPerigo } from "../content/conceitos";

const NOMES = {
  EXPOSICAO_HIDRICA: "Exposição Hídrica",
  TRAFEGABILIDADE: "Trafegabilidade",
  INSTABILIDADE: "Instabilidade",
  INCENDIO: "Incêndio / Propagação de Fogo",
  TEMPESTADES: "Tempestades Severas",
};
const EVID = {
  EXPOSICAO_HIDRICA:
    "Condição meteorológica + suscetibilidade territorial ativada",
  TRAFEGABILIDADE: "Chuva do dia, acúmulo recente e recuperação/secagem",
  INSTABILIDADE: "Declividade e condição hídrica meteorológica",
  INCENDIO: "Temperatura, umidade e vento",
  TEMPESTADES: "Vento e chuva",
};
const ORDEM_PERIGOS = Object.keys(NOMES);
const ROTULOS_CLASSIFICACAO = {
  NORMAL: "NORMAL",
  ATENCAO: "ATENÇÃO",
  ALERTA: "ALERTA",
  CRITICO: "CRÍTICO",
};
const ORDEM_CLASSIFICACAO = { NORMAL: 0, ATENCAO: 1, ALERTA: 2, CRITICO: 3 };
const METODOLOGIAS_TIMELINE = {
  EXPOSICAO_HIDRICA_TERRITORIAL: "Exposição hídrica territorial oficial",
  COMPOSICAO_METEOROLOGICA_PROPRIA_DIA_ACUMULADO_RECUPERACAO_V1:
    "Composição meteorológica de trafegabilidade",
  PERIGO_ATUAL: "Metodologia vigente do perigo",
};
const STATUS = {
  USADA: "USADA",
  CONTEXTO: "CONTEXTO",
  DISPONIVEL: "DISPONÍVEL",
  NAO_UTILIZADO: "NÃO UTILIZADO",
};
const nf = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const pf = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const df = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });
const n = (v) => (v == null ? "Não disponível" : nf.format(v));
const pct = (v) => (v == null ? "Não disponível" : `${pf.format(v)}%`);
const data = (v) => df.format(new Date(`${v}T00:00:00Z`));
const signed = (v) =>
  v == null ? "Não disponível" : `${v > 0 ? "+" : ""}${nf.format(v)} m`;
const distancia = (v) =>
  v == null
    ? "Não disponível"
    : v < 1000
      ? `${nf.format(v)} m`
      : `${nf.format(v / 1000)} km`;
const classeCss = (v) => String(v || "indisponivel").toLowerCase();
const rotuloClassificacao = (v) => ROTULOS_CLASSIFICACAO[v] || v || "INDISPONÍVEL";
const rotuloMetodologia = (v) =>
  METODOLOGIAS_TIMELINE[v] || String(v || "Não informada").replaceAll("_", " ");
const chaveEvento = (evento) =>
  `${evento.perigo}-${evento.inicio}-${evento.fim}-${evento.indice_maximo}`;
const corClassificacao = (v) =>
  v === "CRITICO"
    ? "var(--eq-critico)"
    : v === "ALERTA"
      ? "var(--eq-alerta)"
      : v === "ATENCAO"
        ? "var(--eq-atencao)"
        : "var(--eq-normal)";
const Classe = ({ valor }) =>
  valor ? (
    <span className={`equip-band is-${classeCss(valor)}`}>
      {rotuloClassificacao(valor)}
    </span>
  ) : null;

function Gauge({ e }) {
  const value =
    e.score_publicavel && e.score_atual != null
      ? Math.max(0, Math.min(100, e.score_atual))
      : 0;
  const dash = 182 * (value / 100);
  return (
    <div
      className="gauge equip-condition-gauge"
      role="img"
      aria-label={
        e.score_publicavel
          ? `Score de exposição ${n(e.score_atual)} de 100, classificação ${rotuloClassificacao(e.classificacao_atual)}`
          : "Score de exposição indisponível"
      }
    >
      <svg viewBox="0 0 140 90" aria-hidden="true">
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
          stroke="url(#equip-score-gradient)"
          strokeWidth="13"
          strokeLinecap="round"
          strokeDasharray={`${dash} 999`}
        />
        <defs>
          <linearGradient id="equip-score-gradient" x1="0" x2="1">
            <stop offset="0" stopColor="#21a366" />
            <stop offset=".6" stopColor="#f0a020" />
            <stop offset="1" stopColor="#e0392b" />
          </linearGradient>
        </defs>
      </svg>
      <div className="val">
        <strong>{e.score_publicavel ? n(e.score_atual) : "—"}</strong>
        <span>{e.score_publicavel ? "/100" : "Indisponível"}</span>
      </div>
    </div>
  );
}

function ContextoFazenda({ e, fallback }) {
  const f = e.fazenda || fallback || {},
    t = e.contexto_territorial || {};
  return (
    <section id="equip-contexto" className="farm-context" aria-label="Dados e contexto da fazenda">
      <article>
        <h3>Identificação</h3>
        <b>{f.nome || f.nome_fazenda || `Fazenda ${e.id_fazenda}`}</b>
        <span>
          {f.cidade && f.uf
            ? `${f.cidade} / ${f.uf}`
            : "Localidade não disponível"}
        </span>
        <dl>
          <div>
            <dt>Área</dt>
            <dd>
              {f.area_ha == null
                ? "Não disponível"
                : `${nf.format(f.area_ha)} ha`}
            </dd>
          </div>
        </dl>
      </article>
      <article>
        <h3>Localização</h3>
        <dl>
          <div>
            <dt>Latitude</dt>
            <dd>{n(f.latitude)}</dd>
          </div>
          <div>
            <dt>Longitude</dt>
            <dd>{n(f.longitude)}</dd>
          </div>
        </dl>
      </article>
      <article className="territorial-context">
        <h3>Contexto territorial</h3>
        <div className="territorial-sources">
          <section>
            <b>
              SRTM <ConceptHelp conceito="srtm" />
            </b>
            <dl>
              <div>
                <dt>Declividade média</dt>
                <dd>
                  {t.declividade_media_graus == null
                    ? "Não disponível"
                    : `${nf.format(t.declividade_media_graus)}°`}
                </dd>
              </div>
              <div>
                <dt>
                  Posição topográfica relativa{" "}
                  <ConceptHelp conceito="posicao_topografica" />
                </dt>
                <dd>{signed(t.posicao_topografica_relativa_m)}</dd>
              </div>
            </dl>
          </section>
          <section>
            <b>
              MERIT Hydro <ConceptHelp conceito="merit_distancia" />
            </b>
            <dl>
              <div>
                <dt>Distância à drenagem</dt>
                <dd>{distancia(t.distancia_drenagem_m)}</dd>
              </div>
              <div>
                <dt>
                  Área montante <ConceptHelp conceito="merit_area" />
                </dt>
                <dd>
                  {t.area_montante_km2 == null
                    ? "Não disponível"
                    : `${nf.format(t.area_montante_km2)} km²`}
                </dd>
              </div>
            </dl>
          </section>
        </div>
      </article>
    </section>
  );
}

function Fontes({ e }) {
  const itens = [...(e.fontes_avaliacao || []), ...(e.integracoes || [])];
  return (
    <article className="equip-card sources-card">
      <div className="equip-card-head">
        <div>
          <h3>Fontes e indicadores</h3>
          <p>Uso efetivo nesta avaliação e integrações apenas contextuais.</p>
        </div>
      </div>
      <div className="source-list">
        {itens.map((x) => (
          <section
            key={x.fonte}
            className={`source-item status-${x.status.toLowerCase()}`}
          >
            <header>
              <span className="source-status">
                {STATUS[x.status] || x.status}
              </span>
              <b>{x.nome_exibicao}</b>
              <ConceptHelp conceito={conceitoDaFonte(x.fonte)} />
            </header>
            <p>{x.descricao}</p>
            {x.indicadores?.length > 0 && (
              <small>{x.indicadores.join(" · ")}</small>
            )}
            <strong>
              {x.contribui_score
                ? "Contribui para o score oficial"
                : "Não contribui para o score oficial"}
            </strong>
          </section>
        ))}
      </div>
    </article>
  );
}

function RotuloTimeline({ perigo, eventos }) {
  const dias = eventos.reduce((total, evento) => total + evento.duracao_dias, 0);
  return (
    <div className="timeline-lane-label">
      <div>
        <b>{NOMES[perigo]}</b>
        <small>{EVID[perigo]}</small>
      </div>
      <div className="timeline-lane-stats">
        <span>{eventos.length} {eventos.length === 1 ? "evento" : "eventos"}</span>
        <span>{dias} {dias === 1 ? "dia" : "dias"}</span>
      </div>
      {perigo === "EXPOSICAO_HIDRICA" && (
        <span className="timeline-method">Metodologia oficial</span>
      )}
    </div>
  );
}
function Timeline({ eventos, referencia }) {
  const [filtro, setFiltro] = useState("TODOS");
  const [chaveSelecionada, setChaveSelecionada] = useState(null);
  const inicio = useMemo(() => {
    const d = new Date(`${referencia}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() - 89);
    return d.toISOString().slice(0, 10);
  }, [referencia]);
  const eventosOrdenados = useMemo(
    () =>
      [...(eventos || [])].sort(
        (a, b) =>
          String(b.inicio).localeCompare(String(a.inicio)) ||
          String(a.perigo).localeCompare(String(b.perigo)),
      ),
    [eventos],
  );
  const eventosVisiveis = useMemo(
    () =>
      filtro === "TODOS"
        ? eventosOrdenados
        : eventosOrdenados.filter((evento) => evento.perigo === filtro),
    [eventosOrdenados, filtro],
  );
  const perigosVisiveis = filtro === "TODOS" ? ORDEM_PERIGOS : [filtro];
  const eventoSelecionado =
    eventosVisiveis.find((evento) => chaveEvento(evento) === chaveSelecionada) ||
    eventosVisiveis[0] ||
    null;
  const chaveAtiva = eventoSelecionado ? chaveEvento(eventoSelecionado) : null;
  const diasSinalizados = useMemo(() => {
    const dias = new Set();
    eventosOrdenados.forEach((evento) => {
      const cursor = new Date(`${evento.inicio}T00:00:00Z`);
      const fim = new Date(`${evento.fim}T00:00:00Z`);
      while (cursor <= fim) {
        dias.add(cursor.toISOString().slice(0, 10));
        cursor.setUTCDate(cursor.getUTCDate() + 1);
      }
    });
    return dias.size;
  }, [eventosOrdenados]);
  const maiorClassificacao = eventosOrdenados.reduce(
    (maior, evento) =>
      (ORDEM_CLASSIFICACAO[evento.classificacao_maxima] ?? -1) >
      (ORDEM_CLASSIFICACAO[maior] ?? -1)
        ? evento.classificacao_maxima
        : maior,
    null,
  );
  const marcas = useMemo(
    () =>
      [0, 18, 36, 54, 72, 89].map((dias) => {
        const d = new Date(`${inicio}T00:00:00Z`);
        d.setUTCDate(d.getUTCDate() + dias);
        return d.toISOString().slice(0, 10);
      }),
    [inicio],
  );
  const offset = (v) =>
    Math.round(
      (new Date(`${v}T00:00:00Z`) - new Date(`${inicio}T00:00:00Z`)) / 86400000,
    );
  return (
    <section id="equip-historico" className="equip-card equip-timeline">
      <div className="equip-card-head">
        <div>
          <h3>
            Linha do tempo multirriscos <ConceptHelp conceito="linha_tempo" />
          </h3>
          <p>
            Intervalos reais dos eventos oficiais na janela móvel de 90 dias.
          </p>
        </div>
        <span>{data(inicio)} — {data(referencia)}</span>
      </div>
      <div className="timeline-summary" aria-label="Resumo dos riscos no período">
        <div><span>Eventos identificados</span><b>{eventosOrdenados.length}</b></div>
        <div><span>Perigos com evento</span><b>{new Set(eventosOrdenados.map((x) => x.perigo)).size} de {ORDEM_PERIGOS.length}</b></div>
        <div><span>Dias sinalizados</span><b>{diasSinalizados} de 90</b></div>
        <div>
          <span>Maior classificação</span>
          <b style={{ color: corClassificacao(maiorClassificacao) }}>
            {maiorClassificacao ? rotuloClassificacao(maiorClassificacao) : "—"}
          </b>
        </div>
      </div>
      <div className="timeline-filters" aria-label="Filtrar linha do tempo por perigo">
        <button
          type="button"
          className={filtro === "TODOS" ? "is-active" : ""}
          aria-pressed={filtro === "TODOS"}
          onClick={() => { setFiltro("TODOS"); setChaveSelecionada(null); }}
        >
          Todos <b>{eventosOrdenados.length}</b>
        </button>
        {ORDEM_PERIGOS.map((perigo) => {
          const quantidade = eventosOrdenados.filter((x) => x.perigo === perigo).length;
          return (
            <button
              type="button"
              key={perigo}
              className={filtro === perigo ? "is-active" : ""}
              aria-pressed={filtro === perigo}
              onClick={() => { setFiltro(perigo); setChaveSelecionada(null); }}
            >
              {NOMES[perigo]} <b>{quantidade}</b>
            </button>
          );
        })}
      </div>
      <p className="timeline-scroll-hint">
        Selecione uma faixa para abrir a leitura completa do evento.
      </p>
      <div className="timeline-chart-scroll">
        <div className="timeline-chart">
          <div className="timeline-lanes">
            {perigosVisiveis.map((perigo) => {
              const eventosDoPerigo = eventosOrdenados
                .filter((x) => x.perigo === perigo)
                .sort((a, b) => String(a.inicio).localeCompare(String(b.inicio)));
              return (
                <div className="timeline-lane" key={perigo}>
                  <RotuloTimeline perigo={perigo} eventos={eventosDoPerigo} />
            <div
              className="lane-track"
                      aria-label={`${NOMES[perigo]}: ${eventosDoPerigo.length} eventos`}
            >
                      {eventosDoPerigo.map((x, i) => {
                  const left = Math.max(0, Math.min(89, offset(x.inicio))),
                    right = Math.max(left, Math.min(89, offset(x.fim)));
                  return (
                            <button
                              type="button"
                      key={`${x.inicio}-${i}`}
                              className={`lane-event is-${classeCss(x.classificacao_maxima)} ${chaveEvento(x) === chaveAtiva ? "is-selected" : ""}`}
                      style={{
                        left: `${(left / 90) * 100}%`,
                        width: `${Math.max(1, ((right - left + 1) / 90) * 100)}%`,
                      }}
                              aria-label={`${NOMES[x.perigo]}, ${data(x.inicio)} a ${data(x.fim)}, ${x.duracao_dias} dias, ${rotuloClassificacao(x.classificacao_maxima)}. Abrir detalhes.`}
                              aria-pressed={chaveEvento(x) === chaveAtiva}
                              onClick={() => setChaveSelecionada(chaveEvento(x))}
                    />
                  );
                })}
                    </div>
                  </div>
                );
              })}
            </div>
          <div className="timeline-axis">
            {marcas.map((marca) => <span key={marca}>{data(marca)}</span>)}
          </div>
        </div>
      </div>
      {eventoSelecionado && (
        <article
          className="timeline-event-detail"
          aria-live="polite"
          aria-label="Detalhes do evento selecionado"
        >
          <header>
            <div><span>Evento selecionado</span><h5>{NOMES[eventoSelecionado.perigo]}</h5></div>
            <Classe valor={eventoSelecionado.classificacao_maxima} />
          </header>
          <div>
            <dl><dt>Início</dt><dd>{data(eventoSelecionado.inicio)}</dd></dl>
            <dl><dt>Fim</dt><dd>{data(eventoSelecionado.fim)}</dd></dl>
            <dl><dt>Duração</dt><dd>{eventoSelecionado.duracao_dias} {eventoSelecionado.duracao_dias === 1 ? "dia" : "dias"}</dd></dl>
            <dl><dt>Severidade</dt><dd>{n(eventoSelecionado.severidade)} / 100</dd></dl>
            <dl><dt>Índice médio</dt><dd>{n(eventoSelecionado.indice_medio)} / 100</dd></dl>
            <dl><dt>Índice máximo</dt><dd>{n(eventoSelecionado.indice_maximo)} / 100</dd></dl>
          </div>
          <footer>
            <span>Leitura do risco</span>
            <b>{EVID[eventoSelecionado.perigo]}</b>
            <small>{rotuloMetodologia(eventoSelecionado.metodologia_perigo)}</small>
          </footer>
        </article>
      )}
      <section className="timeline-period-events" aria-label="Riscos identificados no período">
        <header>
          <div>
            <h4>Riscos identificados no período</h4>
            <p>Intervalos mais recentes primeiro. Selecione um item para localizar e detalhar o evento.</p>
          </div>
          <span>{eventosVisiveis.length} resultado(s)</span>
        </header>
        {eventosVisiveis.length > 0 ? (
          <div>
            {eventosVisiveis.map((evento) => (
              <button
                type="button"
                key={chaveEvento(evento)}
                className={chaveEvento(evento) === chaveAtiva ? "is-selected" : ""}
                onClick={() => setChaveSelecionada(chaveEvento(evento))}
              >
                <span className={`timeline-risk-dot is-${classeCss(evento.classificacao_maxima)}`} />
                <span><b>{NOMES[evento.perigo]}</b><small>{data(evento.inicio)} — {data(evento.fim)}</small></span>
                <span><b>{evento.duracao_dias} {evento.duracao_dias === 1 ? "dia" : "dias"}</b><small>Índice máx. {n(evento.indice_maximo)}</small></span>
                <Classe valor={evento.classificacao_maxima} />
              </button>
            ))}
          </div>
        ) : (
          <p className="timeline-empty">Nenhum evento deste perigo foi identificado nos 90 dias.</p>
        )}
      </section>
      {!eventosOrdenados.length && (
        <p className="timeline-empty">
          Nenhum evento relevante identificado na janela atual. As faixas
          neutras não representam ausência absoluta de risco.
        </p>
      )}
    </section>
  );
}

function CardPerigo({ p }) {
  return (
    <section className={!p.participa_score ? "is-informative" : ""}>
      <header>
        <div>
          <i className={`hazard-dot is-${p.classificacao?.toLowerCase()}`} />
          <h4>
            {NOMES[p.perigo]}{" "}
            <ConceptHelp conceito={conceitoDoPerigo(p.perigo)} />
            <small>{EVID[p.perigo]}</small>
          </h4>
        </div>
        <Classe valor={p.classificacao} />
      </header>
      {!p.participa_score && (
        <em>Indicador informativo · não contributivo no score</em>
      )}
      <dl>
        <div>
          <dt>Índice<ConceptHelp conceito={conceitoDoPerigo(p.perigo)} /></dt>
          <dd>{n(p.indice)}</dd>
        </div>
        <div>
          <dt>Peso no índice<ConceptHelp conceito="peso_indice" /></dt>
          <dd>{pct(p.peso * 100)}</dd>
        </div>
        <div>
          <dt>Contribuição oficial<ConceptHelp conceito="contribuicao" /></dt>
          <dd>{n(p.contribuicao)} pts</dd>
        </div>
        <div>
          <dt>Cobertura<ConceptHelp conceito="cobertura" /></dt>
          <dd>{pct(p.cobertura_percentual)}</dd>
        </div>
        <div>
          <dt>Participa do score</dt>
          <dd>{p.participa_score ? "Sim" : "Não"}</dd>
        </div>
      </dl>
    </section>
  );
}

function JanelaHidrica({ titulo, dados }) {
  return (
    <article>
      <h4>{titulo}</h4>
      <strong>{n(dados.indice)}</strong>
      <Classe valor={dados.classificacao} />
      <dl>
        <div>
          <dt>Dias relevantes</dt>
          <dd>{dados.quantidade_dias_relevantes}</dd>
        </div>
        <div>
          <dt>Eventos</dt>
          <dd>{dados.quantidade_eventos}</dd>
        </div>
        <div>
          <dt>Cobertura</dt>
          <dd>{pct(dados.cobertura_percentual)}</dd>
        </div>
      </dl>
    </article>
  );
}
function DetalheHidrico({ e }) {
  const h = e.exposicao_hidrica,
    t = e.contexto_territorial || {};
  return (
    <details
      className="equip-card hazard-detail hydric-detail"
      aria-label="Detalhamento da Exposição Hídrica"
      open
    >
      <summary>
        <div>
          <span>Detalhamento do perigo</span>
          <h3>
            Exposição Hídrica <ConceptHelp conceito="hidrico" />
          </h3>
          <p>Condição meteorológica + suscetibilidade territorial</p>
        </div>
        <div>
          <span className="source-chip">{e.fonte_meteorologica}</span>
          <strong>{n(h.janela_atual.indice)} / 100</strong>
          <Classe valor={h.janela_atual.classificacao} />
        </div>
      </summary>
      <div className="hydric-detail-body">
        <div className="hydric-detail-summary">
          <div>
            <span>Exposição hídrica atual</span>
            <strong>{n(h.janela_atual.indice)}</strong>
            <Classe valor={h.janela_atual.classificacao} />
          </div>
          <div>
            <span>Suscetibilidade territorial</span>
            <strong>{n(h.suscetibilidade_territorial)} / 100</strong>
          </div>
        </div>
        <div className="hydric-detail-grid">
          <section>
            <h4>Componentes territoriais</h4>
            <dl>
              <div>
                <dt>Proximidade da drenagem</dt>
                <dd>{n(h.proximidade_drenagem)} / 100</dd>
              </div>
              <div>
                <dt>Relevância da drenagem pela área montante</dt>
                <dd>{n(h.relevancia_area_montante)} / 100</dd>
              </div>
              <div>
                <dt>Posição topográfica relativa</dt>
                <dd>{n(h.posicao_topografica)} / 100</dd>
              </div>
            </dl>
          </section>
          <section>
            <h4>Valores de origem</h4>
            <dl>
              <div>
                <dt>MERIT · Distância à drenagem</dt>
                <dd>{distancia(t.distancia_drenagem_m)}</dd>
              </div>
              <div>
                <dt>MERIT · Área montante</dt>
                <dd>
                  {t.area_montante_km2 == null
                    ? "Não disponível"
                    : `${nf.format(t.area_montante_km2)} km²`}
                </dd>
              </div>
              <div>
                <dt>SRTM · Posição topográfica relativa</dt>
                <dd>{signed(t.posicao_topografica_relativa_m)}</dd>
              </div>
            </dl>
          </section>
        </div>
        <div className="hydric-windows">
          <JanelaHidrica titulo="Janela atual" dados={h.janela_atual} />
          <JanelaHidrica titulo="Janela anterior" dados={h.janela_anterior} />
        </div>
        <details className="hydric-method">
          <summary>Como a Exposição Hídrica é calculada</summary>
          <p>
            <b>Suscetibilidade territorial:</b> 40% proximidade da drenagem +
            35% relevância da área montante + 25% posição topográfica relativa.
          </p>
          <p>
            <b>Ativação:</b> chuva acumulada de três dias normalizada pela curva
            meteorológica vigente.
          </p>
          <p>
            <b>Incremento diário:</b> 0,30 × ativação × suscetibilidade
            territorial.
          </p>
          <p>
            <b>Resultado diário:</b> condição meteorológica base + incremento
            territorial, limitado a 100.
          </p>
          <p>
            <b>Proveniência:</b> meteorologia por {e.fonte_meteorologica};
            drenagem e área montante por MERIT Hydro; posição topográfica por
            SRTM.
          </p>
          <p>
            Metodologia não calibrada contra sinistros reais e não representa
            probabilidade atuarial.
          </p>
        </details>
      </div>
    </details>
  );
}

function DetalhesPerigos({ e }) {
  const d = e.detalhes_perigos || {};
  const resumos = Object.fromEntries(e.perigos.map((p) => [p.perigo, p]));
  return (
    <section id="equip-detalhes" className="hazard-details" aria-labelledby="hazard-details-title">
      <div className="equip-card-head">
        <div>
          <h3 id="hazard-details-title">
            Detalhamento dos perigos <ConceptHelp conceito="fatores_risco" />
          </h3>
          <p>
            Cálculo do maior dia disponível e agregação histórica da janela
            atual.
          </p>
        </div>
      </div>
      <DetalheHidrico e={e} />
      {d.trafegabilidade && (
        <DetalhePerigo
          resumo={resumos.TRAFEGABILIDADE}
          detalhe={d.trafegabilidade}
        />
      )}
      {d.incendio && (
        <DetalhePerigo resumo={resumos.INCENDIO} detalhe={d.incendio} />
      )}
      {d.instabilidade && (
        <DetalhePerigo
          resumo={resumos.INSTABILIDADE}
          detalhe={d.instabilidade}
        />
      )}
      {d.tempestades && (
        <DetalhePerigo resumo={resumos.TEMPESTADES} detalhe={d.tempestades} />
      )}
    </section>
  );
}

export function ExposicaoMaquinario({
  idFazenda,
  fazenda,
  buscar = buscarExposicaoMaquinario,
}) {
  const [st, setSt] = useState({ loading: true, data: null, error: "" });
  useEffect(() => {
    let live = true;
    const controller = new AbortController();
    setSt({ loading: true, data: null, error: "" });
    buscar(idFazenda, undefined, "NASA_POWER", controller.signal).then(
      (x) => live && setSt({ loading: false, data: x, error: "" }),
      (err) => {
        if (live && err?.name !== "AbortError")
          setSt({
            loading: false,
            data: null,
            error:
              err?.message ||
              "Não foi possível carregar a exposição do maquinário.",
          });
      },
    );
    return () => {
      live = false;
      controller.abort();
    };
  }, [idFazenda, buscar]);
  if (st.loading)
    return (
      <section className="equipment-dashboard" aria-busy="true">
        <h2>Exposição de Maquinário Agrícola</h2>
        <div className="equip-state">Carregando avaliação de exposição...</div>
      </section>
    );
  if (st.error)
    return (
      <section className="equipment-dashboard">
        <h2>Exposição de Maquinário Agrícola</h2>
        <div className="equip-error" role="alert">
          {st.error}
        </div>
      </section>
    );
  const e = st.data;
  if (!e) return null;
  const total = e.perigos.reduce(
      (s, p) => s + ((p.participa_score && p.contribuicao) || 0),
      0,
    ),
    dominante = e.perigo_dominante
      ? NOMES[e.perigo_dominante]
      : "Sem perigo dominante";
  return (
    <section
      className="equipment-dashboard"
      aria-label="Exposição de Maquinário Agrícola"
    >
      <header className="equip-page-head">
        <div>
          <span>AGRISHIELD-EQUIP</span>
          <h2>
            Exposição de Maquinário Agrícola <ConceptHelp conceito="score_exposicao" />
          </h2>
          <p>
            Score de exposição a perigos ambientais e territoriais associados a
            máquinas e equipamentos segurados.
          </p>
        </div>
        <div>
          <small>Data de referência</small>
          <b>{data(e.data_referencia)}</b>
        </div>
      </header>
      <nav className="equip-journey" aria-label="Caminho da análise de exposição">
        <a href="#equip-visao"><span>1</span><b>Visão geral</b><small>Score e comparação</small></a>
        <a href="#equip-composicao"><span>2</span><b>Composição</b><small>Pesos e contribuições</small></a>
        <a href="#equip-detalhes"><span>3</span><b>Perigos</b><small>Evidências e cálculo</small></a>
        <a href="#equip-historico"><span>4</span><b>Histórico</b><small>Eventos em 90 dias</small></a>
        <a href="#equip-fontes"><span>5</span><b>Qualidade</b><small>Fontes e limitações</small></a>
      </nav>
      <ContextoFazenda e={e} fallback={fazenda} />
      <div className="equip-filters">
        <label>
          <span>Classe de equipamento</span>
          <b>Todos os equipamentos</b>
          <small>Contexto apenas — ainda não altera o score</small>
        </label>
        <label>
          <span>Tipo de operação</span>
          <b>{fazenda?.tipo_operacao || "Não informado"}</b>
          <small>Contexto cadastral</small>
        </label>
        <label>
          <span>Período de exposição <ConceptHelp conceito="comparacao_90d" /></span>
          <b>Últimos 90 dias</b>
          <small>Comparação automática com os 90 anteriores</small>
        </label>
      </div>
      <div className="model-strip">
        <span>
          <b>Modelo ativo</b>Metodologia oficial
        </span>
        <span>Parâmetros vigentes</span>
      </div>
      <details className="model-params">
        <summary>Parâmetros do modelo — peso no índice</summary>
        <p className="concept-help-row">
          Entenda o peso no índice <ConceptHelp conceito="peso_indice" />
        </p>
        <div>
          {e.perigos.map((p) => (
            <div key={p.perigo}>
              <b>{NOMES[p.perigo]}</b>
              <span>Peso no índice {pct(p.peso * 100)}</span>
            </div>
          ))}
        </div>
        <p>Pesos configuráveis na tela Riscos e Score.</p>
      </details>
      <div id="equip-visao" className="equip-overview">
        <article className="equip-card score-card">
          <div className="equip-card-head">
            <div>
              <h3>
                Score de Exposição do Maquinário{" "}
                <ConceptHelp conceito="score_exposicao" />
              </h3>
              <p>Janela atual de 90 dias</p>
            </div>
          </div>
          <div className="gauge-wrap equip-score-operational">
            <Gauge e={e} />
            <div className="op-meta equip-score-meta">
              <div
                className="cond"
                style={{ color: corClassificacao(e.classificacao_atual) }}
              >
                <Icon name="warning" size={15} />
                {e.score_publicavel
                  ? rotuloClassificacao(e.classificacao_atual)
                  : "Score indisponível"}
              </div>
              <div><b>{dominante}</b></div>
              <div>
                Perigo dominante na janela <ConceptHelp conceito="perigo_dominante" />
              </div>
              <div>Período analisado: últimos 90 dias</div>
              <div>Classificação publicada diretamente pelo motor</div>
            </div>
          </div>
          <div className="card-foot split-foot equip-score-foot">
            <span className="badge">● {e.qualidade_dados.fonte_meteorologica}</span>
            <span>Referência: {data(e.data_referencia)}</span>
          </div>
        </article>
        <article className="equip-card comparison-card">
          <div className="equip-card-head">
            <div>
              <h3>Comparação de exposição <ConceptHelp conceito="comparacao_90d" /></h3>
              <p>90 dias atuais × 90 dias anteriores</p>
            </div>
            <span
              className={`direction is-${e.direcao_variacao?.toLowerCase()}`}
            >
              {e.direcao_variacao || "INDISPONÍVEL"}
            </span>
          </div>
          {e.comparacao_publicavel ? (
            <>
              <div className="comparison-values">
                <div>
                  <span>Anterior</span>
                  <strong>{n(e.score_anterior)}</strong>
                  <Classe valor={e.classificacao_anterior} />
                </div>
                <i>→</i>
                <div>
                  <span>Atual</span>
                  <strong>{n(e.score_atual)}</strong>
                  <Classe valor={e.classificacao_atual} />
                </div>
              </div>
              <div className="delta">
                <b>{n(e.variacao_pontos)} pontos</b>
                {e.variacao_percentual != null && (
                  <span>{pct(e.variacao_percentual)}</span>
                )}
              </div>
            </>
          ) : (
            <p>Comparação indisponível.</p>
          )}
        </article>
      </div>
      <section className="equip-decision-guide" aria-label="Guia de ação por classificação">
        <header>
          <div>
            <span>Referência de decisão</span>
            <h3>Como agir em cada faixa <ConceptHelp conceito="score_exposicao" /></h3>
          </div>
          <small>Política demonstrativa AGRISHIELD-EQUIP v1.0</small>
        </header>
        <div>
          <article className="is-normal"><b>Normal</b><strong>0–24,99</strong><p>Manter planejamento e monitoramento de rotina.</p></article>
          <article className="is-atencao"><b>Atenção</b><strong>25–49,99</strong><p>Revisar perigo dominante, previsão e condição local.</p></article>
          <article className="is-alerta"><b>Alerta</b><strong>50–74,99</strong><p>Validar dados e restringir atividades expostas quando necessário.</p></article>
          <article className="is-critico"><b>Crítico</b><strong>75–100</strong><p>Priorizar inspeção técnica e decisão operacional formal.</p></article>
        </div>
        <p>As faixas orientam triagem comparável; não são limite universal de fabricante nem probabilidade de sinistro.</p>
      </section>
      <article id="equip-composicao" className="equip-card composition-card">
        <div className="equip-card-head">
          <div>
            <h3>
              Composição do Score de Exposição{" "}
              <ConceptHelp conceito="contribuicao" />{" "}
              <ConceptHelp conceito="cobertura" />
            </h3>
            <p>Índices, pesos e contribuições oficiais da janela atual.</p>
          </div>
          <span>{e.perigos.length} perigos</span>
        </div>
        <div className="hazard-stack">
          {total > 0 ? (
            e.perigos
              .filter((p) => p.participa_score && p.contribuicao > 0)
              .map((p) => (
                <i
                  key={p.perigo}
                  className={`is-${p.classificacao.toLowerCase()}`}
                  style={{ width: `${(p.contribuicao / total) * 100}%` }}
                />
              ))
          ) : (
            <span>Sem contribuição dominante na janela</span>
          )}
        </div>
        <div className="hazard-blocks">
          {e.perigos.map((p) => (
            <CardPerigo key={p.perigo} p={p} />
          ))}
        </div>
      </article>
      <DetalhesPerigos e={e} />
      <Timeline eventos={e.timeline_eventos} referencia={e.data_referencia} />
      <div id="equip-fontes" className="equip-quality-section">
      <Fontes e={e} />
      <div className="equip-bottom">
        <article className="equip-card quality-card">
          <div className="equip-card-head">
            <div>
              <h3>Cobertura e qualidade dos dados <ConceptHelp conceito="qualidade_dados" /></h3>
              <p>Cobertura individual por perigo.</p>
            </div>
            <span className="source-chip">
              {e.qualidade_dados.fonte_meteorologica}
            </span>
          </div>
          <div className="quality-stats">
            <span>
              Warm-up
              <b>
                {e.qualidade_dados.warmup_completo ? "Completo" : "Incompleto"}
              </b>
            </span>
            <span>
              Contexto
              <b>
                {e.qualidade_dados.dias_contexto_disponiveis}/
                {e.qualidade_dados.dias_contexto_esperados} dias
              </b>
            </span>
            <span>
              Gaps<b>{e.qualidade_dados.quantidade_gaps}</b>
            </span>
            <span>
              Dias ausentes<b>{e.qualidade_dados.dias_com_dados_ausentes}</b>
            </span>
          </div>
        </article>
        <article className="equip-card insight-card">
          <div className="equip-card-head">
            <div>
              <h3>Leitura da janela <ConceptHelp conceito="comparacao_90d" /></h3>
              <p>Somente informações publicadas pelo motor.</p>
            </div>
          </div>
          <div>
            <span>Direção do Score de Exposição</span>
            <b>{e.direcao_variacao || "Indisponível"}</b>
          </div>
          <div>
            <span>Perigo dominante na janela <ConceptHelp conceito="perigo_dominante" /></span>
            <b>{dominante}</b>
          </div>
        </article>
      </div>
      </div>
      <details id="equip-metodologia" className="equip-method">
        <summary>Sobre a metodologia e limitações</summary>
        {e.avisos_metodologicos.map((x) => (
          <p key={x}>{x}</p>
        ))}
        <p>{e.disclaimer}</p>
        <p>{e.disclaimer_comparacao}</p>
      </details>
      <footer className="equip-footer">
        {e.disclaimer} {e.disclaimer_comparacao}
      </footer>
    </section>
  );
}
