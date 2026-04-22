import json
import sqlite3
import pandas as pd
import os

def consolidate():
    # 1. Carregar análise inicial de logs
    with open('/analysis/analysis_results.json', 'r') as f:
        initial_analysis = json.load(f)
    
    # 2. Carregar análise de patterns
    with open('/analysis/patterns_analysis.json', 'r') as f:
        patterns_analysis = json.load(f)
    
    # 3. Carregar métricas reais do banco de dados
    conn = sqlite3.connect('green_software_metrics.db')
    db_df = pd.read_sql_query("SELECT * FROM api_metrics", conn)
    conn.close()
    
    # Resumo do banco
    db_summary = {
        'total_simulated': len(db_df),
        'avg_response_size_kb': float(db_df['response_size_bytes'].mean() / 1024),
        'avg_latency_s': float(db_df['latency_seconds'].mean()),
        'host_metrics': db_df.groupby('host').agg({
            'response_size_bytes': 'mean',
            'latency_seconds': 'mean'
        }).to_dict('index')
    }
    
    # 4. Consolidar tudo
    final_data = {
        'initial': initial_analysis,
        'patterns': patterns_analysis,
        'simulation': db_summary
    }
    
    os.makedirs('/analysis/output/dashboard', exist_ok=True)
    with open('/analysis/output/dashboard/dashboard_data.json', 'w') as f:
        json.dump(final_data, f, indent=2)
    
    print("✅ Dados consolidados com sucesso em /analysis/output/dashboard/dashboard_data.json")

if __name__ == "__main__":
    consolidate()
