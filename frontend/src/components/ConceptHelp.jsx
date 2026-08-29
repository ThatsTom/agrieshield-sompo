import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { conceitos } from "../content/conceitos";

export function ConceptHelp({ conceito }) {
  const [aberto, setAberto] = useState(false);
  const [tooltipAberto, setTooltipAberto] = useState(false);
  const tituloId = useId();
  const tooltipId = useId();
  const botao = useRef(null);
  const fechar = () => setAberto(false);
  const item = conceitos[conceito];
  useEffect(() => {
    if (!aberto) return;
    const tecla = (e) => {
      if (e.key === "Escape") fechar();
    };
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("keydown", tecla);
      requestAnimationFrame(() => botao.current?.focus());
    };
  }, [aberto]);
  if (!item) return null;
  const modal = aberto ? (
    <div
      className="concept-help-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) fechar();
      }}
    >
      <section
        className="concept-help-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={tituloId}
      >
        <button
          className="concept-help-close"
          type="button"
          aria-label="Fechar ajuda"
          autoFocus
          onClick={fechar}
        >
          ×
        </button>
        <span className="concept-help-kicker">Guia da métrica</span>
        <h2 id={tituloId}>{item.titulo}</h2>
        <p>{item.descricao}</p>
        {item.interpretacao && (
          <div>
            <h3>Como interpretar</h3>
            <p>{item.interpretacao}</p>
          </div>
        )}
        {item.padrao && (
          <div>
            <h3>Por que este padrão</h3>
            <p>{item.padrao}</p>
          </div>
        )}
        {item.uso && (
          <div>
            <h3>Como é usado no AgriShield</h3>
            <p>{item.uso}</p>
          </div>
        )}
        {item.acao && (
          <div className="concept-help-action">
            <h3>O que fazer na prática</h3>
            <p>{item.acao}</p>
          </div>
        )}
        {item.avisos?.length > 0 && (
          <ul>
            {item.avisos.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  ) : null;
  return (
    <span
      className="concept-help"
      onMouseEnter={() => setTooltipAberto(true)}
      onMouseLeave={() => setTooltipAberto(false)}
    >
      <button
        ref={botao}
        className="concept-help-trigger"
        type="button"
        aria-label={`Ajuda: ${item.titulo}`}
        aria-describedby={tooltipAberto ? tooltipId : undefined}
        onFocus={() => setTooltipAberto(true)}
        onBlur={() => setTooltipAberto(false)}
        onClick={(evento) => {
          evento.preventDefault();
          evento.stopPropagation();
          setTooltipAberto(false);
          setAberto(true);
        }}
      >
      </button>
      {tooltipAberto && !aberto && (
        <span className="concept-help-tooltip" id={tooltipId} role="tooltip">
          <strong>{item.titulo}</strong>
          <span>{item.descricao}</span>
          <small>Clique para ver interpretação e orientação.</small>
        </span>
      )}
      {modal && createPortal(modal, document.body)}
    </span>
  );
}
