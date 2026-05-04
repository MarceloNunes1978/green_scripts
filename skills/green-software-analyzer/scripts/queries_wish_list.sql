-- Consultas analíticas — Padrão: Wish List (Sparse Fieldsets)
-- Banco: green_software_metrics_en.db
--
-- Como usar no sqlite3 CLI:
--   sqlite3 green_software_metrics_en.db
--   .read queries_wish_list.sql

-- ============================================================
-- 1) Totais gerais do padrão
-- ============================================================
SELECT
    'Wish List'                                     AS pattern,
    COUNT(DISTINCT parameter_name)                  AS parametros_distintos,
    SUM(request_count)                              AS total_request_rows,
    ROUND(SUM(total_response_bytes) / 1024.0, 0)   AS total_resposta_kb,
    ROUND(SUM(estimated_saved_bytes) / 1024.0, 0)  AS total_economia_kb,
    ROUND(SUM(estimated_saved_bytes) / 1024.0
          / 1024.0, 1)                             AS total_economia_mb,
    ROUND(
        SUM(estimated_saved_bytes) * 100.0
        / NULLIF(SUM(total_response_bytes), 0),
        1
    )                                              AS pct_economia
FROM api_parameter_pattern_savings
WHERE pattern = 'Wish List';

-- ============================================================
-- 2) Economia por parâmetro
-- ============================================================
SELECT
    parameter_name,
    SUM(request_count)                              AS requisicoes,
    ROUND(SUM(total_response_bytes) / 1024.0, 0)   AS resposta_total_kb,
    ROUND(SUM(estimated_saved_bytes) / 1024.0, 0)  AS economia_kb,
    ROUND(
        SUM(estimated_saved_bytes) * 100.0
        / NULLIF(SUM(total_response_bytes), 0),
        1
    )                                              AS pct_economia
FROM api_parameter_pattern_savings
WHERE pattern = 'Wish List'
GROUP BY parameter_name
ORDER BY economia_kb DESC;

-- ============================================================
-- 3) Top 20 endpoints por economia estimada
-- ============================================================
-- ATENÇÃO: usar MAX (não SUM) para bytes — ver nota em queries_green_by_default.sql
SELECT
    CASE
        WHEN (uri LIKE '%/%2A/%2A/%' OR uri LIKE '%/*/latest%')
             AND uri NOT LIKE '%ECharging%'
             AND uri NOT LIKE '%Parking%'
             AND uri NOT LIKE '%Carsharing%'
             AND uri NOT LIKE '%LinkStation%'
             AND uri NOT LIKE '%Culture%'
             AND uri NOT LIKE '%TrafficSensor%'   THEN 'Todos os sensores'
        WHEN uri LIKE '%EChargingPlug%'            THEN 'EChargingPlug'
        WHEN uri LIKE '%EChargingStation%'         THEN 'EChargingStation'
        WHEN uri LIKE '%ParkingStation%'           THEN 'ParkingStation'
        WHEN uri LIKE '%ParkingSensor%'            THEN 'ParkingSensor'
        WHEN uri LIKE '%CarsharingCar%'            THEN 'CarsharingCar'
        WHEN uri LIKE '%CarsharingStation%'        THEN 'CarsharingStation'
        WHEN uri LIKE '%BikeParking%'              THEN 'BikeParking'
        WHEN uri LIKE '%LinkStation%'              THEN 'LinkStation'
        WHEN uri LIKE '%TrafficSensor%'            THEN 'TrafficSensor'
        WHEN uri LIKE '%Culture%'                  THEN 'Culture'
        WHEN uri LIKE '%Flight%'                   THEN 'Flight'
        WHEN uri LIKE '%ODHActivityPoi%'           THEN 'ODHActivityPoi'
        WHEN uri LIKE '%AccommodationRoom%'        THEN 'AccommodationRoom'
        WHEN uri LIKE '%Accommodation%'            THEN 'Accommodation'
        WHEN uri LIKE '%EventShort%'               THEN 'EventShort'
        WHEN uri LIKE '%Event%'                    THEN 'Event'
        WHEN uri LIKE '%Weather%'                  THEN 'Weather'
        WHEN uri LIKE '%ODHTag%'                   THEN 'ODHTag'
        WHEN uri LIKE '%Activity%'                 THEN 'Activity'
        WHEN uri LIKE '%Gastronomy%'               THEN 'Gastronomy'
        WHEN uri LIKE '%Article%'                  THEN 'Article'
        WHEN uri LIKE '%Poi%'                      THEN 'Poi'
        WHEN uri LIKE '%PROVINCE_BZ%'              THEN 'Province'
        ELSE 'Outros'
    END                                            AS resource,
    host,
    uri,
    MAX(request_count)                             AS requisicoes,
    COUNT(DISTINCT parameter_name)                 AS n_parametros,
    ROUND(MAX(total_response_bytes) / 1024.0, 0)  AS resposta_kb,
    ROUND(MAX(estimated_saved_bytes) / 1024.0, 0) AS economia_kb,
    GROUP_CONCAT(DISTINCT parameter_name)          AS parametros
FROM api_parameter_pattern_savings
WHERE pattern = 'Wish List'
GROUP BY host, uri
ORDER BY economia_kb DESC
LIMIT 20;

-- ============================================================
-- 4) Combinações de fields= mais frequentes (log original)
-- ============================================================
SELECT
    p.parameter_value              AS fields_value,
    COUNT(*)                       AS ocorrencias
FROM api_request_parameters p
WHERE p.parameter_name = 'fields'
GROUP BY p.parameter_value
ORDER BY ocorrencias DESC
LIMIT 20;

-- ============================================================
-- 5) Requisições sem o parâmetro fields (candidatas ao padrão)
-- ============================================================
SELECT
    m.host,
    COUNT(*)                                       AS requisicoes_sem_fields,
    ROUND(AVG(m.response_size_bytes) / 1024.0, 1) AS avg_resposta_kb
FROM api_metrics m
WHERE NOT EXISTS (
    SELECT 1
    FROM api_request_parameters p
    WHERE p.api_metric_id = m.id
      AND p.parameter_name = 'fields'
)
GROUP BY m.host
ORDER BY requisicoes_sem_fields DESC;

-- ============================================================
-- 6) Endpoints com maior resposta média sem fields=
-- ============================================================
SELECT
    m.host,
    SUBSTR(m.uri, 1, INSTR(m.uri || '?', '?') - 1)  AS endpoint,
    COUNT(*)                                           AS requisicoes,
    ROUND(AVG(m.response_size_bytes) / 1024.0, 1)    AS avg_resposta_kb,
    ROUND(MAX(m.response_size_bytes) / 1024.0, 1)    AS max_resposta_kb
FROM api_metrics m
WHERE NOT EXISTS (
    SELECT 1
    FROM api_request_parameters p
    WHERE p.api_metric_id = m.id
      AND p.parameter_name = 'fields'
)
GROUP BY m.host, endpoint
HAVING requisicoes >= 10
ORDER BY avg_resposta_kb DESC
LIMIT 20;
