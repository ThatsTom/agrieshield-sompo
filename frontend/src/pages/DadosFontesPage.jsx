import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { ConceptHelp } from "../components/ConceptHelp";
import { FazendaSearch } from "../components/FazendaSearch";
import { fetchJSON } from "../api/core";
import { buscarParametrosScore } from "../api/parametrosScore";
import { numero } from "../utils/format";
const bases = [
  {
    arquivo: "fazendas.csv",
    titulo: "Cadastro de fazendas",
    descricao:
      "Identificação, apólice, endereço, operação, coordenadas e área.",
    icone: "users",
  },
  {
    arquivo: "fazendas_geoespaciais.csv",
    titulo: "Contexto geoespacial",
    descricao:
      "Declividade, posição topográfica, drenagem, versões do algoritmo e qualidade.",
    icone: "map",
  },
  {
    arquivo: "parametros_score.csv",
    titulo: "Parâmetros do score",
    descricao: "Pesos e coeficientes configuráveis do modelo AgriShield-EQUIP.",
    icone: "gauge",
  },
  {
    arquivo: "base_coordenadas_cep.csv",
    titulo: "Base de apoio por CEP",
    descricao:
      "Coordenadas e endereços usados como apoio à geocodificação local.",
    icone: "database",
  },
];
function Row({ label, value, conceito }) {
  return (
    <div className="data-row">
      <span>
        {label} {conceito && <ConceptHelp conceito={conceito} />}
      </span>
      <b>
        {value === null || value === undefined || value === ""
          ? "—"
          : String(value)}
      </b>
    </div>
  );
}
export function DadosFontesPage({
  fazendas,
  selected,
  setSelected,
  fazenda,
}) {
  const [geo, setGeo] = useState(null),
    [params, setParams] = useState(null),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!selected) return;
    let live = true;
    setLoading(true);
    Promise.allSettled([
      fetchJSON(`/api/fazendas/${selected}/geoespacial`),
      buscarParametrosScore(),
    ]).then(([g, p]) => {
      if (!live) return;
      setGeo(g.status === "fulfilled" ? g.value : null);
      setParams(p.status === "fulfilled" ? p.value : null);
      setLoading(false);
    });
    return () => {
      live = false;
    };
  }, [selected]);
  const grupos = useMemo(() => {
    const m = {};
    for (const p of params?.parametros || []) (m[p.grupo] ??= []).push(p);
    return m;
  }, [params]);
  return (
    <>
      <PageHeader
        eyebrow="Governança"
        title="Dados e Fontes"
        subtitle="Consulte a origem, a disponibilidade e a referência dos dados usados em cada leitura."
      />
      <section className="source-catalog">
        {bases.map((b) => (
          <article key={b.arquivo}>
            <div className="source-icon">
              <Icon name={b.icone} />
            </div>
            <div>
              <b>{b.titulo}</b>
              <code>{b.arquivo}</code>
              <p>{b.descricao}</p>
            </div>
            <span className="source-live">API local</span>
          </article>
        ))}
      </section>
      <div className="filters data-selector">
        <FazendaSearch
          fazendas={fazendas}
          selected={selected}
          onSelect={setSelected}
          label="Inspecionar propriedade"
        />
        {loading && (
          <span className="inline-loading">
            <span className="spinner" />
            Atualizando dados
          </span>
        )}
      </div>
      <div className="data-grid">
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>fazendas.csv</span>
              <h2>Registro cadastral</h2>
            </div>
            <span className="badge green">carregado</span>
          </div>
          <div className="data-list">
            <Row label="ID" value={fazenda?.id_fazenda || fazenda?.id} />
            <Row label="Nome" value={fazenda?.nome_fazenda} />
            <Row label="Apólice" value={fazenda?.numero_apolice} conceito="apolice" />
            <Row label="CEP" value={fazenda?.cep} />
            <Row
              label="Cidade / UF"
              value={`${fazenda?.cidade || "—"} / ${fazenda?.uf || "—"}`}
            />
            <Row label="Operação" value={fazenda?.tipo_operacao} conceito="tipo_operacao" />
            <Row label="Área (ha)" value={fazenda?.area_ha} conceito="area_fazenda" />
            <Row label="Latitude" value={fazenda?.latitude} conceito="coordenadas" />
            <Row label="Longitude" value={fazenda?.longitude} conceito="coordenadas" />
          </div>
        </section>
        <section className="panel-card">
          <div className="panel-head">
            <div>
              <span>fazendas_geoespaciais.csv</span>
              <h2>Registro territorial</h2>
            </div>
            <span
              className={`badge ${geo?.status === "sucesso" ? "green" : "warn"}`}
            >
              {geo?.status || "indisponível"}
            </span>
          </div>
          {geo ? (
            <div className="data-list">
              <Row label="Versão do schema" value={geo.schema_version} />
              <Row label="Algoritmo" value={geo.algorithm_version} />
              <Row
                label="Declividade média"
                conceito="srtm"
                value={
                  geo.declividade_media_graus == null
                    ? null
                    : `${numero(geo.declividade_media_graus, 2)}°`
                }
              />
              <Row
                label="Posição topográfica"
                conceito="posicao_topografica"
                value={
                  geo.posicao_topografica_relativa_m == null
                    ? null
                    : `${numero(geo.posicao_topografica_relativa_m, 2)} m`
                }
              />
              <Row
                label="Distância à drenagem"
                conceito="merit_distancia"
                value={
                  geo.distancia_drenagem_m == null
                    ? null
                    : `${numero(geo.distancia_drenagem_m, 0)} m`
                }
              />
              <Row
                label="Área montante"
                conceito="merit_area"
                value={
                  geo.area_drenagem_montante_km2 == null
                    ? null
                    : `${numero(geo.area_drenagem_montante_km2, 2)} km²`
                }
              />
              <Row label="Calculado em" value={geo.calculado_em_utc} />
            </div>
          ) : (
            <div className="empty-state">
              <Icon name="map" size={23} />
              <b>Sem registro geoespacial</b>
              <span>
                Essa propriedade ainda não possui linha territorial disponível
                pela API.
              </span>
            </div>
          )}
        </section>
        <section className="panel-card wide">
          <div className="panel-head">
            <div>
              <span>parametros_score.csv</span>
              <h2>Parâmetros vigentes do modelo</h2>
            </div>
            <span className="badge blue">
              {params?.parametros?.length || 0} parâmetros
            </span>
          </div>
          {params ? (
            <div className="params-groups">
              {Object.entries(grupos).map(([grupo, itens]) => (
                <div key={grupo}>
                  <h3>{grupo.replaceAll("_", " ")}</h3>
                  <div>
                    {itens.map((p) => (
                      <span key={`${p.grupo}-${p.indicador}-${p.parametro}`}>
                        <small>
                          {p.indicador.replaceAll("_", " ")} ·{" "}
                          {p.parametro.replaceAll("_", " ")}
                        </small>
                        <b>{numero(p.valor_atual, 4)}</b>
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Icon name="gauge" size={23} />
              <b>Parâmetros indisponíveis</b>
              <span>
                Não foi possível consultar a configuração vigente do modelo.
              </span>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
