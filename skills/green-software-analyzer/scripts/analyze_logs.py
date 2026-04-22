import pandas as pd
import numpy as np
import json
from urllib.parse import urlparse, parse_qs
from collections import Counter
import re
import os
from html import escape

os.makedirs('./analysis/output', exist_ok=True)

# ─── Carregar dados ───────────────────────────────────────────────────────────
df = pd.read_csv('../../../logs/unified_logs.csv')
df.columns = ['timestamp', 'host', 'uri']

# Parse timestamp
df['timestamp'] = pd.to_datetime(df['timestamp'], format='%b %d, %Y @ %H:%M:%S.%f')
df = df.sort_values('timestamp').reset_index(drop=True)

print(f"Total de registros: {len(df)}")
print(f"Período: {df['timestamp'].min()} → {df['timestamp'].max()}")
print(f"Duração: {df['timestamp'].max() - df['timestamp'].min()}")

# ─── 1. Distribuição por host (ator) ─────────────────────────────────────────
host_counts = df['host'].value_counts().reset_index()
host_counts.columns = ['host', 'requests']
host_counts['pct'] = (host_counts['requests'] / len(df) * 100).round(2)
print("\n=== Distribuição por Host ===")
print(host_counts.to_string())

# ─── 2. Extrair endpoint base (sem query params) ──────────────────────────────
df['endpoint'] = df['uri'].apply(lambda x: x.split('?')[0] if '?' in x else x)
df['has_params'] = df['uri'].apply(lambda x: '?' in x)
df['api_version'] = df['uri'].apply(lambda x: 'v1' if '/v1/' in x else ('v2' if '/v2/' in x else 'other'))

# ─── 3. Top endpoints ─────────────────────────────────────────────────────────
top_endpoints = df['endpoint'].value_counts().head(30).reset_index()
top_endpoints.columns = ['endpoint', 'count']
top_endpoints['pct'] = (top_endpoints['count'] / len(df) * 100).round(2)
print("\n=== Top 30 Endpoints ===")
print(top_endpoints.to_string())

# ─── 4. Análise temporal ──────────────────────────────────────────────────────
df['hour'] = df['timestamp'].dt.hour
df['minute'] = df['timestamp'].dt.minute
df['second'] = df['timestamp'].dt.second
df['minute_bin'] = df['timestamp'].dt.floor('1min')

requests_per_minute = df.groupby('minute_bin').size().reset_index(name='requests')
requests_per_minute['minute_bin_str'] = requests_per_minute['minute_bin'].dt.strftime('%H:%M')

print("\n=== Requests por Minuto (estatísticas) ===")
print(requests_per_minute['requests'].describe())

requests_per_hour = df.groupby('hour').size().reset_index(name='requests')
print("\n=== Requests por Hora ===")
print(requests_per_hour.to_string())

# ─── 5. Análise de repetição de requests (duplicatas potenciais) ───────────────
# Requests idênticas (mesmo host + uri) dentro de janelas de tempo
df_sorted = df.sort_values(['host', 'uri', 'timestamp'])

# Detectar requests duplicadas exatas (mesmo host + uri) em janela de 60s
df_sorted['prev_host'] = df_sorted['host'].shift(1)
df_sorted['prev_uri'] = df_sorted['uri'].shift(1)
df_sorted['prev_ts'] = df_sorted['timestamp'].shift(1)
df_sorted['time_diff'] = (df_sorted['timestamp'] - df_sorted['prev_ts']).dt.total_seconds()

# Duplicatas: mesmo host+uri em menos de 60 segundos
duplicates_60s = df_sorted[
    (df_sorted['host'] == df_sorted['prev_host']) &
    (df_sorted['uri'] == df_sorted['prev_uri']) &
    (df_sorted['time_diff'] <= 60) &
    (df_sorted['time_diff'] >= 0)
]
print(f"\n=== Requests duplicadas em janela de 60s ===")
print(f"Total: {len(duplicates_60s)} ({len(duplicates_60s)/len(df)*100:.1f}% do total)")

# Duplicatas em 5 segundos
duplicates_5s = duplicates_60s[duplicates_60s['time_diff'] <= 5]
print(f"Total em 5s: {len(duplicates_5s)} ({len(duplicates_5s)/len(df)*100:.1f}% do total)")

# ─── 6. Análise de parâmetros redundantes ─────────────────────────────────────
# Endpoints com muitas variações de parâmetros (candidatos a cache/batch)
endpoint_variations = df.groupby('endpoint')['uri'].nunique().reset_index()
endpoint_variations.columns = ['endpoint', 'unique_uris']
endpoint_variations = endpoint_variations.sort_values('unique_uris', ascending=False).head(20)
print("\n=== Endpoints com mais variações de URI (candidatos a cache) ===")
print(endpoint_variations.to_string())

# ─── 7. Análise de paginação (pagesize, pagenumber) ───────────────────────────
pagination_requests = df[df['uri'].str.contains('pagesize|pagenumber', case=False, na=False)]
print(f"\n=== Requests com paginação: {len(pagination_requests)} ({len(pagination_requests)/len(df)*100:.1f}%) ===")

# Extrair pagesizes
pagesizes = []
for uri in pagination_requests['uri']:
    m = re.search(r'pagesize=(\d+)', uri, re.IGNORECASE)
    if m:
        pagesizes.append(int(m.group(1)))

if pagesizes:
    ps_series = pd.Series(pagesizes)
    print("Pagesize stats:")
    print(ps_series.describe())
    print("Pagesize value_counts:")
    print(ps_series.value_counts().head(10))

# ─── 8. Análise por categoria de endpoint ─────────────────────────────────────
def categorize_endpoint(endpoint):
    ep = endpoint.lower()
    if 'weather' in ep: return 'Weather'
    elif 'event' in ep: return 'Events'
    elif 'echarging' in ep or 'echargingstation' in ep or 'echargingplug' in ep: return 'ECharging'
    elif 'accommodation' in ep: return 'Accommodation'
    elif 'activity' in ep or 'poi' in ep or 'odhactivity' in ep: return 'Activity/POI'
    elif 'gastronomy' in ep: return 'Gastronomy'
    elif 'ski' in ep: return 'Ski'
    elif 'linkstation' in ep or 'parkingstation' in ep or 'bikesharing' in ep: return 'Mobility'
    elif 'municipality' in ep or 'district' in ep or 'region' in ep: return 'Geography'
    elif 'tag' in ep or 'type' in ep or 'category' in ep: return 'Metadata'
    else: return 'Other'

df['category'] = df['endpoint'].apply(categorize_endpoint)
category_counts = df['category'].value_counts().reset_index()
category_counts.columns = ['category', 'count']
category_counts['pct'] = (category_counts['count'] / len(df) * 100).round(2)
print("\n=== Requests por Categoria ===")
print(category_counts.to_string())

# ─── 9. Análise de origem (origin param) ──────────────────────────────────────
origins = []
for uri in df['uri']:
    m = re.search(r'origin=([^&]+)', uri, re.IGNORECASE)
    if m:
        origins.append(m.group(1))
    else:
        origins.append('unknown')

df['origin'] = origins
origin_counts = df[df['origin'] != 'unknown']['origin'].value_counts().head(20).reset_index()
origin_counts.columns = ['origin', 'count']
print(f"\n=== Origins identificadas: {df[df['origin']!='unknown']['origin'].nunique()} ===")
print(origin_counts.to_string())

# ─── 10. Análise de requests limit=-1 (sem paginação, potencial heavy query) ──
heavy_requests = df[df['uri'].str.contains('limit=-1', na=False)]
print(f"\n=== Requests com limit=-1 (heavy queries): {len(heavy_requests)} ({len(heavy_requests)/len(df)*100:.1f}%) ===")
print(heavy_requests['host'].value_counts())

# ─── 11. Taxa de requests por segundo ─────────────────────────────────────────
df['second_bin'] = df['timestamp'].dt.floor('1s')
rps = df.groupby('second_bin').size()
print(f"\n=== Requests por segundo ===")
print(rps.describe())

# ─── 12. Análise de idioma (language param) ───────────────────────────────────
languages = []
for uri in df['uri']:
    m = re.search(r'language=([^&]+)', uri, re.IGNORECASE)
    if m:
        languages.append(m.group(1).lower())
    else:
        languages.append('not_specified')

df['language'] = languages
lang_counts = df['language'].value_counts().reset_index()
lang_counts.columns = ['language', 'count']
lang_counts['pct'] = (lang_counts['count'] / len(df) * 100).round(2)
print("\n=== Distribuição por Idioma ===")
print(lang_counts.head(10).to_string())

# ─── 13. Análise de potencial de cache por endpoint ───────────────────────────
# Endpoints com alta frequência e baixa variação = alto potencial de cache
endpoint_stats = df.groupby('endpoint').agg(
    total_requests=('uri', 'count'),
    unique_uris=('uri', 'nunique')
).reset_index()
endpoint_stats['cache_ratio'] = (endpoint_stats['total_requests'] / endpoint_stats['unique_uris']).round(2)
endpoint_stats = endpoint_stats[endpoint_stats['total_requests'] >= 100]
endpoint_stats = endpoint_stats.sort_values('cache_ratio', ascending=False).head(20)
print("\n=== Top endpoints com maior potencial de cache (ratio requests/unique_uris) ===")
print(endpoint_stats.to_string())

# ─── 14. Análise de requests repetidas por janela de tempo ────────────────────
# Quantas requests idênticas ocorrem em janelas de 1, 5, 10, 30, 60 segundos
windows = [1, 5, 10, 30, 60]
window_results = {}
for w in windows:
    dup = df_sorted[
        (df_sorted['host'] == df_sorted['prev_host']) &
        (df_sorted['uri'] == df_sorted['prev_uri']) &
        (df_sorted['time_diff'] <= w) &
        (df_sorted['time_diff'] >= 0)
    ]
    window_results[w] = len(dup)
    print(f"Duplicatas em janela de {w}s: {len(dup)} ({len(dup)/len(df)*100:.1f}%)")

# ─── Salvar resultados em JSON para uso na página web ─────────────────────────
results = {
    'summary': {
        'total_requests': int(len(df)),
        'period_start': str(df['timestamp'].min()),
        'period_end': str(df['timestamp'].max()),
        'duration_minutes': float((df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60),
        'unique_hosts': int(df['host'].nunique()),
        'unique_endpoints': int(df['endpoint'].nunique()),
        'unique_uris': int(df['uri'].nunique()),
        'requests_with_params': int(df['has_params'].sum()),
        'heavy_queries_limit_minus1': int(len(heavy_requests)),
        'pagination_requests': int(len(pagination_requests)),
    },
    'hosts': host_counts.to_dict(orient='records'),
    'top_endpoints': top_endpoints.head(20).to_dict(orient='records'),
    'categories': category_counts.to_dict(orient='records'),
    'requests_per_minute': requests_per_minute.to_dict(orient='records'),
    'requests_per_hour': requests_per_hour.to_dict(orient='records'),
    'languages': lang_counts.head(10).to_dict(orient='records'),
    'origins': origin_counts.head(15).to_dict(orient='records'),
    'cache_candidates': endpoint_stats.head(15).to_dict(orient='records'),
    'duplicate_windows': {str(k): int(v) for k, v in window_results.items()},
    'duplicate_pct_60s': float(len(duplicates_60s) / len(df) * 100),
    'duplicate_pct_5s': float(len(duplicates_5s) / len(df) * 100),
    'rps_stats': {
        'mean': float(rps.mean()),
        'max': float(rps.max()),
        'p95': float(rps.quantile(0.95)),
        'p99': float(rps.quantile(0.99)),
    },
    'endpoint_variations': endpoint_variations.to_dict(orient='records'),
    'pagesize_distribution': ps_series.value_counts().head(10).reset_index().rename(columns={'index':'pagesize',0:'count'}).to_dict(orient='records') if pagesizes else [],
}


def _fmt_int(value):
        return f"{int(value):,}".replace(',', '.')


def _fmt_pct(value):
        return f"{float(value):.2f}%".replace('.', ',')


def _rows_to_html(rows, columns):
        html_rows = []
        for row in rows:
                cells = []
                for col in columns:
                        cell_value = row.get(col, '')
                        cells.append(f"<td>{escape(str(cell_value))}</td>")
                html_rows.append(f"<tr>{''.join(cells)}</tr>")
        return '\n'.join(html_rows)


def generate_template_html(data, output_path):
        summary = data['summary']
        top_hosts = data['hosts'][:10]
        top_endpoints = data['top_endpoints'][:15]
        top_categories = data['categories'][:10]

        hosts_rows = []
        for idx, row in enumerate(top_hosts, start=1):
                hosts_rows.append({
                        '#': idx,
                        'Host': row.get('host', ''),
                        'Requests': _fmt_int(row.get('requests', 0)),
                        'Participação': _fmt_pct(row.get('pct', 0)),
                })

        endpoints_rows = []
        for idx, row in enumerate(top_endpoints, start=1):
                endpoints_rows.append({
                        '#': idx,
                        'Endpoint': row.get('endpoint', ''),
                        'Requests': _fmt_int(row.get('count', 0)),
                        'Participação': _fmt_pct(row.get('pct', 0)),
                })

        categories_rows = []
        for idx, row in enumerate(top_categories, start=1):
                categories_rows.append({
                        '#': idx,
                        'Categoria': row.get('category', ''),
                        'Requests': _fmt_int(row.get('count', 0)),
                        'Participação': _fmt_pct(row.get('pct', 0)),
                })

        html_template = f"""<!DOCTYPE html>
<html lang=\"pt-BR\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>Template - Resultado da Análise de Logs</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            background: #f4f6f9;
            color: #1f2937;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 24px;
        }}
        h1 {{
            margin: 0 0 8px 0;
            font-size: 1.8rem;
            color: #14532d;
        }}
        .subtitle {{
            margin-bottom: 20px;
            color: #4b5563;
        }}
        .kpis {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .card {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 14px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}
        .card-label {{
            font-size: 0.8rem;
            text-transform: uppercase;
            color: #6b7280;
            margin-bottom: 6px;
        }}
        .card-value {{
            font-size: 1.4rem;
            font-weight: 700;
            color: #111827;
        }}
        section {{
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        h2 {{
            font-size: 1.05rem;
            color: #14532d;
            margin-top: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
        }}
        th, td {{
            border-bottom: 1px solid #e5e7eb;
            text-align: left;
            padding: 8px;
        }}
        th {{
            background: #ecfdf5;
            color: #065f46;
        }}
    </style>
</head>
<body>
    <div class=\"container\">
        <h1>Template de Resultados da Análise</h1>
        <p class=\"subtitle\">Arquivo gerado automaticamente a partir de analysis_results.json.</p>

        <div class=\"kpis\">
            <div class=\"card\">
                <div class=\"card-label\">Total de Requests</div>
                <div class=\"card-value\">{_fmt_int(summary['total_requests'])}</div>
            </div>
            <div class=\"card\">
                <div class=\"card-label\">Hosts Únicos</div>
                <div class=\"card-value\">{_fmt_int(summary['unique_hosts'])}</div>
            </div>
            <div class=\"card\">
                <div class=\"card-label\">Endpoints Únicos</div>
                <div class=\"card-value\">{_fmt_int(summary['unique_endpoints'])}</div>
            </div>
            <div class=\"card\">
                <div class=\"card-label\">Requests com Parâmetros</div>
                <div class=\"card-value\">{_fmt_int(summary['requests_with_params'])}</div>
            </div>
            <div class=\"card\">
                <div class=\"card-label\">Duplicatas em 60s</div>
                <div class=\"card-value\">{_fmt_pct(data['duplicate_pct_60s'])}</div>
            </div>
            <div class=\"card\">
                <div class=\"card-label\">Heavy Queries (limit=-1)</div>
                <div class=\"card-value\">{_fmt_int(summary['heavy_queries_limit_minus1'])}</div>
            </div>
        </div>

        <section>
            <h2>Top Hosts</h2>
            <table>
                <thead>
                    <tr><th>#</th><th>Host</th><th>Requests</th><th>Participação</th></tr>
                </thead>
                <tbody>
                    {_rows_to_html(hosts_rows, ['#', 'Host', 'Requests', 'Participação'])}
                </tbody>
            </table>
        </section>

        <section>
            <h2>Top Endpoints</h2>
            <table>
                <thead>
                    <tr><th>#</th><th>Endpoint</th><th>Requests</th><th>Participação</th></tr>
                </thead>
                <tbody>
                    {_rows_to_html(endpoints_rows, ['#', 'Endpoint', 'Requests', 'Participação'])}
                </tbody>
            </table>
        </section>

        <section>
            <h2>Categorias</h2>
            <table>
                <thead>
                    <tr><th>#</th><th>Categoria</th><th>Requests</th><th>Participação</th></tr>
                </thead>
                <tbody>
                    {_rows_to_html(categories_rows, ['#', 'Categoria', 'Requests', 'Participação'])}
                </tbody>
            </table>
        </section>
    </div>
</body>
</html>
"""

        with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_template)

with open('./analysis/output/analysis_results.json', 'w') as f:
    json.dump(results, f, indent=2, default=str)

generate_template_html(results, './analysis/output/template.html')

print("\n✅ Análise concluída! Resultados salvos em analysis_results.json e template.html")
