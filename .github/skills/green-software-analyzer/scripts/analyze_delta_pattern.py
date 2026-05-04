import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configurações
DB_NAME = 'green_software_metrics.db'
OUTPUT_DIR = '/home/ubuntu/analysis/output/delta_analysis'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def analyze_delta():
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Carregar dados filtrando pelo padrão Delta
    # Usamos LIKE para encontrar o padrão dentro da string de múltiplos padrões
    query = "SELECT * FROM api_metrics WHERE applicable_pattern LIKE '%Just Latest Updates (Delta)%'"
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("⚠️ Nenhuma requisição encontrada para o padrão 'Just Latest Updates (Delta)'.")
        conn.close()
        return

    print(f"📊 Analisando {len(df)} registros candidatos ao padrão Delta...")

    # Converter bytes para KB para melhor visualização
    df['size_kb'] = df['response_size_bytes'] / 1024

    # 2. Distribuição de Tamanho de Resposta (Histograma + KDE)
    plt.figure(figsize=(12, 6))
    sns.histplot(df['size_kb'], kde=True, color='#3498db', bins=20)
    plt.title('Distribuição de Tamanho de Resposta - Candidatos a Delta', fontsize=14, fontweight='bold')
    plt.xlabel('Tamanho da Resposta (KB)')
    plt.ylabel('Frequência')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_size_distribution.png')
    plt.close()

    # 3. Distribuição de Latência (Boxplot por Host)
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df, x='host', y='latency_seconds', palette='viridis')
    plt.title('Distribuição de Latência por Host - Candidatos a Delta', fontsize=14, fontweight='bold')
    plt.xlabel('Host')
    plt.ylabel('Latência (Segundos)')
    plt.xticks(rotation=15)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_latency_distribution.png')
    plt.close()

    # 4. Gráfico de Dispersão: Tamanho vs Latência
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df, x='size_kb', y='latency_seconds', hue='host', style='host', s=100, alpha=0.7)
    plt.title('Candidatos a Delta: Tamanho da Resposta vs Latência', fontsize=14, fontweight='bold')
    plt.xlabel('Tamanho da Resposta (KB)')
    plt.ylabel('Latência (Segundos)')
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_scatter_size_latency.png')
    plt.close()

    # 5. Estatísticas Descritivas
    stats = df[['size_kb', 'latency_seconds']].describe()
    print("\n=== Estatísticas Descritivas (Candidatos a Delta) ===")
    print(stats)

    conn.close()

if __name__ == "__main__":
    analyze_delta()
    print(f"\n✅ Análise concluída! Gráficos salvos em: {OUTPUT_DIR}")
