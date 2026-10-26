import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import {
  baixarModeloMaquinarios,
  cadastrarMaquinario,
  importarCsvMaquinarios,
  listarMaquinarios,
  validarCsvMaquinarios,
} from "../api/maquinarios";

const TIPOS = [
  ["TRATOR", "Trator"],
  ["COLHEITADEIRA", "Colheitadeira"],
  ["PULVERIZADOR_AUTOPROPELIDO", "Pulverizador autopropelido"],
  ["PLANTADEIRA", "Plantadeira"],
  ["IMPLEMENTO_ARRASTO", "Implemento de arrasto"],
  ["PLATAFORMA", "Plataforma"],
  ["UTILITARIO_APOIO", "Utilitário de apoio"],
];
const MARCAS = [
  ["JOHN_DEERE", "John Deere"],
  ["MASSEY_FERGUSON", "Massey Ferguson"],
  ["NEW_HOLLAND", "New Holland"],
  ["VALTRA", "Valtra"],
  ["CASE_IH", "Case IH"],
  ["JACTO", "Jacto"],
  ["STARA", "Stara"],
  ["OUTROS", "Outra"],
];
const SEGURADORAS = [
  ["SOMPO", "Sompo"],
  ["MAPFRE", "Mapfre"],
  ["PORTO_SEGURO", "Porto Seguro"],
  ["ALLIANZ", "Allianz"],
  ["OUTRA", "Outra"],
];
const MOTORIZADOS = new Set([
  "TRATOR",
  "COLHEITADEIRA",
  "PULVERIZADOR_AUTOPROPELIDO",
  "UTILITARIO_APOIO",
]);
const FORM_INICIAL = {
  tipo_equipamento: "",
  marca: "",
  marca_outro: "",
  modelo: "",
  ano_fabricacao: "",
  chassi: "",
  apelido: "",
  horimetro_atual: "",
  hodometro_atual: "",
  media_horas_dia: "",
  possui_seguro: "nao",
  seguradora: "",
  seguradora_outro: "",
  vencimento_apolice: "",
};

const rotulo = (opcoes, valor) =>
  opcoes.find(([codigo]) => codigo === valor)?.[1] || valor || "—";

function formatarNumero(valor, casas = 1) {
  if (valor == null || valor === "") return "—";
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  }).format(Number(valor));
}

function formatarDataCivil(valor) {
  if (!valor) return "—";
  const [ano, mes, dia] = String(valor).slice(0, 10).split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : String(valor);
}

function resumoVazio() {
  return {
    total: 0,
    segurados: 0,
    sem_seguro: 0,
    vencendo_90_dias: 0,
  };
}

export function MaquinariosPage({
  fazenda,
  onVoltar,
  onAtualizado,
  onDirtyChange,
  showToast,
}) {
  const [aba, setAba] = useState("frota");
  const [form, setForm] = useState(FORM_INICIAL);
  const [maquinarios, setMaquinarios] = useState([]);
  const [resumo, setResumo] = useState(resumoVazio());
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [arquivoNome, setArquivoNome] = useState("");
  const [conteudoCsv, setConteudoCsv] = useState("");
  const [validandoCsv, setValidandoCsv] = useState(false);
  const [importando, setImportando] = useState(false);
  const [validacaoCsv, setValidacaoCsv] = useState(null);
  const somenteLeitura = Boolean(fazenda?.arquivada);
  const idFazenda = fazenda?.id || fazenda?.id_fazenda;
  const anoMaximo = new Date().getFullYear() + 1;
  const horimetroObrigatorio = MOTORIZADOS.has(form.tipo_equipamento);

  const carregar = useCallback(async () => {
    if (!idFazenda) return;
    setCarregando(true);
    setErro("");
    try {
      const dados = await listarMaquinarios(idFazenda);
      setMaquinarios(dados.maquinarios || []);
      setResumo(dados.resumo || resumoVazio());
    } catch (exc) {
      setErro(exc.message || "Não foi possível carregar os maquinários.");
    } finally {
      setCarregando(false);
    }
  }, [idFazenda]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  useEffect(() => () => onDirtyChange?.(false), [onDirtyChange]);

  const alterar = (campo, valor) => {
    setForm((atual) => {
      const proximo = { ...atual, [campo]: valor };
      if (campo === "marca" && valor !== "OUTROS") proximo.marca_outro = "";
      if (campo === "seguradora" && valor !== "OUTRA") proximo.seguradora_outro = "";
      if (campo === "possui_seguro" && valor === "nao") {
        proximo.seguradora = "";
        proximo.seguradora_outro = "";
        proximo.vencimento_apolice = "";
      }
      return proximo;
    });
    onDirtyChange?.(true);
  };

  const payload = useMemo(
    () => ({
      ...form,
      ano_fabricacao: Number(form.ano_fabricacao),
      horimetro_atual:
        form.horimetro_atual === "" ? null : Number(form.horimetro_atual),
      hodometro_atual:
        form.hodometro_atual === "" ? null : Number(form.hodometro_atual),
      media_horas_dia:
        form.media_horas_dia === "" ? null : Number(form.media_horas_dia),
      marca_outro: form.marca_outro || null,
      chassi: form.chassi || null,
      apelido: form.apelido || null,
      possui_seguro: form.possui_seguro === "sim",
      seguradora: form.possui_seguro === "sim" ? form.seguradora || null : null,
      seguradora_outro:
        form.possui_seguro === "sim" ? form.seguradora_outro || null : null,
      vencimento_apolice:
        form.possui_seguro === "sim" ? form.vencimento_apolice || null : null,
    }),
    [form],
  );

  async function salvar(event) {
    event.preventDefault();
    setSalvando(true);
    setErro("");
    try {
      await cadastrarMaquinario(idFazenda, payload);
      setForm(FORM_INICIAL);
      onDirtyChange?.(false);
      await carregar();
      await onAtualizado?.();
      setAba("frota");
      showToast?.("Maquinário cadastrado e vinculado à fazenda.");
    } catch (exc) {
      setErro(exc.message || "Não foi possível cadastrar o maquinário.");
    } finally {
      setSalvando(false);
    }
  }

  async function baixarModelo() {
    try {
      await baixarModeloMaquinarios();
    } catch (exc) {
      showToast?.(exc.message || "Não foi possível baixar o modelo CSV.");
    }
  }

  async function selecionarCsv(event) {
    const arquivo = event.target.files?.[0];
    setValidacaoCsv(null);
    setConteudoCsv("");
    setArquivoNome(arquivo?.name || "");
    if (!arquivo) return;
    if (!arquivo.name.toLowerCase().endsWith(".csv")) {
      setValidacaoCsv({
        valido: false,
        total_validos: 0,
        total_erros: 1,
        erros: [{ linha: 1, campo: "arquivo", mensagem: "selecione um arquivo .csv" }],
      });
      return;
    }
    if (arquivo.size > 1_000_000) {
      setValidacaoCsv({
        valido: false,
        total_validos: 0,
        total_erros: 1,
        erros: [{ linha: 1, campo: "arquivo", mensagem: "o limite é de 1 MB" }],
      });
      return;
    }
    setValidandoCsv(true);
    onDirtyChange?.(true);
    try {
      const conteudo = await arquivo.text();
      const validacao = await validarCsvMaquinarios(idFazenda, conteudo);
      setConteudoCsv(conteudo);
      setValidacaoCsv(validacao);
    } catch (exc) {
      setValidacaoCsv({
        valido: false,
        total_validos: 0,
        total_erros: 1,
        erros: [{ linha: 1, campo: "arquivo", mensagem: exc.message }],
      });
    } finally {
      setValidandoCsv(false);
    }
  }

  async function importar() {
    if (!validacaoCsv?.valido || !conteudoCsv) return;
    setImportando(true);
    try {
      const resultado = await importarCsvMaquinarios(idFazenda, conteudoCsv);
      setConteudoCsv("");
      setArquivoNome("");
      setValidacaoCsv(null);
      onDirtyChange?.(false);
      await carregar();
      await onAtualizado?.();
      setAba("frota");
      showToast?.(`${resultado.total_importados} maquinário(s) importado(s).`);
    } catch (exc) {
      setValidacaoCsv({
        valido: false,
        total_validos: 0,
        total_erros: 1,
        erros: [{ linha: 1, campo: "importação", mensagem: exc.message }],
      });
    } finally {
      setImportando(false);
    }
  }

  if (!fazenda) {
    return (
      <div className="empty-state">
        <Icon name="warning" size={24} />
        <b>Fazenda não selecionada</b>
        <button className="btn btn-ghost" type="button" onClick={onVoltar}>Voltar</button>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="Clientes e Apólices"
        title="Maquinário agrícola"
        subtitle={`Inventário vinculado a ${fazenda.nome_fazenda}.`}
        actions={
          <>
            <button className="btn btn-ghost" type="button" onClick={onVoltar}>
              <Icon name="back" size={16} /> Voltar
            </button>
            {!somenteLeitura && (
              <button className="btn btn-ghost" type="button" onClick={baixarModelo}>
                <Icon name="download" size={16} /> Modelo CSV
              </button>
            )}
          </>
        }
      />

      <section className="machinery-farm-context" aria-label="Fazenda vinculada">
        <span className="machinery-context-icon"><Icon name="map" size={19} /></span>
        <div><small>Fazenda</small><b>{fazenda.nome_fazenda}</b></div>
        <div><small>Identificador</small><b>#{fazenda.id_fazenda || fazenda.id}</b></div>
        <div><small>Apólice(s) da fazenda</small><b>{(fazenda.apolices || [fazenda.numero_apolice]).filter(Boolean).join(", ") || "—"}</b></div>
        <div><small>Localização</small><b>{fazenda.cidade || "—"} / {fazenda.uf || "—"}</b></div>
        {somenteLeitura && <span className="badge">Fazenda arquivada · somente consulta</span>}
      </section>

      <div className="machinery-tabs" role="tablist" aria-label="Gestão de maquinários">
        <button type="button" role="tab" aria-selected={aba === "frota"} className={aba === "frota" ? "active" : ""} onClick={() => setAba("frota")}>
          Frota cadastrada <b>{resumo.total || 0}</b>
        </button>
        {!somenteLeitura && (
          <>
            <button type="button" role="tab" aria-selected={aba === "individual"} className={aba === "individual" ? "active" : ""} onClick={() => setAba("individual")}>
              Cadastro individual
            </button>
            <button type="button" role="tab" aria-selected={aba === "csv"} className={aba === "csv" ? "active" : ""} onClick={() => setAba("csv")}>
              Importar CSV
            </button>
          </>
        )}
      </div>

      {erro && <div className="form-message error" role="alert">{erro}</div>}

      {aba === "frota" && (
        <section className="machinery-panel" role="tabpanel">
          <div className="machinery-summary-grid">
            <div><span>Total da frota</span><b>{resumo.total || 0}</b><small>equipamentos cadastrados</small></div>
            <div><span>Com seguro cadastrado</span><b>{resumo.segurados || 0}</b><small>{resumo.percentual_segurado || 0}% da frota</small></div>
            <div><span>Sem seguro</span><b>{resumo.sem_seguro || 0}</b><small>conforme cadastro</small></div>
            <div><span>Vencendo em 90 dias</span><b>{resumo.vencendo_90_dias || 0}</b><small>apólices de maquinário</small></div>
          </div>
          {carregando ? (
            <div className="empty-state" role="status"><b>Carregando inventário…</b></div>
          ) : maquinarios.length ? (
            <div className="machinery-list">
              {maquinarios.map((item) => (
                <article className="machinery-card" key={item.id_maquinario}>
                  <header>
                    <span className="machinery-card-icon"><Icon name="activity" size={18} /></span>
                    <div>
                      <small>{rotulo(TIPOS, item.tipo_equipamento)}</small>
                      <h2>{item.apelido || `${rotulo(MARCAS, item.marca)} ${item.modelo}`}</h2>
                      <p>{item.apelido ? `${rotulo(MARCAS, item.marca)} ${item.modelo}` : `Ano ${item.ano_fabricacao}`}</p>
                    </div>
                    <span className={`machinery-insurance ${item.possui_seguro ? "is-covered" : ""}`}>
                      {item.possui_seguro ? "Seguro cadastrado" : "Sem seguro"}
                    </span>
                  </header>
                  <dl>
                    <div><dt>Ano</dt><dd>{item.ano_fabricacao}</dd></div>
                    <div><dt>Chassi / série</dt><dd>{item.chassi || "Não informado"}</dd></div>
                    <div><dt>Horímetro</dt><dd>{item.horimetro_atual == null ? "—" : `${formatarNumero(item.horimetro_atual)} h`}</dd></div>
                    <div><dt>Hodômetro</dt><dd>{item.hodometro_atual == null ? "—" : `${formatarNumero(item.hodometro_atual)} km`}</dd></div>
                    <div><dt>Uso estimado</dt><dd>{item.media_horas_dia == null ? "—" : `${formatarNumero(item.media_horas_dia)} h/dia`}</dd></div>
                    <div><dt>Proteção</dt><dd>{item.possui_seguro ? `${rotulo(SEGURADORAS, item.seguradora)} · até ${formatarDataCivil(item.vencimento_apolice)}` : "Não informada"}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <Icon name="activity" size={26} />
              <b>Nenhum maquinário cadastrado</b>
              <span>Cadastre individualmente ou importe o modelo CSV desta fazenda.</span>
              {!somenteLeitura && <button className="btn btn-red" type="button" onClick={() => setAba("individual")}>Cadastrar primeiro maquinário</button>}
            </div>
          )}
        </section>
      )}

      {aba === "individual" && !somenteLeitura && (
        <form className="form-card rural-form machinery-form" onSubmit={salvar} role="tabpanel">
          <div className="form-intro">
            <span className="form-intro-icon"><Icon name="activity" /></span>
            <div><b>Novo equipamento</b><p>Os dados serão vinculados somente a {fazenda.nome_fazenda}.</p></div>
          </div>
          <fieldset>
            <legend><span>1</span> Identificação</legend>
            <div className="form-grid">
              <div className="fg"><label htmlFor="machine-type">Tipo de equipamento <i className="required-mark">*</i></label><select id="machine-type" required value={form.tipo_equipamento} onChange={(e) => alterar("tipo_equipamento", e.target.value)}><option value="">Selecione</option>{TIPOS.map(([codigo, label]) => <option key={codigo} value={codigo}>{label}</option>)}</select></div>
              <div className="fg"><label htmlFor="machine-brand">Marca / fabricante <i className="required-mark">*</i></label><select id="machine-brand" required value={form.marca} onChange={(e) => alterar("marca", e.target.value)}><option value="">Selecione</option>{MARCAS.map(([codigo, label]) => <option key={codigo} value={codigo}>{label}</option>)}</select></div>
              {form.marca === "OUTROS" && <div className="fg"><label htmlFor="machine-brand-other">Nome do fabricante <i className="required-mark">*</i></label><input id="machine-brand-other" required maxLength={80} value={form.marca_outro} onChange={(e) => alterar("marca_outro", e.target.value)} /></div>}
              <div className="fg"><label htmlFor="machine-model">Modelo <i className="required-mark">*</i></label><input id="machine-model" required maxLength={100} value={form.modelo} onChange={(e) => alterar("modelo", e.target.value)} /></div>
              <div className="fg"><label htmlFor="machine-year">Ano de fabricação <i className="required-mark">*</i></label><input id="machine-year" required type="number" min="1970" max={anoMaximo} value={form.ano_fabricacao} onChange={(e) => alterar("ano_fabricacao", e.target.value)} /></div>
              <div className="fg"><label htmlFor="machine-chassis">Nº de série / chassi</label><input id="machine-chassis" maxLength={100} value={form.chassi} onChange={(e) => alterar("chassi", e.target.value)} /></div>
              <div className="fg"><label htmlFor="machine-nickname">Apelido</label><input id="machine-nickname" maxLength={80} value={form.apelido} onChange={(e) => alterar("apelido", e.target.value)} /></div>
            </div>
          </fieldset>
          <fieldset>
            <legend><span>2</span> Uso e operação</legend>
            <div className="form-grid">
              <div className="fg"><label htmlFor="machine-hours">Horímetro atual {horimetroObrigatorio && <i className="required-mark">*</i>}</label><div className="input-suffix"><input id="machine-hours" required={horimetroObrigatorio} type="number" min="0" step="0.1" value={form.horimetro_atual} onChange={(e) => alterar("horimetro_atual", e.target.value)} /><span>h</span></div></div>
              <div className="fg"><label htmlFor="machine-km">Hodômetro atual</label><div className="input-suffix"><input id="machine-km" type="number" min="0" step="0.1" value={form.hodometro_atual} onChange={(e) => alterar("hodometro_atual", e.target.value)} /><span>km</span></div></div>
              <div className="fg"><label htmlFor="machine-daily">Média estimada de uso</label><div className="input-suffix"><input id="machine-daily" type="number" min="0" max="24" step="0.1" value={form.media_horas_dia} onChange={(e) => alterar("media_horas_dia", e.target.value)} /><span>h/dia</span></div></div>
            </div>
          </fieldset>
          <fieldset>
            <legend><span>3</span> Proteção e seguro</legend>
            <div className="form-grid">
              <div className="fg"><label htmlFor="machine-insured">Possui seguro cadastrado? <i className="required-mark">*</i></label><select id="machine-insured" required value={form.possui_seguro} onChange={(e) => alterar("possui_seguro", e.target.value)}><option value="nao">Não</option><option value="sim">Sim</option></select></div>
              {form.possui_seguro === "sim" && <><div className="fg"><label htmlFor="machine-insurer">Seguradora <i className="required-mark">*</i></label><select id="machine-insurer" required value={form.seguradora} onChange={(e) => alterar("seguradora", e.target.value)}><option value="">Selecione</option>{SEGURADORAS.map(([codigo, label]) => <option key={codigo} value={codigo}>{label}</option>)}</select></div>{form.seguradora === "OUTRA" && <div className="fg"><label htmlFor="machine-insurer-other">Nome da seguradora <i className="required-mark">*</i></label><input id="machine-insurer-other" required maxLength={80} value={form.seguradora_outro} onChange={(e) => alterar("seguradora_outro", e.target.value)} /></div>}<div className="fg"><label htmlFor="machine-expiry">Vencimento <i className="required-mark">*</i></label><input id="machine-expiry" required type="date" value={form.vencimento_apolice} onChange={(e) => alterar("vencimento_apolice", e.target.value)} /></div></>}
            </div>
          </fieldset>
          <div className="machinery-form-actions">
            <button className="btn btn-ghost" type="button" onClick={() => setAba("frota")}>Cancelar</button>
            <button className="btn btn-red" type="submit" disabled={salvando}><Icon name="save" size={16} /> {salvando ? "Salvando…" : "Salvar maquinário"}</button>
          </div>
        </form>
      )}

      {aba === "csv" && !somenteLeitura && (
        <section className="machinery-panel machinery-import" role="tabpanel">
          <div className="machinery-import-guide">
            <span className="machinery-context-icon"><Icon name="file" size={20} /></span>
            <div>
              <h2>Cadastro em lote por CSV</h2>
              <p>Baixe o modelo, preencha até 500 linhas e envie o arquivo. Todas as linhas são validadas antes da gravação; se houver erro, nenhuma máquina será cadastrada.</p>
              <small>Use separador ponto e vírgula (;), codificação UTF-8 e datas em AAAA-MM-DD. Valores aceitos são os mesmos exibidos no cadastro individual.</small>
            </div>
            <button className="btn btn-ghost" type="button" onClick={baixarModelo}><Icon name="download" size={16} /> Baixar modelo</button>
          </div>
          <label className="machinery-file-drop" htmlFor="machinery-csv">
            <Icon name="file" size={25} />
            <b>{arquivoNome || "Selecionar arquivo CSV"}</b>
            <span>{validandoCsv ? "Validando arquivo…" : "Máximo de 1 MB"}</span>
            <input id="machinery-csv" type="file" accept=".csv,text/csv" onChange={selecionarCsv} />
          </label>
          {validacaoCsv && (
            <div className={`machinery-validation ${validacaoCsv.valido ? "is-valid" : "is-invalid"}`} role="status">
              <header>
                <Icon name={validacaoCsv.valido ? "check" : "warning"} size={19} />
                <div><b>{validacaoCsv.valido ? "Arquivo pronto para importar" : "O arquivo precisa de correção"}</b><span>{validacaoCsv.total_validos || 0} linha(s) válida(s) · {validacaoCsv.total_erros || 0} erro(s)</span></div>
              </header>
              {(validacaoCsv.erros || []).length > 0 && <ul>{validacaoCsv.erros.slice(0, 20).map((item, indice) => <li key={`${item.linha}-${item.campo}-${indice}`}><b>Linha {item.linha} · {item.campo}:</b> {item.mensagem}</li>)}</ul>}
              {validacaoCsv.valido && <button className="btn btn-red" type="button" disabled={importando} onClick={importar}>{importando ? "Importando…" : `Confirmar importação de ${validacaoCsv.total_validos} item(ns)`}</button>}
            </div>
          )}
        </section>
      )}
    </>
  );
}
