export const conceitos = {
  score_exposicao: {
    titulo: "Score de Exposição",
    descricao:
      "Índice consolidado de exposição ambiental e territorial de máquinas e equipamentos agrícolas, calculado a partir do peso configurado de cada indicador.",
    uso: "Escala de 0 a 100. Os cinco indicadores participam com um único peso no índice, ajustável na tela Riscos e Score; os pesos ativos somam sempre 100%.",
    interpretacao:
      "No AGRISHIELD-EQUIP, 0–24,99 é Normal; 25–49,99 é Atenção; 50–74,99 é Alerta; e 75–100 é Crítico. A classe facilita triagem, mas o detalhamento dos perigos mostra o motivo da leitura.",
    padrao:
      "As faixas 25/50/75 pertencem à política demonstrativa AGRISHIELD-EQUIP v1.0. Elas são referências uniformes do protótipo, não limites universais de fabricante ou subscrição.",
    acao:
      "Em Atenção, revise o perigo dominante e programe monitoramento. Em Alerta, valide dados e restrinja a atividade exposta quando necessário. Em Crítico, priorize inspeção técnica e decisão operacional formal.",
    avisos: ["Não representa probabilidade atuarial de sinistro."],
  },
  condicao_operacional: {
    titulo: "Condição Operacional Atual",
    descricao:
      "Resumo diário do contexto operacional da fazenda, calculado a partir de chuva, umidade, condição do solo e fatores cadastrais da operação.",
    interpretacao:
      "No dashboard operacional, score abaixo de 35 é Ideal, de 35 a 59 é Atenção e a partir de 60 é Restrição.",
    padrao:
      "Os cortes 35/60 pertencem ao indicador operacional legado do dashboard e são diferentes das faixas 25/50/75 do AGRISHIELD-EQUIP.",
    acao:
      "Ideal: mantenha o planejamento. Atenção: revise chuva recente, rota e condição do terreno. Restrição: reavalie a execução, especialmente em áreas baixas ou com drenagem limitada.",
  },
  distribuicao_condicoes: {
    titulo: "Distribuição de Condições — 30 dias",
    descricao:
      "Quantidade de dias classificados como Ideais, Atenção ou Restrição dentro dos 30 registros mais recentes do indicador operacional.",
    interpretacao:
      "Observe persistência, não apenas o dia atual. Muitos dias em Atenção ou Restrição indicam uma janela operacional menos favorável.",
    padrao:
      "A janela fixa de 30 dias reduz a influência de um único evento e mantém comparabilidade entre propriedades no dashboard.",
    acao:
      "Se Atenção ou Restrição crescerem, compare chuva acumulada, alertas e drenagem antes de definir cronograma, rota ou alocação de máquinas.",
  },
  alertas_ativos: {
    titulo: "Alertas Ativos",
    descricao:
      "Eventos meteorológicos ou operacionais publicados para a propriedade e ordenados para apoiar priorização.",
    interpretacao:
      "A severidade indica urgência relativa; o detalhe informa valor, período ou condição que originou o alerta.",
    acao:
      "Comece pelos alertas de alta severidade, confira a data e valide a condição local antes de alterar uma operação.",
  },
  severidade_alerta: {
    titulo: "Severidade do Alerta",
    descricao:
      "Classificação de prioridade do evento em Alta, Média ou Baixa, conforme as regras publicadas pelo indicador de origem.",
    interpretacao:
      "Alta pede revisão imediata; Média pede acompanhamento e preparação; Baixa funciona como sinal preventivo.",
    acao:
      "Cruze a severidade com data, previsão e vulnerabilidade da atividade. A severidade isolada não substitui vistoria ou decisão técnica.",
  },
  fatores_risco: {
    titulo: "Principais Fatores de Risco",
    descricao:
      "Variáveis que mais acrescentaram pontos à leitura operacional atual, apresentadas em ordem de impacto.",
    interpretacao:
      "O fator no topo explica a maior parte da pressão sobre o score atual; os pontos são contribuição ao indicador, não probabilidade de sinistro.",
    acao:
      "Atue primeiro nos fatores controláveis, como rota, janela de operação e permanência em solo saturado. Valide fatores ambientais com observação local.",
  },
  recomendacoes: {
    titulo: "Recomendações para a Operação",
    descricao:
      "Orientações de triagem derivadas do contexto exibido para ajudar a preparar a análise operacional.",
    interpretacao:
      "Recomendado indica janela preferível; Atenção pede verificação; Contexto aponta uma informação territorial relevante.",
    acao:
      "Use as recomendações como checklist e registre a decisão final com evidências da propriedade, da máquina e da equipe responsável.",
  },
  tendencias: {
    titulo: "Insights e Tendências",
    descricao:
      "Atalhos para comparar a condição atual, a janela recente, a previsão e a completude dos dados territoriais.",
    acao:
      "Abra a análise completa quando houver piora persistente, concentração de eventos ou dados insuficientes para explicar o resultado.",
  },
  cadastro_operacional: {
    titulo: "Cadastro Operacional",
    descricao:
      "Referência cadastral usada para identificar a propriedade, sua apólice, localização, área e tipo de operação.",
    acao:
      "Corrija o cadastro antes de interpretar métricas quando apólice, área, coordenadas ou tipo de operação não corresponderem ao risco analisado.",
  },
  apolice: {
    titulo: "Número da Apólice",
    descricao: "Identificador contratual usado para relacionar a propriedade à cobertura segurada.",
    acao: "Confirme se a apólice exibida corresponde ao equipamento, vigência e propriedade em análise.",
  },
  tipo_operacao: {
    titulo: "Tipo de Operação",
    descricao:
      "Contexto cadastral que distingue atividade em campo de deslocamento/transporte e pode alterar fatores do indicador operacional.",
    acao: "Atualize o cadastro quando o uso predominante mudar, pois a leitura deve refletir a exposição real da máquina.",
  },
  area_fazenda: {
    titulo: "Área da Fazenda",
    descricao: "Área declarada em hectares e usada para contextualizar a propriedade e estimar geometrias territoriais.",
    avisos: ["Não substitui polígono cadastral, matrícula ou levantamento fundiário."],
    acao: "Corrija valores ausentes ou incompatíveis antes de recalcular o contexto territorial.",
  },
  localizacao_fazenda: {
    titulo: "Localização da Fazenda",
    descricao: "Cidade e UF associadas ao cadastro e usadas como referência humana da propriedade.",
    acao: "Confirme a localidade quando a busca retornar propriedades com nomes semelhantes.",
  },
  coordenadas: {
    titulo: "Coordenadas de Referência",
    descricao: "Latitude e longitude do ponto usado nas consultas meteorológicas e geoespaciais.",
    interpretacao: "Quatro casas decimais representam aproximadamente dezenas de metros; a precisão real depende da origem do cadastro.",
    avisos: ["Um ponto não representa os limites completos da propriedade."],
    acao: "Se o ponto estiver fora da área segurada, corrija a origem geográfica e reprocesse os indicadores territoriais.",
  },
  cobertura_territorial: {
    titulo: "Cobertura Territorial",
    descricao: "Indica se SRTM e MERIT Hydro foram processados e persistidos para a coordenada da propriedade.",
    interpretacao: "Pronto significa que o contexto está disponível; pendente ou erro significa que parte da leitura territorial pode ficar indisponível.",
    acao: "Reprocesse após corrigir coordenadas ou configuração do Earth Engine. Não trate ausência de dado como valor zero.",
  },
  proximidade_agua_cadastral: {
    titulo: "Proximidade de Água — Cadastro",
    descricao: "Sinalização declarada no cadastro de que a operação ocorre próxima a rio, córrego, represa ou área sujeita a acúmulo de água.",
    interpretacao: "É um contexto cadastral simples e não equivale à distância raster calculada pelo MERIT Hydro.",
    acao: "Confirme em vistoria e mantenha o cadastro atualizado; use MERIT e observação local para uma leitura territorial mais completa.",
  },
  previsao_meteorologica: {
    titulo: "Previsão Meteorológica",
    descricao: "Estimativa de precipitação e probabilidade para os próximos dias na grade próxima à propriedade.",
    interpretacao: "A previsão apoia planejamento e pode mudar entre atualizações; não é uma observação medida dentro da fazenda.",
    acao: "Em volumes altos ou alta probabilidade, confirme atualizações e prepare alternativas de janela e rota.",
  },
  comparacao_90d: {
    titulo: "Comparação de Exposição — 90 dias",
    descricao: "Compara o score da janela atual de 90 dias com os 90 dias imediatamente anteriores.",
    interpretacao: "Aumento indica maior exposição relativa; redução indica melhora relativa. A diferença não informa sozinha qual perigo mudou.",
    padrao: "Noventa dias equilibram recência e recorrência sazonal na política demonstrativa AGRISHIELD-EQUIP v1.0.",
    acao: "Abra a composição e os detalhes dos perigos para identificar o driver da variação antes de decidir.",
  },
  linha_tempo: {
    titulo: "Linha do Tempo Multirriscos",
    descricao: "Mostra quando eventos relevantes de cada perigo ocorreram na janela móvel de 90 dias.",
    interpretacao: "Blocos longos indicam duração; blocos repetidos indicam recorrência. Espaço vazio não prova ausência absoluta de risco.",
    acao: "Use datas e duração para relacionar eventos à operação, manutenção ou histórico de ocorrências da máquina.",
  },
  qualidade_dados: {
    titulo: "Cobertura e Qualidade dos Dados",
    descricao: "Resume warm-up, dias de contexto, lacunas e ausências que sustentam a publicação do score.",
    interpretacao: "Cobertura abaixo do mínimo de 80% pode tornar uma avaliação inelegível; dados ausentes nunca devem ser interpretados como zero.",
    padrao: "O mínimo de 80% pertence à política AGRISHIELD-EQUIP v1.0 e protege a leitura contra séries excessivamente incompletas.",
    acao: "Se houver lacunas, verifique fonte, período e coordenadas. Evite comparar scores com qualidades de dados muito diferentes.",
  },
  perigo_dominante: {
    titulo: "Perigo Dominante",
    descricao: "Perigo elegível com maior contribuição ponderada para o Score de Exposição na janela atual.",
    interpretacao: "Dominante não significa único risco nem evento ocorrido; significa maior contribuição matemática entre os indicadores publicados.",
    acao: "Priorize o detalhamento desse perigo e depois confira os demais para evitar uma decisão baseada em uma única dimensão.",
  },
  hidrico: {
    titulo: "Exposição Hídrica",
    descricao:
      "Indicador oficial que combina condição meteorológica com suscetibilidade territorial baseada em MERIT Hydro e SRTM.",
    uso: "A mesma agregação de 90 dias alimenta o card, o score e os eventos da linha do tempo.",
    avisos: [
      "Não representa probabilidade de inundação.",
      "Metodologia não calibrada contra sinistros reais.",
    ],
  },
  trafegabilidade: {
    titulo: "Trafegabilidade",
    descricao:
      "Indicador destinado a representar condição desfavorável do terreno para circulação e operação de máquinas agrícolas.",
    uso: "Usa metodologia meteorológica própria — chuva do dia, acúmulo recente e recuperação/secagem — e participa do score com peso configurável. Não compartilha mais o núcleo de cálculo com a Exposição Hídrica.",
    avisos: [
      "Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
    ],
  },
  instabilidade: {
    titulo: "Instabilidade",
    descricao:
      "Indicador de suscetibilidade operacional associada à combinação entre declividade do terreno e ativação por condição hídrica meteorológica interna.",
    uso: "Usa declividade SRTM. A posição topográfica relativa é somente evidência contextual e não participa da fórmula.",
    avisos: [
      "Não identifica escorregamentos, tombamentos ou falhas de terreno efetivamente ocorridos.",
    ],
  },
  incendio: {
    titulo: "Incêndio / Propagação de Fogo",
    descricao:
      "Indicador ambiental associado a condições que podem favorecer ignição ou propagação de fogo.",
    uso: "Utiliza temperatura máxima, umidade relativa média, vento médio diário e dias desde chuva.",
    avisos: [
      "Não detecta foco de incêndio e não representa probabilidade de sinistro.",
    ],
  },
  tempestades: {
    titulo: "Tempestades Severas",
    descricao:
      "Indicador associado à combinação de vento médio e precipitação diária.",
    uso: "Utiliza vento médio da fonte meteorológica atual; granizo, raios e rajadas não participam atualmente.",
    avisos: [
      "Não detecta diretamente ocorrência observada de tempestade severa.",
    ],
  },
  srtm: {
    titulo: "SRTM — Declividade",
    descricao:
      "Declividade média do relevo derivada de dados de elevação SRTM.",
    uso: "Expressa em graus; participa da Instabilidade. A posição topográfica relativa participa da Exposição Hídrica.",
  },
  posicao_topografica: {
    titulo: "SRTM — Posição topográfica relativa",
    descricao:
      "Comparação da elevação do ponto da fazenda com o relevo do entorno.",
    uso: "Participa da suscetibilidade territorial da Exposição Hídrica.",
    avisos: ["Não representa profundidade de inundação."],
  },
  merit_distancia: {
    titulo: "MERIT — Distância à drenagem",
    descricao:
      "Distância do ponto analisado até a drenagem identificada no raster MERIT Hydro.",
    uso: "Representa contexto hidrológico raster e participa da suscetibilidade territorial da Exposição Hídrica.",
    avisos: ["Não é distância exata até um rio cadastral."],
  },
  merit_area: {
    titulo: "MERIT — Área montante",
    descricao:
      "Área de contribuição hidrológica a montante associada à drenagem identificada.",
    uso: "Valores maiores indicam maior área potencialmente contribuinte para a suscetibilidade territorial da Exposição Hídrica.",
    avisos: ["Não equivale a vazão ou risco de inundação."],
  },
  nasa_power: {
    titulo: "NASA POWER",
    descricao:
      "Fonte meteorológica histórica utilizada como padrão atual do dashboard.",
    uso: "Fornece temperatura, precipitação, umidade relativa e vento.",
  },
  open_meteo: {
    titulo: "Open-Meteo",
    descricao: "Fonte meteorológica alternativa já suportada pelo projeto.",
    uso: "Pode ser usada alternativamente à NASA POWER, sem mistura de fontes na mesma execução. Quando não está ativa, aparece como disponível.",
    avisos: ["Diferenças de fonte podem produzir valores diferentes."],
  },
  mapbiomas: {
    titulo: "MapBiomas",
    descricao: "Fonte de uso e cobertura do solo integrada ao projeto.",
    uso: "Disponível como contexto territorial; não participa matematicamente do score oficial.",
  },
  inmet: {
    titulo: "INMET",
    descricao:
      "Fonte meteorológica oficial brasileira prevista e integrada ao ecossistema do projeto.",
    uso: "Não participa do score oficial e poderá apoiar alertas e validação complementar no futuro.",
  },
  peso_indice: {
    titulo: "Peso no índice",
    descricao: "Peso único configurado para o indicador no Score de Exposição.",
    uso: "Ajustável pelo Analista Sompo na tela Riscos e Score. Os pesos dos indicadores ativos somam sempre 100%, sem redistribuição automática.",
  },
  contribuicao: {
    titulo: "Contribuição oficial",
    descricao:
      "Parcela do Score de Exposição produzida pelo perigo após aplicação do peso no índice.",
    uso: "Conceitualmente: índice multiplicado pelo peso no índice.",
  },
  cobertura: {
    titulo: "Cobertura",
    descricao:
      "Percentual de dias da janela histórica com dados suficientes para cálculo.",
    uso: "Dados ausentes não viram zero; cobertura insuficiente pode invalidar a avaliação. O threshold de elegibilidade vem do backend.",
  },
};

export function conceitoDaFonte(fonte) {
  return (
    {
      NASA_POWER: "nasa_power",
      OPEN_METEO: "open_meteo",
      MAPBIOMAS: "mapbiomas",
      INMET: "inmet",
      SRTM: "srtm",
      MERIT_HYDRO: "merit_distancia",
    }[fonte] || null
  );
}
export function conceitoDoPerigo(perigo) {
  return {
    EXPOSICAO_HIDRICA: "hidrico",
    TRAFEGABILIDADE: "trafegabilidade",
    INSTABILIDADE: "instabilidade",
    INCENDIO: "incendio",
    TEMPESTADES: "tempestades",
  }[perigo];
}
