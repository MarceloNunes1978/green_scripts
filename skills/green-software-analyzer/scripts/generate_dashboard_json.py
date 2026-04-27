"""
Reads analysis/output/analysis_results.json + ../references/patterns_analysis_en.json
+ green_software_metrics_en.db (traffic simulator output)
and writes ../templates/dashboard_data.json in the format expected by index.html.

Run: py generate_dashboard_json.py
"""

import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from urllib.parse import parse_qsl, urlparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON   = os.path.join(SCRIPT_DIR, 'analysis', 'output', 'analysis_results.json')
PATTERNS_JSON = os.path.join(SCRIPT_DIR, '..', 'references', 'patterns_analysis_en.json')
OUTPUT_JSON  = os.path.join(SCRIPT_DIR, '..', 'templates', 'dashboard_data.json')

LANG_NAMES = {
    'not_specified': 'Não especificado',
    'de':  'Alemão (DE)',
    'it':  'Italiano (IT)',
    'en':  'Inglês (EN)',
    'cz':  'Tcheco (CZ)',
    'nl':  'Holandês (NL)',
    'pl':  'Polonês (PL)',
    'dk':  'Dinamarquês (DK)',
    'fr':  'Francês (FR)',
    'es':  'Espanhol (ES)',
    'null':'Null',
    'ld':  'Ladino (LD)',
    'cs':  'Tcheco (CS)',
    'ru':  'Russo (RU)',
    'ko':  'Coreano (KO)',
    'sk':  'Eslovaco (SK)',
}

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'green_software_metrics_en.db')
VALID_SIMULATION_WHERE = 'WHERE simulated_call_timestamp IS NOT NULL'

CURRENT_HOSTS = {
    'tourism.api.opendatahub.com',
    'mobility.api.opendatahub.com',
}

PATTERN_LABELS = [
    ('Green by Default',         'Green by Default'),
    ('Just Latest Updates',      'Just Latest Updates (Delta)'),
    ('Wish List',                'Wish List (Sparse Fieldsets)'),
    ('Wish Template',            'Wish Template'),
]


def read_parameter_savings(cur):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_parameter_pattern_savings'"
    )
    if cur.fetchone() is None:
        return None

    cur.execute("""
        SELECT
            COUNT(*),
            SUM(request_count),
            SUM(total_response_bytes),
            SUM(estimated_saved_bytes)
        FROM api_parameter_pattern_savings
    """)
    row_count, total_requests, total_response_bytes, total_saved_bytes = cur.fetchone()

    cur.execute("""
        SELECT
            parameter_name,
            SUM(request_count) AS request_count,
            SUM(estimated_saved_bytes) AS estimated_saved_bytes,
            SUM(estimated_saved_bytes) / (1024.0 * 1024.0) AS estimated_saved_mb,
            COUNT(DISTINCT pattern) AS pattern_count
        FROM api_parameter_pattern_savings
        GROUP BY parameter_name
        ORDER BY estimated_saved_bytes DESC
        LIMIT 12
    """)
    top_by_parameter = [
        {
            'parameter_name': r[0],
            'request_count': int(r[1] or 0),
            'estimated_saved_bytes': round(r[2] or 0, 2),
            'estimated_saved_mb': round(r[3] or 0, 2),
            'pattern_count': int(r[4] or 0),
        }
        for r in cur.fetchall()
    ]

    cur.execute("""
        SELECT
            pattern,
            SUM(request_count) AS request_count,
            SUM(estimated_saved_bytes) AS estimated_saved_bytes,
            SUM(estimated_saved_bytes) / (1024.0 * 1024.0) AS estimated_saved_mb,
            COUNT(DISTINCT parameter_name) AS parameter_count
        FROM api_parameter_pattern_savings
        GROUP BY pattern
        ORDER BY estimated_saved_bytes DESC
    """)
    by_pattern = [
        {
            'pattern': r[0],
            'request_count': int(r[1] or 0),
            'estimated_saved_bytes': round(r[2] or 0, 2),
            'estimated_saved_mb': round(r[3] or 0, 2),
            'parameter_count': int(r[4] or 0),
        }
        for r in cur.fetchall()
    ]

    # Get top 10 per pattern to show all patterns fairly
    cur.execute("""
        WITH ranked AS (
            SELECT
                host,
                uri,
                parameter_name,
                pattern,
                request_count,
                total_response_bytes,
                estimated_saved_bytes,
                estimated_saved_mb,
                ROW_NUMBER() OVER (PARTITION BY pattern ORDER BY estimated_saved_bytes DESC) as rank
            FROM api_parameter_pattern_savings
        )
        SELECT
            host,
            uri,
            parameter_name,
            pattern,
            request_count,
            total_response_bytes,
            estimated_saved_bytes,
            estimated_saved_mb
        FROM ranked
        WHERE rank <= 10
        ORDER BY pattern, estimated_saved_bytes DESC
    """)
    top_endpoint_parameter_pattern = [
        {
            'host': r[0],
            'uri': r[1],
            'parameter_name': r[2],
            'pattern': r[3],
            'request_count': int(r[4] or 0),
            'total_response_bytes': int(r[5] or 0),
            'estimated_saved_bytes': round(r[6] or 0, 2),
            'estimated_saved_mb': round(r[7] or 0, 2),
        }
        for r in cur.fetchall()
    ]

    reduction_pct = 0
    if total_response_bytes:
        reduction_pct = round((total_saved_bytes or 0) / total_response_bytes * 100, 1)

    return {
        'row_count': int(row_count or 0),
        'total_requests': int(total_requests or 0),
        'total_response_bytes': int(total_response_bytes or 0),
        'total_response_mb': round((total_response_bytes or 0) / (1024.0 * 1024.0), 2),
        'total_saved_bytes': round(total_saved_bytes or 0, 2),
        'total_saved_mb': round((total_saved_bytes or 0) / (1024.0 * 1024.0), 2),
        'estimated_reduction_pct': reduction_pct,
        'top_by_parameter': top_by_parameter,
        'by_pattern': by_pattern,
        'top_endpoint_parameter_pattern': top_endpoint_parameter_pattern,
    }


def build_parameter_analysis_from_original(cur):
    cur.execute('SELECT host, uri FROM api_requests_original')

    total_requests = 0
    requests_with_parameters = 0
    total_parameter_rows = 0
    max_params_per_request = 0

    parameter_rows = Counter()
    parameter_requests = Counter()
    parameter_hosts = defaultdict(set)
    parameter_values = Counter()
    pagesize_values = Counter()

    host_totals = Counter()
    host_requests_with_parameters = Counter()
    host_parameter_rows = Counter()

    spotlight_names = {'fields', 'limit', 'pagesize', 'pagenumber', 'origin'}
    spotlight_requests = Counter()

    while True:
        batch = cur.fetchmany(50000)
        if not batch:
            break

        for host, uri in batch:
            total_requests += 1
            host_totals[host] += 1

            params = parse_qsl(urlparse(uri or '').query, keep_blank_values=True)
            if not params:
                continue

            requests_with_parameters += 1
            host_requests_with_parameters[host] += 1
            total_parameter_rows += len(params)
            max_params_per_request = max(max_params_per_request, len(params))

            seen_names = set()
            for name, value in params:
                name = name or '(empty_name)'
                value = value if value != '' else '(empty)'

                parameter_rows[name] += 1
                parameter_values[(name, value)] += 1
                host_parameter_rows[host] += 1
                seen_names.add(name)

                if name == 'pagesize':
                    pagesize_values[value] += 1

            for name in seen_names:
                parameter_requests[name] += 1
                parameter_hosts[name].add(host)
                if name in spotlight_names:
                    spotlight_requests[name] += 1

    avg_params_per_request = (total_parameter_rows / requests_with_parameters) if requests_with_parameters else 0

    top_parameters = [
        {
            'parameter_name': name,
            'parameter_rows': int(parameter_rows[name]),
            'request_count': int(parameter_requests[name]),
            'request_pct': round(parameter_requests[name] / total_requests * 100, 1) if total_requests else 0,
            'host_count': int(len(parameter_hosts[name])),
        }
        for name in parameter_requests
    ]
    top_parameters.sort(key=lambda r: (-r['request_count'], -r['parameter_rows'], r['parameter_name']))
    top_parameters = top_parameters[:12]

    top_parameter_values = [
        {
            'parameter_name': name,
            'parameter_value': value,
            'occurrences': int(count),
        }
        for (name, value), count in parameter_values.items()
    ]
    top_parameter_values.sort(key=lambda r: (-r['occurrences'], r['parameter_name'], r['parameter_value']))
    top_parameter_values = top_parameter_values[:15]

    host_breakdown = [
        {
            'host': host,
            'total_requests': int(host_totals[host]),
            'requests_with_parameters': int(host_requests_with_parameters[host]),
            'parameterized_request_pct': round(host_requests_with_parameters[host] / host_totals[host] * 100, 1) if host_totals[host] else 0,
            'parameter_rows': int(host_parameter_rows[host]),
        }
        for host in host_totals
    ]
    host_breakdown.sort(key=lambda r: (-r['requests_with_parameters'], -r['parameter_rows'], r['host']))

    spotlight = {}
    for name in ('fields', 'limit', 'pagesize', 'pagenumber', 'origin'):
        req = int(spotlight_requests[name])
        spotlight[name] = {
            'requests': req,
            'pct': round(req / total_requests * 100, 1) if total_requests else 0,
        }

    pagesize_value_distribution = [
        {
            'pagesize_value': value,
            'occurrences': int(count),
            'pct_of_simulated': round(count / total_requests * 100, 3) if total_requests else 0,
        }
        for value, count in sorted(pagesize_values.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    ]

    cur.execute("""
        SELECT
            SUM(CASE WHEN uri LIKE '%pagesize=20000%' THEN 1 ELSE 0 END),
            SUM(CASE WHEN uri LIKE '%pagesize=10000%' THEN 1 ELSE 0 END)
        FROM api_metrics
        WHERE simulated_call_timestamp IS NOT NULL
    """)
    sim_20000, sim_10000 = cur.fetchone()

    return {
        'source': 'original_log',
        'total_parameter_rows': int(total_parameter_rows),
        'requests_with_parameters': int(requests_with_parameters),
        'requests_with_parameters_pct': round(requests_with_parameters / total_requests * 100, 1) if total_requests else 0,
        'requests_without_parameters': int(total_requests - requests_with_parameters),
        'unique_parameter_names': int(len(parameter_requests)),
        'avg_parameters_per_request': round(avg_params_per_request, 2),
        'max_parameters_per_request': int(max_params_per_request),
        'top_parameters': top_parameters,
        'top_parameter_values': top_parameter_values,
        'pagesize_value_distribution': pagesize_value_distribution,
        'pagesize_focus': {
            'original': {
                'pagesize_20000': int(pagesize_values.get('20000', 0)),
                'pagesize_10000': int(pagesize_values.get('10000', 0)),
            },
            'simulated': {
                'pagesize_20000': int(sim_20000 or 0),
                'pagesize_10000': int(sim_10000 or 0),
            },
        },
        'host_breakdown': host_breakdown,
        'spotlight': spotlight,
    }


def read_estimated_traffic_totals(cur):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_metric_original_links'"
    )
    has_links = cur.fetchone() is not None
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_requests_original'"
    )
    has_original = cur.fetchone() is not None

    def payload(value):
        numeric = int(value or 0)
        return {
            'bytes': numeric,
            'kb': round(numeric / 1024.0, 2),
            'mb': round(numeric / (1024.0 ** 2), 2),
            'gb': round(numeric / (1024.0 ** 3), 3),
        }

    total_original_requests = 0
    unlinked_original_requests = 0
    request_bytes = 0
    response_bytes = 0
    transferred_bytes = 0

    if has_original:
        cur.execute('SELECT COUNT(*) FROM api_requests_original')
        total_original_requests = cur.fetchone()[0] or 0

    if has_links:
        cur.execute("""
            WITH link_counts AS (
                SELECT api_metric_id, COUNT(*) AS original_count
                FROM api_metric_original_links
                GROUP BY api_metric_id
            )
            SELECT
                COALESCE(SUM(m.request_size_bytes * lc.original_count), 0),
                COALESCE(SUM(m.response_size_bytes * lc.original_count), 0),
                COALESCE(SUM((m.request_size_bytes + m.response_size_bytes) * lc.original_count), 0)
            FROM api_metrics AS m
            JOIN link_counts AS lc ON lc.api_metric_id = m.id
            WHERE m.simulated_call_timestamp IS NOT NULL
        """)
        request_bytes, response_bytes, transferred_bytes = cur.fetchone()

    if has_links and has_original:
        cur.execute("""
            SELECT COUNT(*)
            FROM api_requests_original AS o
            WHERE NOT EXISTS (
                SELECT 1
                FROM api_metric_original_links AS l
                JOIN api_metrics AS m ON m.id = l.api_metric_id
                WHERE l.original_request_id = o.id
                  AND m.simulated_call_timestamp IS NOT NULL
            )
        """)
        unlinked_original_requests = cur.fetchone()[0] or 0

    linked_original_requests = max(total_original_requests - unlinked_original_requests, 0)
    linked_pct = round(linked_original_requests / total_original_requests * 100, 2) if total_original_requests else 0

    return {
        'source': 'estimated_from_simulated_sizes_weighted_by_original_links' if has_links else 'simulated_sizes_only',
        'total_original_requests': int(total_original_requests),
        'linked_original_requests': int(linked_original_requests),
        'unlinked_original_requests': int(unlinked_original_requests),
        'linked_original_requests_pct': linked_pct,
        'request': payload(request_bytes),
        'response': payload(response_bytes),
        'total': payload(transferred_bytes),
    }


def read_simulation_data():
    """Reads real payload/latency metrics from the SQLite database."""
    if not os.path.exists(DB_PATH):
        print(f"  [aviso] SQLite não encontrado: {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    def table_exists(table_name):
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cur.fetchone() is not None

    # Total and global averages
    cur.execute("""
        SELECT COUNT(*), AVG(response_size_bytes)/1024.0, AVG(latency_seconds)
        FROM api_metrics
        WHERE simulated_call_timestamp IS NOT NULL
    """)
    total_sim, avg_size_kb, avg_latency = cur.fetchone()

    # Per top-level pattern (a row can match multiple patterns)
    pattern_data = []
    for keyword, label in PATTERN_LABELS:
        cur.execute("""
            SELECT COUNT(*),
                   AVG(response_size_bytes)/1024.0,
                   AVG(latency_seconds)
            FROM api_metrics
                        WHERE simulated_call_timestamp IS NOT NULL
                            AND applicable_pattern LIKE ?
        """, (f'%{keyword}%',))
        count, p_size_kb, p_latency = cur.fetchone()
        count = count or 0
        avg_size_kb = round(p_size_kb or 0, 1)
        opt = PATTERN_OPT.get(label, {})
        estimated_saved_kb_total = round(count * (p_size_kb or 0) * opt.get('size_reduction', 0), 1)
        pattern_data.append({
            'pattern':      label,
            'count':        count,
            'pct':          round(count / total_sim * 100, 1) if total_sim else 0,
            'avg_size_kb':  avg_size_kb,
            'avg_latency_s': round(p_latency or 0, 3),
            'estimated_saved_kb_total': estimated_saved_kb_total,
        })

    # Per host
    cur.execute("""
        SELECT host,
               COUNT(*) as n,
               AVG(response_size_bytes)/1024.0 as avg_kb,
               AVG(latency_seconds) as avg_lat
        FROM api_metrics
        WHERE simulated_call_timestamp IS NOT NULL
        GROUP BY host
        ORDER BY n DESC
    """)
    host_metrics = [
        {
            'host':          row[0],
            'count':         row[1],
            'avg_size_kb':   round(row[2], 1),
            'avg_latency_s': round(row[3], 3),
        }
        for row in cur.fetchall()
    ]

    parameter_analysis = None
    if table_exists('api_requests_original'):
        parameter_analysis = build_parameter_analysis_from_original(cur)
        parameter_analysis['parameter_savings'] = read_parameter_savings(cur)
    elif table_exists('api_request_parameters'):
        cur.execute("""
            SELECT COUNT(*), COUNT(DISTINCT api_metric_id), COUNT(DISTINCT parameter_name)
            FROM api_request_parameters
            WHERE api_metric_id IN (
                SELECT id FROM api_metrics WHERE simulated_call_timestamp IS NOT NULL
            )
        """)
        total_parameter_rows, requests_with_parameters, unique_parameter_names = cur.fetchone()

        cur.execute("""
            SELECT AVG(param_count), MAX(param_count)
            FROM (
                SELECT api_metric_id, COUNT(*) AS param_count
                FROM api_request_parameters
                WHERE api_metric_id IN (
                    SELECT id FROM api_metrics WHERE simulated_call_timestamp IS NOT NULL
                )
                GROUP BY api_metric_id
            )
        """)
        avg_params_per_request, max_params_per_request = cur.fetchone()

        cur.execute("""
            SELECT
                p.parameter_name,
                COUNT(*) AS parameter_rows,
                COUNT(DISTINCT p.api_metric_id) AS request_count,
                COUNT(DISTINCT m.host) AS host_count
            FROM api_request_parameters p
            JOIN api_metrics m ON m.id = p.api_metric_id
            WHERE m.simulated_call_timestamp IS NOT NULL
            GROUP BY p.parameter_name
            ORDER BY request_count DESC, parameter_rows DESC, p.parameter_name ASC
            LIMIT 12
        """)
        top_parameters = [
            {
                'parameter_name': row[0],
                'parameter_rows': int(row[1]),
                'request_count': int(row[2]),
                'request_pct': round(row[2] / total_sim * 100, 1) if total_sim else 0,
                'host_count': int(row[3]),
            }
            for row in cur.fetchall()
        ]

        cur.execute("""
            SELECT
                p.parameter_name,
                COALESCE(NULLIF(p.parameter_value, ''), '(empty)') AS parameter_value,
                COUNT(*) AS occurrences
            FROM api_request_parameters p
            JOIN api_metrics m ON m.id = p.api_metric_id
            WHERE m.simulated_call_timestamp IS NOT NULL
            GROUP BY p.parameter_name, COALESCE(NULLIF(p.parameter_value, ''), '(empty)')
            ORDER BY occurrences DESC, p.parameter_name ASC, parameter_value ASC
            LIMIT 15
        """)
        top_parameter_values = [
            {
                'parameter_name': row[0],
                'parameter_value': row[1],
                'occurrences': int(row[2]),
            }
            for row in cur.fetchall()
        ]

        cur.execute("""
            SELECT
                COALESCE(NULLIF(p.parameter_value, ''), '(empty)') AS pagesize_value,
                COUNT(*) AS occurrences
            FROM api_request_parameters p
            JOIN api_metrics m ON m.id = p.api_metric_id
            WHERE m.simulated_call_timestamp IS NOT NULL
              AND p.parameter_name = 'pagesize'
            GROUP BY COALESCE(NULLIF(p.parameter_value, ''), '(empty)')
            ORDER BY occurrences DESC, pagesize_value ASC
            LIMIT 15
        """)
        pagesize_value_distribution = [
            {
                'pagesize_value': row[0],
                'occurrences': int(row[1]),
                'pct_of_simulated': round(row[1] / total_sim * 100, 3) if total_sim else 0,
            }
            for row in cur.fetchall()
        ]

        if table_exists('api_requests_original'):
            cur.execute("""
                SELECT
                    SUM(CASE WHEN uri LIKE '%pagesize=20000%' THEN 1 ELSE 0 END) AS original_pagesize_20000,
                    SUM(CASE WHEN uri LIKE '%pagesize=10000%' THEN 1 ELSE 0 END) AS original_pagesize_10000
                FROM api_requests_original
            """)
            original_pagesize_20000, original_pagesize_10000 = cur.fetchone()
        else:
            original_pagesize_20000, original_pagesize_10000 = 0, 0

        cur.execute("""
            SELECT
                SUM(CASE WHEN uri LIKE '%pagesize=20000%' THEN 1 ELSE 0 END) AS simulated_pagesize_20000,
                SUM(CASE WHEN uri LIKE '%pagesize=10000%' THEN 1 ELSE 0 END) AS simulated_pagesize_10000
            FROM api_metrics
            WHERE simulated_call_timestamp IS NOT NULL
        """)
        simulated_pagesize_20000, simulated_pagesize_10000 = cur.fetchone()

        cur.execute("""
            SELECT
                host,
                COUNT(*) AS total_requests,
                SUM(CASE WHEN param_count > 0 THEN 1 ELSE 0 END) AS requests_with_parameters,
                SUM(param_count) AS parameter_rows
            FROM (
                SELECT
                    m.id,
                    m.host,
                    COUNT(p.id) AS param_count
                FROM api_metrics m
                LEFT JOIN api_request_parameters p ON p.api_metric_id = m.id
                WHERE m.simulated_call_timestamp IS NOT NULL
                GROUP BY m.id, m.host
            ) host_request_params
            GROUP BY host
            ORDER BY requests_with_parameters DESC, parameter_rows DESC, host ASC
        """)
        host_breakdown = [
            {
                'host': row[0],
                'total_requests': int(row[1]),
                'requests_with_parameters': int(row[2]),
                'parameterized_request_pct': round(row[2] / row[1] * 100, 1) if row[1] else 0,
                'parameter_rows': int(row[3] or 0),
            }
            for row in cur.fetchall()
        ]

        spotlight = {}
        for param_name in ('fields', 'limit', 'pagesize', 'pagenumber', 'origin'):
            cur.execute("""
                SELECT COUNT(DISTINCT api_metric_id)
                                FROM api_request_parameters p
                                JOIN api_metrics m ON m.id = p.api_metric_id
                                WHERE p.parameter_name = ?
                                    AND m.simulated_call_timestamp IS NOT NULL
            """, (param_name,))
            param_requests = cur.fetchone()[0] or 0
            spotlight[param_name] = {
                'requests': int(param_requests),
                'pct': round(param_requests / total_sim * 100, 1) if total_sim else 0,
            }

        parameter_savings = None
        if table_exists('api_parameter_pattern_savings'):
            cur.execute("""
                SELECT
                    COUNT(*),
                    SUM(request_count),
                    SUM(total_response_bytes),
                    SUM(estimated_saved_bytes)
                FROM api_parameter_pattern_savings
            """)
            row_count, total_requests, total_response_bytes, total_saved_bytes = cur.fetchone()

            cur.execute("""
                SELECT
                    parameter_name,
                    SUM(request_count) AS request_count,
                    SUM(estimated_saved_bytes) AS estimated_saved_bytes,
                    SUM(estimated_saved_bytes) / (1024.0 * 1024.0) AS estimated_saved_mb,
                    COUNT(DISTINCT pattern) AS pattern_count
                FROM api_parameter_pattern_savings
                GROUP BY parameter_name
                ORDER BY estimated_saved_bytes DESC
                LIMIT 12
            """)
            top_by_parameter = [
                {
                    'parameter_name': r[0],
                    'request_count': int(r[1] or 0),
                    'estimated_saved_bytes': round(r[2] or 0, 2),
                    'estimated_saved_mb': round(r[3] or 0, 2),
                    'pattern_count': int(r[4] or 0),
                }
                for r in cur.fetchall()
            ]

            cur.execute("""
                SELECT
                    pattern,
                    SUM(request_count) AS request_count,
                    SUM(estimated_saved_bytes) AS estimated_saved_bytes,
                    SUM(estimated_saved_bytes) / (1024.0 * 1024.0) AS estimated_saved_mb,
                    COUNT(DISTINCT parameter_name) AS parameter_count
                FROM api_parameter_pattern_savings
                GROUP BY pattern
                ORDER BY estimated_saved_bytes DESC
            """)
            by_pattern = [
                {
                    'pattern': r[0],
                    'request_count': int(r[1] or 0),
                    'estimated_saved_bytes': round(r[2] or 0, 2),
                    'estimated_saved_mb': round(r[3] or 0, 2),
                    'parameter_count': int(r[4] or 0),
                }
                for r in cur.fetchall()
            ]

            # Get top 10 per pattern to show all patterns fairly
            cur.execute("""
                WITH ranked AS (
                    SELECT
                        host,
                        uri,
                        parameter_name,
                        pattern,
                        request_count,
                        total_response_bytes,
                        estimated_saved_bytes,
                        estimated_saved_mb,
                        ROW_NUMBER() OVER (PARTITION BY pattern ORDER BY estimated_saved_bytes DESC) as rank
                    FROM api_parameter_pattern_savings
                )
                SELECT
                    host,
                    uri,
                    parameter_name,
                    pattern,
                    request_count,
                    total_response_bytes,
                    estimated_saved_bytes,
                    estimated_saved_mb
                FROM ranked
                WHERE rank <= 10
                ORDER BY pattern, estimated_saved_bytes DESC
            """)
            top_endpoint_parameter_pattern = [
                {
                    'host': r[0],
                    'uri': r[1],
                    'parameter_name': r[2],
                    'pattern': r[3],
                    'request_count': int(r[4] or 0),
                    'total_response_bytes': int(r[5] or 0),
                    'estimated_saved_bytes': round(r[6] or 0, 2),
                    'estimated_saved_mb': round(r[7] or 0, 2),
                }
                for r in cur.fetchall()
            ]

            reduction_pct = 0
            if total_response_bytes:
                reduction_pct = round((total_saved_bytes or 0) / total_response_bytes * 100, 1)

            parameter_savings = {
                'row_count': int(row_count or 0),
                'total_requests': int(total_requests or 0),
                'total_response_bytes': int(total_response_bytes or 0),
                'total_response_mb': round((total_response_bytes or 0) / (1024.0 * 1024.0), 2),
                'total_saved_bytes': round(total_saved_bytes or 0, 2),
                'total_saved_mb': round((total_saved_bytes or 0) / (1024.0 * 1024.0), 2),
                'estimated_reduction_pct': reduction_pct,
                'top_by_parameter': top_by_parameter,
                'by_pattern': by_pattern,
                'top_endpoint_parameter_pattern': top_endpoint_parameter_pattern,
            }

        parameter_analysis = {
            'total_parameter_rows': int(total_parameter_rows or 0),
            'requests_with_parameters': int(requests_with_parameters or 0),
            'requests_with_parameters_pct': round((requests_with_parameters or 0) / total_sim * 100, 1) if total_sim else 0,
            'requests_without_parameters': int(total_sim - (requests_with_parameters or 0)),
            'unique_parameter_names': int(unique_parameter_names or 0),
            'avg_parameters_per_request': round(avg_params_per_request or 0, 2),
            'max_parameters_per_request': int(max_params_per_request or 0),
            'top_parameters': top_parameters,
            'top_parameter_values': top_parameter_values,
            'pagesize_value_distribution': pagesize_value_distribution,
            'pagesize_focus': {
                'original': {
                    'pagesize_20000': int(original_pagesize_20000 or 0),
                    'pagesize_10000': int(original_pagesize_10000 or 0),
                },
                'simulated': {
                    'pagesize_20000': int(simulated_pagesize_20000 or 0),
                    'pagesize_10000': int(simulated_pagesize_10000 or 0),
                }
            },
            'host_breakdown': host_breakdown,
            'spotlight': spotlight,
            'parameter_savings': parameter_savings,
        }

    estimated_traffic_totals = read_estimated_traffic_totals(cur)
    conn.close()
    return {
        'total_simulated':  int(total_sim),
        'avg_size_kb':      round(avg_size_kb or 0, 1),
        'avg_latency_s':    round(avg_latency or 0, 3),
        'patterns':         pattern_data,
        'host_metrics':     host_metrics,
        'estimated_traffic_totals': estimated_traffic_totals,
        'parameter_analysis': parameter_analysis,
    }

def host_type(host):
    return 'Mobilidade' if 'mobility' in host else 'Turismo'

def host_status(host):
    return 'Atual' if host in CURRENT_HOSTS else 'Legado'

# ── SCI Constants (Green Software Foundation specification) ───────────────────
# SCI = ((E × I) + M) / R
# R = 1 API request (functional unit)
SCI_I  = 233          # Carbon intensity Italy 2023 — gCO2eq/kWh (Ember Climate)
SCI_NET = 0.001       # Network energy — kWh/GB (IEA 2020)
SCI_SVR = 0.100       # Server power under load — kW (100 W typical API server)
SCI_M   = 0.000013    # Embodied carbon — gCO2eq/request (Dell R740, 4-yr lifecycle, 1B req/yr)

# Pattern optimization assumptions (conservative estimates from literature)
PATTERN_OPT = {
    'Green by Default': {
        'size_reduction': 0.60,    # remove limit=-1, add pagesize=25 → 60% smaller payload
        'latency_reduction': 0.30, # less DB work with pagination
        'description': 'Remover limit=-1, exigir pagesize ≤ 100',
    },
    'Just Latest Updates (Delta)': {
        'size_reduction': 0.70,    # only changed fields in delta response
        'latency_reduction': 0.40, # less serialization work
        'description': 'Enviar apenas campos alterados (delta)',
    },
    'Wish List (Sparse Fieldsets)': {
        'size_reduction': 0.60,    # fields= selector removes unnecessary fields
        'latency_reduction': 0.30, # less serialization
        'description': 'Forçar uso de fields= em todos os clientes',
    },
    'Wish Template': {
        'size_reduction': 0.88,    # pre-defined summary template (~1.5 KB vs 12.2 KB avg)
        'latency_reduction': 0.50, # server-side template caching eliminates projection overhead
        'description': 'Templates pré-definidos (summary, map_view, detail_full)',
    },
}

# Wish Template: natural templates inferred from top field usage patterns
WISH_TEMPLATES = [
    {
        'name': 'listing_de',
        'fields': ['Id', 'Detail.de.Title', 'ContactInfos.de.City'],
        'requests': 79349,
        'est_size_kb': 0.5,
        'use_case': 'Listagem turismo (DE)',
    },
    {
        'name': 'accommodation_de',
        'fields': ['Id', 'AccoDetail.de.Name', 'AccoDetail.de.City'],
        'requests': 79235,
        'est_size_kb': 0.4,
        'use_case': 'Listagem alojamento (DE)',
    },
    {
        'name': 'listing_it',
        'fields': ['Id', 'Detail.it.Title', 'ContactInfos.it.City'],
        'requests': 63006,
        'est_size_kb': 0.5,
        'use_case': 'Listagem turismo (IT)',
    },
    {
        'name': 'accommodation_it',
        'fields': ['Id', 'AccoDetail.it.Name', 'AccoDetail.it.City'],
        'requests': 62925,
        'est_size_kb': 0.4,
        'use_case': 'Listagem alojamento (IT)',
    },
    {
        'name': 'booking',
        'fields': ['Id', 'MssResponseShort'],
        'requests': 16133,
        'est_size_kb': 1.0,
        'use_case': 'Disponibilidade para reserva',
    },
    {
        'name': 'id_only',
        'fields': ['Id'],
        'requests': 79811,
        'est_size_kb': 0.1,
        'use_case': 'Lookup por ID',
    },
    {
        'name': 'detail_full',
        'fields': ['(todos os campos)'],
        'requests': None,  # remaining without fields=
        'est_size_kb': 12.2,
        'use_case': 'Página de detalhe completa',
    },
]


def _sci_per_request(avg_size_kb, avg_latency_s):
    """Returns SCI in mgCO2eq per request."""
    size_bytes = avg_size_kb * 1024
    e_net     = (size_bytes / 1e9) * SCI_NET          # kWh
    e_compute = SCI_SVR * (avg_latency_s / 3600)      # kWh
    e_total   = e_net + e_compute
    carbon_op = e_total * SCI_I                        # gCO2eq
    sci_g     = carbon_op + SCI_M                      # gCO2eq
    return round(sci_g * 1000, 4)                      # mgCO2eq


def calc_sci_section(simulation):
    """Builds the SCI section from simulation data and optimization assumptions."""
    if not simulation:
        return None

    patterns_sci = []

    for p in simulation['patterns']:
        label = p['pattern']
        opt   = PATTERN_OPT.get(label, {})

        sci_base = _sci_per_request(p['avg_size_kb'], p['avg_latency_s'])

        opt_size_kb  = p['avg_size_kb']  * (1 - opt.get('size_reduction', 0))
        opt_lat_s    = p['avg_latency_s'] * (1 - opt.get('latency_reduction', 0))
        sci_opt      = _sci_per_request(opt_size_kb, opt_lat_s)

        reduction_pct = round((sci_base - sci_opt) / sci_base * 100, 1) if sci_base else 0
        savings_total_g = round((sci_base - sci_opt) * p['count'] / 1000, 2)  # gCO2eq saved

        # Energy breakdown for baseline
        size_bytes = p['avg_size_kb'] * 1024
        e_net     = (size_bytes / 1e9) * SCI_NET
        e_compute = SCI_SVR * (p['avg_latency_s'] / 3600)
        e_total   = e_net + e_compute
        net_pct   = round(e_net / e_total * 100, 1) if e_total else 0

        patterns_sci.append({
            'pattern':         label,
            'count':           p['count'],
            'avg_size_kb':     p['avg_size_kb'],
            'avg_latency_s':   p['avg_latency_s'],
            'sci_baseline_mg': sci_base,
            'sci_optimized_mg': sci_opt,
            'reduction_pct':   reduction_pct,
            'savings_g_total': savings_total_g,
            'e_network_pct':   net_pct,
            'e_compute_pct':   round(100 - net_pct, 1),
            'opt_size_kb':     round(opt_size_kb, 1),
            'opt_latency_s':   round(opt_lat_s, 3),
            'optimization':    opt.get('description', ''),
        })

    total_savings_g = round(sum(p['savings_g_total'] for p in patterns_sci), 1)

    # Wish Template detailed templates
    wt_pattern = next((p for p in patterns_sci if 'Wish Template' in p['pattern']), None)
    for t in WISH_TEMPLATES:
        t['sci_mg'] = round(_sci_per_request(t['est_size_kb'], wt_pattern['avg_latency_s'] * (1 - 0.50)), 4)

    return {
        'constants': {
            'carbon_intensity_gco2_kwh': SCI_I,
            'network_energy_kwh_per_gb': SCI_NET,
            'server_power_kw':           SCI_SVR,
            'embodied_gco2_per_request': SCI_M,
            'functional_unit':           '1 API request',
            'formula':                   'SCI = ((E_net + E_compute) × I + M) / R',
        },
        'patterns': patterns_sci,
        'total_savings_g': total_savings_g,
        'wish_templates': WISH_TEMPLATES,
    }


def main():
    if not os.path.exists(INPUT_JSON):
        raise FileNotFoundError(f"Analysis JSON not found: {INPUT_JSON}")

    with open(INPUT_JSON, encoding='utf-8') as f:
        src = json.load(f)

    patterns = {}
    if os.path.exists(PATTERNS_JSON):
        with open(PATTERNS_JSON, encoding='utf-8') as f:
            patterns = json.load(f)

    summary      = src['summary']
    total        = summary['total_requests']
    duration_min = summary['duration_minutes']
    heavy        = summary['heavy_queries_limit_minus1']
    pagination   = summary['pagination_requests']

    # Duplicate windows: keys are strings '1','5','10','30','60'
    dup_raw   = src['duplicate_windows']
    dup_pct60 = src.get('duplicate_pct_60s', dup_raw.get('60', 0) / total * 100 if total else 0)

    dup_windows = {k + 's': v for k, v in dup_raw.items()}
    dup_pcts    = {k + 's': round(v / total * 100, 1) if total else 0
                   for k, v in dup_raw.items()}

    # Enriched hosts
    hosts = [
        {
            'host':     h['host'],
            'requests': h['requests'],
            'pct':      h['pct'],
            'type':     host_type(h['host']),
            'status':   host_status(h['host']),
            'rpm':      round(h['requests'] / duration_min, 1) if duration_min else 0,
        }
        for h in src['hosts']
    ]

    # Languages with friendly names (top 10)
    languages = [
        {
            'language': LANG_NAMES.get(l['language'], l['language'].upper()),
            'count':    l['count'],
            'pct':      l['pct'],
        }
        for l in src['languages'][:10]
    ]

    # Period label
    dt_start = datetime.fromisoformat(summary['period_start'])
    dt_end   = datetime.fromisoformat(summary['period_end'])
    period_label = (
        f"{dt_start.strftime('%d/%m/%Y %H:%M')}–{dt_end.strftime('%d/%m/%Y %H:%M')}"
    )

    avg_rpm  = round(total / duration_min, 1) if duration_min else 0
    rps      = src.get('rps_stats', {})
    avg_rps  = round(rps.get('mean', avg_rpm / 60), 1)
    peak_rps = int(rps.get('max', 0))

    unique_langs = len([l for l in src['languages'] if l['count'] > 0])

    simulation = read_simulation_data()

    dashboard = {
        # KPI / meta values for DOM updates
        'meta': {
            'total_requests':    total,
            'period_start':      summary['period_start'],
            'period_end':        summary['period_end'],
            'period_label':      period_label,
            'duration_minutes':  round(duration_min),
            'unique_hosts':      summary['unique_hosts'],
            'unique_endpoints':  summary['unique_endpoints'],
            'unique_uris':       summary['unique_uris'],
            'heavy_queries_count': heavy,
            'heavy_queries_pct': round(heavy / total * 100, 1) if total else 0,
            'pagination_count':  pagination,
            'pagination_pct':    round(pagination / total * 100, 1) if total else 0,
            'duplicate_60s_count': dup_raw.get('60', 0),
            'duplicate_60s_pct': round(dup_pct60, 1),
            'avg_rpm':           avg_rpm,
            'avg_rps':           avg_rps,
            'peak_rps':          peak_rps,
            'unique_languages':  unique_langs,
        },
        # Chart data (same field names the HTML already uses)
        'hosts':             hosts,
        'categories':        src['categories'],
        'topEndpoints':      src['top_endpoints'],
        'duplicateWindows':  dup_windows,
        'duplicateWindowPcts': dup_pcts,
        'languages':         languages,
        'origins':           src['origins'],
        'cacheCandidates':   src['cache_candidates'],
        'hourly':            src['requests_per_hour'],
        'requests_per_minute': src['requests_per_minute'],
        'patterns':          patterns,
        'simulation':        simulation,
        'sci':               calc_sci_section(simulation),
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    print(f"Generated: {OUTPUT_JSON}")
    print(f"  Total requests : {total:,}")
    print(f"  Period         : {period_label}")
    print(f"  Duration       : {round(duration_min)} min")
    print(f"  Duplicate 60s  : {dup_pcts.get('60s', 0)}%")
    print(f"  Heavy queries  : {round(heavy/total*100,1) if total else 0}%")
    if simulation:
        print(f"  Simulation     : {simulation['total_simulated']:,} records  "
              f"avg {simulation['avg_size_kb']} KB  avg {simulation['avg_latency_s']}s latency")


if __name__ == '__main__':
    main()
