import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import re
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_LOGS = os.path.join(SCRIPT_DIR, '../../../logs/unified_logs.csv')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, 'analysis/output/charts')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Paleta green software
COLORS = ['#2ecc71', '#27ae60', '#1abc9c', '#16a085', '#3498db', '#2980b9', '#9b59b6', '#8e44ad', '#e74c3c', '#c0392b']
GREEN_PALETTE = ['#1a7a4a', '#2ecc71', '#27ae60', '#1abc9c', '#16a085', '#0e6655', '#0a5c45', '#3d9970', '#52be80', '#82e0aa']

# ─── Carregar dados ───────────────────────────────────────────────────────────
df = pd.read_csv(CSV_LOGS)
df.columns = ['timestamp', 'host', 'uri']
df['timestamp'] = pd.to_datetime(df['timestamp'], format='%b %d, %Y @ %H:%M:%S.%f')
df = df.sort_values('timestamp').reset_index(drop=True)
df['endpoint'] = df['uri'].apply(lambda x: x.split('?')[0] if '?' in x else x)
df['minute_bin'] = df['timestamp'].dt.floor('1min')
df['second_bin'] = df['timestamp'].dt.floor('1s')

def categorize_endpoint(endpoint):
    ep = endpoint.lower()
    if 'weather' in ep: return 'Weather'
    elif 'event' in ep: return 'Events'
    elif 'echarging' in ep: return 'ECharging'
    elif 'accommodation' in ep: return 'Accommodation'
    elif 'activity' in ep or 'poi' in ep or 'odhactivity' in ep: return 'Activity/POI'
    elif 'gastronomy' in ep: return 'Gastronomy'
    elif 'ski' in ep: return 'Ski'
    elif 'linkstation' in ep or 'parkingstation' in ep or 'bikesharing' in ep or 'carsharing' in ep: return 'Mobility'
    elif 'municipality' in ep or 'district' in ep or 'region' in ep: return 'Geography'
    elif 'tag' in ep or 'type' in ep or 'category' in ep: return 'Metadata'
    else: return 'Other'

df['category'] = df['endpoint'].apply(categorize_endpoint)

# ─── Chart 1: Requests por minuto (série temporal) ────────────────────────────
fig, ax = plt.subplots(figsize=(14, 5))
rpm = df.groupby('minute_bin').size().reset_index(name='requests')
ax.fill_between(rpm['minute_bin'], rpm['requests'], alpha=0.4, color='#2ecc71')
ax.plot(rpm['minute_bin'], rpm['requests'], color='#1a7a4a', linewidth=1.5)
ax.set_title('Requests por Minuto — 24 de Março de 2025', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('Horário', fontsize=11)
ax.set_ylabel('Nº de Requests', fontsize=11)
ax.grid(True, alpha=0.3, linestyle='--')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'requests_per_minute.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 1 salvo")

# ─── Chart 2: Distribuição por host ───────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
host_counts = df['host'].value_counts()
# Simplificar nomes
host_labels = [h.replace('tourism.', 'T.').replace('mobility.', 'M.').replace('.opendatahub', '.ODH') for h in host_counts.index]
bars = ax.barh(host_labels, host_counts.values, color=GREEN_PALETTE[:len(host_counts)])
ax.set_title('Distribuição de Requests por Host (Ator)', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('Número de Requests', fontsize=11)
for bar, val in zip(bars, host_counts.values):
    ax.text(bar.get_width() + 500, bar.get_y() + bar.get_height()/2,
            f'{val:,} ({val/len(df)*100:.1f}%)', va='center', fontsize=9)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(True, axis='x', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'requests_by_host.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 2 salvo")

# ─── Chart 3: Distribuição por categoria ──────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 7))
cat_counts = df['category'].value_counts()
wedges, texts, autotexts = ax.pie(
    cat_counts.values,
    labels=cat_counts.index,
    autopct='%1.1f%%',
    colors=GREEN_PALETTE[:len(cat_counts)],
    startangle=90,
    pctdistance=0.8
)
for text in texts:
    text.set_fontsize(10)
for autotext in autotexts:
    autotext.set_fontsize(9)
    autotext.set_fontweight('bold')
ax.set_title('Distribuição de Requests por Categoria de API', fontsize=14, fontweight='bold', pad=15)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'requests_by_category.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 3 salvo")

# ─── Chart 4: Janelas de duplicação ───────────────────────────────────────────
df_sorted = df.sort_values(['host', 'uri', 'timestamp'])
df_sorted['prev_host'] = df_sorted['host'].shift(1)
df_sorted['prev_uri'] = df_sorted['uri'].shift(1)
df_sorted['prev_ts'] = df_sorted['timestamp'].shift(1)
df_sorted['time_diff'] = (df_sorted['timestamp'] - df_sorted['prev_ts']).dt.total_seconds()

windows = [1, 5, 10, 30, 60]
dup_counts = []
for w in windows:
    dup = df_sorted[
        (df_sorted['host'] == df_sorted['prev_host']) &
        (df_sorted['uri'] == df_sorted['prev_uri']) &
        (df_sorted['time_diff'] <= w) &
        (df_sorted['time_diff'] >= 0)
    ]
    dup_counts.append(len(dup))

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar([f'{w}s' for w in windows], dup_counts, color=['#82e0aa', '#52be80', '#27ae60', '#1e8449', '#1a5c33'])
for bar, val in zip(bars, dup_counts):
    pct = val / len(df) * 100
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 500,
            f'{val:,}\n({pct:.1f}%)', ha='center', va='bottom', fontsize=10, fontweight='bold')
ax.set_title('Requests Duplicadas por Janela de Tempo', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('Janela de Tempo', fontsize=11)
ax.set_ylabel('Nº de Requests Duplicadas', fontsize=11)
ax.axhline(y=len(df), color='red', linestyle='--', alpha=0.5, label=f'Total ({len(df):,})')
ax.legend(fontsize=10)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(True, axis='y', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'duplicate_windows.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 4 salvo")

# ─── Chart 5: Top 10 endpoints por volume ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 7))
top10 = df['endpoint'].value_counts().head(10)
# Encurtar labels
labels = []
for ep in top10.index:
    parts = ep.split('/')
    label = '/'.join(parts[-2:]) if len(parts) > 2 else ep
    labels.append(label[:45])
bars = ax.barh(labels[::-1], top10.values[::-1], color=GREEN_PALETTE[:10])
for bar, val in zip(bars, top10.values[::-1]):
    ax.text(bar.get_width() + 100, bar.get_y() + bar.get_height()/2,
            f'{val:,}', va='center', fontsize=9)
ax.set_title('Top 10 Endpoints por Volume de Requests', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('Número de Requests', fontsize=11)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(True, axis='x', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'top_endpoints.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 5 salvo")

# ─── Chart 6: Distribuição por idioma ─────────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
languages = []
for uri in df['uri']:
    m = re.search(r'language=([^&]+)', uri, re.IGNORECASE)
    if m:
        languages.append(m.group(1).lower())
    else:
        languages.append('não especificado')
lang_series = pd.Series(languages)
lang_counts = lang_series.value_counts().head(8)
bars = ax.bar(lang_counts.index, lang_counts.values, color=GREEN_PALETTE[:len(lang_counts)])
for bar, val in zip(bars, lang_counts.values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 200,
            f'{val:,}\n({val/len(df)*100:.1f}%)', ha='center', va='bottom', fontsize=9)
ax.set_title('Distribuição de Requests por Idioma', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('Idioma', fontsize=11)
ax.set_ylabel('Nº de Requests', fontsize=11)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(True, axis='y', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'language_distribution.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 6 salvo")

# ─── Chart 7: Potencial de economia por estratégia ────────────────────────────
fig, ax = plt.subplots(figsize=(10, 6))
strategies = [
    'Cache (60s TTL)',
    'Cache (30s TTL)',
    'Cache (10s TTL)',
    'Cache (5s TTL)',
    'Batch de Paginação',
    'Remoção limit=-1',
]
savings_pct = [61.3, 56.9, 48.2, 43.1, 15.7, 7.4]
colors_strat = ['#1a5c33', '#1e8449', '#27ae60', '#52be80', '#3498db', '#9b59b6']
bars = ax.barh(strategies, savings_pct, color=colors_strat)
for bar, val in zip(bars, savings_pct):
    ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
            f'{val:.1f}%', va='center', fontsize=11, fontweight='bold')
ax.set_title('Potencial de Redução de Requests por Estratégia', fontsize=14, fontweight='bold', pad=15)
ax.set_xlabel('% de Requests que poderiam ser eliminadas', fontsize=11)
ax.set_xlim(0, 75)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.grid(True, axis='x', alpha=0.3, linestyle='--')
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, 'savings_by_strategy.png'), dpi=150, bbox_inches='tight')
plt.close()
print("✅ Chart 7 salvo")

print("\n✅ Todos os gráficos gerados com sucesso!")
