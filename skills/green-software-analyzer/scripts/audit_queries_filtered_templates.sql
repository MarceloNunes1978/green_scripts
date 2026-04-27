-- Filtered audit query templates for SQLite
-- Database example:
--   .open green_software_metrics_en.db
-- Optional output mode:
--   .mode column
--   .headers on

-- ============================================================
-- TEMPLATE 1: By host
-- Replace HOST_VALUE and ROW_LIMIT
-- ============================================================
SELECT
  m.id AS api_metric_id,
  m.timestamp AS original_log_timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code,
  GROUP_CONCAT(p.parameter_name || '=' || COALESCE(p.parameter_value, ''), '&') AS parameters_compact
FROM api_metrics m
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = m.id
WHERE m.host = 'HOST_VALUE'
GROUP BY m.id, m.timestamp, m.simulated_call_timestamp, m.host, m.uri, m.status_code
ORDER BY m.id DESC
LIMIT 200;

-- ============================================================
-- TEMPLATE 2: By original log timestamp window
-- Replace START_TS and END_TS (ISO strings)
-- ============================================================
SELECT
  m.id,
  m.timestamp AS original_log_timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code
FROM api_metrics m
WHERE m.timestamp >= '2026-03-24T00:00:00'
  AND m.timestamp < '2026-03-25T00:00:00'
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 3: By simulated execution window
-- Replace START_SIM and END_SIM (ISO strings)
-- ============================================================
SELECT
  m.id,
  m.timestamp AS original_log_timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code
FROM api_metrics m
WHERE m.simulated_call_timestamp >= '2026-04-25T00:00:00'
  AND m.simulated_call_timestamp < '2026-04-26T00:00:00'
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 4: By HTTP status and host
-- Replace HOST_VALUE and STATUS_CODE
-- ============================================================
SELECT
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code,
  m.latency_seconds,
  m.response_size_bytes
FROM api_metrics m
WHERE m.host = 'HOST_VALUE'
  AND m.status_code = 200
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 5: By design pattern substring
-- Replace PATTERN_TEXT
-- ============================================================
SELECT
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.applicable_pattern
FROM api_metrics m
WHERE m.applicable_pattern LIKE '%Just Latest Updates (Delta)%'
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 6: Requests that contain a specific parameter name
-- Replace PARAM_NAME
-- ============================================================
SELECT DISTINCT
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code
FROM api_metrics m
JOIN api_request_parameters p
  ON p.api_metric_id = m.id
WHERE p.parameter_name = 'limit'
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 7: Requests that contain parameter name + exact value
-- Replace PARAM_NAME and PARAM_VALUE
-- ============================================================
SELECT DISTINCT
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code
FROM api_metrics m
JOIN api_request_parameters p
  ON p.api_metric_id = m.id
WHERE p.parameter_name = 'limit'
  AND p.parameter_value = '50'
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 8: Combined filters (host + simulated window + status + parameter)
-- Replace values as needed
-- ============================================================
SELECT
  m.id,
  m.timestamp,
  m.simulated_call_timestamp,
  m.host,
  m.uri,
  m.status_code,
  GROUP_CONCAT(p2.parameter_name || '=' || COALESCE(p2.parameter_value, ''), '&') AS parameters_compact
FROM api_metrics m
JOIN api_request_parameters p
  ON p.api_metric_id = m.id
LEFT JOIN api_request_parameters p2
  ON p2.api_metric_id = m.id
WHERE m.host = 'HOST_VALUE'
  AND m.simulated_call_timestamp >= '2026-04-25T00:00:00'
  AND m.simulated_call_timestamp < '2026-04-26T00:00:00'
  AND m.status_code = 200
  AND p.parameter_name = 'limit'
  AND p.parameter_value = '50'
GROUP BY m.id, m.timestamp, m.simulated_call_timestamp, m.host, m.uri, m.status_code
ORDER BY m.id DESC
LIMIT 500;

-- ============================================================
-- TEMPLATE 9: Coverage by host (with optional simulated window)
-- Edit or remove the window lines as needed
-- ============================================================
SELECT
  m.host,
  COUNT(*) AS total_requests,
  SUM(CASE WHEN instr(m.uri, '?') > 0 THEN 1 ELSE 0 END) AS requests_with_querystring,
  COUNT(DISTINCT p.api_metric_id) AS requests_with_stored_parameters,
  COUNT(p.id) AS total_parameter_rows
FROM api_metrics m
LEFT JOIN api_request_parameters p
  ON p.api_metric_id = m.id
WHERE m.simulated_call_timestamp >= '2026-04-25T00:00:00'
  AND m.simulated_call_timestamp < '2026-04-26T00:00:00'
GROUP BY m.host
ORDER BY total_requests DESC;

-- ============================================================
-- TEMPLATE 10: Expanded export (one row per parameter)
-- Useful for CSV export with filters
-- ============================================================
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
WHERE m.host = 'HOST_VALUE'
  AND m.status_code = 200
ORDER BY m.id DESC, p.id ASC
LIMIT 5000;
