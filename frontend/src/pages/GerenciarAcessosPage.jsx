import { useEffect, useMemo, useState } from "react";
import { fetchJSON } from "../api/core";
import { Icon } from "../layout/Icon";
import { PageHeader } from "../layout/PageHeader";

const STATUS = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  rejeitado: "Rejeitado",
};

function dataCurta(valor) {
  if (!valor) return "—";
  const data = new Date(valor);
  return Number.isNaN(data.getTime()) ? "—" : new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(data);
}

export function GerenciarAcessosPage({ showToast }) {
  const [usuarios, setUsuarios] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");
  const [filtro, setFiltro] = useState("todos");
  const [busca, setBusca] = useState("");
  const [processando, setProcessando] = useState("");
  const [rejeicao, setRejeicao] = useState(null);

  const carregar = async () => {
    setCarregando(true);
    setErro("");
    try {
      const resposta = await fetchJSON("/api/auth/usuarios");
      setUsuarios(resposta.usuarios || []);
    } catch (exc) {
      setErro(exc?.message || "Não foi possível carregar os usuários.");
    } finally {
      setCarregando(false);
    }
  };
  useEffect(() => { carregar(); }, []);

  const contagens = useMemo(() => Object.fromEntries(["pendente", "aprovado", "rejeitado"].map((status) => [status, usuarios.filter((usuario) => usuario.status_acesso === status).length])), [usuarios]);
  const visiveis = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return usuarios.filter((usuario) => (filtro === "todos" || usuario.status_acesso === filtro) && (!termo || `${usuario.nome_completo} ${usuario.email} ${usuario.funcao}`.toLowerCase().includes(termo)));
  }, [usuarios, filtro, busca]);

  const atualizar = async (usuario, status, motivo = "") => {
    setProcessando(usuario.usuario_id);
    setErro("");
    try {
      const resposta = await fetchJSON(`/api/auth/usuarios/${usuario.usuario_id}/acesso`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status_acesso: status, funcao: usuario.funcao, motivo_rejeicao: motivo }),
      });
      setUsuarios((atuais) => atuais.map((item) => item.usuario_id === usuario.usuario_id ? resposta.perfil : item));
      setRejeicao(null);
      showToast(status === "aprovado" ? "Acesso aprovado" : status === "rejeitado" ? "Acesso rejeitado" : "Acesso movido para pendente");
    } catch (exc) {
      setErro(exc?.message || "Não foi possível atualizar o acesso.");
    } finally {
      setProcessando("");
    }
  };

  return (
    <>
      <PageHeader eyebrow="Administração" title="Gerenciar acessos" subtitle="Aprove ou rejeite as contas que podem entrar no ambiente AgriShield." />
      <div className="access-admin-summary">
        <article><span>Total</span><b>{usuarios.length}</b><small>perfis do AgriShield</small></article>
        <article className="is-pending"><span>Aguardando</span><b>{contagens.pendente || 0}</b><small>pedidos para revisar</small></article>
        <article className="is-approved"><span>Aprovados</span><b>{contagens.aprovado || 0}</b><small>com acesso ativo</small></article>
        <article className="is-rejected"><span>Rejeitados</span><b>{contagens.rejeitado || 0}</b><small>sem acesso ao sistema</small></article>
      </div>
      <section className="panel-card access-admin-panel">
        <div className="access-admin-toolbar">
          <div className="search"><span><Icon name="search" size={17} /></span><input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome, e-mail ou função" aria-label="Buscar usuários" /></div>
          <div className="access-filter-tabs" aria-label="Filtrar por status">{["todos", "pendente", "aprovado", "rejeitado"].map((status) => <button type="button" key={status} className={filtro === status ? "is-active" : ""} onClick={() => setFiltro(status)}>{status === "todos" ? "Todos" : STATUS[status]}</button>)}</div>
          <button className="btn btn-ghost" type="button" onClick={carregar} disabled={carregando}><Icon name="refresh" size={15} />Atualizar</button>
        </div>
        {erro && <div className="auth-error access-admin-error" role="alert"><Icon name="warning" size={16} />{erro}</div>}
        {carregando ? <div className="access-admin-empty" role="status"><span className="ai-loading-dot is-active" /><b>Carregando acessos...</b></div> : visiveis.length ? (
          <div className="access-users-list">{visiveis.map((usuario) => {
            const admin = usuario.papel === "administrador";
            return <article key={usuario.usuario_id}>
              <div className="avatar">{String(usuario.nome_completo || usuario.email).split(/\s+/).slice(0, 2).map((parte) => parte[0]).join("").toUpperCase()}</div>
              <div className="access-user-main"><div><b>{usuario.nome_completo}</b>{admin && <span className="admin-chip">Administrador</span>}</div><span>{usuario.email}</span><small>{usuario.funcao || "Função não informada"}</small></div>
              <div className="access-user-date"><span>Cadastro</span><b>{dataCurta(usuario.created_at)}</b><small>Último acesso: {dataCurta(usuario.ultimo_acesso_em)}</small></div>
              <span className={`access-badge is-${usuario.status_acesso}`}><i />{STATUS[usuario.status_acesso]}</span>
              <div className="access-user-actions">{!admin && <>{usuario.status_acesso !== "aprovado" && <button className="access-action approve" type="button" disabled={processando === usuario.usuario_id} onClick={() => atualizar(usuario, "aprovado")}><Icon name="check" size={14} />Aprovar</button>}{usuario.status_acesso !== "rejeitado" && <button className="access-action reject" type="button" disabled={processando === usuario.usuario_id} onClick={() => setRejeicao(usuario)}><Icon name="close" size={14} />Rejeitar</button>}{usuario.status_acesso !== "pendente" && <button className="access-action neutral" type="button" disabled={processando === usuario.usuario_id} onClick={() => atualizar(usuario, "pendente")}><Icon name="refresh" size={14} />Revisar</button>}</>}</div>
            </article>;
          })}</div>
        ) : <div className="access-admin-empty"><Icon name="users" size={25} /><b>Nenhum usuário encontrado</b><span>Ajuste os filtros ou aguarde um novo pedido de acesso.</span></div>}
      </section>
      {rejeicao && <div className="modal-backdrop" role="presentation"><section className="access-reject-dialog" role="dialog" aria-modal="true" aria-labelledby="reject-title"><div className="access-status-icon is-rejected"><Icon name="warning" size={22} /></div><h2 id="reject-title">Rejeitar acesso</h2><p>Informe ao usuário por que <b>{rejeicao.nome_completo}</b> não poderá acessar o sistema.</p><label>Motivo<textarea autoFocus rows={4} maxLength={500} value={rejeicao.motivo || ""} onChange={(e) => setRejeicao((atual) => ({ ...atual, motivo: e.target.value }))} placeholder="Ex.: vínculo ainda não validado." /></label><div><button className="btn btn-ghost" type="button" onClick={() => setRejeicao(null)}>Cancelar</button><button className="btn btn-red" type="button" disabled={!String(rejeicao.motivo || "").trim() || Boolean(processando)} onClick={() => atualizar(rejeicao, "rejeitado", rejeicao.motivo)}>Confirmar rejeição</button></div></section></div>}
    </>
  );
}
