"""
Reads analysis/output/analysis_results.json + ../references/patterns_analysis_en.json
and writes ../templates/dashboard_data.json in the format expected by index.html.

Run: py generate_dashboard_json.py
"""

import json
import os
from datetime import datetime

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

CURRENT_HOSTS = {
    'tourism.api.opendatahub.com',
    'mobility.api.opendatahub.com',
}

def host_type(host):
    return 'Mobilidade' if 'mobility' in host else 'Turismo'

def host_status(host):
    return 'Atual' if host in CURRENT_HOSTS else 'Legado'

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


if __name__ == '__main__':
    main()
