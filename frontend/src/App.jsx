import { useEffect, useMemo, useRef, useState } from "react";
import { Sidebar } from "./layout/Sidebar";
import { Icon } from "./layout/Icon";
import { DashboardPage } from "./pages/DashboardPage";
import { ClientesPage } from "./pages/ClientesPage";
import { MaquinariosPage } from "./pages/MaquinariosPage";
import { CadastroPage } from "./pages/CadastroPage";
import { OperacoesPage } from "./pages/OperacoesPage";
import { AlertasPage } from "./pages/AlertasPage";
import { InsightsPage } from "./pages/InsightsPage";
import { RelatoriosPage } from "./pages/RelatoriosPage";
import { DadosFontesPage } from "./pages/DadosFontesPage";
import { ConfiguracoesPage } from "./pages/ConfiguracoesPage";
import { PerfilPage } from "./pages/PerfilPage";
import { GerenciarAcessosPage } from "./pages/GerenciarAcessosPage";
import { RiscosScore } from "./components/RiscosScore";
import { fetchJSON } from "./api/core";
import { DEMO_DASH, DEMO_FAZENDAS } from "./demoData";
function App({ perfilUsuario, onPerfilAtualizado, onLogout, isAdmin }) {
  const [page, setPage] = useState("dashboard"),
    [fazendas, setFazendas] = useState([]),
    [portfolioFazendas, setPortfolioFazendas] = useState([]),
    [fazendasCarregando, setFazendasCarregando] = useState(true),
    [selected, setSelected] = useState("1"),
    [dashboard, setDashboard] = useState(null),
    [erro, setErro] = useState(""),
    [backendDemo, setBackendDemo] = useState(false),
    [toast, setToast] = useState(""),
    [scorePreview, setScorePreview] = useState({}),
    [fazendaEmEdicao, setFazendaEmEdicao] = useState(null),
    [fazendaMaquinarios, setFazendaMaquinarios] = useState(null),
    [formFazendaSujo, setFormFazendaSujo] = useState(false),
    [formMaquinarioSujo, setFormMaquinarioSujo] = useState(false);
  const timer = useRef(null);
  const mainRef = useRef(null);
  const dashboardRequest = useRef(0);
  const showToast = (msg) => {
    setToast(msg);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(""), 3200);
  };
  async function carregarFazendas() {
    setFazendasCarregando(true);
    try {
      const data = await fetchJSON("/api/fazendas?incluir_arquivadas=true");
      const ativas = data.filter((f) => !f.arquivada);
      setPortfolioFazendas(data);
      setFazendas(ativas);
      setScorePreview(
        Object.fromEntries(
          data
            .filter((f) => f.score_preview)
            .map((f) => [String(f.id), f.score_preview]),
        ),
      );
      setBackendDemo(false);
      setErro("");
      if (ativas.length && !ativas.some((f) => String(f.id) === String(selected)))
        setSelected(String(ativas[0].id));
      return data;
    } catch {
      setErro(
        "Backend não encontrado. A interface está usando dados de demonstração; verifique a URL da API e tente novamente.",
      );
      setBackendDemo(true);
      setFazendas(DEMO_FAZENDAS);
      setPortfolioFazendas(DEMO_FAZENDAS);
      return DEMO_FAZENDAS;
    } finally {
      setFazendasCarregando(false);
    }
  }
  async function carregarDashboard(id) {
    if (!id) return;
    const requisicao = ++dashboardRequest.current;
    setDashboard(null);
    try {
      const data = await fetchJSON(`/api/fazendas/${id}/dashboard`);
      if (requisicao !== dashboardRequest.current) return;
      setDashboard(data);
      setScorePreview((p) => ({ ...p, [id]: data.score }));
      setErro("");
    } catch {
      if (requisicao !== dashboardRequest.current) return;
      setDashboard(null);
      setErro(
        "Não foi possível carregar os indicadores desta fazenda. Tente novamente; nenhum dado demonstrativo foi associado ao cadastro real.",
      );
    }
  }
  useEffect(() => {
    carregarFazendas();
  }, []);
  useEffect(() => {
    if (fazendasCarregando) return;
    if (backendDemo) {
      dashboardRequest.current += 1;
      setDashboard(DEMO_DASH);
      return;
    }
    if (!selected || !fazendas.length) {
      dashboardRequest.current += 1;
      setDashboard(null);
      return;
    }
    carregarDashboard(selected);
  }, [selected, backendDemo, fazendasCarregando, fazendas.length]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  const fazenda = useMemo(
    () =>
      fazendas.find((f) => String(f.id) === String(selected)) ||
      fazendas[0] ||
      (backendDemo ? DEMO_FAZENDAS[0] : null),
    [fazendas, selected, backendDemo],
  );
  const navigate = (next, { ignorarFormularioSujo = false } = {}) => {
    if (
      page === "cadastro" &&
      next !== "cadastro" &&
      formFazendaSujo &&
      !ignorarFormularioSujo &&
      !window.confirm("Existem alterações não salvas. Deseja sair mesmo assim?")
    ) return;
    if (
      page === "maquinarios" &&
      next !== "maquinarios" &&
      formMaquinarioSujo &&
      !ignorarFormularioSujo &&
      !window.confirm("Existem dados de maquinário não salvos. Deseja sair mesmo assim?")
    ) return;
    if (ignorarFormularioSujo) setFormFazendaSujo(false);
    if (next !== "maquinarios") setFormMaquinarioSujo(false);
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
    window.setTimeout(() => mainRef.current?.focus({ preventScroll: true }), 0);
  };
  useEffect(() => {
    const nomes = {
      dashboard: "Visão Geral",
      clientes: "Clientes e Apólices",
      maquinarios: "Maquinário agrícola",
      cadastro: "Cadastro de Fazenda",
      operacoes: "Operações",
      riscos: "Riscos e Score",
      alertas: "Alertas",
      insights: "Insights",
      relatorios: "Relatórios",
      dados: "Dados e Fontes",
      configuracoes: "Configurações",
      perfil: "Perfil do Usuário",
      acessos: "Gerenciar Acessos",
    };
    document.title = `${nomes[page] || "Plataforma"} | AgriShield`;
  }, [page]);
  return (
    <div className="app">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>
      <Sidebar
        page={page === "maquinarios" ? "clientes" : page}
        setPage={navigate}
        perfil={perfilUsuario}
        isAdmin={isAdmin}
        onLogout={onLogout}
      />
      <main className="main" id="main-content" ref={mainRef} tabIndex="-1">
        {erro && (
          <div className="system-banner">
            <Icon name="warning" size={17} />
            <div>
              <b>{backendDemo ? "Modo de demonstração" : "Indicadores indisponíveis"}</b>
              <span>{erro}</span>
            </div>
            <button onClick={() => setErro("")} aria-label="Fechar aviso">
              ×
            </button>
          </div>
        )}
        {page === "dashboard" && (
          <DashboardPage
            fazendas={fazendas}
            selected={selected}
            setSelected={setSelected}
            dashboard={dashboard}
            fazenda={fazenda}
            onNavigate={navigate}
            showToast={showToast}
            onRefresh={() => carregarDashboard(selected)}
          />
        )}{" "}
        {page === "clientes" && (
          <ClientesPage
            fazendas={portfolioFazendas}
            carregando={fazendasCarregando}
            scorePreview={scorePreview}
            setPage={navigate}
            setSelected={setSelected}
            carregarFazendas={carregarFazendas}
            showToast={showToast}
            onNovaFazenda={() => {
              setFazendaEmEdicao(null);
              navigate("cadastro");
            }}
            onEditarFazenda={(item) => {
              setFazendaEmEdicao(item);
              navigate("cadastro");
            }}
            onAbrirMaquinarios={(item) => {
              setFazendaMaquinarios(item);
              setSelected(String(item.id));
              setFormMaquinarioSujo(false);
              navigate("maquinarios");
            }}
          />
        )}{" "}
        {page === "maquinarios" && (
          <MaquinariosPage
            fazenda={fazendaMaquinarios}
            showToast={showToast}
            onDirtyChange={setFormMaquinarioSujo}
            onVoltar={() => navigate("clientes")}
            onAtualizado={async () => {
              await carregarFazendas();
              if (fazendaMaquinarios?.id) {
                await carregarDashboard(String(fazendaMaquinarios.id));
              }
            }}
          />
        )}{" "}
        {page === "cadastro" && (
          <CadastroPage
            setPage={navigate}
            carregarFazendas={carregarFazendas}
            showToast={showToast}
            fazenda={fazendaEmEdicao}
            setSelected={setSelected}
            onDirtyChange={setFormFazendaSujo}
          />
        )}{" "}
        {page === "operacoes" && (
          <OperacoesPage
            fazendas={fazendas}
            selected={selected}
            setSelected={setSelected}
            fazenda={fazenda}
            onNavigate={navigate}
          />
        )}{" "}
        {page === "riscos" && <RiscosScore showToast={showToast} />}{" "}
        {page === "alertas" && (
          <AlertasPage
            fazendas={fazendas}
            selected={selected}
            setSelected={setSelected}
            dashboard={dashboard}
            fazenda={fazenda}
          />
        )}{" "}
        {page === "insights" && (
          <InsightsPage
            fazendas={fazendas}
            dashboard={dashboard}
            selected={selected}
            setSelected={setSelected}
            fazenda={fazenda}
          />
        )}{" "}
        {page === "relatorios" && (
          <RelatoriosPage
            fazendas={fazendas}
            scorePreview={scorePreview}
          />
        )}{" "}
        {page === "dados" && (
          <DadosFontesPage
            fazendas={fazendas}
            selected={selected}
            setSelected={setSelected}
            fazenda={fazenda}
          />
        )}{" "}
        {page === "configuracoes" && (
          <ConfiguracoesPage onNavigate={navigate} backendDemo={backendDemo} />
        )}
        {page === "perfil" && (
          <PerfilPage
            perfil={perfilUsuario}
            onPerfilAtualizado={onPerfilAtualizado}
            onLogout={onLogout}
            showToast={showToast}
          />
        )}
        {page === "acessos" && isAdmin && (
          <GerenciarAcessosPage showToast={showToast} />
        )}
      </main>
      {toast && (
        <div className="toast" role="status">
          <span className="toast-check">
            <Icon name="check" size={15} />
          </span>
          {toast}
        </div>
      )}
    </div>
  );
}
export default App;
