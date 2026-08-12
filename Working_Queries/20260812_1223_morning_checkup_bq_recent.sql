-- Morning checkup: recent settled days (daily grain) 2026-08-08..2026-08-10
WITH visits AS (
  SELECT
    SessionStartDate AS d,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_id=([^&]*)')), r'[{}]', '') AS agid,
    COUNT(*) AS v,
    SUM(AddedToCart) AS a,
    SUM(SawProductDisplayPage) AS p
  FROM `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits`
  WHERE cmcode IN ('TT49BTSUF','TT49BTSMF','TT49NBAU','TT49VSA','TT49DPA','TT49GTMMF',
               'TT49VERIFIEDMF','TT49OUTDOORMF','TT49PROMOMF','TT49GTMUF','TT49VERIFIEDUF',
               'TT49OUTDOORUF','TT49PROMOUF','TT49OUTDOORLF','TT49VPROMOMF','TT49VPROMOUF',
               'TT49RMN')
    AND sessionstartdate BETWEEN DATE('2026-08-08') AND DATE('2026-08-10')
    AND event_soid = 49
  GROUP BY ALL
)
SELECT
  d AS date,
  agid AS adgroup_id,
  SUM(v) AS visits,
  SUM(a) AS ATCs,
  SAFE_DIVIDE(SUM(a), SUM(v)) AS atc_rate,
  SUM(p) AS PDP_views,
  SAFE_DIVIDE(SUM(p), SUM(v)) AS pdp_rate,
  SAFE_DIVIDE(SUM(a), SUM(p)) AS vtc_rate
FROM visits
WHERE agid IS NOT NULL AND agid != ''
GROUP BY 1, 2
ORDER BY adgroup_id, date
