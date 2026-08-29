import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { tituloOperacao } from "../utils/format";
export function RelatoriosPage({ fazendas, scorePreview }) {
  return (
    <>
      <PageHeader
        eyebrow="Documentação"
        title="Relatórios"
        subtitle="Consolide o portfólio para revisão e impressão."
        actions={
          <button className="btn btn-ghost" onClick={() => window.print()}>
            <Icon name="print" size={16} /> Imprimir
          </button>
        }
      />
      <section className="report-cover panel-card">
        <div>
          <span className="report-kicker">AgriShield · Sompo Seguros</span>
          <h2>Relatório de Portfólio Rural</h2>
          <p>
            Resumo cadastral das propriedades seguradas e do status de contexto
            territorial.
          </p>
        </div>
        <div className="report-summary">
          <span>
            <small>Propriedades</small>
            <b>{fazendas.length}</b>
          </span>
          <span>
            <small>Contexto pronto</small>
            <b>
              {
                fazendas.filter(
                  (f) =>
                    String(f.status_geoespacial).toUpperCase() === "SUCESSO",
                ).length
              }
            </b>
          </span>
          <span>
            <small>Scores carregados</small>
            <b>{Object.keys(scorePreview).length}</b>
          </span>
        </div>
      </section>
      <div className="table-shell report-table">
        <table>
          <thead>
            <tr>
              <th>Fazenda</th>
              <th>Apólice</th>
              <th>Localização</th>
              <th>Operação</th>
              <th>Território</th>
              <th>Score</th>
            </tr>
          </thead>
          <tbody>
            {fazendas.map((f) => {
              const s = scorePreview[f.id];
              return (
                <tr key={f.id}>
                  <td>
                    <b>{f.nome_fazenda}</b>
                  </td>
                  <td>{f.numero_apolice}</td>
                  <td>
                    {f.cidade}/{f.uf}
                  </td>
                  <td>{tituloOperacao(f.tipo_operacao)}</td>
                  <td>
                    {String(f.status_geoespacial || "PENDENTE").toUpperCase()}
                  </td>
                  <td>
                    {s
                      ? `${s.score}/100 · ${s.condicao_atual}`
                      : "Não carregado"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="notice-card report-disclaimer">
        <Icon name="shield" />
        <div>
          <b>Uso do relatório</b>
          <p>
            Este material organiza informações do protótipo. Não substitui laudo
            técnico, inspeção, regulação ou decisão atuarial.
          </p>
        </div>
      </div>
    </>
  );
}
