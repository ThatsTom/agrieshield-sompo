import { Icon } from "../layout/Icon";

export function AccessStatusPage({ perfil, onRefresh, onLogout, carregando }) {
  const rejeitado = perfil?.status_acesso === "rejeitado";
  return (
    <main className="access-status-page">
      <section className="access-status-card">
        <div className={`access-status-icon ${rejeitado ? "is-rejected" : ""}`}>
          <Icon name={rejeitado ? "warning" : "shield"} size={28} />
        </div>
        <span className="auth-eyebrow">Conta confirmada</span>
        <h1>{rejeitado ? "Acesso não aprovado" : "Aguardando aprovação"}</h1>
        <p>
          {rejeitado
            ? "O administrador não liberou esta conta para acessar o AgriShield."
            : "Seu e-mail foi confirmado. O administrador precisa liberar sua entrada no sistema."}
        </p>
        {rejeitado && perfil?.motivo_rejeicao && (
          <div className="access-reason"><b>Motivo informado</b><span>{perfil.motivo_rejeicao}</span></div>
        )}
        <div className="access-account"><div className="avatar">{String(perfil?.nome_completo || perfil?.email || "U").slice(0, 2).toUpperCase()}</div><span><b>{perfil?.nome_completo}</b><small>{perfil?.email}</small></span></div>
        <div className="access-status-actions">
          <button className="btn btn-red" type="button" onClick={onRefresh} disabled={carregando}><Icon name="refresh" size={15} />{carregando ? "Verificando..." : "Verificar aprovação"}</button>
          <button className="btn btn-ghost" type="button" onClick={() => onLogout("")}>Sair desta conta</button>
        </div>
        <small>A aprovação é exclusiva do administrador do AgriShield.</small>
      </section>
    </main>
  );
}
