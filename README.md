# scripts_green

Projeto para analisar logs de APIs, simular tráfego real, medir payload/latência, classificar padrões de Green Software e gerar um dashboard HTML com os resultados.

## Estrutura principal

- `logs/unified_logs.csv`: log consolidado usado pelos scripts.
- `skills/green-software-analyzer/scripts/`: scripts principais de análise, simulação e geração de dashboard.
- `skills/green-software-analyzer/templates/index.html`: dashboard HTML.
- `skills/green-software-analyzer/templates/dashboard_data.json`: JSON consumido pelo dashboard.
- `skills/green-software-analyzer/scripts/green_software_metrics_en.db`: banco SQLite gerado pela simulação.

## Pré-requisitos

- Python 3.10+.
- Dependências Python:

```bash
pip install pandas matplotlib seaborn aiohttp requests numpy
```

## Diretório de trabalho

Os comandos abaixo assumem este diretório:

```bash
cd skills/green-software-analyzer/scripts
```

No PowerShell, a partir da raiz do projeto:

```powershell
Set-Location "C:\ITA\Dissertação\scripts_green\skills\green-software-analyzer\scripts"
```

## Sequência recomendada de execução

### 1. Análise inicial do log

Gera um resumo inicial do tráfego em JSON.

```bash
python analyze_logs_en.py
```

Saída principal:

- `skills/green-software-analyzer/references/analysis_results.json`

### 2. Análise dos padrões de Green Software

Gera métricas agregadas sobre Green by Default, Delta, Wish List e Wish Template.

```bash
python analyze_patterns_en.py
```

Saída principal:

- `skills/green-software-analyzer/references/patterns_analysis_en.json`

### 3. Geração de gráficos estáticos do log

Usa `analysis_results.json` para salvar gráficos PNG.

```bash
python generate_charts_en.py
```

Saída principal:

- `skills/green-software-analyzer/scripts/analysis/output/charts/`

### 4. Simulação de tráfego e geração do banco SQLite

Executa chamadas HTTP reais, grava payload, latência, padrões aplicáveis e parâmetros de query.

Ao final da simulação em inglês, também atualiza automaticamente a tabela:

- `api_parameter_pattern_savings` (economia estimada de bytes por endpoint + parâmetro + padrão)

Primeira execução ou recriação completa do banco:

```bash
python traffic_simulator_en.py --reset
```

Execução de continuação após interrupção, reaproveitando checkpoint:

```bash
python traffic_simulator_en.py
```

Opções úteis:

```bash
# não recalcula api_parameter_pattern_savings no final
python traffic_simulator_en.py --skip-savings

# recalcula e também exporta CSV completo (arquivo grande)
python traffic_simulator_en.py --export-savings-csv
```

Saídas principais:

- `skills/green-software-analyzer/scripts/green_software_metrics_en.db`
- `skills/green-software-analyzer/scripts/progress_checkpoint.txt`
- tabela `api_parameter_pattern_savings` no SQLite
- opcional: `skills/green-software-analyzer/scripts/bytes_saved_by_endpoint_parameter_pattern.csv`

Observação importante:

- O script agora exige `--reset` se encontrar linhas legadas no banco sem `simulated_call_timestamp`.
- O campo `timestamp` deve guardar a data original do log.
- O campo `simulated_call_timestamp` deve guardar a data/hora real da simulação.

### 5. Visualização dos dados do banco

Gera gráficos a partir de `green_software_metrics_en.db`.

```bash
python visualize_db_data_en.py
```

Saída principal:

- `skills/green-software-analyzer/scripts/analysis/output/db_viz_en/`

### 6. Análise específica do padrão Delta

Etapa opcional para aprofundar apenas os candidatos a `Just Latest Updates (Delta)`.

```bash
python analyze_delta_pattern_en.py
```

### 7. Geração do JSON final do dashboard

Consolida:

- análise inicial do log
- análise de padrões
- métricas reais do banco SQLite
- análise de parâmetros de query
- dados de SCI

```bash
python generate_dashboard_json.py
```

Saída principal:

- `skills/green-software-analyzer/templates/dashboard_data.json`

Observação importante:

- Os valores do dashboard só são atualizados depois que este comando é executado.
- Ou seja: sempre que o banco SQLite for alterado por scripts Python, rode novamente `generate_dashboard_json.py`.
- Isso inclui os blocos de:
	- métricas de simulação
	- análise de parâmetros
	- economia estimada por parâmetro/padrão
	- tráfego total estimado (`request`, `response` e `total`)

Sequência mínima para refletir mudanças no dashboard:

```bash
python traffic_simulator_en.py --reset
python generate_dashboard_json.py
```

Se você recalcular a tabela de savings manualmente:

```bash
python compute_bytes_saved.py
python generate_dashboard_json.py
```

### 8. Abrir o dashboard HTML

O arquivo HTML lê `dashboard_data.json` via `fetch`, então o ideal é abrir com um servidor local simples.

No diretório `skills/green-software-analyzer/templates`:

```bash
python -m http.server 8000
```

Depois abra no navegador:

```text
http://localhost:8000/index.html
```

Arquivo do dashboard:

- `skills/green-software-analyzer/templates/index.html`

## Fluxo rápido

Se você quiser rodar o pipeline principal do zero, use esta ordem:

```bash
python analyze_logs_en.py
python analyze_patterns_en.py
python generate_charts_en.py
python traffic_simulator_en.py --reset
python visualize_db_data_en.py
python generate_dashboard_json.py
```

## Como atualizar o dashboard

Sempre que algum script Python alterar o banco SQLite, rode novamente o gerador do JSON do dashboard:

```bash
python generate_dashboard_json.py
```

Sem esse passo, o HTML pode continuar exibindo valores antigos, mesmo que o banco já tenha sido atualizado.

Casos mais comuns:

```bash
# após recriar/atualizar o banco
python traffic_simulator_en.py --reset
python generate_dashboard_json.py

# após recalcular savings
python compute_bytes_saved.py
python generate_dashboard_json.py
```

## Consultas SQL por padrão de Green Software

Cada arquivo contém consultas específicas para análise do respectivo padrão, incluindo totais gerais, economia por parâmetro e top endpoints.

| Padrão | Arquivo |
|--------|---------|
| Green by Default | [`skills/green-software-analyzer/scripts/queries_green_by_default.sql`](skills/green-software-analyzer/scripts/queries_green_by_default.sql) |
| Just Latest Updates (Delta) | [`skills/green-software-analyzer/scripts/queries_just_latest_updates.sql`](skills/green-software-analyzer/scripts/queries_just_latest_updates.sql) |
| Wish List (Sparse Fieldsets) | [`skills/green-software-analyzer/scripts/queries_wish_list.sql`](skills/green-software-analyzer/scripts/queries_wish_list.sql) |
| Wish Template | [`skills/green-software-analyzer/scripts/queries_wish_template.sql`](skills/green-software-analyzer/scripts/queries_wish_template.sql) |

Cada arquivo oferece:

1. **Totais gerais** — requisições, resposta total (KB), economia estimada (KB/MB) e percentual
2. **Economia por parâmetro** — ordenada por impacto decrescente
3. **Top 20 endpoints** — com parâmetros problemáticos e economia por URI
4. **Consultas específicas do padrão** — ex.: endpoints com `limit=-1`, distribuição de `pagesize`, combinações de `fields=`, candidatos a template

Como executar:

```bash
cd skills/green-software-analyzer/scripts
sqlite3 green_software_metrics_en.db
.read queries_green_by_default.sql
```

## Consultas SQL de auditoria

Arquivos disponíveis:

- `skills/green-software-analyzer/scripts/audit_queries.sql`
- `skills/green-software-analyzer/scripts/audit_queries_filtered_templates.sql`

Esses arquivos ajudam a auditar:

- `api_metrics`
- `api_request_parameters`
- cobertura de parâmetros
- filtros por host, período, status e nome/valor de parâmetro

## Problemas comuns

### 1. `FileNotFoundError` para o log

Confirme se existe:

- `logs/unified_logs.csv`

Os scripts em inglês já estão configurados para esse arquivo.

### 2. Banco com timestamps antigos incorretos

Se o banco já foi gerado antes da mudança de schema, ele pode conter linhas antigas em que:

- `timestamp` guarda a data da simulação antiga
- `simulated_call_timestamp` está nulo

Nesse caso, recrie o banco:

```bash
python traffic_simulator_en.py --reset
```

### 3. Dashboard abre vazio no navegador

Não abra `index.html` apenas com duplo clique. Rode um servidor local e acesse por `http://localhost:8000/index.html`.

## Scripts principais

- `analyze_logs_en.py`: resumo inicial do log.
- `analyze_patterns_en.py`: análise dos 4 padrões de Green Software.
- `generate_charts_en.py`: gráficos estáticos do log.
- `traffic_simulator_en.py`: simulação HTTP e persistência no SQLite.
- `visualize_db_data_en.py`: gráficos derivados do banco.
- `generate_dashboard_json.py`: consolidação final para o dashboard.
