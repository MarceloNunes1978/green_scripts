import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import json
import os

def generate_charts(analysis_results_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    with open(analysis_results_path, 'r') as f:
        results = json.load(f)

    # Set style for plots
    sns.set_theme(style="whitegrid")

    # Chart 1: Top Hosts (Bar Chart)
    plt.figure(figsize=(10, 6))
    top_hosts = pd.Series(results['top_hosts'])
    sns.barplot(x=top_hosts.values, y=top_hosts.index, palette="viridis")
    plt.title('Top 5 Hosts by Request Count', fontsize=16, fontweight='bold')
    plt.xlabel('Number of Requests')
    plt.ylabel('Host')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_hosts.png'))
    plt.close()
    print("✅ Chart 1 saved")

    # Chart 2: Top Origins (Bar Chart)
    plt.figure(figsize=(10, 6))
    top_origins = pd.Series(results['top_origins'])
    sns.barplot(x=top_origins.values, y=top_origins.index, palette="magma")
    plt.title('Top 10 API Origins by Request Count', fontsize=16, fontweight='bold')
    plt.xlabel('Number of Requests')
    plt.ylabel('API Origin')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_origins.png'))
    plt.close()
    print("✅ Chart 2 saved")

    # Chart 3: Heavy Queries by Host (Pie Chart)
    plt.figure(figsize=(8, 8))
    heavy_queries_hosts = pd.Series(results['heavy_queries_hosts'])
    plt.pie(heavy_queries_hosts, labels=heavy_queries_hosts.index, autopct='%1.1f%%', startangle=140, colors=sns.color_palette("pastel"))
    plt.title('Distribution of Heavy Queries (limit=-1) by Host', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'heavy_queries_hosts.png'))
    plt.close()
    print("✅ Chart 3 saved")

    # Chart 4: Duplicate Requests by Time Window (Line Chart)
    plt.figure(figsize=(10, 6))
    duplicate_data = {k: float(re.search(r'\((.*?)\%\)', v).group(1)) for k, v in results['duplicate_requests_by_window'].items()}
    windows = list(duplicate_data.keys())
    percentages = list(duplicate_data.values())
    sns.lineplot(x=windows, y=percentages, marker='o', color='red')
    plt.title('Percentage of Duplicate Requests by Time Window', fontsize=16, fontweight='bold')
    plt.xlabel('Time Window')
    plt.ylabel('Percentage of Duplicate Requests (%)')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'duplicate_requests_by_window.png'))
    plt.close()
    print("✅ Chart 4 saved")

    # Chart 5: Top Cache Potential Endpoints (Bar Chart)
    plt.figure(figsize=(12, 7))
    cache_df = pd.DataFrame(results['top_cache_potential_endpoints'])
    sns.barplot(x='cache_ratio', y='endpoint', data=cache_df, palette="rocket")
    plt.title('Top 10 Endpoints by Cache Potential (Requests/Unique URI)', fontsize=16, fontweight='bold')
    plt.xlabel('Cache Ratio')
    plt.ylabel('Endpoint')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'top_cache_potential_endpoints.png'))
    plt.close()
    print("✅ Chart 5 saved")

    # Chart 6: Language Distribution (Bar Chart)
    plt.figure(figsize=(10, 6))
    lang_dist = pd.Series(results['language_distribution'])
    sns.barplot(x=lang_dist.values, y=lang_dist.index, palette="cubehelix")
    plt.title('Language Distribution of Requests', fontsize=16, fontweight='bold')
    plt.xlabel('Percentage (%)')
    plt.ylabel('Language')
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'language_distribution.png'))
    plt.close()
    print("✅ Chart 6 saved")

    print("✅ All charts generated successfully!")

if __name__ == "__main__":
    # Example usage (assuming analysis_results.json is in /home/ubuntu/analysis/output/)
    # For skill execution, paths will be passed as arguments
    # For local testing:
    # generate_charts("/home/ubuntu/analysis/output/analysis_results.json", "/home/ubuntu/analysis/output/charts")
    pass
