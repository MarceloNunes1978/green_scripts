-- Audit queries for api_metrics and api_request_parameters
-- Usage examples (sqlite3):
--   .open green_software_metrics_en.db
--   .read audit_queries.sql
--
-- The queries below assume the schema includes:
--   api_metrics(id, timestamp, simulated_call_timestamp, host, uri, ...)
--   api_request_parameters(id, api_metric_id, parameter_name, parameter_value)

-- 1) Main audit view: request + compact parameter list
SELECT
  m.id AS api_metric_id,
  m.timestamp AS original_log_timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code,
  COUNT(p.id) AS total_parameters,
  GROUP_CONCAT(
    p.parameter_name || '=' || COALESCE(p.parameter_value, ''),
    '&'
  ) AS parameters_compact
FROM api_metrics m
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = m.id
GROUP BY
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code
ORDER BY m.id DESC
LIMIT 200;

-- 2) Requests with query string but no stored parameters
SELECT
  m.id,
  m.uri
FROM api_metrics m
LEFT JOIN (
  SELECT api_metric_id, COUNT(*) AS param_count
  FROM api_request_parameters
  GROUP BY api_metric_id
) q ON q.api_metric_id = m.id
WHERE instr(m.uri, '?') > 0
  AND COALESCE(q.param_count, 0) = 0
ORDER BY m.id DESC
LIMIT 200;

-- 3) Orphan parameters (no parent request)
SELECT
  p.id,
  p.api_metric_id,
  p.parameter_name,
  p.parameter_value
FROM api_request_parameters p
LEFT JOIN api_metrics m
  ON m.id = p.api_metric_id
WHERE m.id IS NULL
ORDER BY p.id DESC
LIMIT 200;

-- 4) Coverage summary
SELECT
  COUNT(*) AS total_requests,
  SUM(CASE WHEN instr(uri, '?') > 0 THEN 1 ELSE 0 END) AS requests_with_querystring,
  (
    SELECT COUNT(DISTINCT api_metric_id)
    FROM api_request_parameters
  ) AS requests_with_parameter_rows,
  (
    SELECT COUNT(*)
    FROM api_request_parameters
  ) AS total_parameter_rows
FROM api_metrics;

-- 5) Expanded format (one row per parameter), good for CSV export
SELECT
  m.id AS api_metric_id,
  m.timestamp AS original_log_timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code,
  p.parameter_name,
  p.parameter_value
FROM api_metrics m
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = m.id
ORDER BY m.id DESC, p.id ASC
LIMIT 1000;

-- ============================================================
-- 6) Filtered audit queries (optional named parameters)
-- ============================================================
-- You can run these in sqlite3 CLI using:
--   .parameter init
--   .parameter set :host 'api.example.com'
--   .parameter set :status_code 200
--   .parameter set :pattern 'Just Latest Updates (Delta)'
--   .parameter set :param_name 'limit'
--   .parameter set :param_value '50'
--   .parameter set :orig_start '2026-03-24T00:00:00'
--   .parameter set :orig_end   '2026-03-25T00:00:00'
--   .parameter set :sim_start  '2026-04-25T00:00:00'
--   .parameter set :sim_end    '2026-04-26T00:00:00'
--   .parameter set :limit_rows 500
--
-- To ignore a filter, keep the parameter NULL or do not set it.

WITH filtered_metrics AS (
  SELECT m.*
  FROM api_metrics m
  WHERE (:host IS NULL OR m.host = :host)
    AND (:status_code IS NULL OR m.status_code = :status_code)
    AND (:pattern IS NULL OR m.applicable_pattern LIKE '%' || :pattern || '%')
    AND (:orig_start IS NULL OR m.timestamp >= :orig_start)
    AND (:orig_end IS NULL OR m.timestamp < :orig_end)
    AND (:sim_start IS NULL OR m.simulated_call_timestamp >= :sim_start)
    AND (:sim_end IS NULL OR m.simulated_call_timestamp < :sim_end)
    AND (
      :param_name IS NULL OR EXISTS (
        SELECT 1
        FROM api_request_parameters p
        WHERE p.api_metric_id = m.id
          AND p.parameter_name = :param_name
          AND (:param_value IS NULL OR p.parameter_value = :param_value)
      )
    )
)
SELECT
  fm.id AS api_metric_id,
  fm.timestamp AS original_log_timestamp,
  fm.simulated_call_timestamp,
  fm.host,
  fm.uri,
  fm.status_code,
  COUNT(p.id) AS total_parameters,
  GROUP_CONCAT(
    p.parameter_name || '=' || COALESCE(p.parameter_value, ''),
    '&'
  ) AS parameters_compact
FROM filtered_metrics fm
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = fm.id
GROUP BY
  fm.id,
  fm.timestamp,
  fm.simulated_call_timestamp,
  fm.host,
  fm.uri,
  fm.status_code
ORDER BY fm.id DESC
LIMIT COALESCE(:limit_rows, 200);

-- 7) Filtered expanded result (one row per parameter)
WITH filtered_metrics AS (
  SELECT m.*
  FROM api_metrics m
  WHERE (:host IS NULL OR m.host = :host)
    AND (:status_code IS NULL OR m.status_code = :status_code)
    AND (:pattern IS NULL OR m.applicable_pattern LIKE '%' || :pattern || '%')
    AND (:orig_start IS NULL OR m.timestamp >= :orig_start)
    AND (:orig_end IS NULL OR m.timestamp < :orig_end)
    AND (:sim_start IS NULL OR m.simulated_call_timestamp >= :sim_start)
    AND (:sim_end IS NULL OR m.simulated_call_timestamp < :sim_end)
    AND (
      :param_name IS NULL OR EXISTS (
        SELECT 1
        FROM api_request_parameters p
        WHERE p.api_metric_id = m.id
          AND p.parameter_name = :param_name
          AND (:param_value IS NULL OR p.parameter_value = :param_value)
      )
    )
)
SELECT
  fm.id AS api_metric_id,
  fm.timestamp AS original_log_timestamp,
  fm.simulated_call_timestamp,
  fm.host,
  fm.uri,
  fm.status_code,
  p.parameter_name,
  p.parameter_value
FROM filtered_metrics fm
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = fm.id
ORDER BY fm.id DESC, p.id ASC
LIMIT COALESCE(:limit_rows, 1000);

-- ============================================================
-- 8) Full join: api_requests_original + api_metric_original_links + api_metrics
--    Links every original log request to its simulated metric row.
-- ============================================================
SELECT
  o.id                        AS original_request_id,
  o.timestamp                 AS original_timestamp,
  o.host                      AS original_host,
  o.uri                       AS original_uri,
  l.api_metric_id,
  m.simulated_call_timestamp,
  m.host                      AS metric_host,
  m.uri                       AS metric_uri,
  m.status_code,
  m.method,
  m.content_type,
  m.request_size_bytes,
  m.response_size_bytes,
  m.latency_seconds,
  m.request_body,
  m.response_body,
  m.applicable_pattern
FROM api_requests_original o
JOIN api_metric_original_links l ON l.original_request_id = o.id
JOIN api_metrics m               ON m.id = l.api_metric_id
ORDER BY o.id DESC
LIMIT 200;
