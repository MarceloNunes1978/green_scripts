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
CSV_LOGS = '/logs/log_total.csv'
DB_NAME = 'green_software_metrics.db'
SAMPLE_SIZE = 100  # Aumentado para melhor amostragem
TIMEOUT = 10      # Timeout para as requests

def setup_database():
    """Inicializa o banco de dados SQLite com novas colunas"""
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
            request_body TEXT,  -- Novo: corpo da request (vazio para GET)
            response_body TEXT, -- Novo: corpo da response
            applicable_pattern TEXT -- Novo: padrão de design de green software aplicável
        )
    ''')
    conn.commit()
    return conn

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
    print(f"🚀 Iniciando simulação de tráfego baseada em {CSV_LOGS}")
    
    # Carregar logs
    df = pd.read_csv(CSV_LOGS)
    df.columns = ['timestamp', 'host', 'uri']
    
    # Pegar uma amostra para o teste
    sample = df.head(SAMPLE_SIZE)
    
    # Setup DB
    conn = setup_database()
    cursor = conn.cursor()
    
    results_count = 0
    
    for index, row in sample.iterrows():
        host = row['host']
        uri = row['uri']
        
        print(f"[{index+1}/{SAMPLE_SIZE}] Chamando: {host}{uri[:50]}...")
        
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
            
        # Pequeno delay para não sobrecarregar a API durante o teste
        time.sleep(0.2)
    
    conn.close()
    print(f"\n✅ Simulação concluída!")
    print(f"📊 {results_count} registros armazenados em '{DB_NAME}'")

if __name__ == "__main__":
    # Remover DB antigo se existir para recriar com novo schema
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Arquivo de banco de dados '{DB_NAME}' existente removido.")
    main()
