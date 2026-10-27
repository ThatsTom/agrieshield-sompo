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
    arquivo: "agrishield_fazendas",
    titulo: "Cadastro de fazendas",
    descricao:
      "Identificação, apólice, endereço, operação, coordenadas e área.",
    icone: "users",
  },
  {
    arquivo: "agrishield_geoespacial",
    titulo: "Contexto geoespacial",
    descricao:
      "Declividade, posição topográfica, drenagem, versões do algoritmo e qualidade.",
    icone: "map",
  },
  {
    arquivo: "agrishield_parametros_score",
    titulo: "Parâmetros do score",
    descricao: "Pesos e coeficientes configuráveis do modelo AgriShield-EQUIP.",
    icone: "gauge",
  },
  {
    arquivo: "agrishield_coordenadas_cep",
    titulo: "Base de apoio por CEP",
    descricao:
      "Coordenadas e endereços usados como apoio à geocodificação local.",
    icone: "database",
  },
];

const fontesDoScore = [
  {
    nome: "NASA POWER",
    subtitulo: "Meteorologia histórica · fonte padrão",
    descricao:
      "Serviço da NASA que fornece séries diárias de chuva, temperatura, umidade, vento e radiação para as coordenadas da fazenda. É a fonte meteorológica padrão da avaliação.",
    url: "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
    campos: [
      {
        codigo: "PRECTOTCORR",
        nome: "Precipitação diária (mm)",
        explicacao: "Quantidade de chuva estimada em cada dia.",
        uso: "Alimenta Exposição Hídrica, Trafegabilidade e Tempestades; também define a sequência de dias sem chuva usada em Incêndio e a ativação hídrica da Instabilidade.",
      },
      {
        codigo: "T2M_MAX",
        nome: "Temperatura máxima (°C)",
        explicacao: "Maior temperatura do ar a 2 m de altura no dia.",
        uso: "Entra no índice de Propagação de Incêndio.",
      },
      {
        codigo: "RH2M",
        nome: "Umidade relativa média (%)",
        explicacao: "Média diária da umidade do ar a 2 m de altura.",
        uso: "Entra no índice de Propagação de Incêndio: ar mais seco aumenta a exposição.",
      },
      {
        codigo: "WS2M",
        nome: "Vento médio (m/s)",
        explicacao: "Velocidade média diária do vento a 2 m de altura; não representa rajadas.",
        uso: "Entra nos índices de Propagação de Incêndio e Tempestades.",
      },
      {
        codigo: "T2M",
        nome: "Temperatura média (°C)",
        explicacao: "Média diária da temperatura do ar a 2 m de altura.",
        uso: "Registrada na série histórica e nos resumos; não entra diretamente nas fórmulas dos perigos do score atual.",
      },
      {
        codigo: "T2M_MIN",
        nome: "Temperatura mínima (°C)",
        explicacao: "Menor temperatura do ar a 2 m de altura no dia.",
        uso: "Registrada na série histórica e nos resumos; não entra diretamente nas fórmulas dos perigos do score atual.",
      },
      {
        codigo: "ALLSKY_SFC_SW_DWN",
        nome: "Radiação solar (MJ/m²/dia)",
        explicacao: "Energia solar recebida na superfície durante o dia.",
        uso: "Solicitada à NASA POWER, mas não incorporada ao cálculo do score atual.",
      },
    ],
  },
  {
    nome: "Open-Meteo Historical",
    subtitulo: "Meteorologia histórica · fonte alternativa",
    descricao:
      "Série histórica ERA5-Land consultada para o ponto da fazenda. Pode substituir a NASA POWER em uma avaliação; as duas fontes não são combinadas no mesmo cálculo.",
    url: "https://open-meteo.com/en/docs/historical-weather-api",
    campos: [
      {
        codigo: "precipitation_sum",
        nome: "Precipitação diária (mm)",
        explicacao: "Soma da chuva estimada no dia.",
        uso: "Mesmos usos de PRECTOTCORR: Exposição Hídrica, Trafegabilidade, Tempestades e contexto de chuva para Incêndio e Instabilidade.",
      },
      {
        codigo: "temperature_2m_max",
        nome: "Temperatura máxima (°C)",
        explicacao: "Maior temperatura diária a 2 m do solo.",
        uso: "Propagação de Incêndio.",
      },
      {
        codigo: "relative_humidity_2m_mean",
        nome: "Umidade relativa média (%)",
        explicacao: "Média diária da umidade a 2 m do solo.",
        uso: "Propagação de Incêndio.",
      },
      {
        codigo: "wind_speed_10m_mean",
        nome: "Vento médio (m/s)",
        explicacao: "Velocidade média diária a 10 m de altura, não rajada. A altura difere dos 2 m usados pela NASA POWER.",
        uso: "Propagação de Incêndio e Tempestades.",
      },
      {
        codigo: "temperature_2m_mean",
        nome: "Temperatura média (°C)",
        explicacao: "Média diária da temperatura a 2 m do solo.",
        uso: "Série histórica e resumos; não entra diretamente nas fórmulas dos perigos do score atual.",
      },
      {
        codigo: "temperature_2m_min",
        nome: "Temperatura mínima (°C)",
        explicacao: "Menor temperatura diária a 2 m do solo.",
        uso: "Série histórica e resumos; não entra diretamente nas fórmulas dos perigos do score atual.",
      },
    ],
  },
  {
    nome: "SRTM",
    subtitulo: "Relevo · usado no score",
    descricao:
      "Modelo digital de elevação da NASA/USGS consultado pelo Google Earth Engine. O sistema lê a banda elevation, em metros, ao redor do ponto cadastrado da fazenda, em uma grade de aproximadamente 30 m.",
    url: "https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003",
    campos: [
      {
        codigo: "elevation → declividade_media_graus",
        nome: "Declividade média (°)",
        explicacao: "Inclinação média do terreno em um raio de 1 km ao redor do ponto da fazenda.",
        uso: "Compõe a suscetibilidade topográfica do índice de Instabilidade.",
      },
      {
        codigo: "elevation → posicao_topografica_relativa_m",
        nome: "Posição topográfica relativa (m)",
        explicacao: "Elevação no ponto menos a elevação média no mesmo raio de 1 km; valor negativo indica posição mais baixa que o entorno.",
        uso: "Compõe a suscetibilidade topográfica da Instabilidade e a suscetibilidade territorial da Exposição Hídrica.",
      },
    ],
  },
  {
    nome: "MERIT Hydro",
    subtitulo: "Drenagem · usado no score",
    descricao:
      "Mapa global de drenagem consultado pelo Google Earth Engine, com pixels de aproximadamente 93 m. O sistema usa a banda upa (área que contribui água a montante) para localizar o pixel de drenagem elegível mais próximo do ponto da fazenda. Por padrão, considera pixels com pelo menos 10 km² de contribuição em um raio de busca de 50 km.",
    url: "https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1",
    campos: [
      {
        codigo: "upa → distancia_drenagem_m",
        nome: "Distância à drenagem (m)",
        explicacao: "Distância geográfica do ponto da fazenda ao centro do pixel de drenagem selecionado.",
        uso: "Compõe a suscetibilidade territorial da Exposição Hídrica.",
      },
      {
        codigo: "upa → area_drenagem_montante_km2",
        nome: "Área de influência da drenagem (km²)",
        explicacao: "Área a montante que contribui para aquele mesmo pixel. Não é a área da fazenda nem uma área alagada.",
        uso: "Compõe a suscetibilidade territorial da Exposição Hídrica.",
      },
    ],
  },
];

const fontesDeApoio = [
  {
    nome: "Open-Meteo Forecast",
    descricao: "Previsão dos próximos dias usada em alertas e contexto operacional. Não alimenta o score histórico de exposição.",
    campos: [
      ["precipitation_sum", "Chuva diária prevista (mm)."],
      ["precipitation_probability_max", "Maior probabilidade de chuva no dia (%)."],
      ["temperature_2m_max", "Temperatura máxima prevista (°C)."],
    ],
    url: "https://open-meteo.com/en/docs",
  },
  {
    nome: "MapBiomas",
    descricao: "Mapa anual de cobertura e uso da terra, utilizado para contexto territorial. Não participa do score atual.",
    campos: [["classification_2024", "Classe de cobertura do solo no ano padrão de 2024 (coleção 10.1)."]],
    url: "https://brasil.mapbiomas.org/iniciativas-e-produtos/cobertura-e-uso-da-terra/cobertura-30m/cobertura/",
  },
  {
    nome: "INMET",
    descricao: "Dados meteorológicos de estações do Instituto Nacional de Meteorologia. A integração existe, mas não é usada na avaliação atual do score.",
    campos: [],
    url: "https://portal.inmet.gov.br/servicos/bdmep-dados-historicos",
  },
  {
    nome: "ViaCEP",
    descricao: "Consulta dados de endereço pelo CEP para apoiar o cadastro. O ViaCEP não fornece latitude e longitude nem variáveis do score.",
    campos: [
      ["cep", "Código postal usado na consulta."],
      ["logradouro", "Rua ou via associada ao CEP."],
      ["complemento", "Informação adicional do endereço, quando disponível."],
      ["bairro", "Bairro associado ao CEP."],
      ["localidade", "Município, gravado no cadastro como cidade."],
      ["uf", "Sigla do estado."],
      ["ibge", "Código do município no IBGE."],
    ],
    url: "https://viacep.com.br/",
  },
];

function FonteScoreCard({ fonte }) {
  return (
    <article className="external-source-card">
      <div className="external-source-head">
        <div>
          <span>{fonte.subtitulo}</span>
          <h3>{fonte.nome}</h3>
        </div>
        <a href={fonte.url} target="_blank" rel="noopener noreferrer">
          Documentação oficial ↗
        </a>
      </div>
      <p>{fonte.descricao}</p>
      <div className="external-source-fields">
        {fonte.campos.map((campo) => (
          <div className="external-source-field" key={campo.codigo}>
            <div>
              <b>{campo.nome}</b>
              <code>{campo.codigo}</code>
            </div>
            <p>{campo.explicacao}</p>
            <p><strong>No modelo:</strong> {campo.uso}</p>
          </div>
        ))}
      </div>
    </article>
  );
}
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
            <span className="source-live">via API</span>
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
              <span>agrishield_fazendas</span>
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
              <span>agrishield_geoespacial</span>
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
                label="Área de influência da drenagem"
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
              <span>agrishield_parametros_score</span>
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
      <section className="external-sources" aria-labelledby="external-sources-title">
        <div className="external-sources-intro">
          <span>Rastreabilidade do modelo</span>
          <h2 id="external-sources-title">Fontes externas e campos utilizados</h2>
          <p>
            Os dados meteorológicos e territoriais são consultados para as
            coordenadas cadastradas da fazenda. Em cada avaliação, o score usa
            uma fonte meteorológica histórica (NASA POWER ou Open-Meteo) e as
            duas fontes de relevo e drenagem abaixo. A fonte escolhida aparece
            no detalhamento de Operações.
          </p>
          <p>
            A partir da chuva diária, o AgriShield calcula acumulados de 3 e
            7 dias e sequências de dias com ou sem chuva. Esses valores são
            derivados pelo modelo, não são campos adicionais das fontes.
          </p>
        </div>
        <div className="external-sources-grid">
          {fontesDoScore.map((fonte) => (
            <FonteScoreCard key={fonte.nome} fonte={fonte} />
          ))}
        </div>
        <div className="external-sources-intro external-sources-support-title">
          <span>Dados complementares</span>
          <h2>Fontes de previsão, contexto e cadastro</h2>
          <p>Estas integrações ajudam outras telas, mas não entram no cálculo do score histórico de exposição do maquinário.</p>
        </div>
        <div className="external-support-grid">
          {fontesDeApoio.map((fonte) => (
            <article className="external-support-card" key={fonte.nome}>
              <h3>{fonte.nome}</h3>
              <p>{fonte.descricao}</p>
              {fonte.campos.length > 0 && (
                <dl>
                  {fonte.campos.map(([codigo, descricao]) => (
                    <div key={codigo}>
                      <dt><code>{codigo}</code></dt>
                      <dd>{descricao}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <a href={fonte.url} target="_blank" rel="noopener noreferrer">
                Documentação oficial ↗
              </a>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
