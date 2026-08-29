import { useEffect, useState } from "react";
import { ExposicaoMaquinario } from "../components/ExposicaoMaquinario";
import { ConceptHelp } from "../components/ConceptHelp";
import { FazendaSearch } from "../components/FazendaSearch";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { fetchJSON } from "../api/core";
import { obterStatusGeoespacial } from "../cadastro/statusGeoespacial";
import { GeoAnalysisMap } from "../components/GeoAnalysisMap";
import { numero, tituloOperacao } from "../utils/format";
function Metric({ label, value, help, conceito }) {
  return (
    <div className="metric-card">
      <span className="metric-label">
        {label} {conceito && <ConceptHelp conceito={conceito} />}
      </span>
      <b>{value}</b>
      {help && <small>{help}</small>}
    </div>
  );
}
export function OperacoesPage({
  fazendas,
  selected,
  setSelected,
  fazenda,
  onNavigate,
}) {
  const [geo, setGeo] = useState({ loading: false, data: null, error: "" });
  useEffect(() => {
    if (!selected) return;
    let live = true;
    setGeo({ loading: true, data: null, error: "" });
    fetchJSON(`/api/fazendas/${selected}/geoespacial`)
      .then((data) => live && setGeo({ loading: false, data, error: "" }))
      .catch(
        (error) =>
          live && setGeo({ loading: false, data: null, error: error.message }),
      );
    return () => {
      live = false;
    };
  }, [selected]);
  const status = obterStatusGeoespacial(fazenda?.status_geoespacial),
    g = geo.data;
  return (
    <>
      <PageHeader
        eyebrow="Operações"
        title="Contexto da Operação"
        subtitle="Consolide cadastro, território e exposição do maquinário em uma única leitura."
        actions={
          <button
            className="btn btn-ghost"
            onClick={() => onNavigate("clientes")}
          >
            <Icon name="users" size={16} /> Portfólio
          </button>
        }
      />
      <div className="filters operation-selector">
        <FazendaSearch
          fazendas={fazendas}
          selected={selected}
          onSelect={setSelected}
          label="Propriedade analisada"
        />
        <div className={`context-pill ${status.classe}`}>
          <span>{status.icone}</span>
          <div>
            <small>Contexto territorial</small>
            <b>{status.curto}</b>
          </div>
        </div>
      </div>
      <section className="section-block">
        <div className="section-title">
          <div>
            <span>Cadastro operacional</span>
            <h2>
              {fazenda?.nome_fazenda || "Propriedade"}{" "}
              <ConceptHelp conceito="cadastro_operacional" />
            </h2>
            <p>
              Resumo dos campos persistidos em <code>fazendas.csv</code>.
            </p>
          </div>
        </div>
        <div className="metric-grid six">
          <Metric label="Apólice" value={fazenda?.numero_apolice || "—"} conceito="apolice" />
          <Metric
            label="Operação"
            value={tituloOperacao(fazenda?.tipo_operacao)}
            conceito="tipo_operacao"
          />
          <Metric
            label="Área"
            value={fazenda?.area_ha ? `${numero(fazenda.area_ha)} ha` : "—"}
            conceito="area_fazenda"
          />
          <Metric
            label="Localização"
            value={`${fazenda?.cidade || "—"} / ${fazenda?.uf || "—"}`}
            conceito="localizacao_fazenda"
          />
          <Metric label="Latitude" value={numero(fazenda?.latitude, 4)} conceito="coordenadas" />
          <Metric label="Longitude" value={numero(fazenda?.longitude, 4)} conceito="coordenadas" />
        </div>
      </section>
      <section className="section-block">
        <div className="section-title inline">
          <div>
            <span>Território</span>
            <h2>
              Indicadores geoespaciais <ConceptHelp conceito="cobertura_territorial" />
            </h2>
            <p>
              Leitura persistida de SRTM e MERIT Hydro para a propriedade
              selecionada.
            </p>
          </div>
          <button className="text-link" onClick={() => onNavigate("dados")}>
            Abrir dados e fontes <Icon name="arrow" size={14} />
          </button>
        </div>
        {geo.loading ? (
          <div className="loading-panel compact">
            <span className="spinner" />
            Carregando contexto territorial...
          </div>
        ) : g ? (
          <>
          <div className="metric-grid four">
            <Metric
              label="Declividade média"
              value={
                g.declividade_media_graus == null
                  ? "—"
                  : `${numero(g.declividade_media_graus, 2)}°`
              }
              help="SRTM"
              conceito="srtm"
            />
            <Metric
              label="Posição topográfica"
              value={
                g.posicao_topografica_relativa_m == null
                  ? "—"
                  : `${numero(g.posicao_topografica_relativa_m, 1)} m`
              }
              help="SRTM"
              conceito="posicao_topografica"
            />
            <Metric
              label="Distância à drenagem"
              value={
                g.distancia_drenagem_m == null
                  ? "—"
                  : `${numero(g.distancia_drenagem_m, 0)} m`
              }
              help="MERIT Hydro"
              conceito="merit_distancia"
            />
            <Metric
              label="Área montante"
              value={
                g.area_drenagem_montante_km2 == null
                  ? "—"
                  : `${numero(g.area_drenagem_montante_km2, 1)} km²`
              }
              help="MERIT Hydro"
              conceito="merit_area"
            />
          </div>
          <GeoAnalysisMap geo={g} fazenda={fazenda} />
          </>
        ) : (
          <div className="empty-state inline-empty">
            <Icon name="map" size={23} />
            <div>
              <b>Contexto territorial não disponível</b>
              <span>
                {geo.error ||
                  "A propriedade ainda não possui dados geoespaciais persistidos."}
              </span>
            </div>
          </div>
        )}
      </section>
      <ExposicaoMaquinario idFazenda={selected} fazenda={fazenda} />
    </>
  );
}
