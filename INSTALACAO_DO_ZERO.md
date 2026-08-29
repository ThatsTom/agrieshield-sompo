# Instalação do AgriShield do zero — Windows

Este é o roteiro recomendado para alguém que acabou de baixar o projeto do GitHub ou recebeu o ZIP e ainda não possui o ambiente configurado.

## 1. Onde extrair o projeto

Evite trabalhar diretamente dentro do ZIP.

Extraia a pasta para um caminho simples, por exemplo:

```text
C:\Projetos\agrishield
```

Caminhos muito longos podem dificultar ferramentas do Node e do Python no Windows.

## 2. Pré-requisitos

O projeto utiliza:

- Windows 10 ou 11;
- Python 3.12 ou 3.13 de 64 bits;
- Node.js LTS;
- npm, instalado junto com Node.js;
- internet na primeira instalação e para as APIs públicas.

### Instalação automática dos pré-requisitos

Dê dois cliques em:

```text
00_instalar_pre_requisitos.bat
```

O arquivo:

1. procura Python 3.13;
2. procura Python 3.12;
3. verifica Node.js e npm;
4. se algo estiver faltando e o `winget` estiver disponível, oferece instalação automática.

Se o BAT instalar Python ou Node.js, **feche a janela e abra um novo Prompt de Comando/PowerShell** antes de continuar. Isso é necessário para que o Windows recarregue o `PATH`.

## 3. Instalar dependências do projeto

Execute:

```text
01_instalar_dependencias.bat
```

Ele executa automaticamente:

### Backend

- cria `backend\.venv`;
- atualiza `pip`, `setuptools` e `wheel`;
- instala NumPy e Pandas por wheel binária;
- instala o restante de `backend\requirements.txt`;
- testa os imports;
- garante a existência dos CSVs base.

### Frontend

- verifica `node` e `npm`;
- executa `npm install --include=dev`;
- instala React, React DOM, Vite e plugin React;
- verifica `node_modules\.bin\vite.cmd`;
- executa `npm run build` como teste.

A instalação terminou corretamente se aparecer:

```text
INSTALACAO CONCLUIDA COM SUCESSO
```

## 4. Validar a instalação

Execute:

```text
04_verificar_instalacao.bat
```

Ele testa:

- ambiente virtual Python;
- imports FastAPI/Pandas/NumPy/Earth Engine/HTTPX/python-dotenv;
- carregamento da aplicação FastAPI;
- leitura do contexto territorial exigido pela Exposição v1;
- Node.js;
- npm;
- Vite local;
- build do React.

O resultado esperado é:

```text
[OK] INSTALACAO VALIDADA
```

## 4.1. Configurar Google Earth Engine para todas as integrações

As fazendas de demonstração já persistidas abrem a Exposição v1 sem refazer a
consulta territorial. Para cadastrar ou recalcular fazendas e executar o
MapBiomas, autentique sua própria conta Earth Engine:

```powershell
backend\.venv\Scripts\python.exe -c "import ee; ee.Authenticate()"
Copy-Item .env.example .env
notepad .env
```

No `.env`, troque `seu-projeto-gcp-autorizado` pelo ID de um projeto Google
Cloud ao qual a conta autenticada tenha acesso. Valide:

```powershell
backend\.venv\Scripts\python.exe -c "import os,ee; from dotenv import load_dotenv; load_dotenv(); ee.Initialize(project=os.environ['EARTH_ENGINE_PROJECT']); print('Earth Engine OK')"
```

O backend iniciado pelo BAT carrega esse `.env` automaticamente. O arquivo é
ignorado pelo Git e não deve conter credenciais compartilhadas.

## 5. Iniciar o sistema

Execute:

```text
02_iniciar_projeto.bat
```

Serão abertas duas janelas:

1. **AgriShield API - FastAPI**
2. **AgriShield Frontend - React**

Depois de alguns segundos, o navegador deve abrir automaticamente.

Endereços:

```text
Frontend: http://127.0.0.1:5173
API:      http://127.0.0.1:8000
Swagger:  http://127.0.0.1:8000/docs
```

## 6. Teste funcional mínimo

### Teste 1 — API

Abra:

```text
http://127.0.0.1:8000
```

Deve aparecer um JSON informando que o serviço está `ok`.

### Teste 2 — Swagger

Abra:

```text
http://127.0.0.1:8000/docs
```

Teste `GET /api/fazendas`.

### Teste 3 — React

Abra:

```text
http://127.0.0.1:5173
```

Entre em **Clientes e Apólices** e clique em **Nova fazenda**.

### Teste 4 — Pipeline

Depois de abrir uma fazenda no dashboard, confira:

```text
backend\data\nasa_power_bruto_<id>.csv
backend\data\nasa_power_enriquecido_<id>.csv
backend\data\dashboard_indicadores_<id>.csv
```

### Teste 5 — Exposição NASA POWER

Com o backend iniciado, execute no PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/exposicao/1?fonte=NASA_POWER'
```

O resultado esperado é um objeto com `fonte_meteorologica` igual a
`NASA_POWER`, `score_atual` e `contexto_territorial`. Essa chamada é o teste
decisivo; o `GET /api/fazendas/1/geoespacial` sozinho não valida a normalização.

## 7. Executar o ETL manualmente

Use:

```text
03_executar_etl_completo.bat
```

Esse BAT executa em sequência as etapas 1–3 do pipeline climático legado. A
Etapa 4 geoespacial é executada no cadastro ou pelo endpoint explícito, porque
depende de autenticação no Earth Engine:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/fazendas/1/geoespacial/recalcular
```

## 7.1. Se a Exposição retornar `422`

Consulte o JSON da resposta. Se `detail.codigo` for
`CONTEXTO_TERRITORIAL_INDISPONIVEL`, a falha está no contexto SRTM/MERIT e não
no valor `NASA_POWER`. A versão atual reconstrói os dados das fazendas de
demonstração pelo CSV quando o cache local estiver ausente. Para uma fazenda
nova, configure o Earth Engine, reinicie o backend e recalcule pelo comando
acima.

Se o código for `COORDENADAS_INDISPONIVEIS`, complete latitude e longitude no
cadastro. O frontend agora preserva a mensagem detalhada devolvida pelo backend.

## 8. Se aparecer "vite não é reconhecido"

Não instale Vite globalmente.

Execute:

```text
06_reinstalar_frontend.bat
```

O arquivo remove `frontend\node_modules`, reinstala inclusive as `devDependencies` e verifica se existe:

```text
frontend\node_modules\.bin\vite.cmd
```

Depois execute novamente:

```text
02_iniciar_projeto.bat
```

## 9. Se aparecer erro do Pandas, Meson ou Visual Studio

Esse erro normalmente indica uma `.venv` antiga/incompleta ou uso de uma combinação de versão não suportada.

Execute:

```text
05_reinstalar_backend.bat
```

Depois:

```text
01_instalar_dependencias.bat
```

O instalador usa `pandas==2.2.3` e `numpy==2.1.3` e solicita wheel binária antes da instalação completa.

## 10. Se você tiver Python 3.14 instalado

O instalador não escolhe Python 3.14 automaticamente. Ele procura nesta ordem:

```text
Python 3.13
Python 3.12
```

Se nenhum deles existir, execute:

```text
00_instalar_pre_requisitos.bat
```

## 11. Se o npm falhar

Verifique:

```bat
node -v
npm -v
```

Depois tente:

```text
06_reinstalar_frontend.bat
```

Redes de faculdade/empresa podem bloquear `registry.npmjs.org`. Nesse caso, teste em outra rede ou confirme as configurações de proxy do npm.

## 12. Como encerrar

Nas duas janelas abertas pelo `02_iniciar_projeto.bat`, pressione:

```text
Ctrl + C
```

ou simplesmente feche as janelas.

## 13. Instalação manual, sem BAT

### Backend

```bat
cd backend
py -3.13 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install --only-binary=:all: numpy==2.1.3 pandas==2.2.3
python -m pip install -r requirements.txt
cd ..
backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Se você possuir Python 3.12, troque `py -3.13` por `py -3.12`.

### Frontend

Abra outro terminal:

```bat
cd frontend
npm install --include=dev
npm run dev
```

## 13.1. Executar os testes automatizados

Na raiz do projeto:

```powershell
backend\.venv\Scripts\python.exe -B -m unittest discover -s backend\tests -p "test_*.py"
cd frontend
npm.cmd test
npm.cmd run build
```

## 14. Ordem recomendada para entregar/demonstrar

```text
00_instalar_pre_requisitos.bat   (somente se necessário)
01_instalar_dependencias.bat
04_verificar_instalacao.bat
02_iniciar_projeto.bat
```
