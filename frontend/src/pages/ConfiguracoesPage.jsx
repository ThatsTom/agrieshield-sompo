import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { API_URL } from "../api/core";
export function ConfiguracoesPage({ onNavigate, backendDemo }) {
  return (
    <>
      <PageHeader
        eyebrow="Sistema"
        title="Configurações"
        subtitle="Centralize os pontos de configuração disponíveis no protótipo sem misturar ajustes de interface com regras do modelo."
      />
      <div className="settings-grid">
        <section className="panel-card">
          <div className="settings-icon">
            <Icon name="database" />
          </div>
          <div>
            <span>Conexão local</span>
            <h2>API AgriShield</h2>
            <p>
              Endpoint usado pelo front para consultar cadastro, dashboard,
              território e integrações.
            </p>
            <code>{API_URL}</code>
            <div className={`system-status ${backendDemo ? "warning" : "ok"}`}>
              <i />
              {backendDemo
                ? "Modo demonstração / API indisponível"
                : "API conectada"}
            </div>
          </div>
        </section>
        <section className="panel-card">
          <div className="settings-icon">
            <Icon name="gauge" />
          </div>
          <div>
            <span>Modelo de risco</span>
            <h2>Pesos e coeficientes</h2>
            <p>
              Os parâmetros configuráveis são persistidos em{" "}
              <code>parametros_score.csv</code> e possuem validação própria.
            </p>
            <button
              className="btn btn-ghost"
              onClick={() => onNavigate("riscos")}
            >
              Abrir Riscos e Score <Icon name="arrow" size={15} />
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="settings-icon">
            <Icon name="map" />
          </div>
          <div>
            <span>Dados territoriais</span>
            <h2>Fontes e rastreabilidade</h2>
            <p>
              Consulte versões, métricas geoespaciais e os arquivos CSV que
              suportam o protótipo.
            </p>
            <button
              className="btn btn-ghost"
              onClick={() => onNavigate("dados")}
            >
              Abrir Dados e Fontes <Icon name="arrow" size={15} />
            </button>
          </div>
        </section>
        <section className="panel-card">
          <div className="settings-icon">
            <Icon name="file" />
          </div>
          <div>
            <span>Exportação</span>
            <h2>Relatórios do portfólio</h2>
            <p>
              Gere uma visão cadastral do portfólio pronta para impressão.
            </p>
            <button
              className="btn btn-ghost"
              onClick={() => onNavigate("relatorios")}
            >
              Abrir Relatórios <Icon name="arrow" size={15} />
            </button>
          </div>
        </section>
      </div>
      <div className="notice-card">
        <Icon name="info" />
        <div>
          <b>Configurações ambientais</b>
          <p>
            Chaves de serviços externos e variáveis sensíveis continuam fora do
            front e devem ser configuradas no ambiente do backend conforme o{" "}
            <code>.env.example</code>.
          </p>
        </div>
      </div>
    </>
  );
}
