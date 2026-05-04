import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Configurations
DB_NAME = 'green_software_metrics_en.db'
OUTPUT_DIR = './analysis/output/db_viz_en'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def analyze_db():
    conn = sqlite3.connect(DB_NAME)
    
    # 1. Load data into DataFrame
    query = "SELECT * FROM api_metrics"
    df = pd.read_sql_query(query, conn)
    
    print(f"📊 Analyzing {len(df)} records from the database...")

    # 2. Distribution of Applicable Design Patterns
    # Since the applicable_pattern column can have multiple comma-separated patterns, let's expand them
    all_patterns = []
    for p_str in df['applicable_pattern']:
        if p_str:
            patterns = [p.strip() for p in p_str.split(',')]
            all_patterns.extend(patterns)
    
    pattern_counts = pd.Series(all_patterns).value_counts()
    
    plt.figure(figsize=(12, 6))
    pattern_counts.plot(kind='barh', color='#27ae60')
    plt.title('Frequency of Suggested Design Patterns', fontsize=14, fontweight='bold')
    plt.xlabel('Number of Occurrences')
    plt.ylabel('Design Pattern')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/pattern_frequency.png')
    plt.close()

    # 3. Average Response Size by Host
    plt.figure(figsize=(12, 6))
    host_size = df.groupby('host')['response_size_bytes'].mean().sort_values() / 1024 # KB
    host_size.plot(kind='barh', color='#3498db')
    plt.title('Average Response Size by Host (KB)', fontsize=14, fontweight='bold')
    plt.xlabel('Average Size (KB)')
    plt.ylabel('Host')
    plt.grid(axis='x', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/avg_size_by_host.png')
    plt.close()

    # 4. Latency vs Response Size
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df, x='response_size_bytes', y='latency_seconds', hue='host', alpha=0.6)
    plt.title('Correlation: Response Size vs Latency', fontsize=14, fontweight='bold')
    plt.xlabel('Response Size (Bytes)')
    plt.ylabel('Latency (Seconds)')
    plt.xscale('log') # Log scale to handle large variations
    plt.grid(True, which="both", ls="-", alpha=0.2)
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/latency_vs_size.png')
    plt.close()

    # 5. Pattern Summary Table by Host
    pattern_by_host = []
    for host in df['host'].unique():
        host_df = df[df['host'] == host]
        host_patterns = []
        for p_str in host_df['applicable_pattern']:
            host_patterns.extend([p.strip() for p in p_str.split(',')])
        
        top_pattern = pd.Series(host_patterns).value_counts().index[0] if host_patterns else "None"
        avg_size = host_df['response_size_bytes'].mean()
        pattern_by_host.append({
            'Host': host,
            'Top Pattern': top_pattern,
            'Avg Size (KB)': round(avg_size / 1024, 2),
            'Avg Latency (s)': round(host_df['latency_seconds'].mean(), 3)
        })
    
    summary_df = pd.DataFrame(pattern_by_host)
    print("\n=== Summary by Host ===")
    print(summary_df.to_string(index=False))

    conn.close()
    return summary_df

if __name__ == "__main__":
    analyze_db()
    print(f"\n✅ Analysis completed! Charts saved in: {OUTPUT_DIR}")
