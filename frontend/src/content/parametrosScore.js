export const explicacoesParametrosScore = {
  EXPOSICAO_HIDRICA: {
    titulo: "Como interpretar a composição interna",
    itens: [
      [
        "Proximidade da drenagem",
        "Representa a proximidade da fazenda em relação à rede de drenagem mapeada. Quanto menor a distância até rios, córregos ou canais de drenagem, maior tende a ser a suscetibilidade territorial associada à presença e concentração de água.",
      ],
      [
        "Relevância da área montante",
        "Representa a dimensão da área que contribui com escoamento para a drenagem próxima ao local analisado. Áreas montantes maiores podem indicar maior capacidade de concentração de fluxo hídrico naquele contexto territorial.",
      ],
      [
        "Posição topográfica relativa",
        "Compara a elevação do ponto analisado com a elevação média da região ao redor. Pontos relativamente mais baixos que o entorno tendem a apresentar maior suscetibilidade ao acúmulo ou concentração de água.",
      ],
    ],
    comoAtua:
      "Os três componentes formam a Suscetibilidade Territorial utilizada na Exposição Hídrica. Os pesos definem a importância relativa de cada componente e devem totalizar 100%.",
  },
  INSTABILIDADE: {
    titulo: "Como interpretar os fatores de ativação",
    introducao:
      "A Instabilidade combina a suscetibilidade do terreno, determinada principalmente pela declividade, com a condição hídrica meteorológica do período.",
    itens: [
      [
        "Normal",
        "Sem ativação da suscetibilidade topográfica nas condições hídricas mais baixas.",
      ],
      ["Atenção", "Inicia uma ativação parcial da suscetibilidade do terreno."],
      [
        "Alerta",
        "Aumenta a influência da suscetibilidade topográfica diante de condições hídricas mais relevantes.",
      ],
      [
        "Crítico",
        "Aplica integralmente a suscetibilidade topográfica calculada.",
      ],
    ],
    comoAtua:
      "Os valores são fatores de ativação, e não percentuais do score. Quanto maior o fator, maior a influência da suscetibilidade do terreno no índice de Instabilidade.",
  },
  INCENDIO: {
    titulo: "Como interpretar os multiplicadores de secura",
    introducao:
      "O índice considera conjuntamente condições de temperatura, baixa umidade e vento. O período sem precipitação atua como um modificador adicional dessas condições.",
    itens: [
      [
        "0–1 dia sem chuva",
        "Representa uma condição recente ainda pouco influenciada pela ausência de precipitação.",
      ],
      [
        "2–3 dias sem chuva",
        "Mantém a condição ambiental calculada sem aumento adicional.",
      ],
      [
        "4–6 dias sem chuva",
        "Eleva moderadamente a condição favorável à propagação do fogo.",
      ],
      [
        "7 ou mais dias sem chuva",
        "Aplica o maior multiplicador de secura previsto na configuração atual.",
      ],
    ],
    comoAtua:
      "Os valores são multiplicadores aplicados ao índice ambiental de fogo. Valores acima de 1,00 aumentam o índice; abaixo de 1,00, reduzem seu efeito.",
  },
  TEMPESTADES: {
    titulo: "Como interpretar o fator vento–chuva",
    introducao:
      "O índice de Tempestades Severas utiliza o vento como componente principal e a precipitação como elemento de modulação da condição observada.",
    itens: [
      [
        "Base do fator vento–chuva",
        "Determina quanto do índice associado ao vento é preservado mesmo quando o componente de precipitação é baixo ou inexistente.",
      ],
      [
        "Influência da chuva",
        "Define quanto a precipitação pode complementar o fator aplicado ao índice de vento.",
      ],
    ],
    formula: "Fator = Base + Influência da chuva × Componente de chuva",
    comoAtua:
      "Os dois parâmetros devem somar 1,00. Eles não representam simplesmente peso do vento e peso da chuva, pois a precipitação atua como moduladora do índice de vento.",
  },
  TRAFEGABILIDADE: {
    titulo: "Como interpretar a composição interna",
    itens: [
      [
        "Condição do dia atual",
        "Representa o impacto da precipitação observada no próprio dia sobre as condições operacionais para circulação de máquinas.",
      ],
      [
        "Acúmulo recente",
        "Representa a precipitação acumulada nos últimos dias. Esse componente possui maior peso porque a persistência da chuva tende a afetar as condições do terreno mesmo quando a precipitação do dia atual é moderada.",
      ],
      [
        "Recuperação / secagem",
        "Representa a permanência do efeito da chuva recente e sua redução gradual durante períodos sem precipitação. À medida que aumentam os dias secos, esse componente perde influência.",
      ],
      [
        "Limiar de dia relevante",
        "Define a partir de qual valor diário a condição de Trafegabilidade passa a participar da identificação de eventos na agregação histórica de 90 dias. O valor padrão é 25.",
      ],
    ],
    comoAtua:
      "Os três pesos da composição interna devem totalizar 100%. A curva meteorológica utilizada para transformar a precipitação em condição de Trafegabilidade permanece fixa e não é configurável nesta tela.",
    aviso:
      "Metodologia experimental, ainda não calibrada contra sinistros ou dados reais de operação de máquinas.",
  },
};
