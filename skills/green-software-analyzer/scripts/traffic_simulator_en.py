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

# Configurations
CSV_LOGS = '../../../logs/unified_logs.csv'
DB_NAME = 'green_software_metrics_en.db'
CHECKPOINT_FILE = 'progress_checkpoint.txt'
TIMEOUT = 10
WORKERS = 20          # concurrent async workers
BATCH_SIZE = 500      # DB commit batch size
MAX_BODY_SIZE = 2048  # truncate response body to 2KB

db_lock = threading.Lock()


def setup_database(conn):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
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
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_host_uri ON api_metrics(host, uri)')
    conn.commit()


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return int(f.read().strip())
    return 0


def save_checkpoint(count):
    with open(CHECKPOINT_FILE, 'w') as f:
        f.write(str(count))


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


async def worker(semaphore, session, host, uri, results, idx, total):
    async with semaphore:
        metrics = await measure_request_async(session, host, uri)
        if idx % 1000 == 0:
            pct = idx / total * 100
            print(f"  [{idx:,}/{total:,}] {pct:.1f}% — {host}{uri[:40]}...")
        if metrics:
            results.append((
                datetime.now().isoformat(), host, uri,
                metrics['status_code'], metrics['request_size'], metrics['response_size'],
                metrics['latency'], metrics['method'], metrics['content_type'],
                metrics['request_body'], metrics['response_body'], metrics['applicable_pattern']
            ))


def flush_batch(conn, rows):
    cursor = conn.cursor()
    cursor.executemany('''
        INSERT INTO api_metrics
        (timestamp, host, uri, status_code, request_size_bytes, response_size_bytes,
         latency_seconds, method, content_type, request_body, response_body, applicable_pattern)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', rows)
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
            task = asyncio.create_task(worker(semaphore, session, row['host'], row['uri'], results, idx, total))
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


def main(reset=False):
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

    unique_df = df.drop_duplicates(subset=['host', 'uri']).reset_index(drop=True)
    total = len(unique_df)
    print(f"Total unique URIs: {total:,} (reduced from {len(df):,})")

    start_from = load_checkpoint()
    if start_from > 0:
        print(f"Resuming from checkpoint: {start_from:,}/{total:,}")

    conn = sqlite3.connect(db_path)
    setup_database(conn)

    t_start = time.time()
    processed = asyncio.run(run_all(unique_df, conn, start_from))
    elapsed = time.time() - t_start

    conn.close()
    print(f"\nCompleted! {processed:,} records in {elapsed/60:.1f} min stored in '{db_path}'")

    if os.path.exists(checkpoint_path):
        os.remove(checkpoint_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--reset', action='store_true', help='Delete existing DB and restart')
    args = parser.parse_args()
    main(reset=args.reset)
