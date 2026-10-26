import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { FazendaSearch } from "../components/FazendaSearch";
import { ConceptHelp } from "../components/ConceptHelp";
import { fetchJSON } from "../api/core";
import { numero } from "../utils/format";
import {
  avaliarDiaPrevisao,
  calcularComparativoPortfolio,
  calcularQualidadeDados,
  construirRadarOperacional,
  resumirJanelaOperacional,
} from "./insightsCalculations";

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
  const status = avaliarDiaPrevisao(dia).status;
  if (status === "restricao") return "is-alert";
  if (status === "atencao") return "is-attention";
  if (status === "indisponivel") return "is-unavailable";
  return "is-stable";
}

function intervaloCivil(janela) {
  if (!janela) return "Nenhuma sequência identificada";
  const inicio = formatarDiaPrevisao(janela.inicio).data;
  const fim = formatarDiaPrevisao(janela.fim).data;
  return janela.total_dias === 1 ? inicio : `${inicio} a ${fim}`;
}

function PrevisaoSeteDias({ dashboard, fazenda }) {
  const dias = dashboard?.previsao_7d || [];
  const oficial = dashboard?.origem_previsao === "api_open_meteo";
  const chuvaValida = dias
    .map((dia) => dia.precipitacao_mm)
    .filter((valor) => valor !== null && valor !== undefined && valor !== "")
    .map(Number)
    .filter(Number.isFinite);
  const probabilidadeValida = dias
    .map((dia) => dia.prob_precip_pct)
    .filter((valor) => valor !== null && valor !== undefined && valor !== "")
    .map(Number)
    .filter(Number.isFinite);
  const temperaturaValida = dias
    .map((dia) => dia.temp_max_c)
    .filter((valor) => valor !== null && valor !== undefined && valor !== "")
    .map(Number)
    .filter(Number.isFinite);
  const previsaoCompleta = oficial
    && dias.length === 7
    && dias.every((dia) => [
      dia?.precipitacao_mm,
      dia?.prob_precip_pct,
      dia?.temp_max_c,
    ].every((valor) => valor !== null && valor !== undefined && valor !== "" && Number.isFinite(Number(valor))));
  const chuvaCompleta = dias.length === 7 && chuvaValida.length === 7;
  const chuvaAcumulada = chuvaValida.reduce((total, valor) => total + valor, 0);
  const maiorProbabilidade = probabilidadeValida.length
    ? Math.max(...probabilidadeValida)
    : null;
  const maiorTemperatura = temperaturaValida.length
    ? Math.max(...temperaturaValida)
    : null;
  const janela = resumirJanelaOperacional(dias);
  const diasComMenorSinal = janela.contagem.menor_sinal_chuva;
  const diasComAtencao = janela.contagem.atencao + janela.contagem.restricao;

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
          <span className={previsaoCompleta ? "is-live" : oficial ? "is-partial" : ""}>
            {previsaoCompleta ? "Previsão completa" : oficial ? "Previsão parcial" : "Fonte indisponível"}
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
              <b>{chuvaCompleta ? `${numero(chuvaAcumulada, 1)} mm` : "—"}</b>
              <small>{chuvaCompleta ? "7 de 7 dias disponíveis" : `${chuvaValida.length} de 7 dias com valor`}</small>
            </div>
            <div>
              <span>Menor sinal de chuva</span>
              <b>{diasComMenorSinal} de 7 dias</b>
            </div>
            <div>
              <span>Atenção climática</span>
              <b>{diasComAtencao} de 7 dias</b>
            </div>
            <div>
              <span>Pico do período</span>
              <b>{maiorTemperatura == null ? "—" : `${numero(maiorTemperatura, 1)}°C`}</b>
              <small>{maiorProbabilidade == null ? "Probabilidade indisponível" : `até ${numero(maiorProbabilidade, 0)}% de chuva`}</small>
            </div>
          </div>
          <div className="operational-window" aria-label="Leitura operacional da previsão">
            <div>
              <span className="evidence-kind is-calculated">Indicador calculado</span>
              <b>Condição candidata para validação local</b>
              <p>
                Maior sequência com menor sinal de chuva: <strong>{intervaloCivil(janela.melhor_sequencia)}</strong>.
              </p>
            </div>
            <p>
              A triagem usa chuva, probabilidade e temperatura. Confirme vento, condição do solo, acesso e requisitos da atividade antes de programar a operação.
            </p>
          </div>
          <div
            className="weather-days-scroll"
            role="region"
            aria-label="Previsão diária com rolagem horizontal"
            tabIndex={0}
          >
            <div className="weather-days" role="list" aria-label="Previsão diária">
              {dias.map((dia, indice) => {
                const rotulo = formatarDiaPrevisao(dia.data);
                const avaliacao = janela.dias[indice]?.avaliacao_operacional || avaliarDiaPrevisao(dia);
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
                  <span className={`weather-day-status is-${avaliacao.status}`}>{avaliacao.rotulo}</span>
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

const ROTULOS_TIPO_MAQUINARIO = {
  TRATOR: "Tratores",
  COLHEITADEIRA: "Colheitadeiras",
  PULVERIZADOR_AUTOPROPELIDO: "Pulverizadores",
  PLANTADEIRA: "Plantadeiras",
  IMPLEMENTO_ARRASTO: "Implementos",
  PLATAFORMA: "Plataformas",
  UTILITARIO_APOIO: "Utilitários de apoio",
};

function dataCivil(valor) {
  if (!valor) return "—";
  const [ano, mes, dia] = String(valor).slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : String(valor);
}

function RadarOperacional({ dashboard, qualidade, radar }) {
  const janela = resumirJanelaOperacional(dashboard?.previsao_7d || []);
  const frota = dashboard?.maquinarios_resumo || {};
  return (
    <section className="decision-radar-card" aria-labelledby="decision-radar-title">
      <header className="decision-radar-head">
        <div>
          <span>Leitura consolidada</span>
          <h2 id="decision-radar-title">Radar para tomada de decisão</h2>
          <p>Prioridades calculadas com evidência, limite de uso e próximo passo para validação.</p>
        </div>
        <span className="evidence-kind is-calculated">Indicadores determinísticos</span>
      </header>
      {!dashboard ? (
        <div className="decision-radar-state" role="status">
          <span className="ai-loading-dot is-active" />
          <div><b>Consolidando os indicadores</b><p>A leitura aparecerá após o carregamento do dashboard.</p></div>
        </div>
      ) : (
        <div className="decision-radar-content">
          <div className="decision-radar-metrics">
            <div><span>Condição calculada</span><b>{dashboard.score?.condicao_atual || "—"}</b><small>{dashboard.score?.score == null ? "Score indisponível" : `${dashboard.score.score}/100`}</small></div>
            <div><span>Menor sinal de chuva</span><b>{janela.contagem.menor_sinal_chuva} dia(s)</b><small>candidatos à validação local</small></div>
            <div><span>Seguro cadastrado</span><b>{frota.total ? `${frota.percentual_segurado || 0}%` : "—"}</b><small>{frota.total ? `${frota.seguros_vigentes ?? Math.max(0, (frota.segurados || 0) - (frota.seguros_vencidos || 0))} vigente(s)` : "frota não cadastrada"}</small></div>
            <div><span>Cobertura dos dados</span><b>{qualidade.percentual}%</b><small>{qualidade.completos} de {qualidade.total} fontes prontas</small></div>
          </div>
          <div className="decision-action-grid">
            {radar.map((item, indice) => (
              <article className={`is-${item.prioridade}`} key={item.id}>
                <header>
                  <span className="decision-action-rank">{String(indice + 1).padStart(2, "0")}</span>
                  <span className={`ai-priority-tag is-${item.prioridade}`}>{ROTULOS_PRIORIDADE[item.prioridade] || item.prioridade}</span>
                </header>
                <h3>{item.titulo}</h3>
                <p><b>Evidência:</b> {item.evidencia}</p>
                <div><Icon name="arrow" size={14} /><span><b>Recomendação para validação:</b> {item.acao}</span></div>
                <small>{item.natureza === "indicador_calculado" ? "Indicador calculado" : "Lacuna cadastral identificada"}</small>
              </article>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function QualidadeEContexto({ qualidade, comparativo }) {
  return (
    <section className="data-quality-card" aria-labelledby="data-quality-title">
      <header className="data-quality-head">
        <div>
          <span>Transparência da leitura</span>
          <h2 id="data-quality-title">Cobertura dos dados e contexto cadastral</h2>
          <p>Mostra o que sustenta a análise e o que ainda precisa ser confirmado.</p>
        </div>
        <div className={`data-quality-score is-${qualidade.nivel}`}>
          <b>{qualidade.percentual}%</b>
          <span>Cobertura das informações</span>
        </div>
      </header>
      <div className="data-quality-content">
        <div className="data-quality-grid">
          {qualidade.itens.map((item) => (
            <article className={`is-${item.status}`} key={item.id}>
              <span><Icon name={item.status === "ok" ? "check" : "warning"} size={14} /></span>
              <div><b>{item.nome}</b><p>{item.detalhe}</p></div>
            </article>
          ))}
        </div>
        <aside className="portfolio-comparison">
          <span>Comparação cadastral</span>
          <h3>Fazendas da mesma operação</h3>
          {comparativo.suficiente ? (
            <>
              <dl>
                <div><dt>Base comparável</dt><dd>{comparativo.base} fazendas</dd></div>
                <div><dt>Área desta fazenda</dt><dd>{comparativo.area_fazenda_ha == null ? "—" : `${numero(comparativo.area_fazenda_ha, 1)} ha`}</dd></div>
                <div><dt>Mediana de área</dt><dd>{comparativo.area_mediana_ha == null ? "—" : `${numero(comparativo.area_mediana_ha, 1)} ha`}</dd></div>
                <div><dt>Frota desta fazenda</dt><dd>{comparativo.frota_fazenda == null ? "—" : comparativo.frota_fazenda}</dd></div>
                <div><dt>Mediana de frota</dt><dd>{comparativo.frota_mediana == null ? "—" : numero(comparativo.frota_mediana, 1)}</dd></div>
                <div><dt>Base da mediana de frota</dt><dd>{comparativo.frota_base} fazenda(s)</dd></div>
                <div><dt>Contexto territorial pronto</dt><dd>{comparativo.cobertura_territorial_pct}% da base</dd></div>
              </dl>
              <p>Comparação descritiva; não representa desempenho, risco atuarial ou recomendação de dimensionamento.</p>
            </>
          ) : (
            <div className="portfolio-comparison-empty"><Icon name="info" size={18} /><p>É preciso haver ao menos duas fazendas da mesma operação para exibir uma referência cadastral.</p></div>
          )}
        </aside>
      </div>
      <footer>Este percentual mede disponibilidade das informações, não precisão estatística nem qualidade técnica das fontes.</footer>
    </section>
  );
}

function FrotaInsights({ dashboard, fazenda }) {
  const resumo = dashboard?.maquinarios_resumo;
  const composicao = Object.entries(resumo?.por_tipo || {});
  return (
    <section className="fleet-insights-card" aria-labelledby="fleet-insights-title">
      <header className="fleet-insights-head">
        <span className="fleet-insights-symbol"><Icon name="activity" size={20} /></span>
        <div>
          <span>Inventário cadastral</span>
          <h2 id="fleet-insights-title">Maquinário de {fazenda?.nome_fazenda || "produção"}</h2>
          <p>Composição, uso declarado e situação de seguro da frota vinculada à fazenda.</p>
        </div>
      </header>
      {!dashboard ? (
        <div className="fleet-insights-state" role="status"><b>Carregando inventário…</b></div>
      ) : resumo?.disponivel === false ? (
        <div className="fleet-insights-state" role="status"><Icon name="info" size={18} /><div><b>Inventário temporariamente indisponível</b><p>Os demais indicadores continuam válidos.</p></div></div>
      ) : !resumo?.total ? (
        <div className="fleet-insights-state" role="status"><Icon name="activity" size={20} /><div><b>Frota ainda não cadastrada</b><p>Cadastre os equipamentos em Clientes e Apólices para enriquecer esta leitura.</p></div></div>
      ) : (
        <div className="fleet-insights-content">
          <div className="fleet-intelligence-grid">
            <div><span>Total</span><b>{resumo.total}</b><small>equipamentos</small></div>
            <div><span>Seguro cadastrado</span><b>{resumo.percentual_segurado}%</b><small>{resumo.segurados} item(ns)</small></div>
            <div><span>Seguros vigentes</span><b>{resumo.seguros_vigentes ?? Math.max(0, resumo.segurados - (resumo.seguros_vencidos || 0))}</b><small>pela data cadastrada</small></div>
            <div><span>Sem seguro cadastrado</span><b>{resumo.sem_seguro || 0}</b><small>confirmar proteção</small></div>
            <div><span>Seguros vencidos</span><b>{resumo.seguros_vencidos || 0}</b><small>exigem conferência</small></div>
            <div><span>Vencendo em 90 dias</span><b>{resumo.vencendo_90_dias}</b><small>próximo: {dataCivil(resumo.proximo_vencimento)}</small></div>
            <div><span>Idade média</span><b>{resumo.idade_media_anos == null ? "—" : `${numero(resumo.idade_media_anos, 1)} anos`}</b><small>base cadastral</small></div>
            <div><span>Horímetro cadastral</span><b>{resumo.horimetros_informados ? `${numero(resumo.horimetro_total_horas, 1)} h` : "—"}</b><small>{resumo.horimetros_informados ? `soma de ${resumo.horimetros_informados} cadastro(s)` : "não informado"}</small></div>
            <div><span>Uso diário declarado</span><b>{resumo.horas_dia_informadas ? `${numero(resumo.horas_dia_estimadas, 1)} h/dia` : "—"}</b><small>{resumo.horas_dia_informadas ? `soma de ${resumo.horas_dia_informadas} cadastro(s)` : "não informado"}</small></div>
          </div>
          <div className="fleet-composition" aria-label="Composição da frota por tipo">
            {composicao.map(([tipo, total]) => <span key={tipo}><b>{total}</b> {ROTULOS_TIPO_MAQUINARIO[tipo] || tipo}</span>)}
          </div>
          <footer>Dados cadastrais; idade e horímetro não representam diagnóstico de manutenção ou probabilidade de sinistro.</footer>
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
              {(insight.prioridades || []).length ? (
                (insight.prioridades || []).map((item, indice) => (
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
                ))
              ) : (
                <div className="ai-no-priorities" role="status">
                  <Icon name="check" size={17} />
                  <p>Nenhuma prioridade adicional foi sustentada pelos dados enviados à análise assistida.</p>
                </div>
              )}
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
  const qualidade = useMemo(
    () => calcularQualidadeDados({ dashboard, fazenda }),
    [dashboard, fazenda],
  );
  const radar = useMemo(
    () => construirRadarOperacional({ dashboard, qualidade }),
    [dashboard, qualidade],
  );
  const comparativo = useMemo(
    () => calcularComparativoPortfolio({
      fazendas,
      fazenda,
      totalFrota: dashboard?.maquinarios_resumo?.total || 0,
      frotaDisponivel: Boolean(dashboard) && dashboard?.maquinarios_resumo?.disponivel !== false,
    }),
    [fazendas, fazenda, dashboard, dashboard?.maquinarios_resumo?.total],
  );
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

      <RadarOperacional
        dashboard={dashboard}
        qualidade={qualidade}
        radar={radar}
      />

      <PainelInsightsIA
        selected={selected}
        fazenda={fazenda}
        dashboard={dashboard}
      />

      <PrevisaoSeteDias dashboard={dashboard} fazenda={fazenda} />

      <FrotaInsights dashboard={dashboard} fazenda={fazenda} />

      <QualidadeEContexto qualidade={qualidade} comparativo={comparativo} />

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
