import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configurations
DB_NAME = 'green_software_metrics_en.db'
OUTPUT_DIR = '/analysis/output/delta_analysis_en'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def analyze_delta():
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Load data filtering by Delta pattern
    # We use LIKE to find the pattern within the string of multiple patterns
    query = "SELECT * FROM api_metrics WHERE applicable_pattern LIKE '%Just Latest Updates (Delta)%'";
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        print("⚠️ No requests found for the 'Just Latest Updates (Delta)' pattern.")
        conn.close()
        return

    print(f"📊 Analyzing {len(df)} records candidate for Delta pattern...")

    # Convert bytes to KB for better visualization
    df['size_kb'] = df['response_size_bytes'] / 1024

    # 2. Response Size Distribution (Histogram + KDE)
    plt.figure(figsize=(12, 6))
    sns.histplot(df['size_kb'], kde=True, color='#3498db', bins=20)
    plt.title('Response Size Distribution - Delta Candidates', fontsize=14, fontweight='bold')
    plt.xlabel('Response Size (KB)')
    plt.ylabel('Frequency')
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_size_distribution.png')
    plt.close()

    # 3. Latency Distribution (Boxplot by Host)
    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df, x='host', y='latency_seconds', palette='viridis')
    plt.title('Latency Distribution by Host - Delta Candidates', fontsize=14, fontweight='bold')
    plt.xlabel('Host')
    plt.ylabel('Latency (Seconds)')
    plt.xticks(rotation=15)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_latency_distribution.png')
    plt.close()

    # 4. Scatter Plot: Size vs Latency
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df, x='size_kb', y='latency_seconds', hue='host', style='host', s=100, alpha=0.7)
    plt.title('Delta Candidates: Response Size vs Latency', fontsize=14, fontweight='bold')
    plt.xlabel('Response Size (KB)')
    plt.ylabel('Latency (Seconds)')
    plt.grid(True, which="both", ls=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/delta_scatter_size_latency.png')
    plt.close()

    # 5. Descriptive Statistics
    stats = df[['size_kb', 'latency_seconds']].describe()
    print("\n=== Descriptive Statistics (Delta Candidates) ===")
    print(stats)

    conn.close()

if __name__ == "__main__":
    analyze_delta()
    print(f"\n✅ Analysis completed! Charts saved in: {OUTPUT_DIR}")
