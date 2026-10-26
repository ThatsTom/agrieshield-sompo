import App from "../App";
import { Icon } from "../layout/Icon";
import { AccessStatusPage } from "./AccessStatusPage";
import { AuthPage } from "./AuthPage";
import { useAuth } from "./AuthProvider";

function LoadingAuth() {
  return <main className="auth-loading" role="status"><span className="logo" /><div><b>AgriShield</b><small>Validando sessão segura...</small></div></main>;
}

export function AuthGate() {
  const auth = useAuth();
  if (!auth.configurado) {
    return <main className="auth-config-error"><Icon name="warning" size={28} /><h1>Autenticação não configurada</h1><p>Defina VITE_SUPABASE_URL e VITE_SUPABASE_PUBLISHABLE_KEY no frontend.</p></main>;
  }
  if (auth.carregando) return <LoadingAuth />;
  if (!auth.session) return <AuthPage />;
  if (!auth.perfil) {
    if (auth.erroPerfil) {
      return <main className="auth-config-error"><Icon name="warning" size={28} /><h1>Não foi possível validar seu acesso</h1><p>{auth.erroPerfil}</p><div><button className="btn btn-red" onClick={auth.carregarPerfil}>Tentar novamente</button><button className="btn btn-ghost" onClick={() => auth.sair("")}>Sair</button></div></main>;
    }
    return <LoadingAuth />;
  }
  if (auth.perfil.status_acesso !== "aprovado") {
    return <AccessStatusPage perfil={auth.perfil} onRefresh={auth.carregarPerfil} onLogout={auth.sair} carregando={auth.perfilCarregando} />;
  }
  return <App perfilUsuario={auth.perfil} onPerfilAtualizado={auth.definirPerfil} onLogout={auth.sair} isAdmin={auth.perfil.papel === "administrador"} />;
}
