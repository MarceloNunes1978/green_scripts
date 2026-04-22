import json
import sqlite3
import pandas as pd
import os

def consolidate():
    # 1. Load initial log analysis (English version)
    with open("/home/ubuntu/skills/green-software-analyzer/references/analysis_results.json", "r") as f:
        initial_analysis = json.load(f)
    
    # 2. Load patterns analysis (English version)
    with open("/home/ubuntu/skills/green-software-analyzer/references/patterns_analysis_en.json", "r") as f:
        patterns_analysis = json.load(f)
    
    # 3. Load real metrics from the database (English version)
    conn = sqlite3.connect("green_software_metrics_en.db")
    db_df = pd.read_sql_query("SELECT * FROM api_metrics", conn)
    conn.close()
    
    # Database summary
    db_summary = {
        "total_simulated": len(db_df),
        "avg_response_size_kb": float(db_df["response_size_bytes"].mean() / 1024),
        "avg_latency_s": float(db_df["latency_seconds"].mean()),
        "host_metrics": db_df.groupby("host").agg({
            "response_size_bytes": "mean",
            "latency_seconds": "mean"
        }).to_dict("index")
    }
    
    # 4. Consolidate everything
    final_data = {
        "initial": initial_analysis,
        "patterns": patterns_analysis,
        "simulation": db_summary
    }
    
    os.makedirs("/home/ubuntu/green_software_report/data", exist_ok=True)
    with open("/home/ubuntu/green_software_report/data/dashboard_data_en.json", "w") as f:
        json.dump(final_data, f, indent=2)
    
    print("✅ Data successfully consolidated to /home/ubuntu/green_software_report/data/dashboard_data_en.json")

if __name__ == "__main__":
    consolidate()
