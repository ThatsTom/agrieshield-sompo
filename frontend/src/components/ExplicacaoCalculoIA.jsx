import { useEffect, useId, useRef, useState } from "react";
import { fetchJSON } from "../api/core";

export function ExplicacaoCalculoIA(props) {
  const identidade = JSON.stringify([
    props.idFazenda,
    props.avaliacao.data_referencia,
    props.avaliacao.fonte_meteorologica,
    props.perigo || "EXPOSICAO_HIDRICA",
  ]);
  return <ConsultaExplicacao key={identidade} {...props} />;
}

function ConsultaExplicacao({ idFazenda, avaliacao, perigo, nomePerigo, children }) {
  const [estado, setEstado] = useState({ carregando: false, erro: "", dados: null });
  const [visivel, setVisivel] = useState(false);
  const abortRef = useRef(null);
  const resultadoId = useId();

  useEffect(() => () => abortRef.current?.abort(), []);

  async function gerar() {
    if (estado.carregando) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setEstado((anterior) => ({ ...anterior, carregando: true, erro: "" }));
    const params = new URLSearchParams({
      data_referencia: avaliacao.data_referencia,
      fonte: avaliacao.fonte_meteorologica,
    });
    if (perigo) params.set("perigo", perigo);
    const recurso = perigo ? "explicacao-perigo-ia" : "explicacao-hidrica-ia";
    try {
      const dados = await fetchJSON(
        `/api/v1/exposicao/${encodeURIComponent(String(idFazenda))}/${recurso}?${params}`,
        { method: "POST", signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setEstado({ carregando: false, erro: "", dados });
        setVisivel(true);
      }
    } catch (erro) {
      if (!controller.signal.aborted) {
        setEstado((anterior) => ({
          ...anterior,
          carregando: false,
          erro: erro?.message || "Não foi possível explicar este cálculo agora.",
        }));
      }
    }
  }

  const temRelatorio = Boolean(estado.dados);
  return (
    <section className="hydric-ai" aria-label={`Explicação com IA: ${nomePerigo}`}>
      <div className="hydric-ai-actions">
        <button
          className="btn btn-ghost hydric-ai-button"
          type="button"
          onClick={() => temRelatorio ? setVisivel((anterior) => !anterior) : gerar()}
          disabled={estado.carregando}
          aria-expanded={temRelatorio && visivel}
          aria-controls={temRelatorio ? resultadoId : undefined}
        >
          {estado.carregando ? "Explicando o cálculo..." : temRelatorio
            ? visivel ? "Recolher explicação" : "Mostrar explicação novamente"
            : "Deixe a IA te explicar"}
        </button>
        {temRelatorio && (
          <button className="btn btn-ghost" type="button" onClick={gerar} disabled={estado.carregando}>
            Gerar nova explicação
          </button>
        )}
      </div>
      {estado.carregando && <p role="status">Conferindo os valores da fazenda e preparando a explicação.</p>}
      {estado.erro && <p className="hydric-ai-error" role="alert">{estado.erro}</p>}
      {temRelatorio && (
        <div className="hydric-ai-result" id={resultadoId} hidden={!visivel}>
          {children(estado.dados)}
        </div>
      )}
    </section>
  );
}
