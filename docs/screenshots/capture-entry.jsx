// Copiado temporariamente para frontend/ pelo capture.cjs.
import React, { useEffect } from "react";
import { createRoot } from "react-dom/client";
import { Sidebar } from "./src/layout/Sidebar";
import { DashboardPage } from "./src/pages/DashboardPage";
import { ClientesPage } from "./src/pages/ClientesPage";
import { CadastroPage } from "./src/pages/CadastroPage";
import { MaquinariosPage } from "./src/pages/MaquinariosPage";
import { InsightsPage } from "./src/pages/InsightsPage";
import { OperacoesPage } from "./src/pages/OperacoesPage";
import { RiscosScore } from "./src/components/RiscosScore";
import { ExposicaoMaquinario } from "./src/components/ExposicaoMaquinario";
import { AuthProvider } from "./src/auth/AuthProvider";
import { AuthPage } from "./src/auth/AuthPage";
import { DEMO_FAZENDAS, DEMO_DASH } from "./src/demoData";
import { fixtureExposicao } from "./src/test/fixtureExposicao";
import { fixtureParametrosScore } from "./src/test/fixtureParametrosScore";
import "./src/styles.css";

const noop = () => {};
const fazendas = DEMO_FAZENDAS.map((f) => ({ ...f, apolices: [f.numero_apolice], arquivada: false }));
const fazenda = fazendas[0];
const maquinarios = [
  { id_maquinario: 1, tipo_equipamento: "TRATOR", marca: "JOHN_DEERE", modelo: "7230J", ano_fabricacao: 2022, chassi: "DEMO-JD-01", apelido: "Trator demonstrativo", horimetro_atual: 1250.5, media_horas_dia: 8, possui_seguro: true, seguradora: "OUTRA", vencimento_apolice: "2026-11-15" },
  { id_maquinario: 2, tipo_equipamento: "COLHEITADEIRA", marca: "NEW_HOLLAND", modelo: "CR 5.85", ano_fabricacao: 2021, chassi: "DEMO-NH-02", apelido: "Colheitadeira demonstrativa", horimetro_atual: 1860, media_horas_dia: 7.5, possui_seguro: true, seguradora: "MAPFRE", vencimento_apolice: "2027-07-20" },
  { id_maquinario: 3, tipo_equipamento: "PLANTADEIRA", marca: "STARA", modelo: "Estrela", ano_fabricacao: 2023, chassi: "DEMO-ST-03", possui_seguro: false },
];
const resumo = { disponivel: true, total: 3, segurados: 2, seguros_vigentes: 2, seguros_vencidos: 0, sem_seguro: 1, percentual_segurado: 66.7, vencendo_90_dias: 1, proximo_vencimento: "2026-11-15", idade_media_anos: 4, horimetro_total_horas: 3110.5, horimetros_informados: 2, horas_dia_estimadas: 15.5, horas_dia_informadas: 2, por_tipo: { TRATOR: 1, COLHEITADEIRA: 1, PLANTADEIRA: 1 } };
const dashboard = {
  ...DEMO_DASH,
  score: { ...DEMO_DASH.score, data_referencia: "2026-10-28" },
  origem_previsao: "api_open_meteo",
  previsao_atualizada_em: "2026-10-28T12:00:00Z",
  previsao_7d: [0, 1, 2, 3, 4, 5, 6].map((i) => ({ data: `2026-${i < 4 ? "10" : "11"}-${String(i < 4 ? 28 + i : i - 3).padStart(2, "0")}`, precipitacao_mm: [8, 34, 18, 2, 0, 0, 4][i], prob_precip_pct: [60, 86, 70, 25, 10, 10, 40][i], temp_max_c: [31, 29, 30, 32, 33, 34, 32][i] })),
  maquinarios_resumo: resumo,
};
const geo = { ...fixtureExposicao.contexto_territorial, status: "SUCESSO", latitude_referencia: fazenda.latitude, longitude_referencia: fazenda.longitude, raio_analise_m: 1000, area_drenagem_montante_km2: 850.3291, qualidade: {}, fontes: ["SRTM", "MERIT Hydro"], erros: [] };
const insight = {
  resumo_executivo: "Acompanhe a chuva prevista e confirme o acesso antes de mobilizar o maquinário.",
  nivel_atencao: "alto",
  leitura_principal: "A previsão indica chuva mais intensa amanhã. O contexto territorial ajuda a orientar a inspeção de rotas e áreas baixas.",
  prioridades: [
    { titulo: "Confirmar acesso e drenagem", prioridade: "hoje", motivo: "Há previsão de 34 mm de chuva e sinais de umidade recente.", acao_recomendada: "Valide a condição das vias e dos pontos baixos com o responsável local.", dado_base: "Cenário demonstrativo: 92 mm nos últimos sete dias; probabilidade de chuva de 86%." },
    { titulo: "Revisar a programação da frota", prioridade: "proximos_dias", motivo: "A janela prevista mais seca começa após o pico de chuva.", acao_recomendada: "Confirme a viabilidade da operação antes do deslocamento.", dado_base: "Previsão demonstrativa de sete dias e inventário de três equipamentos." },
    { titulo: "Conferir a vigência dos seguros", prioridade: "monitorar", motivo: "Uma apólice está próxima do vencimento.", acao_recomendada: "Confirme a renovação e as condições registradas no inventário.", dado_base: "Uma apólice demonstrativa vence em 15/11/2026." },
  ],
  perguntas_consultor: ["Como estão os acessos após a última chuva?", "Há equipamentos programados para áreas baixas?", "A apólice próxima do vencimento já foi revisada?"],
  pontos_positivos: ["O contexto territorial está disponível.", "O inventário permite identificar os equipamentos segurados."],
  limitacoes: ["Exemplo editorial com dados demonstrativos; nenhuma LLM foi consultada.", "Confirme as condições reais e as atualizações da previsão antes da decisão."],
};

window.fetch = async (input) => {
  const url = new URL(typeof input === "string" ? input : input.url, window.location.origin);
  let dados;
  if (url.pathname.includes("insights-ia")) dados = { modelo: "exemplo editorial", gerado_em: "2026-10-28T12:00:00Z", cache: false, insight };
  else if (url.pathname.includes("parametros-score")) dados = fixtureParametrosScore;
  else if (url.pathname.includes("/exposicao/")) dados = fixtureExposicao;
  else if (url.pathname.includes("geoespacial")) dados = geo;
  else if (url.pathname.includes("maquinarios")) dados = { maquinarios, resumo };
  else if (url.pathname.includes("dashboard")) dados = dashboard;
  else if (url.pathname.includes("fazendas")) dados = fazendas;
  else return new Response(JSON.stringify({ detail: "Rota ausente na documentação" }), { status: 404, headers: { "Content-Type": "application/json" } });
  return new Response(JSON.stringify(dados), { status: 200, headers: { "Content-Type": "application/json" } });
};

const params = new URLSearchParams(window.location.search);
const page = params.get("page") || "dashboard";
const shared = { fazendas, fazenda, selected: "1", setSelected: noop, dashboard, onNavigate: noop, showToast: noop };
const pages = {
  dashboard: <DashboardPage {...shared} onRefresh={noop} />,
  clientes: <ClientesPage {...shared} scorePreview={Object.fromEntries(fazendas.map((f) => [f.id, dashboard.score]))} setPage={noop} carregarFazendas={noop} onNovaFazenda={noop} onEditarFazenda={noop} onAbrirMaquinarios={noop} />,
  maquinarios: <MaquinariosPage fazenda={fazenda} onVoltar={noop} onAtualizado={noop} onDirtyChange={noop} showToast={noop} />,
  cadastro: <CadastroPage setPage={noop} carregarFazendas={noop} showToast={noop} setSelected={noop} onDirtyChange={noop} />,
  riscos: <RiscosScore showToast={noop} />,
  insights: <InsightsPage {...shared} />,
  operacoes: <OperacoesPage {...shared} />,
  exposicao: <ExposicaoMaquinario idFazenda="1" fazenda={fazenda} />,
};
function Capture() {
  useEffect(() => {
    const timer = setTimeout(() => {
      if (params.get("scroll") === "briefing") document.querySelector(".ai-insights-card")?.scrollIntoView({ behavior: "instant", block: "start" });
      document.documentElement.dataset.captureReady = "true";
    }, 2000);
    return () => clearTimeout(timer);
  }, []);
  return <>
    {page === "login" ? <AuthProvider><AuthPage /></AuthProvider> : <div className="app"><Sidebar page={page} setPage={noop} perfil={{ nome_completo: "Analista Demonstração", funcao: "Consultor" }} isAdmin={false} onLogout={noop} /><main className="main">{pages[page]}</main></div>}
    <div style={{ position: "fixed", right: 12, bottom: 8, zIndex: 10000, padding: "8px 12px", background: "#172a39", color: "white", borderRadius: 4, font: "10px sans-serif" }}>DOCUMENTAÇÃO · DADOS DEMONSTRATIVOS</div>
  </>;
}
createRoot(document.getElementById("root")).render(<Capture />);
