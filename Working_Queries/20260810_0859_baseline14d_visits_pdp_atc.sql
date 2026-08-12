-- Morning ad group checkup: 14-day baseline (2026-07-23 to 2026-08-05), aggregated
WITH visits AS (
  SELECT
    SessionStartDate AS date,
    CASE
      WHEN cmcode = 'TT49VPROMOMF' THEN 'TT49PROMOMF'
      WHEN cmcode = 'TT49VPROMOUF' THEN 'TT49PROMOUF'
      ELSE cmcode
    END AS cmcode,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_id=([^&]*)')), r'[{}]', '') AS adgroup_id,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]campaign_id=([^&]*)')), r'[{}]', '') AS campaign_id,
    COALESCE(
      LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_name=([^&]*)')),
      LOWER(REGEXP_EXTRACT(event_url, r'[\?&]utm_adgroup=([^&]*)'))
    ) AS ad_group_name_raw,
    COUNT(*) AS visits,
    SUM(AddedToCart) AS ATCs,
    SUM(SawProductDisplayPage) AS PDP_views,
    SUM(TotalOrders) AS site_orders,
    SUM(TotalRevenue) AS site_revenue
  FROM `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits`
  WHERE cmcode IN ('TT49BTSUF','TT49BTSMF','TT49NBAU','TT49VSA','TT49DPA','TT49GTMMF',
                   'TT49VERIFIEDMF','TT49OUTDOORMF','TT49PROMOMF','TT49GTMUF','TT49VERIFIEDUF',
                   'TT49OUTDOORUF','TT49PROMOUF','TT49OUTDOORLF','TT49VPROMOMF','TT49VPROMOUF','TT49RMN')
    AND sessionstartdate BETWEEN DATE('2026-07-23') AND DATE('2026-08-05')
    AND event_soid = 49
  GROUP BY ALL
),
tiktok_lookup AS (
  SELECT
    CAST(campaignID AS STRING) AS campaign_id,
    CAST(adgroupID AS STRING) AS adgroup_id,
    LOWER(campaignName) AS campaign_name,
    LOWER(adgroupName) AS adgroup_name
  FROM `wf-gcp-us-ae-adtech-prod.marketing_ad_costs.tbl_campaign_costs_tiktok_metrics_report`
  WHERE accountID = "7125498373565726721"
    AND reportDate >= DATE('2026-07-23') - 10
    AND campaignID IS NOT NULL AND adgroupID IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY CAST(campaignID AS STRING), CAST(adgroupID AS STRING)
    ORDER BY reportDate DESC
  ) = 1
)
SELECT
  v.adgroup_id,
  v.campaign_id,
  COALESCE(NULLIF(v.ad_group_name_raw, ''), l.adgroup_name) AS ad_group,
  CASE WHEN v.adgroup_id IS NOT NULL AND v.adgroup_id != '' THEN 'id-matched'
       WHEN l.adgroup_name IS NOT NULL THEN 'name-matched'
       ELSE 'no-match' END AS join_quality,
  SUM(v.visits) AS visits,
  SUM(v.ATCs) AS ATCs,
  SAFE_DIVIDE(SUM(v.ATCs), SUM(v.visits)) AS atc_rate,
  SUM(v.PDP_views) AS PDP_views,
  SAFE_DIVIDE(SUM(v.PDP_views), SUM(v.visits)) AS pdp_rate,
  SUM(v.site_orders) AS site_orders,
  SUM(v.site_revenue) AS site_revenue
FROM visits v
LEFT JOIN tiktok_lookup l
  ON v.campaign_id = l.campaign_id AND v.adgroup_id = l.adgroup_id
GROUP BY 1,2,3,4
