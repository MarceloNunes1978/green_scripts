import pandas as pd
import requests
import sqlite3
import time
import json
from datetime import datetime
import re
from urllib.parse import urlparse, parse_qs
import os

# Configurações
CSV_LOGS = '../../../logs/unified_logs.csv'
DB_NAME = 'green_software_metrics.db'
SAMPLE_SIZE = 100  # Aumentado para melhor amostragem
TIMEOUT = 10      # Timeout para as requests
RAW_LOAD_BATCH_SIZE = 50000

def setup_database():
    """Inicializa o banco de dados SQLite com novas colunas"""
    conn = sqlite3.connect(DB_NAME)
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
            request_body TEXT,  -- Novo: corpo da request (vazio para GET)
            response_body TEXT, -- Novo: corpo da response
            applicable_pattern TEXT -- Novo: padrão de design de green software aplicável
        )
    ''')
    # Migração retrocompatível para bancos antigos sem a coluna de timestamp simulado.
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

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_req_params_metric_id ON api_request_parameters(api_metric_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_orig_timestamp ON api_requests_original(timestamp)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_orig_host_uri ON api_requests_original(host, uri)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_link_metric_id ON api_metric_original_links(api_metric_id)')

    conn.commit()
    return conn


def refresh_original_requests_table(conn, df):
    """Armazena todas as requisições originais do log, sem deduplicação."""
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
    print(f"Tabela de requisições originais carregada: {inserted:,} linhas")


def refresh_metric_original_links(conn):
    """Liga cada requisição original à sua métrica simulada via host + uri."""
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
    print(f"Ligação entre originais e métricas criada: {linked_rows:,} linhas")

def classify_pattern(uri, response_body_str):
    """Classifica a request/response em um ou mais padrões de design de Green Software"""
    patterns = []

    # 1. Green by Default
    # Prioriza a remoção de limit=-1, depois a adição de paginação e fields
    if 'limit=-1' in uri:
        patterns.append('Green by Default (limit=-1)')
    elif not re.search(r'pagesize=|pagenumber=|limit=', uri, re.IGNORECASE):
        patterns.append('Green by Default (no pagination)')
    elif not 'fields=' in uri:
        patterns.append('Green by Default (no fields)')

    # 2. Just Latest Updates (Delta)
    # Candidatos: URIs que parecem ser de dados em tempo real ou frequentemente atualizados
    # Ex: Weather, Realtime, Status, Latest, Forecast, GetbyRoomBooked
    if re.search(r'weather|realtime|status|latest|forecast|getbyroombooked', uri, re.IGNORECASE):
        patterns.append('Just Latest Updates (Delta)')

    # 3. Wish List (Sparse Fieldsets)
    # Aplicável se 'fields=' não foi usado, mas o response_body é grande e JSON (potencial para seleção de campos)
    if 'fields=' not in uri and response_body_str and len(response_body_str) > 500 and response_body_str.strip().startswith(('{', '[')):
        patterns.append('Wish List (Sparse Fieldsets)')

    # 4. Wish Template
    # Aplicável a endpoints com URIs complexas ou que retornam muitos dados, onde um template simplificaria
    # Ex: Endpoints com muitos parâmetros, ou que já são candidatos a Wish List
    if len(uri) > 80 or 'Wish List (Sparse Fieldsets)' in patterns:
        patterns.append('Wish Template')

    return ', '.join(patterns) if patterns else 'Nenhum específico'

def measure_request(host, uri):
    """Realiza a request e mede os tamanhos e latência, capturando o corpo da response"""
    url = f"https://{host}{uri}"
    method = "GET"
    request_body = "" # Para GET, o corpo da request é vazio
    
    # Estimativa do tamanho da request (headers básicos + URL)
    request_headers_size = len(f"{method} {uri} HTTP/1.1\r\nHost: {host}\r\n".encode('utf-8'))
    
    start_time = time.time()
    try:
        response = requests.get(url, timeout=TIMEOUT, stream=True)
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
        print(f"Erro ao acessar {url}: {e}")
        return None

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, CSV_LOGS)

    print(f"🚀 Iniciando simulação de tráfego baseada em {csv_path}")
    
    # Carregar logs
    df = pd.read_csv(csv_path)
    df.columns = ['timestamp', 'host', 'uri']
    parsed_ts = pd.to_datetime(df['timestamp'], format='%b %d, %Y @ %H:%M:%S.%f', errors='coerce')
    df['timestamp_db'] = parsed_ts.dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]
    df['timestamp_db'] = df['timestamp_db'].where(df['timestamp_db'].notna(), df['timestamp'].astype(str))
    
    # Pegar uma amostra para o teste
    sample = df.head(SAMPLE_SIZE)
    
    # Setup DB
    conn = setup_database()
    refresh_original_requests_table(conn, df)
    cursor = conn.cursor()
    
    results_count = 0
    
    for index, row in sample.iterrows():
        original_log_timestamp = row['timestamp']
        host = row['host']
        uri = row['uri']
        
        print(f"[{index+1}/{SAMPLE_SIZE}] Chamando: {host}{uri[:50]}...")
        
        metrics = measure_request(host, uri)
        
        if metrics:
            cursor.execute('''
                INSERT INTO api_metrics 
                (timestamp, simulated_call_timestamp, host, uri, status_code, request_size_bytes, response_size_bytes, latency_seconds, method, content_type, request_body, response_body, applicable_pattern)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                original_log_timestamp,
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

            api_metric_id = cursor.lastrowid
            query_params = parse_qsl(urlparse(uri).query, keep_blank_values=True)
            if query_params:
                cursor.executemany(
                    '''
                    INSERT INTO api_request_parameters (api_metric_id, parameter_name, parameter_value)
                    VALUES (?, ?, ?)
                    ''',
                    [(api_metric_id, name, value) for name, value in query_params]
                )

            conn.commit()
            results_count += 1
            
        # Pequeno delay para não sobrecarregar a API durante o teste
        time.sleep(0.2)
    
    conn.close()
    conn = sqlite3.connect(DB_NAME)
    refresh_metric_original_links(conn)
    conn.close()

    print(f"\n✅ Simulação concluída!")
    print(f"📊 {results_count} registros armazenados em '{DB_NAME}'")

if __name__ == "__main__":
    # Remover DB antigo se existir para recriar com novo schema
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Arquivo de banco de dados '{DB_NAME}' existente removido.")
    main()
