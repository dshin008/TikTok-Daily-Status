
WITH evergreen_ads AS (
  SELECT
    CAST(adid AS STRING) AS ad_id,
    ANY_VALUE(adName) AS ad_name,
    ANY_VALUE(adgroupName) AS adgroup_name,
    ANY_VALUE(CAST(adgroupID AS STRING)) AS adgroup_id,
    ANY_VALUE(CAST(campaignID AS STRING)) AS campaign_id,
    ANY_VALUE(campaignName) AS campaign_name,
    ROUND(SUM(spend), 2) AS spend_90d
  FROM `wf-gcp-us-ae-adtech-prod.marketing_ad_costs.tbl_campaign_costs_tiktok_metrics_report`
  WHERE accountID = '7125498373565726721'
    AND campaignName LIKE 'Evergreen VSA Broad Web%'
    AND reportDate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  GROUP BY 1
),
creative_from_visits AS (
  SELECT
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[?&]ad_id=([^&]*)')), r'[{}]', '') AS ad_id,
    ANY_VALUE(REGEXP_EXTRACT(event_url, r'[?&]creative_id=([0-9]+)')) AS creative_id
  FROM `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits`
  WHERE cmcode = 'TT49VSA'
    AND SessionStartDate >= DATE_SUB(CURRENT_DATE('America/New_York'), INTERVAL 90 DAY)
    AND event_soid = 49
    AND REGEXP_CONTAINS(event_url, r'creative_id=[0-9]+')
    AND REGEXP_CONTAINS(event_url, r'[?&]ad_id=')
  GROUP BY 1
),
masterlist_deduped AS (
  SELECT
    Creative_Asset_ID,
    Filename_or_Creator AS creator,
    Campaign_or_Link AS tiktok_link,
    REGEXP_EXTRACT(Campaign_or_Link, r'/video/([0-9]+)') AS tiktok_item_id
  FROM `wf-gcp-us-ae-mktg-prod.analysis_paidsearch.creative_assets_id_masterlist`
  WHERE Campaign_or_Link LIKE '%tiktok.com%/video/%'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY Creative_Asset_ID
    ORDER BY LENGTH(Campaign_or_Link) DESC
  ) = 1
)
SELECT
  a.ad_id,
  v.creative_id,
  a.ad_name,
  a.adgroup_name,
  a.adgroup_id,
  a.campaign_id,
  a.campaign_name,
  a.spend_90d AS spend_14d,
  m.creator,
  m.tiktok_link,
  m.tiktok_item_id,
  CURRENT_DATE('America/New_York') AS refreshed_date
FROM evergreen_ads a
LEFT JOIN creative_from_visits v ON a.ad_id = v.ad_id
LEFT JOIN masterlist_deduped m ON v.creative_id = m.Creative_Asset_ID
ORDER BY a.adgroup_name, a.spend_90d DESC
