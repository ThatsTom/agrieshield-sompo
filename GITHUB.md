# Como subir o AgriShield para o GitHub

## 1. Antes de começar

Faça a instalação local e confirme que o projeto funciona:

```text
01_instalar_dependencias.bat
04_verificar_instalacao.bat
02_iniciar_projeto.bat
```

Não é necessário subir `node_modules` nem `.venv` para o GitHub. Eles são recriados pelos arquivos de instalação.

## 2. O que será versionado

Deve ser enviado:

- código Python;
- código React;
- `package.json`;
- `requirements.txt`;
- arquivos `.bat`;
- `README.md`;
- `INSTALACAO_DO_ZERO.md`;
- este `GITHUB.md`;
- CSVs base necessários ao projeto;
- imagens de documentação.

Não deve ser enviado:

- `backend/.venv`;
- `frontend/node_modules`;
- `frontend/dist`;
- `__pycache__`;
- `.env` com segredos;
- CSVs derivados que podem ser recriados pelo ETL.

O `.gitignore` do projeto já trata esses itens.

## 3. Instalar Git

Se `git --version` funcionar, pule esta etapa.

No Windows, instale Git for Windows e abra um novo terminal.

Teste:

```bat
git --version
```

## 4. Criar repositório no GitHub

Você pode executar:

```text
07_abrir_github.bat
```

No GitHub:

1. clique em **New repository**;
2. escolha um nome, por exemplo `agrishield-sompo`;
3. escolha `Public` ou `Private` conforme a orientação da faculdade;
4. não marque para criar outro README, pois o projeto já possui um;
5. clique em **Create repository**.

## 5. Inicializar Git na pasta do projeto

Abra o terminal na pasta que contém `README.md` e execute:

```bash
git init
git add .
git status
```

Confira o `git status` antes do commit.

Você **não deve** ver milhares de arquivos de `node_modules` nem arquivos de `.venv`.

## 6. Primeiro commit

```bash
git commit -m "feat: prototipo AgriShield React FastAPI"
```

Se o Git pedir nome e e-mail:

```bash
git config --global user.name "SEU NOME"
git config --global user.email "SEU_EMAIL_DO_GITHUB"
```

Depois repita o commit.

## 7. Usar a branch main

```bash
git branch -M main
```

## 8. Conectar ao GitHub

Copie a URL HTTPS do repositório criado e execute:

```bash
git remote add origin https://github.com/SEU_USUARIO/agrishield-sompo.git
```

Confira:

```bash
git remote -v
```

## 9. Fazer push

```bash
git push -u origin main
```

O GitHub pode abrir o navegador para autenticação.

## 10. Próximas atualizações

Depois de modificar o projeto:

```bash
git status
git add .
git commit -m "descricao da alteracao"
git push
```

Exemplos de commits:

```bash
git commit -m "feat: adiciona cadastro de fazendas"
git commit -m "feat: integra dados NASA POWER"
git commit -m "feat: adiciona alertas Open-Meteo"
git commit -m "fix: corrige instalacao do frontend"
git commit -m "docs: atualiza instrucoes do projeto"
```

## 11. Conferência final no GitHub

Confirme que o repositório mostra pelo menos:

```text
backend/
frontend/
docs/
00_instalar_pre_requisitos.bat
01_instalar_dependencias.bat
02_iniciar_projeto.bat
03_executar_etl_completo.bat
04_verificar_instalacao.bat
README.md
INSTALACAO_DO_ZERO.md
GITHUB.md
.gitignore
```

Confirme também que não aparece:

```text
backend/.venv/
frontend/node_modules/
```

## 12. Como outro integrante deve baixar e executar

```bash
git clone https://github.com/SEU_USUARIO/agrishield-sompo.git
cd agrishield-sompo
```

Depois no Windows:

```text
00_instalar_pre_requisitos.bat
01_instalar_dependencias.bat
04_verificar_instalacao.bat
02_iniciar_projeto.bat
```

Essa é a principal razão para `node_modules` e `.venv` não serem enviados: cada integrante recria o ambiente de maneira limpa.

## 13. Checklist antes da entrega

- [ ] README abre corretamente no GitHub.
- [ ] `.gitignore` está no repositório.
- [ ] `requirements.txt` está no backend.
- [ ] `package.json` está no frontend.
- [ ] todos os BATs estão versionados.
- [ ] `backend/.venv` não foi enviado.
- [ ] `frontend/node_modules` não foi enviado.
- [ ] os três prints estão em `docs/`.
- [ ] `fazendas.csv` e `base_coordenadas_cep.csv` estão presentes.
- [ ] um clone limpo consegue rodar `01_instalar_dependencias.bat`.
- [ ] frontend abre em `127.0.0.1:5173`.
- [ ] Swagger abre em `127.0.0.1:8000/docs`.

## 14. Publicar automaticamente na Vercel pelo GitHub

O repositório usado pelo projeto é `ThatsTom/agrieshield-sompo`. A publicação
automática depende de conectar o repositório em **Settings > Git** de cada
projeto existente da Vercel, com `main` como branch de produção.

| Projeto Vercel | Root Directory | Configuração versionada |
| --- | --- | --- |
| `agrishield-sompo-backend` | raiz do repositório | `vercel.json`, `api/index.py` e `requirements.txt` |
| `agrishield-sompo-frontend` | `frontend` | `frontend/vercel.json`, `frontend/package.json` e lockfile |

O frontend usa Vite, instala com `npm ci`, compila com `npm run build` e
publica `dist`. Defina seu **Root Directory** como `frontend` antes de conectar
o GitHub; assim o build encontra a configuração e o pacote corretos.

Com os dois projetos conectados, um `git push origin main` permite à Vercel
publicar backend e frontend. São dois serviços e dois builds automáticos,
iniciados pelo mesmo push. Não é necessário repetir a publicação pela CLI.
O login da CLI e o vínculo local em `.vercel` são independentes da integração
Git configurada no painel.

Para conectar os projetos existentes pela CLI, depois de autorizar o app
Vercel na conta GitHub proprietária do repositório:

```powershell
npm run vercel -- git connect https://github.com/ThatsTom/agrieshield-sompo.git --project agrishield-sompo-backend --scope desenvolvimento-eau
npm run vercel -- git connect https://github.com/ThatsTom/agrieshield-sompo.git --project agrishield-sompo-frontend --scope desenvolvimento-eau
```

Se a Vercel informar falta de acesso de escrita, confira a conta GitHub
autorizada em sua integração. Para este repositório pessoal, a conta
proprietária é `ThatsTom`. Ter acesso pelo `gh` ou conseguir executar
`git push` não concede automaticamente acesso ao app da Vercel. Autorize o
repositório em <https://github.com/apps/vercel/installations/new> e confira
a conexão em **Settings > Git** dos projetos.

Confira também `npm run vercel:whoami`: a sessão da CLI deve usar um usuário
Vercel vinculado ao GitHub `ThatsTom` e com acesso aos projetos no time
`desenvolvimento-eau`. Instalar o app em `ThatsTom` não troca a identidade
da sessão Vercel. Cada usuário Vercel aceita uma conta GitHub pessoal;
para preservar a conexão `DesenvolvimentoEAU`, use o usuário Vercel
`thatstom`, já autorizado no time, em vez de substituir conexões existentes.

As variáveis de produção continuam configuradas em cada projeto da Vercel.
No frontend, `VITE_API_URL` deve apontar para
`https://agrishield-sompo-backend.vercel.app`. O build de produção é feito pela
Vercel; não envie o `frontend/dist` produzido com configurações locais.

Para usar a CLI instalada na raiz:

```powershell
npm ci
npm run vercel:login
npm run vercel:whoami
```

Para baixar as variáveis exportáveis, sem sobrescrever o `.env.local` de teste:

```powershell
npm run vercel -- env pull .env.production.local --environment=production --project agrishield-sompo-backend --scope desenvolvimento-eau
npm run vercel -- env pull frontend/.env.vercel.production.local --environment=production --project agrishield-sompo-frontend --scope desenvolvimento-eau
```

Os arquivos `.env*` são ignorados pelo Git. Variáveis do tipo **Secret** não
podem ser recuperadas de produção pela CLI; ela grava `[SENSITIVE]` no lugar
do valor. Para executar o backend local, preencha `OPENAI_API_KEY` e
`SUPABASE_SECRET_KEY` diretamente no `.env` da raiz com credenciais próprias
para desenvolvimento. A federação GCP de produção usa OIDC da Vercel; o
ambiente local pode usar suas credenciais locais do Earth Engine.
