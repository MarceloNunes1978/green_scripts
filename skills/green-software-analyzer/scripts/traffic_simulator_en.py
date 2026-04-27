import pandas as pd
import sqlite3
import time
import asyncio
import aiohttp
import threading
from datetime import datetime
import re
import os
import argparse
from urllib.parse import urlparse, parse_qsl
from compute_bytes_saved import main as compute_bytes_saved_main

# Configurations
CSV_LOGS = '../../../logs/unified_logs.csv'
DB_NAME = 'green_software_metrics_en.db'
CHECKPOINT_FILE = 'progress_checkpoint.txt'
TIMEOUT = 10
WORKERS = 20          # concurrent async workers
BATCH_SIZE = 500      # DB commit batch size
MAX_BODY_SIZE = 2048  # truncate response body to 2KB
RAW_LOAD_BATCH_SIZE = 50000

db_lock = threading.Lock()


def setup_database(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            simulated_call_timestamp DATETIME,
            host TEXT,
            uri TEXT,
            status_code INTEGER,
            request_size_bytes INTEGER,
            response_size_bytes INTEGER,
            latency_seconds REAL,
            method TEXT,
            content_type TEXT,
            request_body TEXT,
            response_body TEXT,
            applicable_pattern TEXT
        )
    ''')
    # Backward-compatible migration for DBs created before simulated_call_timestamp existed.
    cursor.execute("PRAGMA table_info(api_metrics)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if 'simulated_call_timestamp' not in existing_columns:
        cursor.execute('ALTER TABLE api_metrics ADD COLUMN simulated_call_timestamp DATETIME')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_request_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_metric_id INTEGER NOT NULL,
            parameter_name TEXT NOT NULL,
            parameter_value TEXT,
            FOREIGN KEY (api_metric_id) REFERENCES api_metrics(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_requests_original (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            host TEXT,
            uri TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_metric_original_links (
            original_request_id INTEGER NOT NULL,
            api_metric_id INTEGER NOT NULL,
            PRIMARY KEY (original_request_id, api_metric_id),
            FOREIGN KEY (original_request_id) REFERENCES api_requests_original(id),
            FOREIGN KEY (api_metric_id) REFERENCES api_metrics(id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_host_uri ON api_metrics(host, uri)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_req_params_metric_id ON api_request_parameters(api_metric_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_orig_timestamp ON api_requests_original(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_orig_host_uri ON api_requests_original(host, uri)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_metric_id ON api_metric_original_links(api_metric_id)')
    conn.commit()


def refresh_original_requests_table(conn, df):
    """Stores all original log requests (no deduplication) for direct DB analytics."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM api_requests_original')

    rows_buffer = []
    inserted = 0

    for row in df[['timestamp_db', 'host', 'uri']].itertuples(index=False, name=None):
        rows_buffer.append(row)
        if len(rows_buffer) >= RAW_LOAD_BATCH_SIZE:
            cursor.executemany(
                'INSERT INTO api_requests_original (timestamp, host, uri) VALUES (?, ?, ?)',
                rows_buffer,
            )
            inserted += len(rows_buffer)
            rows_buffer.clear()

    if rows_buffer:
        cursor.executemany(
            'INSERT INTO api_requests_original (timestamp, host, uri) VALUES (?, ?, ?)',
            rows_buffer,
        )
        inserted += len(rows_buffer)

    conn.commit()
    print(f"Loaded original requests table: {inserted:,} rows")


def refresh_metric_original_links(conn):
    """Links every original request to its simulated metric using host + uri."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM api_metric_original_links')
    cursor.execute('''
        INSERT INTO api_metric_original_links (original_request_id, api_metric_id)
        SELECT o.id, m.id
        FROM api_requests_original o
        JOIN api_metrics m
          ON m.host = o.host
         AND m.uri = o.uri
    ''')
    conn.commit()
    linked_rows = cursor.execute('SELECT COUNT(*) FROM api_metric_original_links').fetchone()[0]
    print(f"Linked original requests to metrics: {linked_rows:,} rows")


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return int(f.read().strip())
    return 0


def save_checkpoint(count):
    with open(CHECKPOINT_FILE, 'w') as f:
        f.write(str(count))


def count_legacy_rows(conn):
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM api_metrics WHERE simulated_call_timestamp IS NULL')
    return cursor.fetchone()[0]


def classify_pattern(uri, response_body_str):
    patterns = []

    if 'limit=-1' in uri:
        patterns.append('Green by Default (limit=-1)')
    elif not re.search(r'pagesize|pagenumber|limit=', uri, re.IGNORECASE):
        patterns.append('Green by Default (no pagination)')
    elif 'fields=' not in uri:
        patterns.append('Green by Default (no fields)')

    if re.search(r'weather|realtime|status|latest|forecast|getbyroombooked', uri, re.IGNORECASE):
        patterns.append('Just Latest Updates (Delta)')

    if 'fields=' not in uri and response_body_str and len(response_body_str) > 500 and response_body_str.strip().startswith(('{', '[')):
        patterns.append('Wish List (Sparse Fieldsets)')

    if len(uri) > 80 or 'Wish List (Sparse Fieldsets)' in patterns:
        patterns.append('Wish Template')

    return ', '.join(patterns) if patterns else 'None specific'


async def measure_request_async(session, host, uri):
    url = f"https://{host}{uri}"
    method = "GET"
    request_headers_size = len(f"{method} {uri} HTTP/1.1\r\nHost: {host}\r\n".encode('utf-8'))

    start_time = time.time()
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=TIMEOUT), ssl=False) as response:
            latency = time.time() - start_time
            body_bytes = await response.read()
            response_body_str = body_bytes.decode('utf-8', errors='ignore')[:MAX_BODY_SIZE]
            response_headers_size = sum(len(k) + len(v) + 4 for k, v in response.headers.items())
            total_response_size = len(body_bytes) + response_headers_size

            return {
                'status_code': response.status,
                'request_size': request_headers_size,
                'response_size': total_response_size,
                'latency': latency,
                'method': method,
                'content_type': response.headers.get('Content-Type', 'unknown'),
                'request_body': '',
                'response_body': response_body_str,
                'applicable_pattern': classify_pattern(uri, response_body_str)
            }
    except Exception:
        return None


async def worker(semaphore, session, host, uri, original_log_timestamp, results, idx, total):
    async with semaphore:
        metrics = await measure_request_async(session, host, uri)
        if idx % 1000 == 0:
            pct = idx / total * 100
            print(f"  [{idx:,}/{total:,}] {pct:.1f}% — {host}{uri[:40]}...")
        if metrics:
            results.append((
                original_log_timestamp,
                datetime.now().isoformat(),
                host, uri,
                metrics['status_code'], metrics['request_size'], metrics['response_size'],
                metrics['latency'], metrics['method'], metrics['content_type'],
                metrics['request_body'], metrics['response_body'], metrics['applicable_pattern']
            ))


def flush_batch(conn, rows):
    def extract_uri_parameters(uri):
        query = urlparse(uri).query
        return parse_qsl(query, keep_blank_values=True)

    cursor = conn.cursor()
    metric_insert_sql = '''
        INSERT INTO api_metrics
        (timestamp, simulated_call_timestamp, host, uri, status_code, request_size_bytes, response_size_bytes,
         latency_seconds, method, content_type, request_body, response_body, applicable_pattern)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    '''
    params_insert_sql = '''
        INSERT INTO api_request_parameters (api_metric_id, parameter_name, parameter_value)
        VALUES (?, ?, ?)
    '''

    for row in rows:
        cursor.execute(metric_insert_sql, row)
        api_metric_id = cursor.lastrowid
        uri = row[3]
        params = extract_uri_parameters(uri)
        if params:
            cursor.executemany(
                params_insert_sql,
                [(api_metric_id, name, value) for name, value in params]
            )

    conn.commit()


async def run_all(unique_df, conn, start_from):
    total = len(unique_df)
    processed = start_from
    semaphore = asyncio.Semaphore(WORKERS)

    connector = aiohttp.TCPConnector(limit=WORKERS, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        results = []

        for idx, (_, row) in enumerate(unique_df.iloc[start_from:].iterrows(), start=start_from + 1):
            task = asyncio.create_task(
                worker(semaphore, session, row['host'], row['uri'], row['timestamp'], results, idx, total)
            )
            tasks.append(task)

            if len(tasks) >= BATCH_SIZE:
                await asyncio.gather(*tasks)
                flush_batch(conn, results)
                processed += len(results)
                save_checkpoint(processed)
                print(f"Batch committed: {processed:,}/{total:,} ({processed/total*100:.1f}%)")
                tasks.clear()
                results.clear()

        if tasks:
            await asyncio.gather(*tasks)
            flush_batch(conn, results)
            processed += len(results)
            save_checkpoint(processed)

    return processed


def main(reset=False, skip_savings=False, export_savings_csv=False):
    global CHECKPOINT_FILE
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_LOGS)
    db_path = os.path.join(script_dir, DB_NAME)
    checkpoint_path = os.path.join(script_dir, CHECKPOINT_FILE)
    CHECKPOINT_FILE = checkpoint_path

    if reset:
        for f in [db_path, checkpoint_path]:
            if os.path.exists(f):
                os.remove(f)
                print(f"Removed: {f}")

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    df.columns = ['timestamp', 'host', 'uri']

    # Keep original text timestamp for api_metrics; use normalized timestamp in raw table for SQL filtering.
    parsed_ts = pd.to_datetime(df['timestamp'], format='%b %d, %Y @ %H:%M:%S.%f', errors='coerce')
    df['timestamp_db'] = parsed_ts.dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
    df['timestamp_db'] = df['timestamp_db'].where(df['timestamp_db'].notna(), df['timestamp'].astype(str))

    unique_df = df.drop_duplicates(subset=['host', 'uri']).reset_index(drop=True)
    total = len(unique_df)
    print(f"Total unique URIs: {total:,} (reduced from {len(df):,})")

    start_from = load_checkpoint()
    if start_from > 0:
        print(f"Resuming from checkpoint: {start_from:,}/{total:,}")

    conn = sqlite3.connect(db_path)
    setup_database(conn)
    refresh_original_requests_table(conn, df)

    legacy_rows = count_legacy_rows(conn)
    if legacy_rows:
        conn.close()
        raise RuntimeError(
            f"Database contains {legacy_rows:,} legacy rows without simulated_call_timestamp. "
            "Run with --reset to rebuild the database with original log timestamps and simulated call timestamps."
        )

    t_start = time.time()
    processed = asyncio.run(run_all(unique_df, conn, start_from))
    refresh_metric_original_links(conn)
    elapsed = time.time() - t_start

    conn.close()
    print(f"\nCompleted! {processed:,} records in {elapsed/60:.1f} min stored in '{db_path}'")

    if skip_savings:
        print("Skipping savings table update (--skip-savings).")
    else:
        print("Updating api_parameter_pattern_savings table...")
        compute_bytes_saved_main(export_full_csv=export_savings_csv)

    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='Delete existing DB and restart')
    parser.add_argument('--skip-savings', action='store_true', help='Do not refresh api_parameter_pattern_savings at the end')
    parser.add_argument('--export-savings-csv', action='store_true', help='Also export bytes_saved_by_endpoint_parameter_pattern.csv when refreshing savings')
    args = parser.parse_args()
    main(
        reset=args.reset,
        skip_savings=args.skip_savings,
        export_savings_csv=args.export_savings_csv,
    )
