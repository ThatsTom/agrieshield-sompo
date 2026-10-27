import { useEffect, useRef, useState } from "react";
import { fetchJSON } from "../api/core";

const nf = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const numero = (valor) =>
  valor == null || !Number.isFinite(Number(valor)) ? "indisponível" : nf.format(valor);
const nf4 = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 4,
  maximumFractionDigits: 4,
});
const numero4 = (valor) => valor == null ? "indisponível" : nf4.format(valor);
const percentual = (valor) => `${numero(valor == null ? null : 100 * valor)}%`;
const data = (valor) => valor ? new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${valor}T00:00:00Z`)) : "indisponível";

export function ExplicacaoHidricaIA({ idFazenda, avaliacao }) {
  const [estado, setEstado] = useState({ carregando: false, erro: "", dados: null });
  const abortRef = useRef(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function explicar() {
    if (estado.carregando) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setEstado({ carregando: true, erro: "", dados: null });
    const params = new URLSearchParams({
      data_referencia: avaliacao.data_referencia,
      fonte: avaliacao.fonte_meteorologica,
    });
    try {
      const dados = await fetchJSON(
        `/api/v1/exposicao/${encodeURIComponent(String(idFazenda))}/explicacao-hidrica-ia?${params}`,
        { method: "POST", signal: controller.signal },
      );
      if (!controller.signal.aborted) setEstado({ carregando: false, erro: "", dados });
    } catch (erro) {
      if (!controller.signal.aborted)
        setEstado({
          carregando: false,
          erro: erro?.message || "Não foi possível explicar este cálculo agora.",
          dados: null,
        });
    }
  }

  const { calculo: c, explicacao: ia } = estado.dados || {};
  const t = c?.territorio;
  const m = c?.meteorologia_dia;
  const j = c?.janela_90d;

  return (
    <section className="hydric-ai" aria-label="Explicação do cálculo da Exposição Hídrica">
      <button
        className="btn btn-ghost hydric-ai-button"
        type="button"
        onClick={explicar}
        disabled={estado.carregando}
        aria-expanded={Boolean(c)}
      >
        {estado.carregando ? "Explicando o cálculo..." : c ? "Atualizar explicação com IA" : "Explicar este cálculo com IA"}
      </button>
      {estado.carregando && <p role="status">Conferindo os valores da fazenda e preparando a explicação.</p>}
      {estado.erro && <p className="hydric-ai-error" role="alert">{estado.erro}</p>}
      {c && (
        <div className="hydric-ai-result">
          <header>
            <h4>Como chegamos ao valor</h4>
            <span>{c.fazenda} · {c.fonte_meteorologica} · referência {data(c.data_referencia)}</span>
          </header>
          <p>{ia?.resumo}</p>
          <div className="hydric-ai-steps">
            <section>
              <h5>1. Território: {numero(t?.indice)} / 100</h5>
              <p>
                Drenagem a {numero(c.medidas_territorio?.distancia_drenagem_m)} m → D2 = {numero(t?.proximidade_drenagem)};
                área de influência de {numero(c.medidas_territorio?.area_influencia_drenagem_km2)} km² → A2 = {numero(t?.relevancia_area_influencia)};
                posição topográfica de {numero(c.medidas_territorio?.posicao_topografica_relativa_m)} m → P2 = {numero(t?.posicao_topografica)}.
              </p>
              <p className="hydric-ai-formula">
                T3 ≈ ({percentual(t?.pesos?.proximidade)} × {numero(t?.proximidade_drenagem)}) +
                ({percentual(t?.pesos?.area)} × {numero(t?.relevancia_area_influencia)}) +
                ({percentual(t?.pesos?.posicao)} × {numero(t?.posicao_topografica)}) = {numero(t?.indice)}
              </p>
              <p>A declividade média de {numero(c.medidas_territorio?.declividade_media_graus)}° não entra neste T3; ela participa do indicador de Instabilidade.</p>
              <details>
                <summary>Como as medidas foram transformadas em índices</summary>
                <p>D2 = 100 × {numero(t?.parametros_normalizacao?.mediana_distancia_m)} ÷ ({numero(t?.parametros_normalizacao?.mediana_distancia_m)} + {numero(c.medidas_territorio?.distancia_drenagem_m)}) = {numero(t?.proximidade_drenagem)}.</p>
                <p>A2 = limitar entre 0 e 100 o resultado de 100 × [ln(1 + {numero(c.medidas_territorio?.area_influencia_drenagem_km2)}) − {numero(t?.parametros_normalizacao?.area_log_min)}] ÷ [{numero(t?.parametros_normalizacao?.area_log_max)} − {numero(t?.parametros_normalizacao?.area_log_min)}] = {numero(t?.relevancia_area_influencia)}.</p>
                <p>P2 = 100 ÷ [1 + exp(({numero(c.medidas_territorio?.posicao_topografica_relativa_m)} − {numero(t?.parametros_normalizacao?.mediana_posicao_m)}) ÷ {numero(t?.parametros_normalizacao?.iqr_posicao_m)})] = {numero(t?.posicao_topografica)}.</p>
              </details>
              <p>{ia?.leitura_territorial}</p>
            </section>
            <section>
              <h5>2. Meteorologia em {data(m?.data)}: {numero(m?.base)} / 100</h5>
              <p>Chuva do dia: {numero(m?.chuva_hoje_mm)} mm → {numero(m?.chuva_hoje_normalizada)}; dias 1–3 anteriores: {numero(m?.chuva_d1_d3_mm)} mm → {numero(m?.chuva_d1_d3_normalizada)}; dias 4–7: {numero(m?.chuva_d4_d7_mm)} mm → {numero(m?.chuva_d4_d7_normalizada)}.</p>
              <p>Curva de chuva, com interpolação entre pontos: {m?.curva_chuva?.map((ponto) => `${numero(ponto.mm)} mm → ${numero(ponto.indice)}`).join("; ")}.</p>
              <p className="hydric-ai-formula">Antecedente ≈ min(100; [({percentual(m?.pesos_antecedente?.d1_d3)} × {numero(m?.chuva_d1_d3_normalizada)}) + ({percentual(m?.pesos_antecedente?.d4_d7)} × {numero(m?.chuva_d4_d7_normalizada)})] × {numero(m?.multiplicador_persistencia)}) = {numero(m?.antecedente_normalizado)}.</p>
              <p className="hydric-ai-formula">H_base ≈ {percentual(m?.pesos_base?.hoje)} × {numero(m?.chuva_hoje_normalizada)} + {percentual(m?.pesos_base?.antecedente)} × {numero(m?.antecedente_normalizado)} = {numero(m?.base)}.</p>
              <p>{ia?.leitura_meteorologica}</p>
            </section>
            <section>
              <h5>3. Resultado do dia: {numero(m?.indice_diario)} / 100</h5>
              <p>Chuva acumulada em 3 dias: {numero(m?.chuva_3d_mm)} mm; ativação territorial g3 = {numero(m?.chuva_3d_normalizada)} ÷ 100 = {numero4(m?.ativacao_chuva_3d)}.</p>
              <p className="hydric-ai-formula">Incremento ≈ {numero(m?.fator_incremento)} × {numero4(m?.ativacao_chuva_3d)} × {numero(t?.indice)} = {numero(m?.incremento_territorial)}. Índice diário ≈ min(100; {numero(m?.base)} + {numero(m?.incremento_territorial)}) = {numero(m?.indice_diario)}.</p>
            </section>
            <section>
              <h5>4. Valor exibido para a janela de 90 dias: {numero(j?.indice)} / 100</h5>
              <p>Período: {data(j?.inicio)} a {data(j?.fim)}; {j?.dias_disponiveis} de {j?.dias_esperados} dias disponíveis; {j?.dias_relevantes} dias relevantes e {j?.eventos} eventos. O índice do último dia não é o valor da janela.</p>
              <p className="hydric-ai-formula">Índice da janela ≈ {percentual(j?.pesos?.severidade)} × {numero(j?.componentes?.severidade)} + {percentual(j?.pesos?.frequencia)} × {numero(j?.componentes?.frequencia)} + {percentual(j?.pesos?.duracao)} × {numero(j?.componentes?.duracao)} + {percentual(j?.pesos?.recorrencia)} × {numero(j?.componentes?.recorrencia)} = {numero(j?.indice)}.</p>
              <p>{ia?.leitura_janela}</p>
            </section>
          </div>
          <p className="hydric-ai-limits">{ia?.limitacoes} {c.limitacao_geografica}</p>
          <small>Explicação por {estado.dados.modelo}; números e fórmulas fornecidos pelo motor AgriShield.</small>
        </div>
      )}
    </section>
  );
}
