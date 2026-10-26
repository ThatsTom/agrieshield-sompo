import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "../layout/PageHeader";
import { Icon } from "../layout/Icon";
import { LocationPickerMap } from "../components/LocationPickerMap";
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

const CAMPOS_ENDERECO = [
  "logradouro",
  "numero_km",
  "complemento",
  "bairro",
  "cidade",
  "uf",
];
const apenasDigitos = (valor) => String(valor || "").replace(/\D/g, "");

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
function Campo({
  label,
  required,
  help,
  helpId,
  helpLive = false,
  children,
  className = "",
}) {
  return (
    <div className={`fg ${className}`}>
      <label>
        {label}
        {required && <span className="required-mark"> *</span>}
      </label>
      {children}
      {help && (
        <span
          className="hint"
          id={helpId}
          role={helpLive ? "status" : undefined}
          aria-live={helpLive ? "polite" : undefined}
        >
          {help}
        </span>
      )}
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
  const formRef = useRef(form);
  const cepRequestRef = useRef(0);
  const cepPendenteRef = useRef("");
  const ultimoCepConsultadoRef = useRef(
    emEdicao ? apenasDigitos(form.cep) : "",
  );
  const localizacaoRequestRef = useRef(0);
  const localizacaoPendenteRef = useRef(null);
  const montadoRef = useRef(true);
  const salvamentoRequestRef = useRef(0);
  const salvamentoEmCursoRef = useRef(false);
  const localizacaoRequerConfirmacaoRef = useRef(false);
  const ultimoEnderecoConsultadoRef = useRef("");
  const camposEnderecoEditadosRef = useRef(new Set());
  const origemCoordenadasRef = useRef(
    String(form.latitude ?? "").trim() && String(form.longitude ?? "").trim()
      ? "manual"
      : null,
  );
  const sujo = useMemo(
    () => JSON.stringify(form) !== inicialRef.current,
    [form],
  );
  const [hint, setHint] = useState(
      "Digite o CEP para sugerir endereço e localização.",
    ),
    [cepState, setCepState] = useState("idle"),
    [localizacaoState, setLocalizacaoState] = useState("idle"),
    [localizacaoHint, setLocalizacaoHint] = useState(
      origemCoordenadasRef.current === "manual"
        ? "Coordenadas existentes mantidas como manuais. Para gerar uma nova sugestão pelo endereço, limpe latitude e longitude."
        : "Após preencher CEP e Número/Km, o endereço será consultado no OpenStreetMap/Nominatim para sugerir as coordenadas. O ajuste manual continua disponível.",
    ),
    [localizacaoRequerConfirmacao, setLocalizacaoRequerConfirmacao] = useState(false),
    [salvando, setSalvando] = useState(false);
  const upd = (k, v) => setForm((anterior) => {
    const proximo = { ...anterior, [k]: v };
    formRef.current = proximo;
    return proximo;
  });
  const coordenadasManuaisAtivas = origemCoordenadasRef.current === "manual";

  const definirConfirmacaoLocalizacao = useCallback((necessaria) => {
    localizacaoRequerConfirmacaoRef.current = Boolean(necessaria);
    setLocalizacaoRequerConfirmacao(Boolean(necessaria));
  }, []);

  const cancelarLocalizacaoPendente = useCallback(() => {
    const pendencia = localizacaoPendenteRef.current;
    if (!pendencia) return;
    localizacaoPendenteRef.current = null;
    pendencia.cancelar();
  }, []);

  useEffect(() => {
    formRef.current = form;
  }, [form]);

  const atualizarCep = (valorBruto) => {
    const valor = formatarCep(valorBruto);
    const mudou = apenasDigitos(valor) !== apenasDigitos(formRef.current.cep);
    if (!mudou) {
      upd("cep", valor);
      return;
    }
    cancelarLocalizacaoPendente();
    cepRequestRef.current += 1;
    localizacaoRequestRef.current += 1;
    cepPendenteRef.current = "";
    ultimoEnderecoConsultadoRef.current = "";
    if (mudou) {
      ultimoCepConsultadoRef.current = "";
      camposEnderecoEditadosRef.current.clear();
    }
    setCepState("idle");
    setHint("Digite o CEP para sugerir endereço e localização.");
    setLocalizacaoState("idle");
    definirConfirmacaoLocalizacao(false);
    setLocalizacaoHint(
      "Após preencher CEP e Número/Km, o endereço será consultado no OpenStreetMap/Nominatim para sugerir as coordenadas. O ajuste manual continua disponível.",
    );
    setForm((anterior) => {
      const proximo = { ...anterior, cep: valor };
      if (mudou) {
        CAMPOS_ENDERECO.forEach((campo) => {
          if (!camposEnderecoEditadosRef.current.has(campo)) proximo[campo] = "";
        });
        if (origemCoordenadasRef.current !== "manual") {
          proximo.latitude = "";
          proximo.longitude = "";
          origemCoordenadasRef.current = null;
        }
      }
      formRef.current = proximo;
      return proximo;
    });
  };

  const atualizarCampoEndereco = (campo, valor, { afetaLocalizacao = true } = {}) => {
    camposEnderecoEditadosRef.current.add(campo);
    if (!afetaLocalizacao) {
      upd(campo, valor);
      return;
    }

    cancelarLocalizacaoPendente();
    localizacaoRequestRef.current += 1;
    ultimoEnderecoConsultadoRef.current = "";
    setLocalizacaoState("idle");
    const deveLimparCoordenadas = origemCoordenadasRef.current === "endereco";
    if (deveLimparCoordenadas) definirConfirmacaoLocalizacao(false);
    setLocalizacaoHint(
      localizacaoRequerConfirmacaoRef.current
        ? "Endereço alterado. Mantivemos a referência aproximada do CEP; confirme ou ajuste o pino no mapa."
        : "Endereço alterado. Ao terminar, use a localização automática ou ajuste as coordenadas manualmente.",
    );
    setForm((anterior) => {
      const proximo = { ...anterior, [campo]: valor };
      if (deveLimparCoordenadas) {
        proximo.latitude = "";
        proximo.longitude = "";
        origemCoordenadasRef.current = null;
      }
      formRef.current = proximo;
      return proximo;
    });
  };

  const atualizarCoordenada = (campo, valor) => {
    cancelarLocalizacaoPendente();
    localizacaoRequestRef.current += 1;
    ultimoEnderecoConsultadoRef.current = "";
    const origemAnterior = origemCoordenadasRef.current;
    const proximo = { ...formRef.current, [campo]: valor };
    if (["cep", "endereco"].includes(origemAnterior)) {
      const outroCampo = campo === "latitude" ? "longitude" : "latitude";
      proximo[outroCampo] = "";
    }
    const ambasVazias = !String(proximo.latitude ?? "").trim()
      && !String(proximo.longitude ?? "").trim();
    origemCoordenadasRef.current = ambasVazias ? null : "manual";
    setLocalizacaoState("idle");
    definirConfirmacaoLocalizacao(false);
    setLocalizacaoHint(
      ambasVazias
        ? "Coordenadas liberadas para preenchimento automático pelo endereço."
        : "Coordenadas ajustadas manualmente; elas têm prioridade sobre a sugestão automática.",
    );
    setForm((anterior) => {
      const atualizado = { ...anterior, [campo]: valor };
      if (["cep", "endereco"].includes(origemAnterior)) {
        const outroCampo = campo === "latitude" ? "longitude" : "latitude";
        atualizado[outroCampo] = "";
      }
      formRef.current = atualizado;
      return atualizado;
    });
  };

  const atualizarCoordenadasPeloMapa = useCallback((latitude, longitude) => {
    if (salvamentoEmCursoRef.current) return;
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (
      !Number.isFinite(lat)
      || !Number.isFinite(lon)
      || lat < -90
      || lat > 90
      || lon < -180
      || lon > 180
      || (lat === 0 && lon === 0)
    ) return;

    cancelarLocalizacaoPendente();
    localizacaoRequestRef.current += 1;
    ultimoEnderecoConsultadoRef.current = "";
    origemCoordenadasRef.current = "manual";
    definirConfirmacaoLocalizacao(false);
    const coordenadas = {
      latitude: String(Math.round(lat * 1e7) / 1e7),
      longitude: String(Math.round(lon * 1e7) / 1e7),
    };
    setLocalizacaoState("success");
    setLocalizacaoHint(
      "Coordenadas definidas pelo pino no mapa. Arraste o pino, clique em outro ponto ou edite os campos para ajustar.",
    );
    setForm((anterior) => {
      const proximo = { ...anterior, ...coordenadas };
      formRef.current = proximo;
      return proximo;
    });
  }, [cancelarLocalizacaoPendente, definirConfirmacaoLocalizacao]);

  const removerPinoMapa = useCallback(() => {
    if (salvamentoEmCursoRef.current) return;
    cancelarLocalizacaoPendente();
    localizacaoRequestRef.current += 1;
    ultimoEnderecoConsultadoRef.current = "";
    origemCoordenadasRef.current = null;
    definirConfirmacaoLocalizacao(false);
    setLocalizacaoState("idle");
    setLocalizacaoHint(
      "Pino removido. Clique no mapa, informe as coordenadas ou use a localização automática pelo endereço.",
    );
    setForm((anterior) => {
      const proximo = { ...anterior, latitude: "", longitude: "" };
      formRef.current = proximo;
      return proximo;
    });
  }, [cancelarLocalizacaoPendente, definirConfirmacaoLocalizacao]);

  const localizarEndereco = useCallback(async (dados, { forcar = false } = {}) => {
    const atual = dados || formRef.current;
    if (origemCoordenadasRef.current === "manual") {
      cancelarLocalizacaoPendente();
      setLocalizacaoState("idle");
      setLocalizacaoHint(
        "Coordenadas manuais mantidas. Para usar a sugestão automática, limpe latitude e longitude.",
      );
      return;
    }
    const cep = apenasDigitos(atual.cep);
    const payload = {
      cep,
      logradouro: String(atual.logradouro || "").trim(),
      numero_km: String(atual.numero_km || "").trim(),
      bairro: String(atual.bairro || "").trim(),
      cidade: String(atual.cidade || "").trim(),
      uf: String(atual.uf || "").trim().toUpperCase(),
    };
    if (
      cep.length !== 8
      || !payload.logradouro
      || !payload.numero_km
      || !payload.cidade
      || payload.uf.length !== 2
    ) {
      cancelarLocalizacaoPendente();
      setLocalizacaoState("idle");
      setLocalizacaoHint(
        "Complete CEP, logradouro, Número/Km, cidade e UF para localizar automaticamente.",
      );
      return;
    }
    const assinatura = JSON.stringify(payload);
    const pendenciaAtual = localizacaoPendenteRef.current;
    if (!forcar && pendenciaAtual?.assinatura === assinatura) {
      return pendenciaAtual.promise;
    }
    if (!forcar && ultimoEnderecoConsultadoRef.current === assinatura) return;

    cancelarLocalizacaoPendente();
    const requisicao = ++localizacaoRequestRef.current;
    let concluirPendencia;
    let rejeitarCancelamento;
    let expirou = false;
    let timeoutId;
    const promise = new Promise((resolve) => {
      concluirPendencia = resolve;
    });
    const controller = new AbortController();
    const cancelamento = new Promise((_, reject) => {
      rejeitarCancelamento = reject;
    });
    const pendencia = {
      assinatura,
      promise,
      cancelar: () => {
        controller.abort();
        rejeitarCancelamento(new DOMException("Consulta cancelada", "AbortError"));
        concluirPendencia();
      },
    };
    localizacaoPendenteRef.current = pendencia;
    setLocalizacaoState("loading");
    setLocalizacaoHint("Localizando o endereço completo com segurança...");
    try {
      const limiteDeTempo = new Promise((_, reject) => {
        timeoutId = window.setTimeout(() => {
          expirou = true;
          controller.abort();
          reject(new Error("Tempo limite da localização excedido"));
        }, 15000);
      });
      const resposta = await Promise.race([
        fetchJSON("/api/geocodificacao/endereco", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: controller.signal,
        }),
        cancelamento,
        limiteDeTempo,
      ]);
      if (
        requisicao !== localizacaoRequestRef.current
        || origemCoordenadasRef.current === "manual"
      ) return;
      ultimoEnderecoConsultadoRef.current = assinatura;
      const respostaObjeto = resposta && typeof resposta === "object" && !Array.isArray(resposta);
      const latitudeBruta = respostaObjeto ? resposta.latitude : null;
      const longitudeBruta = respostaObjeto ? resposta.longitude : null;
      const latitudePreenchida = (
        typeof latitudeBruta === "number"
        || (typeof latitudeBruta === "string" && latitudeBruta.trim() !== "")
      );
      const longitudePreenchida = (
        typeof longitudeBruta === "number"
        || (typeof longitudeBruta === "string" && longitudeBruta.trim() !== "")
      );
      const latitudeResposta = Number(latitudeBruta);
      const longitudeResposta = Number(longitudeBruta);
      const coordenadasRespostaValidas = (
        latitudePreenchida
        && longitudePreenchida
        && Number.isFinite(latitudeResposta)
        && Number.isFinite(longitudeResposta)
        && latitudeResposta >= -90
        && latitudeResposta <= 90
        && longitudeResposta >= -180
        && longitudeResposta <= 180
        && (latitudeResposta !== 0 || longitudeResposta !== 0)
      );
      if (
        !respostaObjeto
        || !resposta.encontrado
        || !coordenadasRespostaValidas
      ) {
        const manterConfirmacao = (
          localizacaoRequerConfirmacaoRef.current
          || origemCoordenadasRef.current === "cep"
        );
        definirConfirmacaoLocalizacao(manterConfirmacao);
        setLocalizacaoState("error");
        const referenciaCepAtiva = origemCoordenadasRef.current === "cep";
        setLocalizacaoHint(
          referenciaCepAtiva
            ? "O número não foi localizado. Mantivemos apenas a referência aproximada do CEP; confirme ou ajuste no mapa."
            : manterConfirmacao
            ? "A nova consulta não encontrou outro ponto. Mantivemos a sugestão anterior; confirme ou ajuste o pino no mapa."
            : respostaObjeto && resposta.aviso
            ? resposta.aviso
            : "Endereço não localizado automaticamente. Posicione o pino no mapa ou informe as coordenadas.",
        );
        return;
      }
      origemCoordenadasRef.current = "endereco";
      const requerConfirmacao = Boolean(
        resposta.requer_confirmacao
        || ["cep", "logradouro"].includes(String(resposta.precisao || "")),
      );
      definirConfirmacaoLocalizacao(requerConfirmacao);
      const coordenadas = {
        latitude: String(latitudeResposta),
        longitude: String(longitudeResposta),
      };
      formRef.current = { ...formRef.current, ...coordenadas };
      setForm((anterior) => ({ ...anterior, ...coordenadas }));
      setLocalizacaoState("success");
      setLocalizacaoHint(
        `${resposta.aviso || "Coordenadas sugeridas."} ${resposta.atribuicao || "© OpenStreetMap contributors"}${requerConfirmacao ? " Confirme este ponto antes de salvar." : ""}`,
      );
    } catch (erro) {
      if (
        requisicao !== localizacaoRequestRef.current
        || (!expirou && erro?.name === "AbortError")
      ) return;
      const manterConfirmacao = (
        localizacaoRequerConfirmacaoRef.current
        || origemCoordenadasRef.current === "cep"
      );
      definirConfirmacaoLocalizacao(manterConfirmacao);
      setLocalizacaoState("error");
      const detalhePublico = String(erro?.publicMessage || "").trim();
      setLocalizacaoHint(
        expirou
          ? "A localização automática demorou mais que o esperado. Tente novamente ou posicione o pino no mapa."
          : origemCoordenadasRef.current === "cep"
          ? "A consulta pelo número está indisponível. Mantivemos a referência aproximada do CEP; confirme ou ajuste no mapa."
          : manterConfirmacao
          ? "A nova consulta está indisponível. Mantivemos a sugestão anterior; confirme ou ajuste o pino no mapa."
          : detalhePublico
          ? `${detalhePublico} Posicione o pino no mapa ou tente novamente.`
          : "A localização automática está indisponível. Você pode continuar e informar as coordenadas manualmente.",
      );
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId);
      if (localizacaoPendenteRef.current === pendencia) {
        localizacaoPendenteRef.current = null;
      }
      concluirPendencia();
    }
  }, [cancelarLocalizacaoPendente, definirConfirmacaoLocalizacao]);

  const confirmarLocalizacaoSugerida = useCallback(() => {
    if (salvamentoEmCursoRef.current || !localizacaoRequerConfirmacaoRef.current) return;
    definirConfirmacaoLocalizacao(false);
    setLocalizacaoState("success");
    setLocalizacaoHint(
      "Ponto confirmado. Você ainda pode arrastar o pino ou editar as coordenadas antes de salvar.",
    );
  }, [definirConfirmacaoLocalizacao]);

  const buscarCep = useCallback(async (cepBruto, { forcar = false } = {}) => {
    if (salvamentoEmCursoRef.current) return;
    const cep = apenasDigitos(cepBruto ?? formRef.current.cep);
    if (cep.length !== 8) {
      setCepState("error");
      setHint("Digite um CEP com 8 dígitos.");
      return;
    }
    if (cepPendenteRef.current === cep) return;
    if (!forcar && ultimoCepConsultadoRef.current === cep) return;

    const requisicao = ++cepRequestRef.current;
    cepPendenteRef.current = cep;
    setCepState("loading");
    setHint("Buscando endereço e coordenadas de referência...");
    try {
      const d = await fetchJSON(`/api/cep/${cep}`);
      if (
        requisicao !== cepRequestRef.current
        || apenasDigitos(formRef.current.cep) !== cep
      ) return;
      ultimoCepConsultadoRef.current = cep;
      const latitudeCep = Number(d.latitude);
      const longitudeCep = Number(d.longitude);
      const coordenadasRecebidas = (
        d.latitude !== null
        && d.latitude !== ""
        && d.longitude !== null
        && d.longitude !== ""
        && Number.isFinite(latitudeCep)
        && Number.isFinite(longitudeCep)
        && latitudeCep >= -90
        && latitudeCep <= 90
        && longitudeCep >= -180
        && longitudeCep <= 180
        && (latitudeCep !== 0 || longitudeCep !== 0)
      );
      const podeAplicarCoordenadas = coordenadasRecebidas
        && !["manual", "endereco"].includes(origemCoordenadasRef.current);
      if (podeAplicarCoordenadas) {
        origemCoordenadasRef.current = "cep";
        definirConfirmacaoLocalizacao(true);
      }
      const enderecoAtualizado = {
        ...formRef.current,
        cep: formatarCep(d.cep || cep),
      };
      CAMPOS_ENDERECO.forEach((campo) => {
        if (!camposEnderecoEditadosRef.current.has(campo) && d[campo]) {
          enderecoAtualizado[campo] = d[campo];
        }
      });
      if (podeAplicarCoordenadas) {
        enderecoAtualizado.latitude = String(d.latitude);
        enderecoAtualizado.longitude = String(d.longitude);
      }
      formRef.current = enderecoAtualizado;
      setForm((anterior) => {
        if (apenasDigitos(anterior.cep) !== cep) return anterior;
        const proximo = { ...anterior, cep: formatarCep(d.cep || cep) };
        CAMPOS_ENDERECO.forEach((campo) => {
          if (!camposEnderecoEditadosRef.current.has(campo) && d[campo]) {
            proximo[campo] = d[campo];
          }
        });
        if (podeAplicarCoordenadas) {
          proximo.latitude = String(d.latitude);
          proximo.longitude = String(d.longitude);
        }
        formRef.current = proximo;
        return proximo;
      });
      setHint(
        coordenadasRecebidas
          ? "Endereço preenchido pelo ViaCEP; coordenadas de referência do CEP disponíveis. Confirme no mapa ou informe Número/Km para refinar."
          : "Endereço preenchido pelo ViaCEP. Informe Número/Km para tentar localizar o ponto no mapa.",
      );
      setCepState("success");
      if (String(enderecoAtualizado.numero_km || "").trim()) {
        void localizarEndereco(enderecoAtualizado);
      }
    } catch {
      if (requisicao !== cepRequestRef.current) return;
      setHint(
        "Não foi possível consultar o CEP. Você ainda pode preencher os campos manualmente.",
      );
      setCepState("error");
    } finally {
      if (cepPendenteRef.current === cep) cepPendenteRef.current = "";
    }
  }, [definirConfirmacaoLocalizacao, localizarEndereco]);

  useEffect(() => {
    onDirtyChange?.(sujo);
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

  useEffect(() => {
    const cep = apenasDigitos(form.cep);
    if (
      salvando
      || cep.length !== 8
      || ultimoCepConsultadoRef.current === cep
    ) return undefined;
    const timer = window.setTimeout(() => buscarCep(cep), 500);
    return () => window.clearTimeout(timer);
  }, [buscarCep, form.cep, salvando]);

  useEffect(() => {
    montadoRef.current = true;
    return () => {
      montadoRef.current = false;
      salvamentoRequestRef.current += 1;
      cepRequestRef.current += 1;
      localizacaoRequestRef.current += 1;
      cancelarLocalizacaoPendente();
    };
  }, [cancelarLocalizacaoPendente]);

  async function salvar(e) {
    e.preventDefault();
    if (salvamentoEmCursoRef.current) return;
    salvamentoEmCursoRef.current = true;
    const requisicao = ++salvamentoRequestRef.current;
    cepRequestRef.current += 1;
    cepPendenteRef.current = "";
    setSalvando(true);
    try {
      await localizarEndereco(formRef.current);
      if (!montadoRef.current || requisicao !== salvamentoRequestRef.current) return;
      if (localizacaoRequerConfirmacaoRef.current) {
        setLocalizacaoHint(
          "A sugestão é aproximada. Confirme o ponto no mapa antes de salvar a fazenda.",
        );
        showToast("Confirme a localização aproximada no mapa antes de salvar.");
        return;
      }

      const dadosFormulario = formRef.current;
      if (
        !dadosFormulario.nome_fazenda
        || !dadosFormulario.numero_apolice
        || !dadosFormulario.cep
        || !dadosFormulario.cidade
        || !dadosFormulario.uf
      ) {
        showToast("Preencha nome, CEP, cidade, UF e número da apólice.");
        return;
      }
      const area = Number(dadosFormulario.area_ha);
      if (!Number.isFinite(area) || area <= 0) {
        showToast("Informe uma área aproximada positiva.");
        return;
      }
      const erro = validarCoordenadas(
        dadosFormulario.latitude,
        dadosFormulario.longitude,
      );
      if (erro) {
        showToast(erro);
        return;
      }
      const salva = await fetchJSON(
        emEdicao ? `/api/fazendas/${fazenda.id}` : "/api/fazendas",
        {
        method: emEdicao ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(montarPayloadFazenda(dadosFormulario)),
        },
      );
      if (!montadoRef.current || requisicao !== salvamentoRequestRef.current) return;
      await carregarFazendas();
      setSelected(String(salva.id));
      if (Number(salva.latitude) !== 0 || Number(salva.longitude) !== 0) {
        await fetchJSON(`/api/fazendas/${salva.id}/clima/processar`, {
          method: "POST",
        }).catch(() => null);
      }
      showToast(
        emEdicao
          ? `Fazenda "${dadosFormulario.nome_fazenda}" atualizada com sucesso!`
          : `Fazenda "${dadosFormulario.nome_fazenda}" cadastrada com sucesso!`,
      );
      inicialRef.current = JSON.stringify(dadosFormulario);
      onDirtyChange?.(false);
      setPage("clientes", { ignorarFormularioSujo: true });
    } catch (err) {
      if (montadoRef.current && requisicao === salvamentoRequestRef.current) {
        showToast(err.message || "Erro ao salvar. Verifique a API.");
      }
    } finally {
      if (requisicao === salvamentoRequestRef.current) {
        salvamentoEmCursoRef.current = false;
      }
      if (montadoRef.current && requisicao === salvamentoRequestRef.current) {
        setSalvando(false);
      }
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
          <button
            className="btn btn-ghost"
            onClick={() => setPage("clientes")}
            disabled={salvando}
          >
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
          <fieldset disabled={salvando}>
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
          <fieldset disabled={salvando}>
            <legend>
              <span>2</span> Endereço rural
            </legend>
            <p className="section-hint">
              O CEP é usado como apoio ao preenchimento. Revise o endereço antes
              de salvar.
            </p>
            <div className="form-grid">
              <Campo
                label="CEP"
                required
                help={hint}
                helpId="cep-feedback"
                helpLive
              >
                <div className={`input-action state-${cepState}`}>
                  <input
                    required
                    value={form.cep}
                    onChange={(e) => atualizarCep(e.target.value)}
                    placeholder="78890-000"
                    inputMode="numeric"
                    aria-label="CEP"
                    aria-describedby="cep-feedback"
                  />
                  <button
                    type="button"
                    onClick={() => buscarCep(form.cep, { forcar: true })}
                    aria-label="Buscar CEP"
                    disabled={cepState === "loading"}
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
                  onChange={(e) => atualizarCampoEndereco("logradouro", e.target.value)}
                  placeholder="Rodovia Carlos João Strass"
                  aria-label="Logradouro ou rodovia"
                />
              </Campo>
              <Campo label="Número / Km">
                <input
                  value={form.numero_km}
                  onChange={(e) => atualizarCampoEndereco("numero_km", e.target.value)}
                  onBlur={() => localizarEndereco()}
                  placeholder="s/n ou km 14"
                  aria-label="Número ou Km"
                />
              </Campo>
              <Campo label="Bairro / Zona">
                <input
                  value={form.bairro}
                  onChange={(e) => atualizarCampoEndereco("bairro", e.target.value)}
                  placeholder="Zona Rural"
                  aria-label="Bairro ou zona"
                />
              </Campo>
              <Campo label="Complemento">
                <input
                  value={form.complemento}
                  onChange={(e) => atualizarCampoEndereco(
                    "complemento",
                    e.target.value,
                    { afetaLocalizacao: false },
                  )}
                  placeholder="Distrito, campus, setor..."
                  aria-label="Complemento"
                />
              </Campo>
              <Campo label="Cidade" required>
                <input
                  required
                  value={form.cidade}
                  onChange={(e) => atualizarCampoEndereco("cidade", e.target.value)}
                  placeholder="Município"
                  aria-label="Cidade"
                />
              </Campo>
              <Campo label="Estado / UF" required>
                <input
                  required
                  maxLength="2"
                  value={form.uf}
                  onChange={(e) => atualizarCampoEndereco(
                    "uf",
                    e.target.value.toUpperCase(),
                  )}
                  placeholder="MT"
                  aria-label="Estado ou UF"
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
          <fieldset disabled={salvando}>
            <legend>
              <span>3</span> Localização precisa
            </legend>
            <p className="section-hint">
              A plataforma pode sugerir o ponto usando o endereço completo.
              Confirme no mapa, clique para adicionar o pino ou arraste-o para
              ajustar; coordenadas escolhidas manualmente sempre têm prioridade.
            </p>
            <div
              className={`location-lookup state-${localizacaoState}`}
              aria-live="polite"
            >
              <span className="location-lookup-icon">
                <Icon
                  name={localizacaoState === "loading" ? "refresh" : "map"}
                  size={18}
                />
              </span>
              <div>
                <b>Localização automática pelo endereço</b>
                <span>{localizacaoHint}</span>
              </div>
              <div className="location-lookup-actions">
                {localizacaoRequerConfirmacao && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={confirmarLocalizacaoSugerida}
                  >
                    Confirmar este ponto
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => localizarEndereco(undefined, { forcar: true })}
                  disabled={localizacaoState === "loading" || coordenadasManuaisAtivas}
                >
                  {localizacaoState === "loading" ? "Localizando..." : "Localizar pelo endereço"}
                </button>
              </div>
            </div>
            <div className="form-grid">
              <Campo label="Latitude">
                <input
                  type="number"
                  min="-90"
                  max="90"
                  step="any"
                  value={form.latitude}
                  onChange={(e) => atualizarCoordenada("latitude", e.target.value)}
                  placeholder="-12.5450"
                  aria-label="Latitude"
                />
              </Campo>
              <Campo label="Longitude">
                <input
                  type="number"
                  min="-180"
                  max="180"
                  step="any"
                  value={form.longitude}
                  onChange={(e) => atualizarCoordenada("longitude", e.target.value)}
                  placeholder="-55.7210"
                  aria-label="Longitude"
                />
              </Campo>
            </div>
            <LocationPickerMap
              latitude={form.latitude}
              longitude={form.longitude}
              onChange={atualizarCoordenadasPeloMapa}
              onClear={removerPinoMapa}
              disabled={salvando}
            />
          </fieldset>
          <fieldset disabled={salvando}>
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
              disabled={salvando}
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
                A API persiste a fazenda no banco e tenta enriquecer o contexto
                geoespacial.
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
