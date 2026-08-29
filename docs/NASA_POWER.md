# NASA POWER no AgriShield

A API REST NASA POWER usada pelo projeto é pública e não exige conta,
token, chave de API ou autenticação. A "autenticação" consiste apenas em
validar que o computador consegue acessar o serviço HTTPS.

## Teste no Windows

1. Execute `01_instalar_dependencias.bat` uma vez.
2. Execute `08_testar_nasa_power.bat`.
3. O resultado deve mostrar `[OK] NASA POWER acessível sem chave ou login`.

Para testar outra localização e período pelo Prompt de Comando:

```bat
08_testar_nasa_power.bat -23.5505 -46.6333 14
```

Os argumentos são latitude, longitude e quantidade de dias. Sem argumentos, o
script usa Sorriso/MT e sete dias. Para evitar valores ainda não publicados na
grade near-real-time, o período de teste termina dez dias antes da data atual.

Se o teste falhar, confira acesso à internet, proxy corporativo, firewall e se o
relógio do Windows está correto. O coletor normal do projeto mantém um fallback
simulado para a demonstração, mas o teste retorna erro se não receber dados reais.

Documentação oficial:

- https://power.larc.nasa.gov/docs/services/api/temporal/daily/
- https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/
