# Indicadores API

API em **FastAPI** que serve indicadores econômicos brasileiros, alimentada por um **pipeline de
ETL incremental** em Python que extrai dados de duas fontes públicas:

| Série | Fonte | Frequência |
|---|---|---|
| `ipca_mensal`: IPCA, variação mensal (%) | IBGE, API de agregados (tabela 1737, variável 63) | mensal |
| `ipca_indice`: IPCA, número-índice | IBGE, API de agregados (tabela 1737, variável 2266) | mensal |
| `dolar_ptax`: dólar PTAX, venda (R$) | Banco Central, serviço Olinda/PTAX | diária |

**Stack:** Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · pandas · httpx · PostgreSQL (SQLite
em desenvolvimento) · pytest · Ruff · Docker · GitHub Actions

## Como o pipeline funciona

```
 IBGE (JSON aninhado, período "AAAAMM")   ┐
                                          ├─ extração ─ transformação ─ carga ─ PostgreSQL
 BCB PTAX (OData, data e hora)            ┘   httpx       pandas        upsert
```

- **Extração** (`etl/fontes.py`): `httpx` com nova tentativa e espera exponencial em erro de
  rede ou 5xx. Erros 4xx não são repetidos. Falha com mensagem clara se a resposta mudar de formato.
- **Transformação** (`etl/transformacao.py`): converte cada fonte numa tabela única `(data, valor)`
  com pandas. Descarta os símbolos de ausência do IBGE (`...`, `-`, `X`), datas e valores
  inválidos e não finitos, e fica com a última cotação de cada dia.
- **Carga** (`etl/carga.py`): compara com o que já está no banco e grava só o que é novo ou mudou
  (revisões da fonte), com upsert `ON CONFLICT` em lotes. Reexecutar não duplica nada.
- **Incremental** (`etl/pipeline.py`): cada execução recomeça da última data carregada, menos uma
  margem (7 dias nas séries diárias, 2 meses nas mensais) para capturar revisões.
- **Observabilidade:** cada série gera um registro em `execucoes_etl` com status, linhas extraídas,
  descartadas, inseridas e atualizadas, e o erro em caso de falha. As séries rodam
  independentes e cada uma em sua própria transação: a falha de uma não interrompe as outras nem
  deixa carga pela metade.

## Endpoints

Documentação interativa em `/docs` (Swagger) com a API no ar.

| Método | Rota | O que faz |
|---|---|---|
| GET | `/saude` | Verifica a API e a conexão com o banco |
| GET | `/series` | Catálogo com total de observações e cobertura de datas |
| GET | `/series/{codigo}/observacoes` | Observações, com filtro `inicio`/`fim` e `limite` |
| GET | `/series/{codigo}/resumo` | Mínimo, máximo, média, primeiro/último valor e variação no período |
| GET | `/series/{codigo}/agregado` | Agregação `mensal` ou `anual` em SQL (`GROUP BY`) |
| GET | `/indicadores/ipca-12m` | IPCA acumulado em 12 meses, calculado a partir do número-índice |
| GET | `/etl/execucoes` | Histórico das execuções do pipeline |
| POST | `/etl/execucoes` | Dispara o ETL em segundo plano (header `X-API-Key`) |

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -e ".[dev]"
cp .env.example .env

alembic upgrade head            # cria as tabelas (SQLite em ./indicadores.db)
python -m indicadores.etl       # primeira carga: desde 2015
uvicorn indicadores.api.main:app --reload
```

O ETL aceita `--serie dolar_ptax` (repetível) e `--desde 2020-01-01` para reprocessar um período.
Ele sai com código 1 se alguma série falhar, o que facilita o uso em agendadores (cron, Agendador
de Tarefas do Windows, Kubernetes CronJob).

### Com Docker (PostgreSQL)

```bash
docker compose up -d --build           # banco + API em http://localhost:8000
docker compose run --rm etl            # roda o pipeline
```

## Testes

```bash
pytest                    # SQLite em memória
ruff check . && ruff format --check .
```

A suíte cobre transformação, extração (com transporte HTTP simulado), idempotência, carga
incremental, revisões da fonte, isolamento de falhas, todos os endpoints e a correspondência
entre as migrações do Alembic e os modelos. No CI (GitHub Actions) ela roda também contra um
**PostgreSQL** real, definindo `TEST_DATABASE_URL`.
