---
name: green-software-analyzer
description: "Analisa logs CSV para identificar padrões de Green Software, simula tráfego de API para medir tamanhos de payload e latência, classifica requisições por padrões de design aplicáveis (Green by Default, Just Latest Updates, Wish List, Wish Template), e gera relatórios web interativos e insights de banco de dados. Use esta skill para: identificar oportunidades de otimização no uso de APIs, medir o impacto de padrões de design de Green Software, e gerar relatórios acionáveis."
---

# Green Software Analyzer

## Visão Geral

Esta skill fornece um conjunto de ferramentas para analisar o tráfego de APIs a partir de logs, simular requisições para coletar métricas detalhadas de Green Software e visualizar os resultados em relatórios interativos e bancos de dados. O objetivo é identificar e quantificar o impacto de padrões de design que visam reduzir o consumo de recursos (energia, banda, CPU).

## Capacidades Principais

### 1. Análise de Logs de Green Software

Processa logs de requisições em formato CSV para identificar padrões de uso, como requisições duplicadas, queries pesadas (`limit=-1`), e uso de paginação. Gera um relatório JSON com insights e gráficos estáticos que resumem o comportamento do tráfego.

-   **Script**: `scripts/analyze_logs.py`
-   **Entrada**: Arquivo CSV de logs (ex: `/home/ubuntu/upload/logs.csv`)
-   **Saída**: JSON de resultados (`references/analysis_results.json`), gráficos PNG (`analysis/output/`) e um relatório HTML interativo (`templates/index.html`).

### 2. Simulação de Tráfego e Coleta de Métricas

Realiza requisições HTTP baseadas nos logs fornecidos, medindo o tamanho exato do payload de request e response, latência e status HTTP. Classifica cada requisição com base em sua aplicabilidade a quatro padrões de design de Green Software:

-   **Green by Default**: Requisições que poderiam ser mais eficientes por padrão (ex: sem `limit=-1`, com paginação, com seleção de campos).
-   **Just Latest Updates (Delta)**: Requisições para dados voláteis que se beneficiariam do envio apenas de deltas.
-   **Wish List (Sparse Fieldsets)**: Requisições que poderiam especificar campos para reduzir o payload.
-   **Wish Template**: Requisições complexas que se beneficiariam de templates de resposta pré-definidos.

Os dados coletados são armazenados em um banco de dados SQLite (ou PostgreSQL, com adaptação).

-   **Script**: `scripts/traffic_simulator.py`
-   **Entrada**: Arquivo CSV de logs (ex: `/home/ubuntu/upload/logs.csv`)
-   **Saída**: Banco de dados SQLite (`green_software_metrics.db`) com métricas detalhadas e classificação de padrões.

### 3. Visualização de Dados do Banco de Dados

Analisa o banco de dados gerado pela simulação para criar visualizações que destacam a distribuição dos padrões de Green Software, a relação entre tamanho de resposta e latência, e o impacto potencial de cada padrão. Isso permite uma compreensão aprofundada das oportunidades de otimização.

-   **Script**: `scripts/visualize_db_data.py`
-   **Entrada**: Banco de dados SQLite (`green_software_metrics.db`)
-   **Saída**: Gráficos PNG detalhados (`analysis/output/db_viz/`).

## Fluxo de Trabalho Recomendado

1.  **Preparar Logs**: Forneça seus logs em formato CSV.
2.  **Análise Inicial**: Execute `scripts/analyze_logs.py` para uma visão geral do tráfego e identificação de problemas básicos.
3.  **Simulação Detalhada**: Execute `scripts/traffic_simulator.py` para simular o tráfego, coletar métricas de payload/latência e classificar as requisições pelos padrões de Green Software.
4.  **Análise de Padrões**: Execute `scripts/analyze_delta_pattern.py` (ou scripts similares para outros padrões) para aprofundar a análise em padrões específicos.
5.  **Visualização de Insights**: Execute `scripts/visualize_db_data.py` para gerar gráficos a partir do banco de dados e entender o impacto potencial das otimizações.
6.  **Relatório Interativo**: Utilize o `templates/index.html` para visualizar os resultados de forma interativa.

## Recursos

-   **`scripts/`**: Contém os scripts Python para análise, simulação e visualização.
-   **`references/`**: Armazena resultados JSON da análise inicial e de padrões.
-   **`templates/`**: Inclui o template HTML para o relatório web interativo.
