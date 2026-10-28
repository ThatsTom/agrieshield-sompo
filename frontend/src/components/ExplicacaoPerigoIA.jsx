import { ExplicacaoCalculoIA } from "./ExplicacaoCalculoIA";

const nf = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const numero = (valor) => valor == null ? "indisponível" : nf.format(valor);
const data = (valor) => valor
  ? new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${valor}T00:00:00Z`))
  : "indisponível";

export function ExplicacaoPerigoIA({ idFazenda, avaliacao, perigo, nomePerigo }) {
  return (
    <ExplicacaoCalculoIA idFazenda={idFazenda} avaliacao={avaliacao} perigo={perigo} nomePerigo={nomePerigo}>
      {(dados) => <RelatorioPerigo dados={dados} />}
    </ExplicacaoCalculoIA>
  );
}

function RelatorioPerigo({ dados }) {
  const { calculo: c, explicacao: ia } = dados;
  const j = c.janela_90d;
  const diarioDisponivel = c.dia?.indice_diario != null;
  return (
    <>
      <header>
        <h4>Como chegamos ao valor de {c.nome_perigo}</h4>
        <span>{c.fazenda} · {c.fonte_meteorologica} · referência {data(c.data_referencia)}</span>
      </header>
      <p>{ia.resumo}</p>
      {c.disponibilidade_diaria?.motivo && <p className="hydric-ai-limits" role="status">{c.disponibilidade_diaria.motivo}</p>}
      <div className="hydric-ai-steps">
        <section>
          <h5>1. Dados utilizados{c.dia?.data ? ` em ${data(c.dia.data)}` : ""}</h5>
          <dl className="hydric-ai-data">
            {c.dados_utilizados.map((dado) => (
              <div key={dado.rotulo}>
                <dt>{dado.rotulo}</dt>
                <dd>{dado.valor == null ? "indisponível" : `${numero(dado.valor)}${dado.unidade ? ` ${dado.unidade}` : ""}`}</dd>
              </div>
            ))}
          </dl>
          <p>{ia.leitura_dados}</p>
        </section>
        <section>
          <h5>2. Cálculo diário: {diarioDisponivel ? `${numero(c.dia.indice_diario)} / 100` : "dados insuficientes"}</h5>
          {c.etapas.map((etapa) => (
            <div key={etapa.titulo}>
              <b>{etapa.titulo}</b>
              <p className="hydric-ai-formula">{etapa.formula}</p>
            </div>
          ))}
          {!diarioDisponivel && <p>Não há resultado diário calculável com as entradas disponíveis. Ausência de dado não significa valor igual a zero.</p>}
          <p>{ia.leitura_calculo}</p>
        </section>
        <section>
          <h5>3. Valor da janela de 90 dias: {j.indice == null ? "dados insuficientes" : `${numero(j.indice)} / 100`}</h5>
          <p>Período: {data(j.inicio)} a {data(j.fim)}; {j.dias_disponiveis} de {j.dias_esperados} dias disponíveis; {j.dias_relevantes} dias relevantes e {j.eventos} eventos. O exemplo diário e o indicador da janela representam períodos diferentes.</p>
          {j.indice != null ? (
            <p className="hydric-ai-formula">
              Índice da janela ≈ {numero(j.pesos.severidade * 100)}% × {numero(j.componentes.severidade)} + {numero(j.pesos.frequencia * 100)}% × {numero(j.componentes.frequencia)} + {numero(j.pesos.duracao * 100)}% × {numero(j.componentes.duracao)} + {numero(j.pesos.recorrencia * 100)}% × {numero(j.componentes.recorrencia)} = {numero(j.indice)}.
            </p>
          ) : <p>A janela não tem dados suficientes para publicar o indicador.</p>}
          <p>{ia.leitura_janela}</p>
        </section>
      </div>
      <p className="hydric-ai-limits">{ia.limitacoes} {c.limitacoes.join(" ")}</p>
      <small>Explicação por {dados.modelo}; números e fórmulas fornecidos pelo motor AgriShield.</small>
    </>
  );
}
