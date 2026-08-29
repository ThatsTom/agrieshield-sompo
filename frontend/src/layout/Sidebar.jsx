import { Icon } from "./Icon";
const items = [
  ["dashboard", "home", "Visão Geral"],
  ["clientes", "users", "Clientes e Apólices"],
  ["operacoes", "activity", "Operações"],
  ["riscos", "gauge", "Riscos e Score"],
  ["alertas", "bell", "Alertas"],
  ["insights", "chart", "Insights"],
  ["relatorios", "file", "Relatórios"],
  ["dados", "database", "Dados e Fontes"],
  ["configuracoes", "settings", "Configurações"],
];
export function Sidebar({ page, setPage }) {
  return (
    <aside className="sidebar">
      <button
        className="brand brand-button"
        type="button"
        onClick={() => setPage("dashboard")}
        aria-label="Ir para a visão geral"
      >
        <div className="logo" />
        <div className="brand-copy">
          <b>AgriShield</b>
          <div className="sub">Sompo Seguros</div>
        </div>
      </button>
      <nav className="nav" aria-label="Navegação principal">
        {items.map(([id, icon, label]) => (
          <button
            key={id}
            className={page === id ? "active" : ""}
            onClick={() => setPage(id)}
            title={label}
          >
            <span className="ico">
              <Icon name={icon} />
            </span>
            <span className="nav-label">{label}</span>
          </button>
        ))}
      </nav>
      <div className="userbox">
        <div className="avatar">AS</div>
        <div className="user-copy">
          <div className="nm">Analista Sompo</div>
          <div className="rl">Subscrição e Riscos</div>
        </div>
      </div>
    </aside>
  );
}
