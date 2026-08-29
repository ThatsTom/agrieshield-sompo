# Portfólio avançado de fazendas

## Condição e origem

A tela **Clientes e Apólices** mostra score, condição, data de referência e
origem. `NASA real` identifica uma resposta da NASA POWER; `Simulado` identifica
o fallback de contingência e não deve ser interpretado como medição observada.

O botão **Atualizar clima** cria um job em segundo plano. A barra informa as
etapas de coleta, cálculo e persistência. Os jobs ficam em memória e, portanto,
seu status de andamento reinicia junto com a API; o resultado concluído permanece
nos CSVs.

## Múltiplas apólices

No cadastro, a primeira apólice é a principal. O botão **Adicionar apólice**
inclui vínculos adicionais. A listagem apresenta todas e oferece um link **PDF**
individual, garantindo a exportação por fazenda e apólice.

## Mapa e polígono

Latitude e longitude da sede são conferidas em um mapa OpenStreetMap. O mapa
precisa de internet, mas o restante do formulário continua funcional sem ele.

O perímetro aceita um vértice por linha no formato `latitude, longitude`:

```text
-12.5450, -55.7210
-12.5500, -55.7100
-12.5600, -55.7250
```

São necessários pelo menos três vértices. O backend valida os limites
geográficos, fecha o anel automaticamente e persiste um `Polygon` GeoJSON.

## Arquivamento

**Arquivar** remove a fazenda das telas operacionais sem apagar cadastro,
apólices, clima ou contexto territorial. Use o filtro **Cadastro > Arquivadas**
para localizar e restaurar registros.

## Migração do CSV

Ao iniciar a API, `fazendas.csv` recebe automaticamente as colunas:

- `apolices_json`;
- `arquivada`;
- `poligono_geojson`.

Registros antigos continuam válidos: `numero_apolice` passa a ser a apólice
principal, arquivamento vazio equivale a ativo e polígono vazio permanece
opcional.
