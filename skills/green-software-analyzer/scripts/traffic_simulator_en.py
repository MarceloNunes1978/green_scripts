import pandas as pd
import requests
import sqlite3
import time
import json
from datetime import datetime
import re
from urllib.parse import urlparse, parse_qs
import os

# Configurations
CSV_LOGS = '../../../logs/unified_logs.csv'
DB_NAME = 'green_software_metrics_en.db'
SAMPLE_SIZE = 100  # Increased for better sampling
TIMEOUT = 10      # Timeout for requests

def setup_database():
    """Initializes the SQLite database with new columns"""
    conn = sqlite3.connect(DB_NAME)
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
            request_body TEXT,  -- New: request body (empty for GET)
            response_body TEXT, -- New: response body
            applicable_pattern TEXT -- New: applicable green software design pattern
        )
    ''')
    conn.commit()
    return conn

def classify_pattern(uri, response_body_str):
    """Classifies the request/response into one or more Green Software design patterns"""
    patterns = []

    # 1. Green by Default
    # Prioritizes removing limit=-1, then adding pagination and fields
    if 'limit=-1' in uri:
        patterns.append('Green by Default (limit=-1)')
    elif not re.search(r'pagesize|pagenumber|limit=', uri, re.IGNORECASE):
        patterns.append('Green by Default (no pagination)')
    elif not 'fields=' in uri:
        patterns.append('Green by Default (no fields)')

    # 2. Just Latest Updates (Delta)
    # Candidates: URIs that appear to be real-time or frequently updated data
    # Ex: Weather, Realtime, Status, Latest, Forecast, GetbyRoomBooked
    if re.search(r'weather|realtime|status|latest|forecast|getbyroombooked', uri, re.IGNORECASE):
        patterns.append('Just Latest Updates (Delta)')

    # 3. Wish List (Sparse Fieldsets)
    # Applicable if 'fields=' was not used, but the response_body is large and JSON (potential for field selection)
    if 'fields=' not in uri and response_body_str and len(response_body_str) > 500 and response_body_str.strip().startswith(('{', '[')):
        patterns.append('Wish List (Sparse Fieldsets)')

    # 4. Wish Template
    # Applicable to endpoints with complex URIs or that return a lot of data, where a template would simplify
    # Ex: Endpoints with many parameters, or that are already Wish List candidates
    if len(uri) > 80 or 'Wish List (Sparse Fieldsets)' in patterns:
        patterns.append('Wish Template')

    return ', '.join(patterns) if patterns else 'None specific'

def measure_request(host, uri):
    """Performs the request and measures sizes and latency, capturing the response body"""
    url = f"https://{host}{uri}"
    method = "GET"
    request_body = "" # For GET, the request body is empty
    
    # Estimate request size (basic headers + URL)
    request_headers_size = len(f"{method} {uri} HTTP/1.1\r\nHost: {host}\r\n".encode('utf-8'))
    
    start_time = time.time()
    try:
        response = requests.get(url, timeout=TIMEOUT, stream=True, verify=False)
        latency = time.time() - start_time
        
        response_body_bytes = response.content
        response_body_str = response_body_bytes.decode('utf-8', errors='ignore')
        
        response_headers_size = len(str(response.headers).encode('utf-8'))
        total_response_size = len(response_body_bytes) + response_headers_size
        
        return {
            'status_code': response.status_code,
            'request_size': request_headers_size,
            'response_size': total_response_size,
            'latency': latency,
            'method': method,
            'content_type': response.headers.get('Content-Type', 'unknown'),
            'request_body': request_body,
            'response_body': response_body_str,
            'applicable_pattern': classify_pattern(uri, response_body_str)
        }
    except requests.exceptions.RequestException as e:
        print(f"Error accessing {url}: {e}")
        return None

def main():
    print(f"🚀 Starting traffic simulation based on {CSV_LOGS}")
    
    # Load logs
    df = pd.read_csv(CSV_LOGS)
    df.columns = ['timestamp', 'host', 'uri']
    
    # Get a sample for testing
    sample = df.head(SAMPLE_SIZE)
    
    # Setup DB
    conn = setup_database()
    cursor = conn.cursor()
    
    results_count = 0
    
    for index, row in sample.iterrows():
        host = row['host']
        uri = row['uri']
        
        print(f"[{index+1}/{SAMPLE_SIZE}] Calling: {host}{uri[:50]}...")
        
        metrics = measure_request(host, uri)
        
        if metrics:
            cursor.execute('''
                INSERT INTO api_metrics 
                (timestamp, host, uri, status_code, request_size_bytes, response_size_bytes, latency_seconds, method, content_type, request_body, response_body, applicable_pattern)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(),
                host,
                uri,
                metrics['status_code'],
                metrics['request_size'],
                metrics['response_size'],
                metrics['latency'],
                metrics['method'],
                metrics['content_type'],
                metrics['request_body'],
                metrics['response_body'],
                metrics['applicable_pattern']
            ))
            conn.commit()
            results_count += 1
            
        # Small delay to avoid overloading the API during testing
        time.sleep(0.2)
    
    conn.close()
    print(f"\n✅ Simulation completed!")
    print(f"📊 {results_count} records stored in '{DB_NAME}'")

if __name__ == "__main__":
    # Remove old DB if it exists to recreate with new schema
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Existing database file '{DB_NAME}' removed.")
    main()
