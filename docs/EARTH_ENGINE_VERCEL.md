# Earth Engine na Vercel sem chave privada

O backend suporta Workload Identity Federation com OIDC da Vercel. A conta de serviço é utilizada por representação temporária, sem gerar chave JSON e sem baixar um arquivo de configuração ADC no formulário do Google Cloud.

## Configuração deste projeto

Os identificadores abaixo são públicos e correspondem à configuração informada nesta implementação:

| Item | Valor |
|---|---|
| Projeto Google Cloud | `sompo-api` |
| Número do projeto | `644279865927` |
| Pool / provedor | `vercel` / `vercel` |
| Conta de serviço | `agrishield-backend@sompo-api.iam.gserviceaccount.com` |
| Equipe Vercel | `desenvolvimento-eau` |
| Projeto Vercel | `agrishield-sompo-backend` |
| Ambiente autorizado | `production` |

O projeto Google Cloud precisa estar registrado para Earth Engine, com a API habilitada. O registro não comercial depende da elegibilidade declarada pelo responsável.

## Provedor e vínculo IAM

Na Vercel, configure o emissor **Team** em **Settings > Security > Secure backend access with OIDC federation**. No provedor Google, use:

- Emissor: `https://oidc.vercel.com/desenvolvimento-eau`.
- Público-alvo permitido: `https://vercel.com/desenvolvimento-eau`.
- Mapeamento: `google.subject = assertion.sub`.
- Condição do atributo: restrita à equipe, ao projeto e ao ambiente desejados.

```text
assertion.owner_id == 'team_00oM0ielqmGbkm1rOjdcsXuT' &&
assertion.project_id == 'prj_WAidCt62FCrzQZpE2eFa04qyxHkS' &&
assertion.environment == 'production'
```

Conecte a conta de serviço ao pool com **Workload Identity User** (`roles/iam.workloadIdentityUser`), limitado ao subject:

```text
owner:desenvolvimento-eau:project:agrishield-sompo-backend:environment:production
```

O identificador IAM completo desse principal é:

```text
principal://iam.googleapis.com/projects/644279865927/locations/global/workloadIdentityPools/vercel/subject/owner:desenvolvimento-eau:project:agrishield-sompo-backend:environment:production
```

Na conta de serviço, conceda os papéis **Earth Engine Resource Viewer** e **Service Usage Consumer** no projeto Google. Confira também as APIs Earth Engine, IAM, Security Token Service e IAM Service Account Credentials habilitadas.

## Variáveis do backend

Em **agrishield-sompo-backend > Settings > Environment Variables**, configure para **Production**:

```dotenv
EARTH_ENGINE_PROJECT=sompo-api
GCP_PROJECT_NUMBER=644279865927
GCP_WORKLOAD_IDENTITY_POOL_ID=vercel
GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID=vercel
GCP_SERVICE_ACCOUNT_EMAIL=agrishield-backend@sompo-api.iam.gserviceaccount.com
```

Esses valores são identificadores de configuração. A Vercel fornece o token de curta duração automaticamente em `x-vercel-oidc-token`; não copie um token de build para as variáveis de Production. A integração não requer `EARTH_ENGINE_SERVICE_ACCOUNT_JSON`, caminho de token ou chave privada.

Publique a versão atualizada do código depois de salvar as variáveis. Um simples redeploy de um código antigo não acrescenta o suporte OIDC. Em seguida, vá a **Clientes e Apólices** e clique em **Reprocessar** no contexto territorial da fazenda. Resultados de erro já persistidos não são recalculados apenas por alterar uma variável.

O vínculo descrito libera somente Production. Preview e desenvolvimento local precisam de autorizações próprias se forem usar a federação; não copie automaticamente a configuração de produção para esses ambientes.

## Funcionamento no código

[`autenticacao_earth_engine.py`](../backend/autenticacao_earth_engine.py) implementa o middleware ASGI e as credenciais do `google-auth`:

1. O middleware captura o token OIDC fornecido pela plataforma e o mantém em um `ContextVar` por requisição. O contexto acompanha os handlers síncronos executados em threads e é removido ao terminar, inclusive em falhas.
2. Se as quatro variáveis `GCP_*` estiverem preenchidas, o backend cria `identity_pool.Credentials` com o provedor configurado e um fornecedor de token do contexto atual.
3. O Google STS valida e troca o token Vercel. O IAM Credentials autoriza a representação da conta de serviço e emite o acesso temporário.
4. O backend passa as credenciais explicitamente para `ee.Initialize()`. Geoespacial SRTM/MERIT e MapBiomas utilizam esse fluxo compartilhado.

O audience do STS é o identificador canônico do provedor `//iam.googleapis.com/projects/.../providers/vercel`. Ele tem função diferente do público-alvo do token Vercel configurado no provedor; os dois valores não precisam ser iguais no fluxo com público-alvo permitido.

Sem nenhuma das quatro variáveis `GCP_*`, a aplicação mantém `ee.Initialize(project=...)` e as credenciais locais existentes. Uma configuração parcial de federação gera erro explícito, sem fallback silencioso. Fora da Vercel, `VERCEL_OIDC_TOKEN` pode ser utilizado em testes locais autorizados. Na Vercel, o token da requisição é obrigatório.

Os tokens não são gravados em arquivos, variáveis globais compartilhadas, banco ou respostas. O backend não verifica assinaturas JWT por conta própria: a validação do token, do emissor, público-alvo e vínculo IAM pertence ao Google durante a troca.

## Verificação e diagnóstico

Os testes em [`test_autenticacao_earth_engine.py`](../backend/tests/test_autenticacao_earth_engine.py) exercitam a troca STS/IAM com transporte simulado, integração com o endpoint de recálculo, inicialização das duas fontes, configuração incompleta, ausência de token, isolamento concorrente e limpeza após erros. Esses testes não comprovam que o IAM ou um deployment remoto estejam configurados.

Se continuar com falha, consulte `GET /api/fazendas/{id}/geoespacial`, especialmente `erros[]`. `EARTH_ENGINE_PROJECT` ausente, variáveis de federação incompletas e token OIDC ausente possuem diagnósticos explícitos. Uma falha de autorização remota também requer conferir os papéis, as APIs habilitadas, emissor, público-alvo e subject autorizado.

## Referências oficiais

- [Vercel OIDC e token por requisição](https://vercel.com/docs/oidc).
- [Vercel com Google Cloud](https://vercel.com/docs/oidc/gcp).
- [Workload Identity Federation e representação de conta](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers).
- [Fornecedor de token em google-auth](https://google-auth.readthedocs.io/en/latest/reference/google.auth.identity_pool.html).
- [Permissões Earth Engine](https://developers.google.com/earth-engine/guides/access_control).
