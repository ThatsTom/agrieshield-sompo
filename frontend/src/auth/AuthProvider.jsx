import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { fetchJSON } from "../api/core";
import { supabase, supabaseConfigured } from "./supabase";

export const INACTIVITY_MS = 15 * 60 * 1000;
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [perfil, setPerfil] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [perfilCarregando, setPerfilCarregando] = useState(false);
  const [erroPerfil, setErroPerfil] = useState("");
  const [motivoSaida, setMotivoSaida] = useState("");
  const requisicaoPerfil = useRef(0);

  const carregarPerfil = useCallback(async () => {
    if (!supabase) return null;
    const numero = ++requisicaoPerfil.current;
    setPerfilCarregando(true);
    setErroPerfil("");
    try {
      const resposta = await fetchJSON("/api/auth/me");
      if (numero === requisicaoPerfil.current) setPerfil(resposta.perfil);
      return resposta.perfil;
    } catch (erro) {
      if (numero === requisicaoPerfil.current) {
        setPerfil(null);
        setErroPerfil(
          erro?.message || "Não foi possível carregar seu acesso ao AgriShield.",
        );
      }
      return null;
    } finally {
      if (numero === requisicaoPerfil.current) setPerfilCarregando(false);
    }
  }, []);

  const sair = useCallback(async (motivo = "") => {
    requisicaoPerfil.current += 1;
    setMotivoSaida(motivo);
    setPerfil(null);
    setErroPerfil("");
    if (supabase) await supabase.auth.signOut({ scope: "local" });
    setSession(null);
  }, []);

  useEffect(() => {
    if (!supabase) {
      setCarregando(false);
      return undefined;
    }
    let ativo = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!ativo) return;
      setSession(data.session || null);
      setCarregando(false);
      if (data.session) window.setTimeout(carregarPerfil, 0);
    });
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_evento, proximaSessao) => {
      if (!ativo) return;
      setSession(proximaSessao || null);
      if (!proximaSessao) {
        requisicaoPerfil.current += 1;
        setPerfil(null);
        setPerfilCarregando(false);
      } else {
        window.setTimeout(carregarPerfil, 0);
      }
      setCarregando(false);
    });
    return () => {
      ativo = false;
      subscription.unsubscribe();
    };
  }, [carregarPerfil]);

  useEffect(() => {
    if (!session?.user?.id) return undefined;
    const chave = `agrishield:last-activity:${session.user.id}`;
    const atividadePersistida = Number(localStorage.getItem(chave) || 0);
    let ultimaAtividade = atividadePersistida || Date.now();
    let ultimoRegistro = 0;

    if (Date.now() - ultimaAtividade >= INACTIVITY_MS) {
      localStorage.removeItem(chave);
      window.setTimeout(
        () => sair("Sua sessão foi encerrada após 15 minutos sem atividade."),
        0,
      );
      return undefined;
    }
    if (!atividadePersistida) localStorage.setItem(chave, String(ultimaAtividade));

    const registrar = () => {
      const agora = Date.now();
      ultimaAtividade = agora;
      if (agora - ultimoRegistro > 15000) {
        ultimoRegistro = agora;
        localStorage.setItem(chave, String(agora));
      }
    };
    const verificar = () => {
      const compartilhada = Number(localStorage.getItem(chave) || 0);
      ultimaAtividade = Math.max(ultimaAtividade, compartilhada);
      if (Date.now() - ultimaAtividade >= INACTIVITY_MS) {
        localStorage.removeItem(chave);
        sair("Sua sessão foi encerrada após 15 minutos sem atividade.");
        return true;
      }
      return false;
    };
    const visibilidade = () => {
      if (document.visibilityState === "visible" && !verificar()) registrar();
    };
    const sincronizar = (evento) => {
      if (evento.key === chave && evento.newValue) {
        ultimaAtividade = Math.max(ultimaAtividade, Number(evento.newValue));
      }
    };
    const eventos = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"];
    eventos.forEach((evento) =>
      window.addEventListener(evento, registrar, { passive: true }),
    );
    document.addEventListener("visibilitychange", visibilidade);
    window.addEventListener("storage", sincronizar);
    const intervalo = window.setInterval(verificar, 30000);
    return () => {
      eventos.forEach((evento) => window.removeEventListener(evento, registrar));
      document.removeEventListener("visibilitychange", visibilidade);
      window.removeEventListener("storage", sincronizar);
      window.clearInterval(intervalo);
    };
  }, [session?.user?.id, sair]);

  useEffect(() => {
    const expirada = () => sair("Sua sessão expirou. Entre novamente para continuar.");
    window.addEventListener("agrishield:unauthorized", expirada);
    return () => window.removeEventListener("agrishield:unauthorized", expirada);
  }, [sair]);

  const valor = useMemo(
    () => ({
      configurado: supabaseConfigured,
      session,
      perfil,
      carregando,
      perfilCarregando,
      erroPerfil,
      motivoSaida,
      limparMotivoSaida: () => setMotivoSaida(""),
      carregarPerfil,
      definirPerfil: setPerfil,
      sair,
    }),
    [
      session,
      perfil,
      carregando,
      perfilCarregando,
      erroPerfil,
      motivoSaida,
      carregarPerfil,
      sair,
    ],
  );
  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const contexto = useContext(AuthContext);
  if (!contexto) throw new Error("useAuth precisa estar dentro de AuthProvider");
  return contexto;
}
