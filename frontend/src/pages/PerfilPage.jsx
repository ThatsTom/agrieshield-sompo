import { useEffect, useState } from "react";
import { fetchJSON } from "../api/core";
import { Icon } from "../layout/Icon";
import { PageHeader } from "../layout/PageHeader";

export function PerfilPage({ perfil, onPerfilAtualizado, onLogout, showToast }) {
  const [form, setForm] = useState({ nome_completo: "", funcao: "", telefone: "" });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  useEffect(() => {
    setForm({
      nome_completo: perfil?.nome_completo || "",
      funcao: perfil?.funcao || "",
      telefone: perfil?.telefone || "",
    });
  }, [perfil]);
  const alterar = (campo) => (evento) => setForm((atual) => ({ ...atual, [campo]: evento.target.value }));
  const salvar = async (evento) => {
    evento.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      const resposta = await fetchJSON("/api/auth/perfil", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      onPerfilAtualizado(resposta.perfil);
      showToast("Perfil atualizado com sucesso");
    } catch (exc) {
      setErro(exc?.message || "Não foi possível atualizar o perfil.");
    } finally {
      setSalvando(false);
    }
  };
  return (
    <>
      <PageHeader eyebrow="Minha conta" title="Perfil do usuário" subtitle="Mantenha seus dados profissionais atualizados e consulte a segurança da sua sessão." />
      <div className="profile-layout">
        <form className="panel-card profile-form" onSubmit={salvar}>
          <div className="profile-identity">
            <div className="avatar profile-avatar">{String(perfil?.nome_completo || "U").split(/\s+/).slice(0, 2).map((parte) => parte[0]).join("").toUpperCase()}</div>
            <div><span>Perfil AgriShield</span><h2>{perfil?.nome_completo}</h2><p>{perfil?.email}</p></div>
          </div>
          <div className="profile-fields">
            <label>Nome completo<input value={form.nome_completo} onChange={alterar("nome_completo")} minLength={2} maxLength={120} required autoComplete="name" /></label>
            <label>Função<input value={form.funcao} onChange={alterar("funcao")} minLength={2} maxLength={80} required autoComplete="organization-title" /></label>
            <label>Telefone<input value={form.telefone} onChange={alterar("telefone")} maxLength={30} autoComplete="tel" placeholder="(00) 00000-0000" /></label>
            <label>E-mail confirmado<input value={perfil?.email || ""} readOnly disabled /></label>
          </div>
          {erro && <div className="auth-error" role="alert"><Icon name="warning" size={16} />{erro}</div>}
          <div className="profile-form-actions"><button className="btn btn-red" type="submit" disabled={salvando}><Icon name="save" size={15} />{salvando ? "Salvando..." : "Salvar alterações"}</button></div>
        </form>
        <aside className="profile-security">
          <section className="panel-card"><div className="settings-icon"><Icon name="shield" /></div><div><span>Estado do acesso</span><h2>Acesso aprovado</h2><p>Sua conta está liberada para usar os recursos do AgriShield.</p><span className="access-badge is-approved"><i />Aprovado</span></div></section>
          <section className="panel-card"><div className="settings-icon"><Icon name="activity" /></div><div><span>Segurança da sessão</span><h2>15 minutos de inatividade</h2><p>A sessão é encerrada automaticamente quando não há interação com a página.</p><button className="btn btn-ghost" type="button" onClick={() => onLogout("")}><Icon name="back" size={15} />Sair agora</button></div></section>
        </aside>
      </div>
    </>
  );
}
