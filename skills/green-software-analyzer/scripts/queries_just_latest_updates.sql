-- Consultas analíticas — Padrão: Just Latest Updates (Delta)
-- Banco: green_software_metrics_en.db
--
-- Como usar no sqlite3 CLI:
--   sqlite3 green_software_metrics_en.db
--   .read queries_just_latest_updates.sql

-- ============================================================
-- 1) Totais gerais do padrão
-- ============================================================
SELECT
    'Just Latest Updates'                           AS pattern,
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
WHERE pattern = 'Just Latest Updates';

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
WHERE pattern = 'Just Latest Updates'
GROUP BY parameter_name
ORDER BY economia_kb DESC;

-- ============================================================
-- 3) Top 20 endpoints por economia estimada (com resource)
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
WHERE pattern = 'Just Latest Updates'
GROUP BY host, uri
ORDER BY economia_kb DESC
LIMIT 20;

-- ============================================================
-- 4) Candidatos a delta — URIs com padrão de polling repetido
--    (mesmo URI simulado mais de uma vez)
-- ============================================================
SELECT
    host,
    uri,
    COUNT(*)                                       AS simulacoes,
    ROUND(AVG(response_size_bytes) / 1024.0, 1)   AS avg_resposta_kb,
    ROUND(AVG(latency_seconds), 3)                 AS avg_latencia_s
FROM api_metrics
WHERE applicable_pattern LIKE '%Just Latest Updates%'
GROUP BY host, uri
HAVING simulacoes > 1
ORDER BY simulacoes DESC
LIMIT 20;

-- ============================================================
-- 5) Intervalo médio entre polls para o mesmo endpoint
-- ============================================================
SELECT
    host,
    uri,
    COUNT(*)                                           AS chamadas,
    ROUND(
        (JULIANDAY(MAX(timestamp)) - JULIANDAY(MIN(timestamp)))
        * 86400.0 / NULLIF(COUNT(*) - 1, 0),
        1
    )                                                  AS avg_intervalo_s
FROM api_metrics
WHERE applicable_pattern LIKE '%Just Latest Updates%'
GROUP BY host, uri
HAVING chamadas > 1
ORDER BY avg_intervalo_s ASC
LIMIT 20;

-- ============================================================
-- 6) Endpoints /latest com limit=-1 (delta + excesso de dados, com resource)
-- ============================================================
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
        WHEN uri LIKE '%CarsharingCar%'            THEN 'CarsharingCar'
        WHEN uri LIKE '%LinkStation%'              THEN 'LinkStation'
        WHEN uri LIKE '%Culture%'                  THEN 'Culture'
        ELSE 'Outros'
    END                                            AS resource,
    host,
    MAX(request_count)                             AS requisicoes,
    ROUND(MAX(total_response_bytes) / 1024.0, 0)  AS resposta_kb,
    ROUND(MAX(estimated_saved_bytes) / 1024.0, 0) AS economia_kb
FROM api_parameter_pattern_savings
WHERE pattern = 'Just Latest Updates'
  AND uri LIKE '%/latest%'
  AND uri LIKE '%limit=-1%'
GROUP BY host, uri
ORDER BY economia_kb DESC;

-- ============================================================
-- 7) Economia agregada por resource
-- ============================================================
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
        WHEN uri LIKE '%CarsharingCar%'            THEN 'CarsharingCar'
        WHEN uri LIKE '%LinkStation%'              THEN 'LinkStation'
        WHEN uri LIKE '%Culture%'                  THEN 'Culture'
        WHEN uri LIKE '%ODHActivityPoi%'           THEN 'ODHActivityPoi'
        WHEN uri LIKE '%EventShort%'               THEN 'EventShort'
        WHEN uri LIKE '%Event%'                    THEN 'Event'
        WHEN uri LIKE '%Weather%'                  THEN 'Weather'
        WHEN uri LIKE '%Activity%'                 THEN 'Activity'
        ELSE 'Outros'
    END                                            AS resource,
    COUNT(DISTINCT host || uri)                    AS endpoints,
    SUM(t.req)                                     AS requisicoes,
    ROUND(SUM(t.resp_kb), 0)                       AS total_resp_kb,
    ROUND(SUM(t.saved_kb), 0)                      AS total_saved_kb
FROM (
    SELECT host, uri,
           MAX(request_count)                      AS req,
           MAX(total_response_bytes) / 1024.0      AS resp_kb,
           MAX(estimated_saved_bytes) / 1024.0     AS saved_kb
    FROM api_parameter_pattern_savings
    WHERE pattern = 'Just Latest Updates'
    GROUP BY host, uri
) t
GROUP BY resource
ORDER BY total_saved_kb DESC;
