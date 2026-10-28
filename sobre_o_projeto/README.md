# Sobre o AgriShield

Esta pasta reúne a documentação detalhada do projeto, revisada a partir do código em **26 de outubro de 2026**. O objetivo é explicar o funcionamento para quem vai apresentar o trabalho, estudar a implementação ou continuar o desenvolvimento.

## Por onde começar

| Documento | Quando ler |
|---|---|
| [README principal](../README.md) | Para conhecer a proposta, ver as telas, instalar e localizar os módulos |
| [BACKEND.md](BACKEND.md) | Para entender API, persistência, fontes externas, regras, exposição e autenticação |
| [FRONTEND.md](FRONTEND.md) | Para entender navegação, componentes, formulários, mapas e apresentação dos dados |
| [INSIGHTS_E_LLM.md](INSIGHTS_E_LLM.md) | Para acompanhar cada etapa entre os dados da fazenda e o briefing assistido por IA |
| [SOBRE_O_PROJETO.txt](SOBRE_O_PROJETO.txt) | Para ler a visão geral e os três documentos consolidados em um único arquivo de texto |

O `.txt` é uma versão consolidada dos documentos desta pasta. Em futuras revisões, mantenha seu conteúdo alinhado aos arquivos de origem. Os caminhos de referência da consolidação seguem a mesma base desta pasta.

## Visão geral do produto

O AgriShield é um protótipo acadêmico de análise agrícola. Ele organiza informações de fazendas, operações, apólices e maquinário agrícola para apoiar a análise de condições ambientais, exposição e prioridades de acompanhamento.

O analista acessa a aplicação, seleciona uma propriedade e consulta indicadores e evidências. Pode cadastrar ou editar fazendas, confirmar localização, acompanhar processamentos, registrar máquinas, revisar parâmetros e consultar um briefing de apoio à conversa com o segurado.

O frontend React apresenta e coordena esses fluxos. O backend FastAPI valida entradas, acessos e contratos, consulta fontes, calcula indicadores e organiza os dados persistidos. O Supabase atende autenticação e persistência quando configurado. Repositórios locais têm finalidades específicas para desenvolvimento.

## Conceitos que precisam ser distinguidos

1. **Cadastro:** informações declaradas sobre propriedade, apólices e máquinas. Horímetro cadastrado não é telemetria.
2. **Dados externos:** fontes meteorológicas e territoriais com origem, período, cobertura e limitações próprias.
3. **Score operacional:** cálculo legado do dashboard, com condição atual e distribuição recente.
4. **Exposição v1:** outro motor, com cinco perigos, composição e comparação de janelas de 90 dias.
5. **Radar de Insights:** prioridades e indicadores calculados por regras locais de apresentação.
6. **Briefing da LLM:** interpretação textual de um contexto selecionado pelo backend, validada estruturalmente antes de ser exibida.
7. **Hídrico v2 experimental:** análise separada, que não substitui automaticamente o fluxo oficial da interface.

Essas camadas se relacionam, mas não representam um único modelo. A LLM atual não recebe o resultado completo da exposição v1 e não calcula os índices de risco.

## Caminho de leitura recomendado

Para uma apresentação, comece pela proposta e pela galeria do README principal. Em seguida, leia as responsabilidades do frontend e do backend e a distinção entre os modelos. Finalize com o fluxo de Insights: dados consultados, contexto enviado, instruções, saída, validação e limites.

Para manutenção técnica, comece pelo backend e pelos contratos HTTP, depois acompanhe seus consumidores no frontend. A documentação de Insights apresenta exemplos e referências para conferir o fluxo no código.

## Imagens e verificação

As [capturas atuais](../docs/screenshots/README.md) usam os componentes reais com respostas locais demonstrativas, identificadas na própria imagem. Não são evidência de uma coleta meteorológica real, de um deploy em funcionamento ou de uma chamada real à LLM. O texto do briefing das imagens é editorial.

Nesta revisão, o build do frontend foi concluído e passaram nove testes específicos de IA no backend e doze no frontend, com mocks. Links locais, referências de imagens e codificação dos documentos também foram conferidos. A suíte completa e os serviços externos não foram validados como parte desta atualização documental.

## Alcance da documentação

Os documentos descrevem a implementação versionada e os arquivos locais de referência. Configurações e valores persistidos em um ambiente remoto podem diferir. Os modelos são acadêmicos e não foram calibrados contra sinistros; índices, proxies e textos precisam ser interpretados com seus limites.
