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
