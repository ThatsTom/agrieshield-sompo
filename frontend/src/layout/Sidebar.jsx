import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

const gruposBase = [
  {
    label: "Monitoramento",
    items: [
      ["dashboard", "home", "Visão Geral"],
      ["operacoes", "activity", "Operações"],
      ["riscos", "gauge", "Riscos e Score"],
      ["alertas", "bell", "Alertas"],
      ["insights", "chart", "Insights"],
    ],
  },
  {
    label: "Gestão",
    items: [
      ["clientes", "users", "Clientes e Apólices"],
      ["relatorios", "file", "Relatórios"],
      ["dados", "database", "Dados e Fontes"],
    ],
  },
  {
    label: "Sistema",
    items: [
      ["perfil", "users", "Meu Perfil"],
      ["configuracoes", "settings", "Configurações"],
    ],
  },
];

function montarGrupos(isAdmin) {
  return gruposBase.map((grupo) => ({
    ...grupo,
    items:
      grupo.label === "Sistema" && isAdmin
        ? [["acessos", "shield", "Gerenciar Acessos"], ...grupo.items]
        : grupo.items,
  }));
}

function Navigation({ page, onNavigate, groups, mobile = false }) {
  return (
    <nav className={mobile ? "mobile-nav" : "nav"} aria-label="Navegação principal">
      {groups.map((group) => (
        <div className="nav-section" key={group.label}>
          <span className="nav-section-label">{group.label}</span>
          {group.items.map(([id, icon, label]) => (
            <button
              key={id}
              type="button"
              className={page === id ? "active" : ""}
              onClick={() => onNavigate(id)}
              title={label}
              aria-current={page === id ? "page" : undefined}
            >
              <span className="ico">
                <Icon name={icon} />
              </span>
              <span className="nav-label">{label}</span>
              {mobile && <Icon name="chevron" size={16} className="nav-chevron" />}
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}

function iniciais(perfil) {
  const nome = String(perfil?.nome_completo || perfil?.email || "Usuário");
  return nome.split(/\s+/).slice(0, 2).map((parte) => parte[0]).join("").toUpperCase();
}

export function Sidebar({ page, setPage, perfil, isAdmin, onLogout }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const toggleRef = useRef(null);
  const closeRef = useRef(null);
  const drawerRef = useRef(null);
  const groups = montarGrupos(isAdmin);
  const items = groups.flatMap((group) => group.items);
  const currentLabel = items.find(([id]) => id === page)?.[2] || "Visão Geral";

  useEffect(() => {
    if (!mobileOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    const handleKeyboard = (event) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
        window.setTimeout(() => toggleRef.current?.focus(), 0);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = drawerRef.current?.querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyboard);
    closeRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyboard);
    };
  }, [mobileOpen]);

  const navigate = (next) => {
    setMobileOpen(false);
    setPage(next);
  };

  const closeMobile = () => {
    setMobileOpen(false);
    window.setTimeout(() => toggleRef.current?.focus(), 0);
  };

  return (
    <>
      <header className="mobile-app-bar">
        <button
          ref={toggleRef}
          className="mobile-menu-trigger"
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Abrir menu de navegação"
          aria-expanded={mobileOpen}
        >
          <Icon name="menu" size={22} />
        </button>
        <button
          className="mobile-brand"
          type="button"
          onClick={() => navigate("dashboard")}
          aria-label="Ir para a visão geral"
        >
          <span className="logo" />
          <span>
            <b>AgriShield</b>
            <small>Sompo Seguros</small>
          </span>
        </button>
        <span className="mobile-current-page">{currentLabel}</span>
      </header>

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
        <Navigation page={page} onNavigate={setPage} groups={groups} />
        <div className="userbox">
          <button className="user-profile-button" type="button" onClick={() => setPage("perfil")} title="Abrir meu perfil">
            <div className="avatar">{iniciais(perfil)}</div>
            <div className="user-copy">
              <div className="nm">{perfil?.nome_completo || "Usuário AgriShield"}</div>
              <div className="rl">{perfil?.funcao || "Consultor"}</div>
            </div>
          </button>
          <button className="user-logout-button" type="button" onClick={() => onLogout("")} aria-label="Sair do AgriShield" title="Sair"><Icon name="back" size={16} /></button>
        </div>
      </aside>

      <button
        type="button"
        className={`mobile-nav-backdrop ${mobileOpen ? "is-open" : ""}`}
        onClick={closeMobile}
        aria-label="Fechar menu de navegação"
        tabIndex={mobileOpen ? 0 : -1}
      />
      <aside
        ref={drawerRef}
        className={`mobile-nav-drawer ${mobileOpen ? "is-open" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label="Menu de navegação"
        aria-hidden={!mobileOpen}
      >
        <div className="mobile-nav-head">
          <div className="brand">
            <div className="logo" />
            <div className="brand-copy">
              <b>AgriShield</b>
              <div className="sub">Sompo Seguros</div>
            </div>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="mobile-nav-close"
            onClick={closeMobile}
            aria-label="Fechar menu"
          >
            <Icon name="close" size={21} />
          </button>
        </div>
        <div className="mobile-nav-context">
          <span>Navegação</span>
          <b>{currentLabel}</b>
        </div>
        <Navigation page={page} onNavigate={navigate} groups={groups} mobile />
        <div className="mobile-userbox">
          <button type="button" className="mobile-user-profile" onClick={() => navigate("perfil")}>
            <div className="avatar">{iniciais(perfil)}</div>
            <span><b>{perfil?.nome_completo || "Usuário AgriShield"}</b><small>{perfil?.funcao || "Consultor"}</small></span>
          </button>
          <button className="user-logout-button" type="button" onClick={() => onLogout("")} aria-label="Sair do AgriShield"><Icon name="back" size={16} /></button>
        </div>
      </aside>
    </>
  );
}
