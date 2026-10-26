import { useEffect, useState } from "react";
import { Icon } from "../layout/Icon";
import { supabase } from "./supabase";
import { useAuth } from "./AuthProvider";

const INTERVALO_REENVIO_MS = 60 * 1000;
const ESPERA_LIMITE_EMAIL_MS = 60 * 60 * 1000;

function limiteDeEmailAtingido(erro) {
  const codigo = String(erro?.code || "").toLowerCase();
  const texto = String(erro?.message || "").toLowerCase();
  return (
    codigo === "over_email_send_rate_limit" ||
    texto.includes("email rate limit") ||
    texto.includes("rate limit exceeded")
  );
}

function mensagemErro(erro) {
  const texto = String(erro?.message || "").toLowerCase();
  if (texto.includes("seconds"))
    return "Aguarde 60 segundos antes de solicitar outro código.";
  if (texto.includes("expired") || texto.includes("invalid"))
    return "O código é inválido ou expirou. Solicite um novo código.";
  if (texto.includes("signups not allowed") || texto.includes("user not found"))
    return "Conta não encontrada. Use a opção Criar conta.";
  return erro?.message || "Não foi possível continuar. Tente novamente.";
}

function formatarEspera(milissegundos) {
  const total = Math.max(0, Math.ceil(milissegundos / 1000));
  const minutos = Math.floor(total / 60);
  const segundos = String(total % 60).padStart(2, "0");
  return `${minutos}:${segundos}`;
}

export function AuthPage() {
  const { motivoSaida, limparMotivoSaida } = useAuth();
  const [tipo, setTipo] = useState("entrar");
  const [etapa, setEtapa] = useState("dados");
  const [email, setEmail] = useState("");
  const [nome, setNome] = useState("");
  const [funcao, setFuncao] = useState("Consultor");
  const [codigo, setCodigo] = useState("");
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [bloqueioAte, setBloqueioAte] = useState(0);
  const [agora, setAgora] = useState(Date.now());
  const bloqueado = bloqueioAte > agora;
  const espera = formatarEspera(bloqueioAte - agora);

  useEffect(() => {
    if (!bloqueado) return undefined;
    const intervalo = window.setInterval(() => setAgora(Date.now()), 1000);
    return () => window.clearInterval(intervalo);
  }, [bloqueado]);

  const trocarTipo = (proximo) => {
    setTipo(proximo);
    setEtapa("dados");
    setCodigo("");
    setErro("");
    limparMotivoSaida();
  };

  const enviarEmail = async (evento) => {
    evento?.preventDefault();
    if (bloqueado) return;
    setErro("");
    setEnviando(true);
    try {
      const emailNormalizado = email.trim().toLowerCase();
      const options = {
        shouldCreateUser: tipo === "cadastro",
        emailRedirectTo: window.location.origin,
      };
      if (tipo === "cadastro") {
        options.data = {
          nome_completo: nome.trim(),
          funcao: funcao.trim(),
          origem_aplicacao: "agrishield",
        };
      }
      const { error } = await supabase.auth.signInWithOtp({
        email: emailNormalizado,
        options,
      });
      if (error) throw error;
      setEmail(emailNormalizado);
      const proximoEnvio = Date.now() + INTERVALO_REENVIO_MS;
      setAgora(Date.now());
      setBloqueioAte(proximoEnvio);
      setEtapa(tipo === "cadastro" ? "confirmacao" : "codigo");
    } catch (exc) {
      if (limiteDeEmailAtingido(exc)) {
        const proximaTentativa = Date.now() + ESPERA_LIMITE_EMAIL_MS;
        setAgora(Date.now());
        setBloqueioAte(proximaTentativa);
        setErro(
          `O limite temporário de e-mails foi atingido e ${tipo === "cadastro" ? "a confirmação" : "o código"} não foi enviado. Tente novamente em até ${formatarEspera(ESPERA_LIMITE_EMAIL_MS)}.`,
        );
      } else {
        setErro(mensagemErro(exc));
      }
    } finally {
      setEnviando(false);
    }
  };

  const confirmarCodigo = async (evento) => {
    evento.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      const { error } = await supabase.auth.verifyOtp({
        email: email.trim().toLowerCase(),
        token: codigo,
        type: "email",
      });
      if (error) throw error;
    } catch (exc) {
      setErro(mensagemErro(exc));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Apresentação do AgriShield">
        <div className="auth-brand">
          <span className="logo" />
          <div><b>AgriShield</b><span>Sompo Seguros</span></div>
        </div>
        <div className="auth-story-copy">
          <span className="auth-eyebrow">Inteligência para o risco rural</span>
          <h1>Decisões mais claras começam com acesso seguro.</h1>
          <p>
            Entre para acompanhar portfólio, alertas climáticos, exposição e
            recomendações operacionais em um único ambiente.
          </p>
          <div className="auth-benefits">
            <article><Icon name="shield" /><span><b>Acesso aprovado</b><small>Novos usuários passam pela validação do administrador.</small></span></article>
            <article><Icon name="activity" /><span><b>Sessão protegida</b><small>Saída automática após 15 minutos sem atividade.</small></span></article>
            <article><Icon name="chart" /><span><b>Leitura prática</b><small>Informações direcionadas ao trabalho do consultor.</small></span></article>
          </div>
        </div>
        <small className="auth-story-foot">AgriShield · Ambiente de subscrição e riscos</small>
      </section>

      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-card">
          {motivoSaida && (
            <div className="auth-session-notice" role="status">
              <Icon name="info" size={17} /><span>{motivoSaida}</span>
            </div>
          )}
          <div className="auth-tabs" role="tablist" aria-label="Acesso à conta">
            <button type="button" role="tab" aria-selected={tipo === "entrar"} className={tipo === "entrar" ? "is-active" : ""} onClick={() => trocarTipo("entrar")}>Entrar</button>
            <button type="button" role="tab" aria-selected={tipo === "cadastro"} className={tipo === "cadastro" ? "is-active" : ""} onClick={() => trocarTipo("cadastro")}>Criar conta</button>
          </div>

          {etapa === "dados" ? (
            <form onSubmit={enviarEmail} className="auth-form">
              <header>
                <span>{tipo === "cadastro" ? "Novo acesso" : "Bem-vindo de volta"}</span>
                <h2 id="auth-title">{tipo === "cadastro" ? "Crie sua conta" : "Acesse o AgriShield"}</h2>
                <p>
                  {tipo === "cadastro"
                    ? "Enviaremos um link para confirmar seu e-mail. Depois disso, seu acesso ficará aguardando aprovação."
                    : "Você receberá um código de seis dígitos no e-mail. Não usamos senha."}
                </p>
              </header>
              {tipo === "cadastro" && (
                <>
                  <label>Nome completo<input value={nome} onChange={(e) => setNome(e.target.value)} required minLength={2} maxLength={120} autoComplete="name" placeholder="Como devemos chamar você?" /></label>
                  <label>Função<input value={funcao} onChange={(e) => setFuncao(e.target.value)} required minLength={2} maxLength={80} autoComplete="organization-title" placeholder="Ex.: Consultor de riscos" /></label>
                </>
              )}
              <label>E-mail corporativo<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" placeholder="voce@empresa.com.br" /></label>
              {erro && <div className="auth-error" role="alert"><Icon name="warning" size={16} />{erro}</div>}
              <button className="btn btn-red auth-submit" type="submit" disabled={enviando || bloqueado}>{enviando ? "Enviando..." : bloqueado ? `Tente novamente em ${espera}` : tipo === "cadastro" ? "Enviar confirmação por e-mail" : "Receber código por e-mail"}<Icon name="arrow" size={16} /></button>
              {tipo === "cadastro" && <small className="auth-consent">Ao continuar, você solicita acesso ao ambiente AgriShield. Confirme o link recebido para entrar na fila de aprovação.</small>}
            </form>
          ) : etapa === "confirmacao" ? (
            <section className="auth-form auth-confirmation-card" aria-labelledby="auth-title" role="status">
              <button className="auth-back" type="button" onClick={() => { setEtapa("dados"); setErro(""); }}><Icon name="back" size={15} /> Alterar e-mail</button>
              <div className="auth-confirmation-icon"><Icon name="check" size={30} /></div>
              <header>
                <span>Confirmação enviada</span>
                <h2 id="auth-title">Verifique seu e-mail</h2>
                <p>Enviamos um link de confirmação para <b>{email}</b>.</p>
              </header>
              <ol className="auth-confirmation-steps">
                <li><b>1</b><span>Abra a mensagem enviada pelo AgriShield.</span></li>
                <li><b>2</b><span>Clique em <strong>Confirmar meu e-mail</strong>.</span></li>
                <li><b>3</b><span>Depois da confirmação, aguarde a aprovação do administrador.</span></li>
              </ol>
              <p className="auth-confirmation-help">Caso não encontre a mensagem, verifique também as pastas de spam e lixo eletrônico.</p>
              {erro && <div className="auth-error" role="alert"><Icon name="warning" size={16} />{erro}</div>}
              <button className="btn btn-ghost auth-submit" type="button" disabled={enviando || bloqueado} onClick={enviarEmail}>{enviando ? "Enviando..." : bloqueado ? `Reenviar em ${espera}` : "Reenviar e-mail de confirmação"}<Icon name="refresh" size={16} /></button>
            </section>
          ) : (
            <form onSubmit={confirmarCodigo} className="auth-form auth-code-form">
              <button className="auth-back" type="button" onClick={() => { setEtapa("dados"); setCodigo(""); setErro(""); }}><Icon name="back" size={15} /> Alterar e-mail</button>
              <header>
                <span>Verificação de e-mail</span>
                <h2 id="auth-title">Digite o código recebido</h2>
                <p>Enviamos um código para <b>{email}</b>. Ele é temporário e só pode ser usado uma vez.</p>
              </header>
              <label className="auth-code-label">Código de seis dígitos<input value={codigo} onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))} required minLength={6} maxLength={6} inputMode="numeric" autoComplete="one-time-code" autoFocus placeholder="000000" /></label>
              {erro && <div className="auth-error" role="alert"><Icon name="warning" size={16} />{erro}</div>}
              <button className="btn btn-red auth-submit" type="submit" disabled={enviando || codigo.length !== 6}>{enviando ? "Confirmando..." : "Confirmar e continuar"}<Icon name="check" size={16} /></button>
              <button className="auth-resend" type="button" disabled={enviando || bloqueado} onClick={enviarEmail}>{bloqueado ? `Reenviar em ${espera}` : "Não recebeu? Enviar outro código"}</button>
            </form>
          )}
        </div>
      </section>
    </main>
  );
}
