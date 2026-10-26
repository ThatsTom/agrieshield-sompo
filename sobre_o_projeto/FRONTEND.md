# Frontend do AgriShield

Este documento descreve a interface implementada no repositório: como ela é organizada, como o usuário navega, quais dados são consultados e como os resultados são apresentados. A referência é o código atual, revisado em **26 de outubro de 2026**. O [README principal](../README.md) apresenta a visão geral e as instruções integradas do projeto; [Insights e LLM](INSIGHTS_E_LLM.md) detalha o contexto e a geração da análise assistida no servidor.

## 1. Responsabilidade da interface

O frontend organiza o trabalho de análise de propriedades rurais e de sua frota. Ele permite cadastrar fazendas e apólices, localizar a sede no mapa, acompanhar processamentos, consultar contexto territorial, interpretar indicadores de exposição, administrar os parâmetros disponíveis e apresentar um briefing gerado por IA.

O navegador não executa o motor de exposição nem acessa diretamente as tabelas do projeto. Essas operações passam pela API. O Supabase é usado diretamente no frontend para autenticação; o cadastro de fazendas, o inventário, o perfil profissional e os indicadores de negócio são consultados pela API autenticada.

A tela de Insights reúne duas camadas distintas: indicadores calculados por regras locais de apresentação e uma análise textual produzida no backend com apoio de LLM. Essa distinção é importante para compreender a origem de cada recomendação.

## 2. Tecnologias e organização

As versões declaradas em [package.json](../frontend/package.json) são:

| Tecnologia | Versão declarada | Uso |
| --- | --- | --- |
| React e React DOM | `18.3.1` | Componentes, formulários e estado da interface |
| Vite | `5.4.10` | Desenvolvimento e build estático |
| Plugin React do Vite | `4.3.3` | Integração JSX e React |
| Leaflet | `^1.9.4` | Mapa de localização e mapa territorial |
| Supabase JS | `2.117.1` | OTP por e-mail, sessão e token de acesso |
| Vitest | `^2.1.9` | Testes automatizados |
| Testing Library React | `^16.1.0` | Verificação de comportamento dos componentes |
| jsdom | `^25.0.1` | Ambiente DOM para os testes |

Os arquivos de interface são predominantemente JavaScript e JSX. Os contratos de exposição e parâmetros possuem arquivos TypeScript específicos; o projeto não deve ser descrito como uma aplicação integralmente em TypeScript. A estilização é feita em [styles.css](../frontend/src/styles.css), com regras responsivas e de impressão.

```text
frontend/
├── index.html                 # Página de entrada
├── package.json               # Scripts e dependências
├── vite.config.js             # Vite e ambiente de testes
└── src/
    ├── main.jsx               # Montagem React e autenticação
    ├── App.jsx                # Navegação e estado compartilhado
    ├── styles.css             # Estilo global e adaptações de tela
    ├── auth/                  # Entrada, sessão e bloqueio por acesso
    ├── api/                   # Cliente HTTP e contratos por domínio
    ├── cadastro/              # Payload, validações e estados territoriais
    ├── components/            # Mapas, exposição, score e ajuda conceitual
    ├── content/               # Explicações de conceitos e parâmetros
    ├── layout/                # Menu, cabeçalho e ícones
    ├── pages/                 # Telas da aplicação
    ├── types/                 # Tipos de exposição e parâmetros
    ├── test/                  # Fixtures de testes
    ├── utils/                 # Formatação
    └── demoData.js            # Dados de fallback da interface
```

## 3. Inicialização, navegação e estado

[main.jsx](../frontend/src/main.jsx) monta `AuthProvider` e `AuthGate` dentro de `React.StrictMode`. Depois da validação do acesso, [App.jsx](../frontend/src/App.jsx) passa a controlar a página visível e os dados compartilhados.

O fluxo inicial é:

1. Validar a configuração do Supabase e recuperar a sessão.
2. Consultar `/api/auth/me` para obter o perfil e o estado de aprovação.
3. Renderizar a aplicação somente para perfil com `status_acesso = aprovado`.
4. Carregar `/api/fazendas?incluir_arquivadas=true`.
5. Manter o portfólio completo para a gestão cadastral e separar as fazendas ativas para o monitoramento.
6. Selecionar uma propriedade ativa e consultar `/api/fazendas/{id}/dashboard`.
7. Compartilhar a fazenda e o dashboard selecionados com as telas que precisam desses dados.

A navegação usa a variável React `page`. Não há React Router ou rotas de URL individuais para cada tela: clicar em Insights ou Operações muda o componente renderizado dentro da aplicação. Recarregar o navegador reinicia essa navegação na Visão Geral. As âncoras da análise de exposição servem para rolar até seções da mesma página.

O estado compartilhado guarda o cadastro das fazendas, o portfólio incluindo arquivadas, a propriedade selecionada, o dashboard, os scores já carregados, os avisos e os formulários em edição. Requisições antigas de dashboard são descartadas quando uma consulta mais recente passa a ser a válida, evitando associar uma resposta atrasada à propriedade selecionada depois.

Ao sair de um cadastro de fazenda ou de maquinário com dados alterados, o aplicativo pede confirmação para evitar perda do formulário. O cadastro de fazenda também registra o evento de saída/recarregamento do navegador. Após a navegação, o conteúdo principal recebe foco e a página volta ao início.

### Busca de propriedades

[FazendaSearch.jsx](../frontend/src/components/FazendaSearch.jsx) é reutilizado em Visão Geral, Operações, Alertas, Insights e Dados e Fontes. Ele permite buscar por nome, apólice principal, ID, CEP, cidade, UF e tipo de operação, ignorando acentos e diferenças de maiúsculas. Também filtra por operação, UF e disponibilidade do contexto territorial.

A busca ordena os resultados por correspondência e mostra até 12 opções. `Enter` seleciona o primeiro resultado e `Escape` fecha a lista. A tabela de Clientes e Apólices possui busca e filtros próprios, incluindo as apólices adicionais.

### Responsividade e acessibilidade

O [menu lateral](../frontend/src/layout/Sidebar.jsx) possui versão para desktop e um painel móvel acionado pelo botão de menu. O painel móvel controla o foco, fecha por `Escape` e devolve o foco ao botão de abertura. Há link para pular ao conteúdo, rótulos nos controles, estados de carregamento e erro anunciáveis, tabelas e regiões com rolagem apropriada.

O CSS inclui adaptações para diferentes larguras, impressão e preferência por movimento reduzido. Esses recursos são implementados no código; não equivalem a uma certificação formal de acessibilidade.

## 4. Autenticação, perfil e autorização

A autenticação usa **OTP por e-mail**, sem campo de senha no fluxo atual. [AuthPage.jsx](../frontend/src/auth/AuthPage.jsx) oferece entrada e criação de conta. No cadastro, o usuário informa nome completo, função e e-mail. Na entrada, solicita o código e confirma os seis dígitos recebidos.

O envio usa `signInWithOtp`; a verificação do código usa `verifyOtp`. O primeiro envio do cadastro apresenta uma etapa de confirmação de e-mail. O frontend impõe intervalo de 60 segundos para novo envio e apresenta uma espera de até uma hora quando o provedor informa limite temporário de envio. O limite efetivo continua dependendo da configuração do serviço de autenticação.

A sessão do Supabase é persistida com a chave `agrishield-auth-session`, com renovação automática e detecção de sessão no retorno por URL. O cliente HTTP acrescenta `Authorization: Bearer <token>` às requisições para a API. A resposta `401` dispara um evento local que encerra a sessão e pede nova entrada.

[AuthGate.jsx](../frontend/src/auth/AuthGate.jsx) distingue os seguintes estados:

| Estado | Comportamento |
| --- | --- |
| Variáveis públicas do Supabase ausentes | Exibe “Autenticação não configurada” |
| Sessão em validação | Exibe carregamento |
| Sem sessão | Exibe entrada/criação de conta |
| Falha ao recuperar o perfil | Exibe erro, nova tentativa e saída |
| Perfil pendente ou rejeitado | Exibe a situação do acesso, sem abrir a aplicação |
| Perfil aprovado | Abre as telas de negócio |
| Perfil aprovado e papel `administrador` | Acrescenta Gerenciar Acessos ao menu |

[AuthProvider.jsx](../frontend/src/auth/AuthProvider.jsx) encerra a sessão após **15 minutos sem atividade**. Os eventos de ponteiro, teclado, rolagem e toque atualizam a atividade. O registro por usuário em `localStorage` permite compartilhar atividade entre abas. O encerramento usa saída local do Supabase.

**Meu Perfil** permite alterar nome completo, função e telefone via `PUT /api/auth/perfil`; o e-mail confirmado é exibido somente para consulta. **Gerenciar Acessos** lista e filtra contas e permite aprovar, devolver ao estado pendente ou rejeitar, exigindo motivo na rejeição. A autorização efetiva dessas operações deve ser conferida pela API; esconder um botão não é uma barreira de segurança suficiente.

## 5. Telas e funcionalidades

| Tela | Finalidade e recursos implementados |
| --- | --- |
| Visão Geral | Fazenda selecionada, condição operacional, score, distribuição de 30 dias, alertas, fatores e atalhos |
| Operações | Cadastro operacional, SRTM, MERIT Hydro, mapa de análise e painel AGRISHIELD-EQUIP |
| Riscos e Score | Explicação dos perigos, pesos, coeficientes, restauração de padrões e persistência dos parâmetros |
| Alertas | Eventos da propriedade, contagens por severidade e apoio da previsão disponível |
| Insights | Briefing por IA, radar determinístico, previsão de 7 dias, frota, cobertura de dados e contexto do portfólio |
| Clientes e Apólices | Portfólio, filtros, cadastro/edição, arquivamento/restauração, processamentos, frota e PDF por apólice |
| Cadastro de Fazenda | Identificação, apólices adicionais, área, operação, endereço, sede no mapa e polígono opcional |
| Maquinário agrícola | Frota da fazenda, cadastro individual e importação validada por CSV |
| Relatórios | Visão cadastral do portfólio e impressão pelo navegador |
| Dados e Fontes | Registros cadastrais, indicadores territoriais, versões e parâmetros vigentes |
| Configurações | URL da API, indicação de conexão/demo e atalhos para modelo, fontes e relatórios |
| Meu Perfil | Dados profissionais e informações da sessão |
| Gerenciar Acessos | Administração das contas, exclusiva do administrador |

### 5.1 Visão Geral e Alertas

A [Visão Geral](../frontend/src/pages/DashboardPage.jsx) usa o objeto de dashboard retornado pela API. Ela mostra a condição atual da fazenda, o score, a origem dos dados, a data de referência, o gráfico de distribuição das condições em 30 dias, até três alertas e os principais fatores de risco.

O botão **Atualizar leitura** consulta novamente o dashboard da propriedade. Isso é uma atualização da leitura publicada pela API; não é o mesmo comando que iniciar a aquisição/processamento do histórico climático em Clientes e Apólices.

Os cartões de recomendações e tendências da Visão Geral contêm orientações e atalhos definidos na interface. O briefing personalizado da LLM é apresentado na tela de Insights. É incorreto atribuir todos os textos da Visão Geral a uma geração de IA.

[AlertasPage.jsx](../frontend/src/pages/AlertasPage.jsx) expande a lista de eventos do dashboard, com tipo, detalhe, severidade e período. A disponibilidade dos alertas acompanha os dados publicados para a propriedade selecionada.

### 5.2 Clientes, apólices e processamento

[ClientesPage.jsx](../frontend/src/pages/ClientesPage.jsx) reúne o portfólio em tabela. A busca considera nome, apólices, ID, CEP, cidade e UF. Os filtros incluem operação, estado, contexto territorial pronto/pendente, proximidade de água, condição calculada e registros ativos/arquivados. A ordenação pode usar nome, cidade ou score.

Cada fazenda pode possuir mais de uma apólice. O relatório individual é solicitado por apólice à API e baixado como PDF autenticado. O arquivamento preserva o registro e o histórico; a restauração o devolve ao portfólio ativo. Fazendas arquivadas continuam disponíveis para consulta na gestão e possuem inventário de maquinário em modo de leitura.

A tela permite iniciar o processamento climático em segundo plano, acompanhar o estado do trabalho e atualizar a lista ao concluir. Durante o acompanhamento, o cliente consulta o estado em intervalos de aproximadamente um segundo, por até 300 tentativas. Também verifica trabalhos já em andamento ao abrir a tela. Quando permitido pelo estado territorial, oferece recalcular o contexto geoespacial.

### 5.3 Cadastro, endereço, mapa e polígono

[CadastroPage.jsx](../frontend/src/pages/CadastroPage.jsx) é usado tanto para uma nova fazenda quanto para editar um cadastro existente. Os dados incluem nome, área, apólice principal e adicionais, tipo de operação, proximidade de água, CEP, logradouro, número/km, bairro, complemento, cidade, UF, referência e coordenadas da sede.

O preenchimento segue esta lógica:

1. O CEP de oito dígitos dispara uma consulta de apoio após cerca de 500 ms sem alteração.
2. A API fornece os dados de endereço e, quando disponíveis, coordenadas aproximadas de referência do CEP.
3. Ao completar CEP, logradouro, número/km, cidade e UF, o frontend solicita a geocodificação do endereço completo pela API, com referência a OpenStreetMap/Nominatim.
4. Sugestões de precisão limitada são identificadas e exigem confirmação do ponto antes de salvar.
5. O usuário pode clicar/tocar no mapa, arrastar o pino, fixá-lo no centro do mapa ou preencher latitude e longitude manualmente.
6. A escolha manual passa a ser preservada nas consultas automáticas seguintes.

O mapa de localização usa Leaflet e tiles do OpenStreetMap. Para navegação por teclado, é possível mover o mapa com as setas e usar **Fixar pino no centro**; os campos de coordenadas são uma alternativa ao mapa.

Consultas de endereço usam cancelamento, identificação da requisição atual e limite de 15 segundos. Alterações de CEP/endereço invalidam respostas antigas. Se o serviço falhar, a interface informa o problema e mantém a possibilidade de preenchimento manual. Um resultado aproximado não é apresentado como a posição confirmada da sede.

As validações do frontend em [fazenda.js](../frontend/src/cadastro/fazenda.js) exigem coordenadas em par quando informadas, latitude entre −90 e 90, longitude entre −180 e 180 e rejeitam o par `0,0`. É permitido enviar o cadastro sem coordenadas quando ambos os campos estão vazios; isso pode deixar o contexto dependente de localização posterior. A área deve ser positiva, e nome, apólice, CEP, cidade e UF são verificados antes do envio.

O polígono é opcional e informado como um vértice `latitude, longitude` por linha, com no mínimo três vértices. O payload converte os pontos para `[longitude, latitude]`. A prévia ajuda a conferir o desenho; não é um editor cartográfico de perímetro completo.

Depois de salvar, o aplicativo recarrega o portfólio, seleciona a fazenda e tenta iniciar o processamento climático se houver localização utilizável. A fazenda salva continua válida mesmo quando a tentativa complementar de iniciar o clima falha.

### 5.4 Operações, território e exposição

[OperacoesPage.jsx](../frontend/src/pages/OperacoesPage.jsx) combina cadastro, indicadores territoriais e exposição. Os dados geoespaciais exibidos incluem declividade média, posição topográfica relativa, distância à drenagem e área de drenagem a montante.

[GeoAnalysisMap.jsx](../frontend/src/components/GeoAnalysisMap.jsx) mostra:

- A sede ou referência territorial.
- O círculo da área efetivamente analisada.
- O perímetro cadastrado, quando existir, ou o círculo equivalente estimado pela área.
- O ponto de drenagem MERIT quando retornado pela API.
- Os raios de análise e de busca de drenagem disponíveis no resultado.

O mapa explicita que o polígono cadastrado é referência visual: ele ainda não substitui o círculo usado pelo processamento territorial atual. O raio desenhado reflete a resposta da API; o componente utiliza 1.000 m como valor de apresentação quando esse campo está ausente.

[ExposicaoMaquinario.jsx](../frontend/src/components/ExposicaoMaquinario.jsx) apresenta o painel AGRISHIELD-EQUIP com score publicável, classificação, perigo dominante, pesos/contribuições, comparação de exposição, explicações por perigo, eventos históricos e qualidade das fontes. A navegação interna oferece Visão geral, Composição, Perigos, Histórico e Qualidade. A linha do tempo pode ser filtrada por perigo e permite selecionar eventos.

Os cinco perigos exibidos são exposição hídrica, trafegabilidade, instabilidade, incêndio/propagação de fogo e tempestades severas. O frontend respeita os estados de elegibilidade, participação no score e insuficiência de dados que recebe do backend, em vez de transformar todo valor ausente em zero.

A chamada atual desse componente usa `fonte=NASA_POWER`. Embora o cliente da API aceite `OPEN_METEO`, não existe seletor de fonte nem de data de referência nessa tela. A classe de equipamento é exibida como “Todos os equipamentos”, explicitamente contextual e sem alterar o score. O período mostrado é de 90 dias, comparado automaticamente aos 90 anteriores.

### 5.5 Riscos e Score

[RiscosScore.jsx](../frontend/src/components/RiscosScore.jsx) explica os indicadores e permite editar os parâmetros publicados pela API: pesos gerais e coeficientes/limiares dos grupos disponíveis. Os pesos ativos precisam somar 100%; a API realiza a validação final, incluindo erros estruturados por grupo.

**Restaurar padrões** preenche os campos com os valores de referência. A alteração só é persistida ao clicar em **Salvar parâmetros**. A restauração pode ser feita por perigo ou para todos os grupos.

A própria tela informa que os valores padrão pertencem à política demonstrativa AGRISHIELD-EQUIP v1.0 e ainda não foram calibrados contra sinistros reais ou limites de fabricante. O motor de cálculo permanece no backend.

### 5.6 Inventário de maquinários

[MaquinariosPage.jsx](../frontend/src/pages/MaquinariosPage.jsx) é aberto a partir de uma fazenda em Clientes e Apólices. A página sempre mostra a propriedade e suas apólices para deixar explícito o vínculo do inventário. Existem três abas: **Frota cadastrada**, **Cadastro individual** e **Importar CSV**.

O cadastro individual contempla:

- Tipo: trator, colheitadeira, pulverizador autopropelido, plantadeira, implemento de arrasto, plataforma ou utilitário de apoio.
- Fabricante, opção de outra marca, modelo, ano de fabricação, chassi/série e apelido.
- Horímetro, hodômetro e média declarada de horas por dia.
- Indicação de seguro cadastrado, seguradora e vencimento; outras seguradoras possuem campo próprio.

O formulário exige horímetro para os tipos motorizados. O ano de fabricação vai de 1970 até o próximo ano civil, e a média de uso aceita valores de 0 a 24 horas/dia. As validações do backend continuam sendo a referência para a gravação.

A importação CSV tem modelo baixável, separador `;`, codificação UTF-8, datas `AAAA-MM-DD`, até 500 linhas e limite de 1 MB no seletor. O arquivo é validado antes de a interface habilitar a confirmação. Os erros indicam linha, campo e mensagem; a tela mostra até os primeiros 20 erros retornados. O envio de importação é separado da validação, e a interface informa que um arquivo com erros não deve gerar cadastro parcial.

Após cadastro ou importação, a lista e o resumo da frota são atualizados, assim como os dados compartilhados da fazenda. O painel apresenta seguro como informação cadastral. Horímetro e uso diário são valores informados, sem telemetria ao vivo. A interface atual oferece listagem, cadastro e importação; não possui controles de edição ou exclusão individual de equipamentos.

### 5.7 Relatórios, Dados e Fontes e Configurações

[RelatoriosPage.jsx](../frontend/src/pages/RelatoriosPage.jsx) cria um resumo cadastral do portfólio ativo, com propriedade, apólice principal, localização, operação, estado territorial e score disponível. A ação **Imprimir** chama `window.print()`, permitindo usar a impressão/salvamento em PDF do navegador. Essa tela é diferente do PDF por apólice gerado pelo backend em Clientes e Apólices.

[DadosFontesPage.jsx](../frontend/src/pages/DadosFontesPage.jsx) apresenta o registro cadastral, o registro territorial, versões do schema/algoritmo, data do cálculo e os parâmetros vigentes agrupados. As consultas territorial e de parâmetros são independentes: falha em uma não impede mostrar o resultado da outra. Os nomes das bases exibidas são referências de rastreabilidade; a tela não é um explorador SQL nem um editor direto de tabelas.

[ConfiguracoesPage.jsx](../frontend/src/pages/ConfiguracoesPage.jsx) mostra a URL efetiva da API e atalhos para parâmetros, fontes e relatórios. Ela não altera chaves, endpoints ou variáveis de ambiente pelo navegador. O indicador “API conectada” reflete o estado de carregamento das fazendas mantido pelo aplicativo, não um monitor contínuo de todas as integrações.

## 6. Insights: leitura visual, regras locais e briefing da LLM

[InsightsPage.jsx](../frontend/src/pages/InsightsPage.jsx) oferece uma análise extensa da propriedade selecionada. Ela combina o briefing por IA com elementos auditáveis de contexto: previsão, radar, cobertura de dados, inventário, comparação cadastral, distribuição do portfólio, condições dos últimos 30 dias e fatores de risco.

### 6.1 O que o frontend envia à geração por IA

Depois que o dashboard está disponível, o painel chama automaticamente:

```http
POST /api/fazendas/{id}/insights-ia
Content-Type: application/json
Authorization: Bearer <token>

{"forcar": false}
```

O frontend **não envia o texto de um prompt, o cadastro inteiro ou uma chave de IA**. Ele informa a propriedade na URL e se deseja forçar uma nova leitura. O backend é responsável por consultar os dados autorizados, montar o contexto enviado à LLM, validar a resposta e gerenciar o reaproveitamento da análise.

O botão **Atualizar análise** repete a chamada com `{"forcar": true}`. Trocar de propriedade limpa o resultado anterior e invalida respostas atrasadas. Se uma atualização falha depois de existir uma leitura, o painel pode manter a leitura anterior acompanhada do erro. Falhas na IA não removem os demais indicadores da tela.

O resultado esperado contém `insight`, `cache` e `gerado_em`. A interface mostra os seguintes campos de `insight`:

| Campo | Uso na tela |
| --- | --- |
| `resumo_executivo` | Síntese principal do briefing |
| `leitura_principal` | Explicação da situação |
| `nivel_atencao` | Baixo, moderado, alto ou crítico |
| `prioridades[]` | Título, motivo, prazo, ação recomendada e evidência |
| `pontos_positivos[]` | Sinais positivos sustentados pela leitura |
| `perguntas_consultor[]` | Perguntas para confirmar a situação com o cliente |
| `limitacoes[]` | Limites e lacunas da análise |

Cada prioridade exibe `dado_base`, para relacionar o texto à evidência usada. O rodapé informa se houve leitura reaproveitada ou nova leitura e a data/hora de geração. O nível de atenção sugerido não é apresentado como probabilidade de sinistro.

O cabeçalho visual contém o texto fixo “GPT-4o mini”. Esse rótulo é uma escolha do componente e não uma consulta dinâmica ao modelo realmente configurado no backend. A configuração e o processamento da LLM são detalhados em [Insights e LLM](INSIGHTS_E_LLM.md) e devem ser conferidos no serviço responsável.

### 6.2 Previsão e janela candidata

A previsão usa `dashboard.previsao_7d`, `origem_previsao` e `previsao_atualizada_em`. O painel reconhece o Open-Meteo quando `origem_previsao = api_open_meteo`. Sete entradas oficiais são necessárias para a grade diária; a condição de previsão completa exige também chuva, probabilidade e temperatura máxima válidas nos sete dias.

O resumo mostra chuva acumulada, quantidade de dias com menor sinal de chuva, dias de atenção, temperatura máxima e maior probabilidade de precipitação. Chuva acumulada total só é mostrada quando os sete valores estão presentes. Ausências aparecem como indisponibilidade, não como chuva zero.

[insightsCalculations.js](../frontend/src/pages/insightsCalculations.js) classifica cada dia com regras explícitas:

| Regra, em ordem de avaliação | Resultado |
| --- | --- |
| Chuva, probabilidade e temperatura ausentes | Dados incompletos/indisponível |
| Chuva ≥ 20 mm **ou** probabilidade ≥ 70% | Chuva relevante |
| Chuva ≥ 5 mm, probabilidade ≥ 40%, máxima ≥ 35 °C **ou** alguma variável ausente | Atenção climática |
| Nenhuma das condições anteriores | Menor sinal de chuva |

A maior sequência contígua de dias com menor sinal de chuva vira uma **condição candidata para validação local**. É uma triagem meteorológica determinística: não libera uma operação nem confirma segurança do solo, do vento, do acesso ou dos requisitos de uma atividade. Esses fatores precisam ser conferidos antes do planejamento operacional.

Quando a origem oficial ou a quantidade de dias não é suficiente, o painel mostra a previsão indisponível. Ele não substitui a previsão ausente por dias meteorológicos simulados para preencher a grade.

No backend, a fachada `previsao_open_meteo` em [servicos_externos.py](../backend/app/servicos_externos.py) também impede a exposição de valores sintéticos internos: quando o cliente rico indica simulação, ela devolve `origem = fallback_simulado`, `dias = []` e `alertas = []`. Com isso, `previsao_5d` e `previsao_7d` chegam vazias ao dashboard. A rota de alertas ainda pode acrescentar eventos derivados do histórico, como o indício de encharcamento; lista vazia na fachada de previsão não significa que todos os alertas da fazenda necessariamente desapareçam.

### 6.3 Radar de decisão

O radar também é calculado localmente, sem nova chamada à LLM. Ele usa os alertas e a condição do dashboard, o resumo da frota, o estado dos seguros e a cobertura dos dados. Pode recomendar conferir seguros vencidos, revisar a proteção cadastrada, validar o planejamento diante do clima, revisar os fatores atuais, completar o inventário ou completar as fontes.

As ações são ordenadas por `imediata`, `hoje`, `proximos_dias` e `monitorar`, e o painel mostra até três prioridades. Cada item inclui evidência, recomendação para validação e a natureza da leitura. Os limiares e textos ficam em `insightsCalculations.js`; não são decisões autônomas da LLM.

### 6.4 Cobertura dos dados

O percentual de cobertura é a proporção de **seis verificações** com estado pronto:

1. Cadastro com nome, cidade, UF, área e operação preenchidos.
2. Estado territorial `SUCESSO`.
3. Score numérico disponível.
4. Previsão oficial com sete dias e as três variáveis completas em cada dia.
5. Inventário disponível e com ao menos um equipamento.
6. Contagem de equipamentos com e sem seguro coerente com o total da frota.

Cada verificação vale uma parte igual. O resultado é arredondado para um percentual inteiro; níveis a partir de 85% são altos, a partir de 60% intermediários e abaixo disso parciais. **Esse percentual mede disponibilidade das informações, não confiança da LLM, precisão estatística ou qualidade técnica das fontes.** A verificação de seguro mede coerência cadastral das contagens; não valida a cobertura contratual de cada apólice.

### 6.5 Frota e comparação cadastral

O painel de frota mostra quantidade, composição por tipo, seguro cadastrado, seguros vigentes/vencidos, vencimentos em até 90 dias, próximo vencimento, idade média, soma dos horímetros informados e soma do uso diário declarado. Inventário vazio e inventário temporariamente indisponível possuem mensagens distintas.

O comparativo usa fazendas da mesma operação, exigindo pelo menos duas propriedades para oferecer uma referência. Ele apresenta mediana de área, mediana de tamanho da frota, tamanho da base válida e proporção com contexto territorial pronto. Contagens de frota explicitamente indisponíveis são excluídas da mediana.

É uma comparação descritiva de cadastros. Não mede desempenho, capacidade ótima, adequação atuarial ou dimensionamento recomendado. Os gráficos adicionais de distribuição do portfólio e de condições históricas ajudam a contextualizar a leitura; não são uma validação estatística do modelo.

## 7. Contrato HTTP e tratamento de falhas

[api/core.js](../frontend/src/api/core.js) centraliza a URL base, o token de acesso, o evento de sessão expirada, a leitura de JSON e o download autenticado. `fetchJSON` utiliza `detail` quando a API devolve uma mensagem textual; caso contrário, informa o status HTTP e o caminho consultado. O erro carrega `status` e `publicMessage`.

Os módulos especializados de [exposição](../frontend/src/api/exposicao.ts) e [parâmetros](../frontend/src/api/parametrosScore.ts) tratam contratos adicionais. Exposição aceita mensagens/códigos estruturados e textos específicos para `404`, `422` e `503`. Parâmetros interpreta os erros de validação por grupo e os mostra próximos ao bloco correspondente.

As principais rotas consumidas são:

| Área | Método e rota | Aplicação |
| --- | --- | --- |
| Sessão e perfil | `GET /api/auth/me`; `PUT /api/auth/perfil` | Autorização e dados profissionais |
| Administração | `GET /api/auth/usuarios`; `PATCH /api/auth/usuarios/{id}/acesso` | Contas e aprovação |
| Portfólio | `GET /api/fazendas?incluir_arquivadas=true` | Lista completa para a gestão |
| Cadastro | `POST /api/fazendas`; `PUT /api/fazendas/{id}` | Criação e edição |
| Arquivamento | `POST /api/fazendas/{id}/arquivamento` | Arquivar/restaurar |
| Localização | `GET /api/cep/{cep}`; `POST /api/geocodificacao/endereco` | Sugestões de endereço e posição |
| Dashboard | `GET /api/fazendas/{id}/dashboard` | Condição, fatores, alertas, previsão e resumo da frota |
| Território | `GET /api/fazendas/{id}/geoespacial`; `POST /api/fazendas/{id}/geoespacial/recalcular` | Consulta e reprocessamento |
| Clima | `POST /api/fazendas/{id}/clima/processar`; `GET /api/fazendas/{id}/clima/status` | Aquisição/processamento em segundo plano |
| Exposição | `GET /api/v1/exposicao/{id}?fonte=NASA_POWER` | Painel AGRISHIELD-EQUIP |
| Parâmetros | `GET` e `PUT /api/v1/parametros-score` | Leitura e edição do modelo |
| Inventário | `GET` e `POST /api/fazendas/{id}/maquinarios` | Frota e cadastro individual |
| CSV | `POST /api/fazendas/{id}/maquinarios/importacoes/validar`; `POST /api/fazendas/{id}/maquinarios/importacoes` | Validação e importação |
| Modelo CSV | `GET /api/maquinarios/modelo.csv` | Download autenticado do modelo |
| Insights IA | `POST /api/fazendas/{id}/insights-ia` | Geração/reuso do briefing |
| PDF por apólice | `GET /api/fazendas/{id}/relatorio.pdf?apolice=...` | Documento gerado pela API |

As rotas de autenticação do Supabase são chamadas pelo SDK, separadamente das rotas de negócio acima. Regras de acesso, persistência e validações definitivas pertencem ao backend.

### Modo de demonstração e indisponibilidade

[demoData.js](../frontend/src/demoData.js) contém três fazendas fictícias e um dashboard de exemplo. Esse conjunto é usado por `App` quando a consulta inicial das fazendas falha. O aplicativo exibe o aviso **Modo de demonstração** e não trata esses registros como dados reais salvos.

Esse fallback **não é uma entrada pública ou um modo offline completo**. O `AuthGate` continua exigindo Supabase configurado, sessão e perfil aprovado antes de renderizar `App`. Não existe botão de acesso sem autenticação, parâmetro de URL de demo ou flag de ambiente de bypass no código atual.

O fallback não implementa uma API local para as outras páginas. Cadastro, importação, território, parâmetros e geração de IA continuam dependendo dos serviços reais. Portanto, algumas telas podem mostrar estados indisponíveis mesmo quando a Visão Geral demonstra um dashboard.

Quando uma fazenda real foi carregada, mas seu dashboard falha, o aplicativo limpa esse dashboard e mostra o erro. Ele não associa `DEMO_DASH` ao cadastro real. Essa diferença evita que números fictícios preencham uma análise real com falha.

## 8. Configuração e execução do frontend

Execute os comandos abaixo dentro de `frontend`:

```powershell
npm ci
npm run dev
```

O Vite usa `http://127.0.0.1:5173` e `strictPort: true`: se a porta estiver ocupada, não escolhe outra silenciosamente. O script `npm start` inicia o mesmo servidor de desenvolvimento.

As variáveis necessárias podem ser definidas em um arquivo local não versionado, como `frontend/.env.local`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://SEU_PROJECT_REF.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=SUA_CHAVE_PUBLICA
```

`VITE_SUPABASE_ANON_KEY` também é aceito como alternativa legada à publishable key. `VITE_API_URL` possui o valor local padrão `http://127.0.0.1:8000` quando ausente. Já a URL e a chave pública do Supabase não possuem credenciais de fallback.

O arquivo [frontend/.env.example](../frontend/.env.example) apresenta a URL local da API. O [exemplo de produção](../frontend/.env.production.example) também documenta as variáveis de autenticação. Para executar a área autenticada, é preciso configurar as três variáveis acima e o backend correspondente. Variáveis `VITE_*` ficam no bundle público do navegador: somente a chave pública de autenticação deve ser utilizada ali. Chaves de LLM, `service_role` e segredos do servidor pertencem ao ambiente do backend.

Para compilar e verificar o bundle:

```powershell
npm run build
npm run preview
```

O build gera `frontend/dist`. A prévia usa `http://127.0.0.1:4173`. Alterações de variáveis no Vite exigem reiniciar o servidor de desenvolvimento ou refazer o build. A prévia não substitui o backend nem provisiona serviços externos.

### Como percorrer as telas atuais

1. Inicie a API e o frontend com os ambientes configurados.
2. Entre com o e-mail e o código de seis dígitos. Se for uma nova conta, complete a confirmação e aguarde a aprovação administrativa.
3. Na Visão Geral, selecione uma fazenda ativa com dados disponíveis.
4. Abra Operações para conferir o mapa, a composição da exposição e os eventos históricos.
5. Abra Insights e aguarde o dashboard e a análise assistida. Confira também a previsão, frota e cobertura mais abaixo na página.
6. Em Clientes e Apólices, abra o cadastro, a edição ou o inventário de uma fazenda.
7. Abra Dados e Fontes, Relatórios e Riscos e Score para verificar as demais áreas.
8. Em tela móvel, use o botão de menu; a navegação não depende de rotas distintas de URL.

## 9. Verificação e limites atuais

O script de testes é:

```powershell
npm test
```

Os testes existentes cobrem autenticação da interface, cliente HTTP, busca de fazendas, cadastro/geocodificação, mapas, inventário/importação, parâmetros, exposição, ajuda conceitual, menu e Insights. Os testes de cálculos de Insights verificam regras como ausência de dados, previsão parcial, prioridade das ações e comparação cadastral. A presença desses testes não implica que provedores externos reais tenham sido consultados durante sua execução.

Ao avaliar o frontend atual, considere os limites implementados:

- A navegação é por estado de componente, sem links permanentes por tela ou restauração geral da navegação no recarregamento.
- O fallback demonstrativo é parcial e continua atrás da autenticação.
- A tela de Configurações não edita variáveis de ambiente.
- A exposição é consultada com NASA POWER pela interface atual; outros modos do contrato não têm controle visível nessa página.
- O inventário é cadastral, sem leitura automática de sensores ou máquinas.
- O cadastro da classe do equipamento não individualiza o score de exposição exibido.
- O perímetro da fazenda é uma referência visual e cadastral; o processamento territorial ainda informa seu próprio entorno de análise.
- A lista e a busca do portfólio são filtradas no navegador sobre os dados recebidos; a busca compartilhada limita a apresentação a 12 sugestões.
- A impressão do portfólio usa os scores disponíveis em memória/preview e a apólice principal; o PDF por apólice possui fluxo próprio na API.
- A porcentagem de cobertura dos Insights não é uma probabilidade, um índice de confiança da IA ou uma auditoria técnica das fontes.
- O briefing depende do backend, da configuração do provedor de IA e das evidências disponíveis. A interface não cria uma resposta fictícia de IA quando o serviço falha.
- Os parâmetros de referência e as recomendações são demonstrativos e exigem validação técnica; a LLM não substitui a análise do consultor.

Esses limites fazem parte do comportamento observado no código e ajudam a distinguir o que a aplicação já executa do que pode ser desenvolvido em evoluções futuras.
