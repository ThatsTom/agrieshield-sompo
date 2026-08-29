import { useId } from "react";

const nf = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const df = new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" });
const n = (v) => (v == null ? "Não disponível" : nf.format(v));
const data = (v) =>
  v ? df.format(new Date(`${v}T00:00:00Z`)) : "Não disponível";
const valor = (v, sufixo = "") =>
  v == null ? "Não disponível" : `${nf.format(v)}${sufixo}`;
const componente = (v) =>
  v == null ? "Não disponível" : `${nf.format(v)} / 1,00`;
const indice = (v) => (v == null ? "Não disponível" : `${nf.format(v)} / 100`);
const Classe = ({ valor }) =>
  valor ? (
    <span className={`equip-band is-${valor.toLowerCase()}`}>{valor}</span>
  ) : null;

const configuracoes = {
  INCENDIO: {
    nome: "Incêndio / Propagação de Fogo",
    resumo:
      "Condições meteorológicas favoráveis à ignição ou propagação de fogo.",
    dados: (d) => [
      ["Temperatura máxima", valor(d.temperatura_maxima_c, " °C")],
      ["Umidade relativa média", valor(d.umidade_relativa_media_pct, "%")],
      ["Vento médio diário", valor(d.velocidade_vento_media_m_s, " m/s")],
      [
        "Dias desde chuva",
        d.dias_desde_ultima_chuva == null
          ? "Não disponível"
          : `${d.dias_desde_ultima_chuva} dia(s)`,
      ],
    ],
    componentes: (d) => [
      ["Componente de temperatura", componente(d.componente_temperatura)],
      ["Componente de baixa umidade", componente(d.componente_baixa_umidade)],
      ["Componente de vento", componente(d.componente_vento)],
      ["Índice base", indice(d.indice_base)],
      [
        "Multiplicador de secura",
        d.multiplicador_secura == null
          ? "Não disponível"
          : `${nf.format(d.multiplicador_secura)}×`,
      ],
    ],
    calculo: (
      <>
        <p>
          Temperatura máxima, baixa umidade e vento médio são normalizados entre
          0 e 1 e combinados por média geométrica.
        </p>
        <p>
          <b>Índice base:</b> 100 × raiz cúbica do produto dos três componentes.
        </p>
        <p>
          <b>Índice diário:</b> índice base × multiplicador de secura, limitado
          a 100.
        </p>
      </>
    ),
    interpretacao:
      "Temperaturas mais elevadas, baixa umidade, vento e persistência de condição seca tendem a elevar o indicador.",
    limitacao:
      "Representa condições ambientais favoráveis à ocorrência ou propagação de fogo. Não detecta foco de incêndio e não representa probabilidade de sinistro.",
  },
  INSTABILIDADE: {
    nome: "Instabilidade",
    resumo:
      "Suscetibilidade do relevo ativada pela condição hídrica meteorológica interna.",
    dados: (d) => [
      ["Declividade média SRTM", valor(d.declividade_media_graus, "°")],
      [
        "Condição hídrica meteorológica interna",
        indice(d.condicao_hidrica_meteorologica),
      ],
    ],
    componentes: (d) => [
      ["Suscetibilidade topográfica", indice(d.suscetibilidade_topografica)],
      ["Fator de ativação", componente(d.fator_ativacao)],
    ],
    calculo: (
      <>
        <p>
          A declividade média SRTM é convertida em suscetibilidade topográfica
          pela curva vigente.
        </p>
        <p>
          A condição hídrica meteorológica interna define o fator de ativação.
        </p>
        <p>
          <b>Índice diário:</b> suscetibilidade topográfica × fator de ativação,
          limitado a 100.
        </p>
      </>
    ),
    interpretacao:
      "Terrenos mais inclinados podem apresentar maior suscetibilidade, enquanto a condição hídrica meteorológica atua como fator de ativação.",
    limitacao:
      "Representa suscetibilidade associada ao relevo e às condições meteorológicas. Não identifica escorregamentos, tombamentos ou falhas de terreno efetivamente ocorridos.",
  },
  TRAFEGABILIDADE: {
    nome: "Trafegabilidade",
    resumo:
      "Condições meteorológicas que podem dificultar a circulação e operação de máquinas.",
    dados: (d) => [
      ["Precipitação do dia", valor(d.precipitacao_d0, " mm")],
      ["Precipitação acumulada recente / 3 dias", valor(d.acumulado_3d, " mm")],
      [
        "Dias secos desde a última chuva relevante",
        d.dias_desde_ultima_chuva_relevante == null
          ? "Não disponível"
          : `${d.dias_desde_ultima_chuva_relevante} dia(s)`,
      ],
    ],
    componentes: (d) => [
      ["Componente do dia", indice(d.componente_dia)],
      ["Componente acumulado", indice(d.componente_acumulado)],
      ["Recuperação / secagem", indice(d.componente_recuperacao)],
    ],
    pesos: (detalhe) => [
      ["Condição do dia", valor(detalhe.peso_dia * 100, "%")],
      ["Acúmulo recente", valor(detalhe.peso_acumulado * 100, "%")],
      ["Recuperação / secagem", valor(detalhe.peso_recuperacao * 100, "%")],
    ],
    agregacaoExtra: (detalhe) => [
      ["Limiar de dia relevante", valor(detalhe.limiar_relevancia)],
    ],
    calculo: (
      <>
        <p>
          A Trafegabilidade estima condições meteorológicas que podem dificultar
          a circulação e operação de máquinas agrícolas. O índice diário combina
          a precipitação do dia, o acúmulo recente de chuva e um componente de
          recuperação/secagem.
        </p>
        <p>
          <b>Condição do dia atual:</b> representa o impacto da precipitação
          observada no próprio dia.
        </p>
        <p>
          <b>Acúmulo recente:</b> representa o efeito da precipitação acumulada
          nos últimos dias.
        </p>
        <p>
          <b>Recuperação / secagem:</b> representa a permanência do efeito da
          chuva recente e sua redução gradual durante períodos sem precipitação.
        </p>
        <p>
          <b>Fórmula:</b> T = peso_dia × componente_dia + peso_acumulado ×
          componente_acumulado + peso_recuperacao × componente_recuperacao.
        </p>
        <p>
          A precipitação é transformada em componentes por uma curva
          meteorológica fixa da metodologia.
        </p>
      </>
    ),
    interpretacao:
      "Precipitação recente mais intensa e persistente tende a elevar o indicador; a ausência de chuva por vários dias reduz gradualmente sua influência.",
    limitacao:
      "A Trafegabilidade representa uma condição ambiental favorável ou desfavorável à operação de máquinas e não uma medição direta da condição física do solo. Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
  },
  TEMPESTADES: {
    nome: "Tempestades Severas",
    resumo: "Combinação de vento médio diário e precipitação diária.",
    dados: (d) => [
      ["Vento médio diário", valor(d.velocidade_vento_media_m_s, " m/s")],
      ["Precipitação diária", valor(d.precipitacao_diaria_mm, " mm")],
    ],
    componentes: (d) => [
      ["Componente de vento", componente(d.componente_vento)],
      ["Componente de chuva", componente(d.componente_chuva)],
      ["Índice de vento", indice(d.indice_vento)],
      [
        "Fator combinado vento–chuva",
        componente(d.fator_combinado_vento_chuva),
      ],
    ],
    calculo: (
      <>
        <p>
          O vento médio diário e a precipitação do dia são normalizados pelas
          curvas vigentes.
        </p>
        <p>
          <b>Índice de vento:</b> 100 × componente de vento.
        </p>
        <p>
          <b>Fator combinado vento–chuva:</b> 0,75 + 0,25 × componente de chuva.
        </p>
        <p>
          <b>Índice diário:</b> índice de vento × fator combinado vento–chuva,
          limitado a 100.
        </p>
      </>
    ),
    interpretacao:
      "Ventos médios mais intensos e maior precipitação diária tendem a elevar o indicador combinado.",
    limitacao:
      "Não detecta diretamente granizo, raios, rajadas ou ocorrência observada de tempestade severa. Esses dados não participam atualmente do cálculo.",
  },
};

function Lista({ itens }) {
  return (
    <dl>
      {itens.map(([rotulo, conteudo]) => (
        <div key={rotulo}>
          <dt>{rotulo}</dt>
          <dd>{conteudo}</dd>
        </div>
      ))}
    </dl>
  );
}

function Proveniencia({ perigo, detalhe }) {
  const p = detalhe.proveniencia;
  return (
    <section className="hazard-detail-provenance">
      <h4>Proveniência</h4>
      <dl>
        <div>
          <dt>Fonte meteorológica</dt>
          <dd>{p.fonte_meteorologica}</dd>
        </div>
        <div>
          <dt>Dataset meteorológico</dt>
          <dd>{p.dataset_meteorologico}</dd>
        </div>
        {p.parametro_vento && (
          <>
            <div>
              <dt>Variável de vento</dt>
              <dd>{p.parametro_vento}</dd>
            </div>
            <div>
              <dt>Medição do vento</dt>
              <dd>Vento médio diário a {n(p.altura_vento_m)} m</dd>
            </div>
            <div>
              <dt>Unidade do vento</dt>
              <dd>{p.unidade_vento}</dd>
            </div>
          </>
        )}
        {perigo === "INSTABILIDADE" && (
          <>
            <div>
              <dt>Fonte da declividade</dt>
              <dd>{detalhe.fonte_declividade}</dd>
            </div>
            <div>
              <dt>Dataset de relevo</dt>
              <dd>{detalhe.dataset_declividade}</dd>
            </div>
          </>
        )}
      </dl>
    </section>
  );
}

function Agregacao90d({ agregacao, extra }) {
  return (
    <section className="hazard-detail-aggregation">
      <h4>Agregação histórica de 90 dias</h4>
      <p>
        {data(agregacao.inicio)} a {data(agregacao.fim)} · Os índices diários
        formam eventos; severidade, frequência, duração e recorrência compõem o
        resultado histórico.
      </p>
      <div className="hazard-aggregation-grid">
        <span>
          Severidade<b>{indice(agregacao.severidade)}</b>
        </span>
        <span>
          Frequência<b>{indice(agregacao.frequencia)}</b>
        </span>
        <span>
          Duração<b>{indice(agregacao.duracao)}</b>
        </span>
        <span>
          Recorrência<b>{indice(agregacao.recorrencia)}</b>
        </span>
      </div>
      <dl>
        <div>
          <dt>Dias relevantes</dt>
          <dd>{agregacao.quantidade_dias_relevantes}</dd>
        </div>
        <div>
          <dt>Eventos</dt>
          <dd>{agregacao.quantidade_eventos}</dd>
        </div>
        <div>
          <dt>Maior duração de evento</dt>
          <dd>{agregacao.maior_duracao_evento} dia(s)</dd>
        </div>
        <div>
          <dt>Cobertura</dt>
          <dd>{valor(agregacao.cobertura_percentual, "%")}</dd>
        </div>
        {extra?.map(([rotulo, conteudo]) => (
          <div key={rotulo}>
            <dt>{rotulo}</dt>
            <dd>{conteudo}</dd>
          </div>
        ))}
      </dl>
      <div className="hazard-aggregate-result">
        <span>Índice agregado final</span>
        <strong>{indice(agregacao.indice_agregado)}</strong>
        <Classe valor={agregacao.classificacao} />
      </div>
    </section>
  );
}

export function DetalhePerigo({ resumo, detalhe }) {
  const tituloId = useId(),
    config = configuracoes[resumo.perigo],
    dia = detalhe.dia_maior_indice;
  if (!config) return null;
  return (
    <details className="equip-card hazard-detail" aria-labelledby={tituloId}>
      <summary>
        <div>
          <span>Detalhamento do perigo</span>
          <h3 id={tituloId}>{config.nome}</h3>
          <p>{config.resumo}</p>
        </div>
        <div>
          <strong>{indice(detalhe.agregacao_90d.indice_agregado)}</strong>
          <Classe valor={detalhe.agregacao_90d.classificacao} />
        </div>
      </summary>
      <div className="hazard-detail-body">
        <section className="hazard-detail-result">
          <h4>Resultado</h4>
          <dl>
            <div>
              <dt>Índice agregado</dt>
              <dd>{indice(resumo.indice)}</dd>
            </div>
            <div>
              <dt>Classificação</dt>
              <dd>{resumo.classificacao || "Não disponível"}</dd>
            </div>
            <div>
              <dt>Contribuição para o score</dt>
              <dd>
                {resumo.contribuicao == null
                  ? "Não disponível"
                  : `${n(resumo.contribuicao)} pts`}
              </dd>
            </div>
            <div>
              <dt>Peso no índice</dt>
              <dd>{valor(resumo.peso * 100, "%")}</dd>
            </div>
          </dl>
        </section>
        <section className="hazard-detail-daily">
          <h4>Cálculo diário — dia de maior índice disponível</h4>
          {dia ? (
            <>
              <div className="hazard-daily-head">
                <span>
                  Data<b>{data(dia.data)}</b>
                </span>
                <span>
                  Índice diário<b>{indice(dia.indice_diario)}</b>
                </span>
              </div>
              <div className="hazard-detail-columns">
                <section>
                  <h5>Dados utilizados</h5>
                  <Lista itens={config.dados(dia)} />
                </section>
                <section>
                  <h5>Componentes intermediários</h5>
                  <Lista itens={config.componentes(dia)} />
                </section>
                {config.pesos && (
                  <section className="hazard-detail-pesos">
                    <h5>Pesos aplicados</h5>
                    <Lista itens={config.pesos(detalhe)} />
                  </section>
                )}
              </div>
            </>
          ) : (
            <p className="hazard-detail-unavailable">
              Nenhum índice diário disponível na janela atual.
            </p>
          )}
          {resumo.perigo === "INSTABILIDADE" && (
            <aside>
              <b>Contexto topográfico:</b> posição topográfica relativa{" "}
              {detalhe.posicao_topografica_relativa_m == null
                ? "não disponível"
                : `${n(detalhe.posicao_topografica_relativa_m)} m`}
              . É evidência contextual e não participa da fórmula de
              Instabilidade.
            </aside>
          )}
        </section>
        <Agregacao90d
          agregacao={detalhe.agregacao_90d}
          extra={config.agregacaoExtra?.(detalhe)}
        />
        <Proveniencia perigo={resumo.perigo} detalhe={detalhe} />
        <details className="hazard-detail-method">
          <summary>Como é calculado, interpretação e limitações</summary>
          <h4>Como é calculado</h4>
          {config.calculo}
          <h4>Interpretação</h4>
          <p>{config.interpretacao}</p>
          <h4>Limitações</h4>
          <p>{config.limitacao}</p>
        </details>
      </div>
    </details>
  );
}
