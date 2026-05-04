"""
Reads analysis/output/analysis_results.json + ../references/patterns_analysis_en.json
+ green_software_metrics_en.db (traffic simulator output)
and writes ../templates/dashboard_data.json in the format expected by index.html.

Run: py generate_dashboard_json.py
"""

import json
import os
import sqlite3
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

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'green_software_metrics_en.db')

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


def read_simulation_data():
    """Reads real payload/latency metrics from the SQLite database."""
    if not os.path.exists(DB_PATH):
        print(f"  [aviso] SQLite não encontrado: {DB_PATH}")
        return None

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # Total and global averages
    cur.execute("""
        SELECT COUNT(*), AVG(response_size_bytes)/1024.0, AVG(latency_seconds)
        FROM api_metrics
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
            WHERE applicable_pattern LIKE ?
        """, (f'%{keyword}%',))
        count, p_size_kb, p_latency = cur.fetchone()
        count = count or 0
        pattern_data.append({
            'pattern':      label,
            'count':        count,
            'pct':          round(count / total_sim * 100, 1) if total_sim else 0,
            'avg_size_kb':  round(p_size_kb or 0, 1),
            'avg_latency_s': round(p_latency or 0, 3),
        })

    # Per host
    cur.execute("""
        SELECT host,
               COUNT(*) as n,
               AVG(response_size_bytes)/1024.0 as avg_kb,
               AVG(latency_seconds) as avg_lat
        FROM api_metrics
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

    conn.close()
    return {
        'total_simulated':  int(total_sim),
        'avg_size_kb':      round(avg_size_kb or 0, 1),
        'avg_latency_s':    round(avg_latency or 0, 3),
        'patterns':         pattern_data,
        'host_metrics':     host_metrics,
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

    total_sim = simulation['total_simulated']
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
