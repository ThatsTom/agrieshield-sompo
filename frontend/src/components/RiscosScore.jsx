import { useEffect, useState } from "react";
import {
  ErroApiParametrosScore,
  buscarParametrosScore,
  salvarParametrosScore,
} from "../api/parametrosScore";
import { ConceptHelp } from "./ConceptHelp";
import { conceitoDoPerigo, conceitos } from "../content/conceitos";
import { explicacoesParametrosScore } from "../content/parametrosScore";

const ORDEM_PERIGOS = [
  "EXPOSICAO_HIDRICA",
  "TRAFEGABILIDADE",
  "INSTABILIDADE",
  "INCENDIO",
  "TEMPESTADES",
];
const NOMES = {
  EXPOSICAO_HIDRICA: "Exposição Hídrica",
  TRAFEGABILIDADE: "Trafegabilidade",
  INSTABILIDADE: "Instabilidade",
  INCENDIO: "Incêndio / Propagação de Fogo",
  TEMPESTADES: "Tempestades Severas",
};

const pf = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const pfFator = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const chave = (grupo, indicador, parametro) =>
  `${grupo}|${indicador}|${parametro}`;
const chavePeso = (perigo) => chave("SCORE", perigo, "peso");

// Metadados de exibicao dos campos internos por perigo, na ordem do mockup.
// "totalLabel" so aparece onde a soma interna e uma regra de validacao (Hidrico).
const CAMPOS_INTERNOS = {
  EXPOSICAO_HIDRICA: {
    titulo: "Composição interna",
    totalLabel: "Total interno",
    campos: [
      [
        "Proximidade da drenagem",
        chave("EXPOSICAO_HIDRICA", "T3", "proximidade_drenagem"),
      ],
      [
        "Relevância da área montante",
        chave("EXPOSICAO_HIDRICA", "T3", "relevancia_area_montante"),
      ],
      [
        "Posição topográfica relativa",
        chave("EXPOSICAO_HIDRICA", "T3", "posicao_topografica"),
      ],
    ],
  },
  INSTABILIDADE: {
    titulo: "Fatores de ativação",
    campos: [
      ["Normal", chave("INSTABILIDADE", "ATIVACAO", "normal")],
      ["Atenção", chave("INSTABILIDADE", "ATIVACAO", "atencao")],
      ["Alerta", chave("INSTABILIDADE", "ATIVACAO", "alerta")],
      ["Crítico", chave("INSTABILIDADE", "ATIVACAO", "critico")],
    ],
  },
  INCENDIO: {
    titulo: "Multiplicadores de secura",
    campos: [
      ["0–1 dia", chave("INCENDIO", "SECURA", "0_1_dia")],
      ["2–3 dias", chave("INCENDIO", "SECURA", "2_3_dias")],
      ["4–6 dias", chave("INCENDIO", "SECURA", "4_6_dias")],
      ["7+ dias", chave("INCENDIO", "SECURA", "7_mais_dias")],
    ],
  },
  TEMPESTADES: {
    titulo: "Fator vento–chuva",
    campos: [
      [
        "Base do fator vento–chuva",
        chave("TEMPESTADES", "VENTO_CHUVA", "base"),
      ],
      [
        "Influência da chuva",
        chave("TEMPESTADES", "VENTO_CHUVA", "influencia_chuva"),
      ],
    ],
  },
  TRAFEGABILIDADE: {
    titulo: "Composição interna",
    totalLabel: "Total interno",
    campos: [
      [
        "Condição do dia atual",
        chave("TRAFEGABILIDADE", "COMPOSICAO", "peso_dia"),
      ],
      [
        "Acúmulo recente",
        chave("TRAFEGABILIDADE", "COMPOSICAO", "peso_acumulado"),
      ],
      [
        "Recuperação / secagem",
        chave("TRAFEGABILIDADE", "COMPOSICAO", "peso_recuperacao"),
      ],
    ],
    camposAdicionais: [
      [
        "Limiar de dia relevante",
        chave("TRAFEGABILIDADE", "AGREGACAO", "limiar_relevancia"),
      ],
    ],
  },
};

const paraTexto = (valor, tipo) =>
  tipo === "percentual"
    ? String(Math.round(valor * 10000) / 100)
    : String(valor);
const paraNumero = (texto, tipo) =>
  tipo === "percentual" ? Number(texto) / 100 : Number(texto);
const rotuloValor = (valor, tipo) =>
  tipo === "percentual"
    ? `${pf.format(Math.round(valor * 10000) / 100)}%`
    : pfFator.format(valor);

function paraCampos(parametros) {
  const campos = {};
  for (const p of parametros) {
    campos[chave(p.grupo, p.indicador, p.parametro)] = {
      grupo: p.grupo,
      indicador: p.indicador,
      parametro: p.parametro,
      texto: paraTexto(p.valor_atual, p.tipo),
      padrao: p.valor_padrao,
      tipo: p.tipo,
    };
  }
  return campos;
}

function IndicadoresCard() {
  return (
    <article className="equip-card riscos-indicadores">
      <div className="equip-card-head">
        <div>
          <h3>Indicadores</h3>
          <p>Os cinco indicadores considerados no Score de Exposição.</p>
        </div>
      </div>
      <div className="riscos-indicadores-list">
        {ORDEM_PERIGOS.map((perigo) => {
          const conceito = conceitos[conceitoDoPerigo(perigo)];
          return (
            <section key={perigo}>
              <h4>
                {NOMES[perigo]}{" "}
                <ConceptHelp conceito={conceitoDoPerigo(perigo)} />
              </h4>
              <p>{conceito?.descricao}</p>
            </section>
          );
        })}
      </div>
    </article>
  );
}

function CampoNumerico({ rotulo, campo, valor, onAlterar }) {
  return (
    <label className="riscos-peso-campo">
      <span>{rotulo}</span>
      <span className="riscos-peso-input">
        <input
          type="number"
          step="0.01"
          value={valor.texto}
          onChange={(e) => onAlterar(campo, e.target.value)}
          aria-label={rotulo}
        />
        {valor.tipo === "percentual" && <b>%</b>}
      </span>
      <small className="riscos-peso-padrao">
        Padrão: {rotuloValor(valor.padrao, valor.tipo)}
      </small>
    </label>
  );
}

function ExplicacaoParametros({ conteudo }) {
  if (!conteudo) return null;
  return (
    <aside className="riscos-explicacao" aria-label={conteudo.titulo}>
      <h4>{conteudo.titulo}</h4>
      {conteudo.introducao && (
        <p className="riscos-explicacao-intro">{conteudo.introducao}</p>
      )}
      {conteudo.paragrafos?.map((paragrafo) => (
        <p key={paragrafo} className="riscos-explicacao-paragrafo">
          {paragrafo}
        </p>
      ))}
      {conteudo.itens?.map(([subtitulo, texto]) => (
        <div key={subtitulo} className="riscos-explicacao-item">
          <b>{subtitulo}</b>
          <p>{texto}</p>
        </div>
      ))}
      {conteudo.comoAtua && (
        <div className="riscos-explicacao-atua">
          <b>Como os parâmetros atuam</b>
          {conteudo.formula && (
            <p className="riscos-explicacao-formula">{conteudo.formula}</p>
          )}
          <p>{conteudo.comoAtua}</p>
        </div>
      )}
      {conteudo.aviso && (
        <p className="riscos-explicacao-aviso">{conteudo.aviso}</p>
      )}
    </aside>
  );
}

function BlocoIndicador({
  perigo,
  campos,
  onAlterar,
  onRestaurarBloco,
  erroGrupo,
}) {
  const pesoCampo = campos[chavePeso(perigo)];
  const interno = CAMPOS_INTERNOS[perigo];
  const totalInterno =
    interno && interno.totalLabel
      ? Math.round(
          interno.campos.reduce(
            (soma, [, campo]) => soma + (Number(campos[campo]?.texto) || 0),
            0,
          ) * 100,
        ) / 100
      : null;
  return (
    <details className="equip-card hazard-detail riscos-bloco-indicador">
      <summary>
        <div>
          <span>Indicador</span>
          <h3>
            {NOMES[perigo]} <ConceptHelp conceito={conceitoDoPerigo(perigo)} />
          </h3>
          <p>
            Peso no índice:{" "}
            {pesoCampo
              ? rotuloValor(Number(pesoCampo.texto) / 100, "percentual")
              : "—"}
          </p>
        </div>
      </summary>
      <div className="riscos-bloco-corpo">
        <div
          className={`riscos-bloco-grid${interno ? "" : " riscos-bloco-grid--somente-explicacao"}`}
        >
          {interno && (
            <div className="riscos-bloco-config">
              <h4>{interno.titulo}</h4>
              <div className="riscos-campos-internos">
                {interno.campos.map(([rotulo, campo]) => (
                  <CampoNumerico
                    key={campo}
                    rotulo={rotulo}
                    campo={campo}
                    valor={campos[campo]}
                    onAlterar={onAlterar}
                  />
                ))}
              </div>
              {interno.totalLabel && (
                <div
                  className={`riscos-peso-total ${totalInterno === 100 ? "is-ok" : "is-invalido"}`}
                >
                  <span>{interno.totalLabel}</span>
                  <b>{pf.format(totalInterno)}%</b>
                </div>
              )}
              {interno.camposAdicionais && (
                <div className="riscos-campos-internos riscos-campos-adicionais">
                  {interno.camposAdicionais.map(([rotulo, campo]) => (
                    <CampoNumerico
                      key={campo}
                      rotulo={rotulo}
                      campo={campo}
                      valor={campos[campo]}
                      onAlterar={onAlterar}
                    />
                  ))}
                </div>
              )}
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => onRestaurarBloco(perigo)}
              >
                Restaurar padrão
              </button>
            </div>
          )}
          <ExplicacaoParametros conteudo={explicacoesParametrosScore[perigo]} />
        </div>
        {erroGrupo && (
          <p className="riscos-peso-erro" role="alert">
            {erroGrupo}
          </p>
        )}
      </div>
    </details>
  );
}

function PesosCard({ showToast, buscar, salvar: salvarPesos }) {
  const [st, setSt] = useState({ loading: true, dados: null, error: "" });
  const [campos, setCampos] = useState(null);
  const [errosPorGrupo, setErrosPorGrupo] = useState({});
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    let ativo = true;
    setSt({ loading: true, dados: null, error: "" });
    buscar().then(
      (dados) => {
        if (!ativo) return;
        setSt({ loading: false, dados, error: "" });
        setCampos(paraCampos(dados.parametros));
      },
      (err) => {
        if (ativo)
          setSt({
            loading: false,
            dados: null,
            error:
              err?.message ||
              "Não foi possível carregar os parâmetros do modelo.",
          });
      },
    );
    return () => {
      ativo = false;
    };
  }, [buscar]);

  if (st.loading)
    return (
      <article className="equip-card riscos-pesos" aria-busy="true">
        <h3>Pesos do índice</h3>
        <div className="equip-state">Carregando parâmetros...</div>
      </article>
    );
  if (st.error)
    return (
      <article className="equip-card riscos-pesos">
        <h3>Pesos do índice</h3>
        <div className="equip-error" role="alert">
          {st.error}
        </div>
      </article>
    );

  const totalGeral =
    Math.round(
      ORDEM_PERIGOS.reduce(
        (soma, perigo) =>
          soma + (Number(campos[chavePeso(perigo)]?.texto) || 0),
        0,
      ) * 100,
    ) / 100;

  const alterar = (campo, texto) => {
    setErrosPorGrupo({});
    setCampos((prev) => ({ ...prev, [campo]: { ...prev[campo], texto } }));
  };

  const restaurarCampos = (chaves) => {
    setCampos((prev) => {
      const novo = { ...prev };
      for (const c of chaves)
        novo[c] = {
          ...prev[c],
          texto: paraTexto(prev[c].padrao, prev[c].tipo),
        };
      return novo;
    });
  };

  const restaurarBloco = (perigo) => {
    const interno = CAMPOS_INTERNOS[perigo];
    const chaves = [
      chavePeso(perigo),
      ...(interno?.campos.map(([, c]) => c) || []),
      ...(interno?.camposAdicionais?.map(([, c]) => c) || []),
    ];
    restaurarCampos(chaves);
    setErrosPorGrupo({});
    showToast(
      `Padrão de ${NOMES[perigo]} carregado. Clique em Salvar parâmetros para aplicar.`,
    );
  };

  const restaurarTudo = () => {
    restaurarCampos(Object.keys(campos));
    setErrosPorGrupo({});
    showToast(
      "Todos os padrões foram carregados. Clique em Salvar parâmetros para aplicar.",
    );
  };

  const salvar = async (e) => {
    e.preventDefault();
    setErrosPorGrupo({});
    const parametros = [];
    for (const campo of Object.values(campos)) {
      const numero = paraNumero(campo.texto, campo.tipo);
      if (campo.texto === "" || !Number.isFinite(numero) || numero < 0) {
        setErrosPorGrupo({
          [campo.grupo]: "Nenhum valor pode ser negativo ou inválido.",
        });
        return;
      }
      parametros.push({
        grupo: campo.grupo,
        indicador: campo.indicador,
        parametro: campo.parametro,
        valor: numero,
      });
    }

    setSalvando(true);
    try {
      const dados = await salvarPesos({ parametros });
      setSt({ loading: false, dados, error: "" });
      setCampos(paraCampos(dados.parametros));
      showToast("Parâmetros do modelo salvos com sucesso.");
    } catch (err) {
      if (err instanceof ErroApiParametrosScore && err.erros?.length) {
        setErrosPorGrupo(
          Object.fromEntries(
            err.erros.map(({ grupo, mensagem }) => [grupo, mensagem]),
          ),
        );
      } else {
        setErrosPorGrupo({
          ESTRUTURA:
            err?.message || "Não foi possível salvar os parâmetros do modelo.",
        });
      }
    } finally {
      setSalvando(false);
    }
  };

  return (
    <form className="riscos-pesos-form" onSubmit={salvar} noValidate>
      <article className="equip-card riscos-pesos">
        <div className="equip-card-head">
          <div>
            <h3>
              Pesos do índice <ConceptHelp conceito="peso_indice" />
            </h3>
            <p>
              Cada indicador participa do score com um único peso. A soma dos
              pesos ativos deve ser sempre 100%.
            </p>
          </div>
        </div>
        <div className="riscos-pesos-lista">
          {ORDEM_PERIGOS.map((perigo) => (
            <CampoNumerico
              key={perigo}
              rotulo={`Peso no índice — ${NOMES[perigo]}`}
              campo={chavePeso(perigo)}
              valor={campos[chavePeso(perigo)]}
              onAlterar={alterar}
            />
          ))}
        </div>
        <div
          className={`riscos-peso-total ${totalGeral === 100 ? "is-ok" : "is-invalido"}`}
        >
          <span>Total geral</span>
          <b>{pf.format(totalGeral)}%</b>
        </div>
        {errosPorGrupo.SCORE && (
          <p className="riscos-peso-erro" role="alert">
            {errosPorGrupo.SCORE}
          </p>
        )}
        {errosPorGrupo.ESTRUTURA && (
          <p className="riscos-peso-erro" role="alert">
            {errosPorGrupo.ESTRUTURA}
          </p>
        )}
      </article>

      <div className="riscos-blocos">
        {ORDEM_PERIGOS.map((perigo) => (
          <BlocoIndicador
            key={perigo}
            perigo={perigo}
            campos={campos}
            onAlterar={alterar}
            onRestaurarBloco={restaurarBloco}
            erroGrupo={errosPorGrupo[perigo]}
          />
        ))}
      </div>

      <div className="riscos-peso-acoes">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={restaurarTudo}
          disabled={salvando}
        >
          Restaurar todos os padrões
        </button>
        <button type="submit" className="btn btn-red" disabled={salvando}>
          {salvando ? "Salvando..." : "Salvar parâmetros"}
        </button>
      </div>
    </form>
  );
}

export function RiscosScore({
  showToast,
  buscar = buscarParametrosScore,
  salvar = salvarParametrosScore,
}) {
  return (
    <section
      className="equipment-dashboard riscos-score-dashboard"
      aria-label="Riscos e Score"
    >
      <header className="equip-page-head">
        <div>
          <span>AGRISHIELD-EQUIP</span>
          <h2>Riscos e Score</h2>
          <p>
            Indicadores considerados no score de exposição e os parâmetros
            configuráveis pelo Analista Sompo. O motor de cálculo permanece no
            backend.
          </p>
        </div>
      </header>
      <aside className="model-governance-guide">
        <div className="model-governance-icon">!</div>
        <div>
          <h3>Antes de alterar os padrões</h3>
          <p>
            Os valores padrão pertencem à política demonstrativa AGRISHIELD-EQUIP v1.0.
            Eles mantêm uma referência reproduzível, mas ainda não foram calibrados contra
            sinistros reais ou limites de fabricante.
          </p>
          <ol>
            <li><b>Identifique a situação:</b> confira qual perigo e evidência precisam mudar.</li>
            <li><b>Altere com hipótese registrada:</b> aumente peso apenas quando houver justificativa técnica para maior influência relativa.</li>
            <li><b>Valide o efeito:</b> preserve totais de 100%, compare propriedades e restaure o padrão se a mudança distorcer a leitura.</li>
          </ol>
        </div>
      </aside>
      <IndicadoresCard />
      <PesosCard showToast={showToast} buscar={buscar} salvar={salvar} />
    </section>
  );
}
