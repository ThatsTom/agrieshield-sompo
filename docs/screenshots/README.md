# Capturas atuais da interface

Capturas produzidas em **28/10/2026**, usando os componentes React, estilos e contratos da revisão atual do repositório.

## Procedência

- A interface foi renderizada localmente com Vite e capturada por Chrome em modo headless, por meio de seu protocolo de depuração.
- Desktop: **1512 × 1080 pixels**. Captura móvel: **390 × 844 pixels**.
- As páginas internas foram montadas em uma entrada temporária de documentação, usando os componentes reais de página e navegação. A entrada foi removida após as capturas e não faz parte do produto. O roteiro e o cenário de demonstração estão em [`capture.cjs`](capture.cjs) e [`capture-entry.jsx`](capture-entry.jsx).
- As respostas da API foram substituídas localmente por dados demonstrativos derivados de `frontend/src/demoData.js`, das fixtures de exposição/parâmetros em `frontend/src/test/` e de exemplos de frota/previsão compatíveis com esses contratos.
- O login foi renderizado com seus componentes reais, sem enviar e-mail ou autenticar uma conta.
- O briefing foi escrito como exemplo editorial no formato esperado pela interface. **Nenhuma chamada à LLM foi feita para produzir as imagens.**
- As fontes e os valores apresentados fazem parte do cenário demonstrativo; não certificam uma coleta real. O mapa mantém a atribuição OpenStreetMap exibida pelo componente.
- Todas as imagens incluem o selo **DOCUMENTAÇÃO · DADOS DEMONSTRATIVOS**. Não foram usadas credenciais, perfis pessoais ou registros privados para compor o cenário.

## Arquivos

| Captura | Conteúdo |
|---|---|
| [01-visao-geral.png](01-visao-geral.png) | Score de exposição, distribuição operacional, alertas e contribuições |
| [02-clientes-apolices.png](02-clientes-apolices.png) | Gestão de propriedades, filtros e ações |
| [03-maquinarios.png](03-maquinarios.png) | Inventário de equipamentos e seguros |
| [04-cadastro-fazenda.png](04-cadastro-fazenda.png) | Formulário atual de cadastro |
| [05-riscos-score.png](05-riscos-score.png) | Parâmetros do modelo de exposição |
| [06-insights.png](06-insights.png) | Radar de decisão e início do briefing |
| [07-insights-briefing.png](07-insights-briefing.png) | Prioridades, evidências, ações, perguntas e limitações |
| [08-insights-mobile.png](08-insights-mobile.png) | Apresentação responsiva em tela móvel |
| [09-operacoes-territorio.png](09-operacoes-territorio.png) | Indicadores territoriais e mapa |
| [10-exposicao-maquinario.png](10-exposicao-maquinario.png) | Exposição de maquinário e comparação histórica |
| [11-login.png](11-login.png) | Login sem senha por e-mail |

As imagens `docs_dashboard.png`, `docs_clientes.png` e `docs_cadastro.png`, na pasta superior, e `output/insights-production-mobile.png` foram sincronizadas com as capturas correspondentes desta pasta. O nome do arquivo de saída móvel é legado: seu conteúdo atual também usa apenas dados demonstrativos.

## Como atualizar novamente

Instale as dependências do frontend e execute, a partir da raiz:

```powershell
node docs/screenshots/capture.cjs
```

O roteiro requer Node.js com `fetch` e `WebSocket` globais, Chrome/Edge instalado e as portas locais 5175 e 9229 disponíveis. Use `AGRISHIELD_CAPTURE_BROWSER` para informar outro executável Chromium. Para repetir apenas uma captura, passe seu nome, por exemplo `node docs/screenshots/capture.cjs 07-insights-briefing.png`.

O processo esvazia a configuração Supabase no servidor temporário, simula todas as respostas de API, cria um perfil de navegador isolado e não envia e-mails nem acessa registros reais. As imagens de mapa podem consultar os tiles públicos OpenStreetMap. A captura confirma a renderização do cenário de documentação; não valida o backend ou serviços de produção.

1. Use os componentes da revisão a ser documentada e dados de demonstração identificados. Não remova as proteções de autenticação do produto para obter capturas.
2. Se for necessário um ambiente de captura separado, mantenha-o temporário e faça com que as requisições sejam respondidas por fixtures locais.
3. Aguarde o carregamento dos componentes e do mapa, mantenha a escala do navegador e registre as dimensões.
4. Verifique visualmente as imagens, evite dados pessoais e atualize as legendas/procedência.
5. Confira as referências no README e na documentação. Uma captura demonstrativa não substitui testes de API, integração ou disponibilidade de produção.
