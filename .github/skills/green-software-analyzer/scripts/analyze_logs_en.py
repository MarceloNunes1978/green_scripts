import pandas as pd
import json
import re
from urllib.parse import urlparse, parse_qs

def analyze_logs(csv_path):
    df = pd.read_csv(csv_path)
    df.columns = ["timestamp", "host", "uri"]

    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%b %d, %Y @ %H:%M:%S.%f")

    # Extract origin (first part of URI path)
    df["origin"] = df["uri"].apply(lambda x: urlparse(x).path.split("/")[1] if urlparse(x).path else "")
    df["origin"] = df["origin"].replace("v1", "API_v1").replace("v2", "API_v2").replace("api", "API_General")

    # Extract language from URI
    df["language"] = df["uri"].apply(lambda x: parse_qs(urlparse(x).query).get("language", ["not_specified"])[0])

    # Identify heavy queries (limit=-1)
    heavy_queries = df[df["uri"].str.contains("limit=-1", na=False)]

    # Calculate duplicate requests within time windows
    df_sorted = df.sort_values(by=["host", "uri", "timestamp"])
    df_sorted["prev_timestamp"] = df_sorted.groupby(["host", "uri"])["timestamp"].shift(1)

    duplicate_counts = {}
    for window in ["1s", "5s", "10s", "30s", "60s"]:
        df_sorted["time_diff"] = (df_sorted["timestamp"] - df_sorted["prev_timestamp"]).dt.total_seconds()
        duplicates = df_sorted[df_sorted["time_diff"] <= pd.to_timedelta(window).total_seconds()]
        duplicate_counts[window] = len(duplicates)

    # Analyze cache potential (ratio of total requests to unique URIs per endpoint)
    df["endpoint"] = df["uri"].apply(lambda x: x.split("?")[0])
    endpoint_counts = df.groupby("endpoint").size().reset_index(name="total_requests")
    unique_uris_per_endpoint = df.groupby("endpoint")["uri"].nunique().reset_index(name="unique_uris")
    cache_potential = pd.merge(endpoint_counts, unique_uris_per_endpoint, on="endpoint")
    cache_potential["cache_ratio"] = cache_potential["total_requests"] / cache_potential["unique_uris"]
    cache_potential = cache_potential.sort_values(by="cache_ratio", ascending=False)

    # Prepare results for JSON output
    results = {
        "total_requests": len(df),
        "unique_hosts": df["host"].nunique(),
        "top_hosts": df["host"].value_counts().head(5).to_dict(),
        "top_origins": df["origin"].value_counts().head(10).to_dict(),
        "heavy_queries_count": len(heavy_queries),
        "heavy_queries_hosts": heavy_queries["host"].value_counts().to_dict(),
        "duplicate_requests_by_window": {k: f"{v} ({v / len(df) * 100:.1f}%) " for k, v in duplicate_counts.items()},
        "top_cache_potential_endpoints": cache_potential.head(10).to_dict("records"),
        "language_distribution": df["language"].value_counts(normalize=True).mul(100).round(2).to_dict()
    }

    output_path = "../references/analysis_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)
    
    print(f"✅ Analysis completed! Results saved to {output_path}")
    return results

if __name__ == "__main__":
    # Example usage (assuming logs_24_march_16_00.csv is in /home/ubuntu/upload/)
    # For skill execution, the path will be passed as an argument
    # For local testing:
    analyze_logs("../../../logs/unified_logs.csv")
    #pass
