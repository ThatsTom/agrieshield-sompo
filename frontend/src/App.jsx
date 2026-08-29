import { useEffect, useMemo, useRef, useState } from "react";
import { Sidebar } from "./layout/Sidebar";
import { Icon } from "./layout/Icon";
import { DashboardPage } from "./pages/DashboardPage";
import { ClientesPage } from "./pages/ClientesPage";
import { CadastroPage } from "./pages/CadastroPage";
import { OperacoesPage } from "./pages/OperacoesPage";
import { AlertasPage } from "./pages/AlertasPage";
import { InsightsPage } from "./pages/InsightsPage";
import { RelatoriosPage } from "./pages/RelatoriosPage";
import { DadosFontesPage } from "./pages/DadosFontesPage";
import { ConfiguracoesPage } from "./pages/ConfiguracoesPage";
import { RiscosScore } from "./components/RiscosScore";
import { fetchJSON } from "./api/core";
import { DEMO_DASH, DEMO_FAZENDAS } from "./demoData";
function App() {
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
    [formFazendaSujo, setFormFazendaSujo] = useState(false);
  const timer = useRef(null);
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
        "Backend não encontrado. A interface está usando dados de demonstração; inicie a API local para trabalhar com os CSVs reais.",
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
    setDashboard(null);
    try {
      const data = await fetchJSON(`/api/fazendas/${id}/dashboard`);
      setDashboard(data);
      setScorePreview((p) => ({ ...p, [id]: data.score }));
    } catch {
      setDashboard(DEMO_DASH);
    }
  }
  useEffect(() => {
    carregarFazendas();
  }, []);
  useEffect(() => {
    carregarDashboard(selected);
  }, [selected]);
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
      DEMO_FAZENDAS[0],
    [fazendas, selected],
  );
  const navigate = (next, { ignorarFormularioSujo = false } = {}) => {
    if (
      page === "cadastro" &&
      next !== "cadastro" &&
      formFazendaSujo &&
      !ignorarFormularioSujo &&
      !window.confirm("Existem alterações não salvas. Deseja sair mesmo assim?")
    ) return;
    if (ignorarFormularioSujo) setFormFazendaSujo(false);
    setPage(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  return (
    <div className="app">
      <Sidebar page={page} setPage={navigate} />
      <main className="main">
        {erro && (
          <div className="system-banner">
            <Icon name="warning" size={17} />
            <div>
              <b>Modo de demonstração</b>
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
          <InsightsPage fazendas={fazendas} dashboard={dashboard} />
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
