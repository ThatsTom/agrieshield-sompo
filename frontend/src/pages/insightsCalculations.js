const ORDEM_PRIORIDADE = {
  imediata: 0,
  hoje: 1,
  proximos_dias: 2,
  monitorar: 3,
};

function numeroFinito(valor) {
  if (valor === null || valor === undefined || valor === "") return null;
  const numero = Number(valor);
  return Number.isFinite(numero) ? numero : null;
}

function plural(total, singular, pluralizado) {
  return `${total} ${total === 1 ? singular : pluralizado}`;
}

export function avaliarDiaPrevisao(dia = {}) {
  const chuva = numeroFinito(dia.precipitacao_mm);
  const probabilidade = numeroFinito(dia.prob_precip_pct);
  const temperatura = numeroFinito(dia.temp_max_c);
  const motivos = [];

  if (chuva === null && probabilidade === null && temperatura === null) {
    return {
      status: "indisponivel",
      rotulo: "Dados incompletos",
      motivos: ["Sem variáveis suficientes para classificar o dia."],
    };
  }

  if (chuva !== null && chuva >= 20) motivos.push(`${chuva.toFixed(1)} mm previstos`);
  if (probabilidade !== null && probabilidade >= 70) motivos.push(`${Math.round(probabilidade)}% de probabilidade de chuva`);
  if (motivos.length) {
    return { status: "restricao", rotulo: "Chuva relevante", motivos };
  }

  if (chuva !== null && chuva >= 5) motivos.push(`${chuva.toFixed(1)} mm previstos`);
  if (probabilidade !== null && probabilidade >= 40) motivos.push(`${Math.round(probabilidade)}% de probabilidade de chuva`);
  if (temperatura !== null && temperatura >= 35) motivos.push(`máxima de ${temperatura.toFixed(1)}°C`);
  if ([chuva, probabilidade, temperatura].some((valor) => valor === null)) {
    motivos.push("leitura climática parcial");
  }
  if (motivos.length) {
    return { status: "atencao", rotulo: "Atenção climática", motivos };
  }

  return {
    status: "menor_sinal_chuva",
    rotulo: "Menor sinal de chuva",
    motivos: ["Chuva e probabilidade abaixo dos limiares de atenção da plataforma."],
  };
}

export function resumirJanelaOperacional(dias = []) {
  const avaliados = dias.map((dia) => ({
    ...dia,
    avaliacao_operacional: avaliarDiaPrevisao(dia),
  }));
  const contagem = {
    menor_sinal_chuva: 0,
    atencao: 0,
    restricao: 0,
    indisponivel: 0,
  };
  let atual = [];
  let melhor = [];
  avaliados.forEach((dia) => {
    const status = dia.avaliacao_operacional.status;
    contagem[status] += 1;
    if (status === "menor_sinal_chuva") {
      atual.push(dia.data);
      if (atual.length > melhor.length) melhor = [...atual];
    } else {
      atual = [];
    }
  });
  return {
    dias: avaliados,
    contagem,
    melhor_sequencia: melhor.length
      ? { inicio: melhor[0], fim: melhor[melhor.length - 1], total_dias: melhor.length }
      : null,
  };
}

export function calcularQualidadeDados({ dashboard, fazenda }) {
  const resumoFrota = dashboard?.maquinarios_resumo;
  const camposCadastro = [
    [fazenda?.nome_fazenda, "nome"],
    [fazenda?.cidade, "cidade"],
    [fazenda?.uf, "UF"],
    [numeroFinito(fazenda?.area_ha), "área"],
    [fazenda?.tipo_operacao, "tipo de operação"],
  ];
  const pendenciasCadastro = camposCadastro
    .filter(([valor]) => valor === null || valor === undefined || valor === "")
    .map(([, rotulo]) => rotulo);
  const contextoPronto = String(fazenda?.status_geoespacial || "").toUpperCase() === "SUCESSO";
  const scorePronto = numeroFinito(dashboard?.score?.score) !== null;
  const diasClima = dashboard?.previsao_7d || [];
  const climaPronto = dashboard?.origem_previsao === "api_open_meteo"
    && diasClima.length === 7
    && diasClima.every((dia) => [
      dia?.precipitacao_mm,
      dia?.prob_precip_pct,
      dia?.temp_max_c,
    ].every((valor) => numeroFinito(valor) !== null));
  const frotaDisponivel = resumoFrota?.disponivel !== false;
  const frotaCadastrada = frotaDisponivel && Number(resumoFrota?.total || 0) > 0;
  const totalFrota = Number(resumoFrota?.total || 0);
  const seguroCoerente = frotaCadastrada
    && Number(resumoFrota?.segurados || 0) + Number(resumoFrota?.sem_seguro || 0) === totalFrota;

  const itens = [
    {
      id: "cadastro",
      nome: "Cadastro da fazenda",
      status: pendenciasCadastro.length ? "atencao" : "ok",
      detalhe: pendenciasCadastro.length
        ? `Completar: ${pendenciasCadastro.join(", ")}.`
        : "Identificação, localização, área e operação informadas.",
    },
    {
      id: "territorial",
      nome: "Contexto territorial",
      status: contextoPronto ? "ok" : "atencao",
      detalhe: contextoPronto ? "Leitura geoespacial disponível." : "Processamento territorial pendente ou indisponível.",
    },
    {
      id: "score",
      nome: "Leitura calculada",
      status: scorePronto ? "ok" : "atencao",
      detalhe: scorePronto ? "Score e fatores publicados." : "Score ainda não disponível.",
    },
    {
      id: "clima",
      nome: "Previsão meteorológica",
      status: climaPronto ? "ok" : "atencao",
      detalhe: climaPronto ? "Sete dias completos recebidos do Open-Meteo." : "Previsão oficial incompleta ou indisponível.",
    },
    {
      id: "frota",
      nome: "Inventário de maquinários",
      status: frotaCadastrada ? "ok" : "atencao",
      detalhe: frotaCadastrada
        ? `${plural(totalFrota, "equipamento cadastrado", "equipamentos cadastrados")}.`
        : frotaDisponivel ? "Nenhum equipamento cadastrado." : "Inventário temporariamente indisponível.",
    },
    {
      id: "seguro",
      nome: "Situação cadastral do seguro",
      status: seguroCoerente ? "ok" : "atencao",
      detalhe: seguroCoerente ? "Todos os equipamentos têm situação informada." : "A leitura depende de uma frota cadastrada e consistente.",
    },
  ];
  const completos = itens.filter((item) => item.status === "ok").length;
  const percentual = Math.round((completos / itens.length) * 100);
  return {
    percentual,
    nivel: percentual >= 85 ? "alta" : percentual >= 60 ? "intermediaria" : "parcial",
    itens,
    completos,
    total: itens.length,
  };
}

export function construirRadarOperacional({ dashboard, qualidade }) {
  if (!dashboard) return [];
  const itens = [];
  const frota = dashboard.maquinarios_resumo || {};
  const janela = resumirJanelaOperacional(dashboard.previsao_7d || []);
  const vencidos = Number(frota.seguros_vencidos || 0);
  const semSeguro = Number(frota.sem_seguro || 0);
  const vencendo = Number(frota.vencendo_90_dias || 0);

  if (vencidos || semSeguro || vencendo) {
    const evidencias = [];
    if (vencidos) evidencias.push(plural(vencidos, "seguro cadastrado vencido", "seguros cadastrados vencidos"));
    if (semSeguro) evidencias.push(plural(semSeguro, "equipamento sem seguro cadastrado", "equipamentos sem seguro cadastrado"));
    if (vencendo) evidencias.push(plural(vencendo, "vencimento em até 90 dias", "vencimentos em até 90 dias"));
    itens.push({
      id: "seguro",
      prioridade: vencidos ? "imediata" : "proximos_dias",
      titulo: vencidos ? "Conferir seguros cadastrados vencidos" : "Revisar a proteção cadastral da frota",
      evidencia: evidencias.join(" · "),
      acao: "Confirmar vigência, vínculo e condições diretamente nas apólices antes de orientar o segurado.",
      natureza: "indicador_calculado",
    });
  }

  const alertaPrincipal = (dashboard.alertas || []).find((alerta) => alerta?.severidade === "Alta")
    || (dashboard.alertas || [])[0];
  if (alertaPrincipal || janela.contagem.restricao > 0) {
    itens.push({
      id: "clima",
      prioridade: alertaPrincipal?.severidade === "Alta" ? "hoje" : "proximos_dias",
      titulo: "Validar o planejamento diante das condições",
      evidencia: alertaPrincipal
        ? `${alertaPrincipal.tipo}: ${alertaPrincipal.detalhe}`
        : plural(janela.contagem.restricao, "dia com chuva relevante", "dias com chuva relevante"),
      acao: "Conferir origem e período do alerta, condições locais, acesso e agenda operacional antes de orientar a atividade.",
      natureza: "indicador_calculado",
    });
  }

  const condicao = String(dashboard?.score?.condicao_atual || "");
  const fator = (dashboard?.score?.fatores_risco || [])[0];
  if (/aten|restr|cr[ií]t|alert/i.test(condicao)) {
    itens.push({
      id: "score",
      prioridade: /restr|cr[ií]t|alert/i.test(condicao) ? "hoje" : "proximos_dias",
      titulo: "Revisar os fatores da leitura atual",
      evidencia: `${condicao}${fator?.fator ? ` · principal fator: ${fator.fator}` : ""}`,
      acao: "Usar os fatores publicados como roteiro de validação, sem interpretar o score como probabilidade de sinistro.",
      natureza: "indicador_calculado",
    });
  }

  if (!Number(frota.total || 0) && frota.disponivel !== false) {
    itens.push({
      id: "frota",
      prioridade: "monitorar",
      titulo: "Completar o inventário de maquinários",
      evidencia: "Nenhum equipamento cadastrado para a fazenda.",
      acao: "Cadastrar a frota para habilitar leituras de composição, uso declarado e situação de seguro.",
      natureza: "recomendacao_validacao",
    });
  }

  if (qualidade?.percentual < 85) {
    const pendentes = qualidade.itens.filter((item) => item.status !== "ok").map((item) => item.nome);
    itens.push({
      id: "qualidade",
      prioridade: "monitorar",
      titulo: "Completar as fontes desta leitura",
      evidencia: `${qualidade.percentual}% das fontes de informação disponíveis · pendências: ${pendentes.join(", ")}`,
      acao: "Atualizar os cadastros pendentes antes de transformar os indicadores em orientação definitiva.",
      natureza: "recomendacao_validacao",
    });
  }

  if (!itens.length) {
    itens.push({
      id: "monitoramento",
      prioridade: "monitorar",
      titulo: "Manter o acompanhamento dos indicadores",
      evidencia: "Nenhum sinal prioritário foi calculado com as informações disponíveis.",
      acao: "Revisar a previsão e os dados cadastrais periodicamente.",
      natureza: "indicador_calculado",
    });
  }

  return itens
    .sort((a, b) => ORDEM_PRIORIDADE[a.prioridade] - ORDEM_PRIORIDADE[b.prioridade])
    .slice(0, 3);
}

function mediana(valores) {
  const ordenados = valores.filter(Number.isFinite).sort((a, b) => a - b);
  if (!ordenados.length) return null;
  const meio = Math.floor(ordenados.length / 2);
  return ordenados.length % 2
    ? ordenados[meio]
    : (ordenados[meio - 1] + ordenados[meio]) / 2;
}

export function calcularComparativoPortfolio({
  fazendas = [],
  fazenda,
  totalFrota = 0,
  frotaDisponivel = true,
}) {
  const operacao = fazenda?.tipo_operacao;
  const comparaveis = fazendas.filter((item) => !operacao || item.tipo_operacao === operacao);
  const areas = comparaveis.map((item) => numeroFinito(item.area_ha)).filter(Number.isFinite);
  const idSelecionado = String(fazenda?.id ?? fazenda?.id_fazenda ?? "");
  const frotas = comparaveis
    .map((item) => {
      const idItem = String(item?.id ?? item?.id_fazenda ?? "");
      if (idItem === idSelecionado) {
        return frotaDisponivel ? numeroFinito(totalFrota) : null;
      }
      if (item.total_maquinarios_disponivel === false) return null;
      return numeroFinito(item.total_maquinarios);
    })
    .filter(Number.isFinite);
  const contextosProntos = comparaveis.filter(
    (item) => String(item.status_geoespacial || "").toUpperCase() === "SUCESSO",
  ).length;
  return {
    suficiente: comparaveis.length >= 2,
    base: comparaveis.length,
    operacao,
    area_fazenda_ha: numeroFinito(fazenda?.area_ha),
    area_mediana_ha: mediana(areas),
    frota_fazenda: frotaDisponivel ? Number(totalFrota || 0) : null,
    frota_mediana: mediana(frotas),
    frota_base: frotas.length,
    cobertura_territorial_pct: comparaveis.length
      ? Math.round((contextosProntos / comparaveis.length) * 100)
      : 0,
  };
}
