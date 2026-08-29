import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { fetchJSON } from "../api/core";
import {
  formatarCep,
  montarPayloadFazenda,
  parsePoligonoTexto,
  validarCoordenadas,
} from "../cadastro/fazenda";

const FORM_VAZIO = {
  nome_fazenda: "",
  cep: "",
  numero_apolice: "",
  area_ha: "",
  logradouro: "",
  numero_km: "",
  complemento: "",
  bairro: "",
  cidade: "",
  uf: "",
  referencia_acesso: "",
  latitude: "",
  longitude: "",
  tipo_operacao: "campo",
  proximidade_agua: false,
  apolices_adicionais: [],
  poligono_texto: "",
};

function formularioInicial(fazenda) {
  if (!fazenda) return { ...FORM_VAZIO, apolices_adicionais: [] };
  return {
    ...FORM_VAZIO,
    ...Object.fromEntries(
      Object.keys(FORM_VAZIO).map((campo) => [
        campo,
        fazenda[campo] ?? FORM_VAZIO[campo],
      ]),
    ),
    cep: formatarCep(fazenda.cep),
    latitude: Number(fazenda.latitude) === 0 ? "" : fazenda.latitude,
    longitude: Number(fazenda.longitude) === 0 ? "" : fazenda.longitude,
    area_ha: fazenda.area_ha ?? "",
    proximidade_agua: Boolean(fazenda.proximidade_agua),
    apolices_adicionais: (fazenda.apolices || []).filter(
      (numero) => numero !== fazenda.numero_apolice,
    ),
    poligono_texto: (fazenda.poligono || [])
      .map(([longitude, latitude]) => `${latitude}, ${longitude}`)
      .join("\n"),
  };
}

function MapaSede({ latitude, longitude }) {
  const lat = Number(latitude), lon = Number(longitude);
  if (
    String(latitude ?? "").trim() === "" ||
    String(longitude ?? "").trim() === "" ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lon) ||
    (lat === 0 && lon === 0)
  ) {
    return (
      <div className="map-placeholder">
        <Icon name="map" size={22} />
        <span>Informe latitude e longitude para confirmar a sede no mapa.</span>
      </div>
    );
  }
  const margem = 0.012;
  const bbox = `${lon - margem},${lat - margem},${lon + margem},${lat + margem}`;
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${lat}%2C${lon}`;
  return (
    <div className="farm-map">
      <iframe title="Mapa da sede da fazenda" src={src} loading="lazy" />
      <span>Sede indicada em {lat.toFixed(6)}, {lon.toFixed(6)}</span>
    </div>
  );
}

function PoligonoPreview({ texto }) {
  let pontos = [];
  try { pontos = parsePoligonoTexto(texto); } catch { /* preview parcial */ }
  if (pontos.length < 3) return null;
  const xs = pontos.map((p) => p[0]), ys = pontos.map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const dx = maxX - minX || 1, dy = maxY - minY || 1;
  const desenho = pontos.map(([x, y]) =>
    `${12 + ((x - minX) / dx) * 176},${108 - ((y - minY) / dy) * 96}`,
  ).join(" ");
  return (
    <div className="polygon-preview">
      <svg viewBox="0 0 200 120" role="img" aria-label="Prévia do polígono">
        <polygon points={desenho} />
      </svg>
      <span>{pontos.length} vértices válidos · formato GeoJSON</span>
    </div>
  );
}
function Campo({ label, required, help, children, className = "" }) {
  return (
    <div className={`fg ${className}`}>
      <label>
        {label}
        {required && <span className="required-mark"> *</span>}
      </label>
      {children}
      {help && <span className="hint">{help}</span>}
    </div>
  );
}
export function CadastroPage({
  setPage,
  carregarFazendas,
  showToast,
  fazenda,
  setSelected,
  onDirtyChange,
}) {
  const emEdicao = Boolean(fazenda?.id);
  const [form, setForm] = useState(() => formularioInicial(fazenda));
  const inicialRef = useRef(JSON.stringify(form));
  const sujo = useMemo(
    () => JSON.stringify(form) !== inicialRef.current,
    [form],
  );
  const [hint, setHint] = useState(
      "Digite o CEP para sugerir endereço e localização.",
    ),
    [cepState, setCepState] = useState("idle"),
    [salvando, setSalvando] = useState(false);
  const upd = (k, v) => setForm((p) => ({ ...p, [k]: v }));
  useEffect(() => {
    onDirtyChange(sujo);
  }, [onDirtyChange, sujo]);
  useEffect(() => {
    const avisarSaida = (event) => {
      if (!sujo) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", avisarSaida);
    return () => window.removeEventListener("beforeunload", avisarSaida);
  }, [sujo]);
  async function buscarCep() {
    const cep = form.cep.replace(/\D/g, "");
    if (cep.length !== 8) {
      setCepState("error");
      setHint("Digite um CEP com 8 dígitos.");
      return;
    }
    setCepState("loading");
    setHint("Buscando endereço e coordenadas...");
    try {
      const d = await fetchJSON(`/api/cep/${cep}`);
      setForm((p) => ({
        ...p,
        cep: formatarCep(d.cep || cep),
        logradouro: d.logradouro || p.logradouro || "",
        complemento: p.complemento || d.complemento || "",
        bairro: d.bairro || p.bairro || "",
        cidade: d.cidade || p.cidade || "",
        uf: d.uf || p.uf || "",
        latitude: p.latitude || d.latitude || "",
        longitude: p.longitude || d.longitude || "",
      }));
      setHint(d.latitude != null && d.longitude != null
        ? `Endereço ViaCEP e coordenadas locais: ${d.latitude}, ${d.longitude}.`
        : "Endereço preenchido pelo ViaCEP. Se souber, informe as coordenadas da sede rural.");
      setCepState("success");
    } catch {
      setHint(
        "Não foi possível consultar o CEP. Você ainda pode preencher os campos manualmente.",
      );
      setCepState("error");
    }
  }
  async function salvar(e) {
    e.preventDefault();
    if (!form.nome_fazenda || !form.numero_apolice || !form.cep) {
      showToast("Preencha nome, CEP e número da apólice.");
      return;
    }
    const area = Number(form.area_ha);
    if (!Number.isFinite(area) || area <= 0) {
      showToast("Informe uma área aproximada positiva.");
      return;
    }
    const erro = validarCoordenadas(form.latitude, form.longitude);
    if (erro) {
      showToast(erro);
      return;
    }
    setSalvando(true);
    try {
      const salva = await fetchJSON(
        emEdicao ? `/api/fazendas/${fazenda.id}` : "/api/fazendas",
        {
        method: emEdicao ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(montarPayloadFazenda(form)),
        },
      );
      await carregarFazendas();
      setSelected(String(salva.id));
      if (Number(salva.latitude) !== 0 || Number(salva.longitude) !== 0) {
        await fetchJSON(`/api/fazendas/${salva.id}/clima/processar`, {
          method: "POST",
        }).catch(() => null);
      }
      showToast(
        emEdicao
          ? `Fazenda "${form.nome_fazenda}" atualizada com sucesso!`
          : `Fazenda "${form.nome_fazenda}" cadastrada com sucesso!`,
      );
      inicialRef.current = JSON.stringify(form);
      onDirtyChange(false);
      setPage("clientes", { ignorarFormularioSujo: true });
    } catch (err) {
      showToast(err.message || "Erro ao salvar. Verifique a API.");
    } finally {
      setSalvando(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="Clientes e Apólices"
        title={emEdicao ? "Editar Fazenda" : "Cadastro de Fazenda"}
        subtitle={emEdicao
          ? "Revise e atualize os dados rurais, a apólice e a localização."
          : "Informe os dados rurais, a apólice e a localização da propriedade."}
        actions={
          <button className="btn btn-ghost" onClick={() => setPage("clientes")}>
            <Icon name="back" size={16} /> Voltar
          </button>
        }
      />
      <div className="form-layout">
        <form className="form-card rural-form" onSubmit={salvar}>
          <div className="form-intro">
            <div className="form-intro-icon">
              <Icon name="map" />
            </div>
            <div>
              <b>{emEdicao ? "Edição da propriedade" : "Cadastro da propriedade"}</b>
              <p>
                Campos com * são obrigatórios. O contexto territorial é
                processado após o cadastro quando houver coordenadas válidas.
              </p>
            </div>
          </div>
          <fieldset>
            <legend>
              <span>1</span> Dados da propriedade
            </legend>
            <div className="form-grid">
              <Campo label="Nome da fazenda" required className="full">
                <input
                  required
                  value={form.nome_fazenda}
                  onChange={(e) => upd("nome_fazenda", e.target.value)}
                  placeholder="Ex.: Fazenda Boa Esperança"
                />
              </Campo>
              <Campo
                label="Área aproximada (ha)"
                required
                help="Usada também no contexto territorial."
              >
                <div className="input-suffix">
                  <input
                    type="number"
                    min="0.01"
                    step="any"
                    required
                    value={form.area_ha}
                    onChange={(e) => upd("area_ha", e.target.value)}
                    placeholder="250"
                  />
                  <span>ha</span>
                </div>
              </Campo>
              <Campo label="Número da apólice" required>
                <input
                  required
                  value={form.numero_apolice}
                  onChange={(e) => upd("numero_apolice", e.target.value)}
                  placeholder="1234567890"
                />
              </Campo>
              <Campo
                label="Apólices adicionais"
                className="full"
                help="Uma fazenda pode estar vinculada a várias apólices."
              >
                <div className="policy-list">
                  {form.apolices_adicionais.map((numero, indice) => (
                    <div className="policy-row" key={indice}>
                      <input
                        value={numero}
                        minLength="3"
                        onChange={(e) => upd(
                          "apolices_adicionais",
                          form.apolices_adicionais.map((item, posicao) =>
                            posicao === indice ? e.target.value : item),
                        )}
                        placeholder="Número da apólice adicional"
                      />
                      <button
                        type="button"
                        aria-label={`Remover apólice ${indice + 2}`}
                        onClick={() => upd(
                          "apolices_adicionais",
                          form.apolices_adicionais.filter((_, posicao) => posicao !== indice),
                        )}
                      >×</button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="add-policy"
                    onClick={() => upd(
                      "apolices_adicionais",
                      [...form.apolices_adicionais, ""],
                    )}
                  >
                    <Icon name="plus" size={14} /> Adicionar apólice
                  </button>
                </div>
              </Campo>
              <Campo label="Tipo de operação">
                <select
                  value={form.tipo_operacao}
                  onChange={(e) => upd("tipo_operacao", e.target.value)}
                >
                  <option value="campo">Campo</option>
                  <option value="transporte">Transporte</option>
                </select>
              </Campo>
              <Campo label="Proximidade de água (cadastral)">
                <label className="check check-card">
                  <input
                    type="checkbox"
                    checked={form.proximidade_agua}
                    onChange={(e) => upd("proximidade_agua", e.target.checked)}
                  />
                  <span>
                    <b>Próxima de áreas com água</b>
                    <small>Rios, lagos, várzeas ou áreas alagáveis.</small>
                  </span>
                </label>
              </Campo>
            </div>
          </fieldset>
          <fieldset>
            <legend>
              <span>2</span> Endereço rural
            </legend>
            <p className="section-hint">
              O CEP é usado como apoio ao preenchimento. Revise o endereço antes
              de salvar.
            </p>
            <div className="form-grid">
              <Campo label="CEP" required help={hint}>
                <div className={`input-action state-${cepState}`}>
                  <input
                    required
                    value={form.cep}
                    onChange={(e) => {
                      upd("cep", formatarCep(e.target.value));
                      setCepState("idle");
                    }}
                    onBlur={buscarCep}
                    placeholder="78890-000"
                  />
                  <button
                    type="button"
                    onClick={buscarCep}
                    aria-label="Buscar CEP"
                  >
                    <Icon
                      name={cepState === "loading" ? "refresh" : "search"}
                      size={16}
                    />
                  </button>
                </div>
              </Campo>
              <Campo label="Logradouro / Rodovia">
                <input
                  value={form.logradouro}
                  onChange={(e) => upd("logradouro", e.target.value)}
                  placeholder="Rodovia Carlos João Strass"
                />
              </Campo>
              <Campo label="Número / Km">
                <input
                  value={form.numero_km}
                  onChange={(e) => upd("numero_km", e.target.value)}
                  placeholder="s/n ou km 14"
                />
              </Campo>
              <Campo label="Bairro / Zona">
                <input
                  value={form.bairro}
                  onChange={(e) => upd("bairro", e.target.value)}
                  placeholder="Zona Rural"
                />
              </Campo>
              <Campo label="Complemento">
                <input
                  value={form.complemento}
                  onChange={(e) => upd("complemento", e.target.value)}
                  placeholder="Distrito, campus, setor..."
                />
              </Campo>
              <Campo label="Cidade" required>
                <input
                  required
                  value={form.cidade}
                  onChange={(e) => upd("cidade", e.target.value)}
                  placeholder="Município"
                />
              </Campo>
              <Campo label="Estado / UF" required>
                <input
                  required
                  maxLength="2"
                  value={form.uf}
                  onChange={(e) => upd("uf", e.target.value.toUpperCase())}
                  placeholder="MT"
                />
              </Campo>
              <Campo label="Referência / Acesso" className="full">
                <textarea
                  value={form.referencia_acesso}
                  onChange={(e) => upd("referencia_acesso", e.target.value)}
                  placeholder="Ex.: entrada pela estrada municipal; próximo ao campo de pesquisa"
                />
              </Campo>
            </div>
          </fieldset>
          <fieldset>
            <legend>
              <span>3</span> Localização precisa
            </legend>
            <p className="section-hint">
              Opcional. Coordenadas manuais têm prioridade sobre a localização
              aproximada por CEP. Informe latitude e longitude juntas.
            </p>
            <div className="form-grid">
              <Campo label="Latitude">
                <input
                  type="number"
                  min="-90"
                  max="90"
                  step="any"
                  value={form.latitude}
                  onChange={(e) => upd("latitude", e.target.value)}
                  placeholder="-12.5450"
                />
              </Campo>
              <Campo label="Longitude">
                <input
                  type="number"
                  min="-180"
                  max="180"
                  step="any"
                  value={form.longitude}
                  onChange={(e) => upd("longitude", e.target.value)}
                  placeholder="-55.7210"
                />
              </Campo>
            </div>
            <MapaSede latitude={form.latitude} longitude={form.longitude} />
          </fieldset>
          <fieldset>
            <legend>
              <span>4</span> Perímetro da propriedade
            </legend>
            <p className="section-hint">
              Opcional. Informe um vértice por linha no formato latitude,
              longitude. O sistema armazena o perímetro como GeoJSON.
            </p>
            <Campo
              label="Vértices do polígono"
              help="Exemplo: -12.5450, -55.7210 (mínimo de 3 linhas)."
            >
              <textarea
                className="polygon-input"
                value={form.poligono_texto}
                onChange={(e) => upd("poligono_texto", e.target.value)}
                placeholder={"-12.5450, -55.7210\n-12.5500, -55.7100\n-12.5600, -55.7250"}
              />
            </Campo>
            <PoligonoPreview texto={form.poligono_texto} />
          </fieldset>
          <div className="form-actions sticky-actions">
            <button className="btn btn-red" type="submit" disabled={salvando}>
              <Icon name="save" size={16} />
              {salvando
                ? "Salvando…"
                : emEdicao
                  ? "Salvar alterações"
                  : "Salvar fazenda"}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => setPage("clientes")}
            >
              Cancelar
            </button>
          </div>
        </form>
        <aside className="form-aside">
          <div className="aside-card">
            <Icon name="info" />
            <div>
              <b>O que acontece ao salvar?</b>
              <p>
                A API grava a fazenda em <code>fazendas.csv</code> e tenta
                enriquecer o contexto geoespacial.
              </p>
            </div>
          </div>
          <div className="aside-card">
            <Icon name="shield" />
            <div>
              <b>Dados usados no risco</b>
              <p>
                Cadastro, meteorologia e contexto territorial permanecem
                separados para rastreabilidade.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
}
