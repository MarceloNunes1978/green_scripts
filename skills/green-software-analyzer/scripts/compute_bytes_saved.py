import argparse
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "green_software_metrics_en.db"
CSV_PATH = BASE_DIR / "bytes_saved_by_endpoint_parameter_pattern.csv"
TABLE_NAME = "api_parameter_pattern_savings"

PATTERNS = [
    ("Green by Default", 0.60),
    ("Just Latest Updates", 0.70),
    ("Wish List", 0.60),
    ("Wish Template", 0.88),
]


def collect_rows(conn):
    agg = defaultdict(lambda: [0, 0.0, 0.0])
    cur = conn.cursor()
    has_links = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_metric_original_links'"
    ).fetchone() is not None

    if has_links:
        cur.execute(
            """
            SELECT
                m.host,
                m.uri,
                p.parameter_name,
                m.applicable_pattern,
                m.response_size_bytes,
                COALESCE(link_counts.original_count, 1) AS original_weight
            FROM api_metrics m
            JOIN api_request_parameters p ON p.api_metric_id = m.id
            LEFT JOIN (
                SELECT api_metric_id, COUNT(*) AS original_count
                FROM api_metric_original_links
                GROUP BY api_metric_id
            ) link_counts ON link_counts.api_metric_id = m.id
            WHERE m.simulated_call_timestamp IS NOT NULL
            """
        )
    else:
        cur.execute(
            """
            SELECT
                m.host,
                m.uri,
                p.parameter_name,
                m.applicable_pattern,
                m.response_size_bytes,
                1 AS original_weight
            FROM api_metrics m
            JOIN api_request_parameters p ON p.api_metric_id = m.id
            WHERE m.simulated_call_timestamp IS NOT NULL
            """
        )

    while True:
        batch = cur.fetchmany(50000)
        if not batch:
            break

        for host, uri, parameter_name, applicable_pattern, response_size_bytes, original_weight in batch:
            text = (applicable_pattern or "").lower()
            size = float(response_size_bytes or 0)
            weight = int(original_weight or 1)
            for pattern, factor in PATTERNS:
                if pattern.lower() in text:
                    key = (host, uri, parameter_name, pattern)
                    rec = agg[key]
                    rec[0] += weight
                    rec[1] += size * weight
                    rec[2] += size * factor * weight

    rows = []
    for (host, uri, parameter_name, pattern), (request_count, total_response_bytes, estimated_saved_bytes) in agg.items():
        estimated_saved_mb = estimated_saved_bytes / (1024.0 * 1024.0)
        rows.append([
            host,
            uri,
            parameter_name,
            pattern,
            request_count,
            int(total_response_bytes),
            estimated_saved_bytes,
            estimated_saved_mb,
        ])

    rows.sort(key=lambda r: r[6], reverse=True)
    return rows


def persist_to_sqlite(conn, rows):
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            uri TEXT NOT NULL,
            parameter_name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            request_count INTEGER NOT NULL,
            total_response_bytes INTEGER NOT NULL,
            estimated_saved_bytes REAL NOT NULL,
            estimated_saved_mb REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(f"DELETE FROM {TABLE_NAME}")

    cur.executemany(
        f"""
        INSERT INTO {TABLE_NAME}
        (host, uri, parameter_name, pattern, request_count, total_response_bytes, estimated_saved_bytes, estimated_saved_mb)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_pattern ON {TABLE_NAME}(pattern)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_param ON {TABLE_NAME}(parameter_name)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_host_uri ON {TABLE_NAME}(host, uri)"
    )
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_saved ON {TABLE_NAME}(estimated_saved_bytes DESC)"
    )
    conn.commit()


def export_csv(rows):
    headers = [
        "host",
        "uri",
        "parameter_name",
        "pattern",
        "request_count",
        "total_response_bytes",
        "estimated_saved_bytes",
        "estimated_saved_mb",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def main(export_full_csv=False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-200000")
        has_links = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_metric_original_links'"
        ).fetchone() is not None
        rows = collect_rows(conn)
        persist_to_sqlite(conn, rows)

    if export_full_csv:
        export_csv(rows)
        print(f"Saved {len(rows)} rows to {CSV_PATH}")
    else:
        print("CSV export skipped (use --export-csv to generate it).")

    if has_links:
        print("Savings were weighted by original log volume via api_metric_original_links.")
    else:
        print("Savings used unweighted simulated volume (api_metric_original_links not found).")

    print(f"Saved {len(rows)} rows to SQLite table: {TABLE_NAME}")
    print("Top 20 rows by estimated_saved_bytes:")
    for r in rows[:20]:
        print(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}\t{r[6]:.2f}\t{r[7]:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Also writes bytes_saved_by_endpoint_parameter_pattern.csv (large file).",
    )
    args = parser.parse_args()
    main(export_full_csv=args.export_csv)
