# Data model — morning-ad-group-checkup

This is the full contract behind `SKILL.md`: exact tables, join keys, funnel map, and SQL
templates. Reverse-engineered from the live BigQuery Data Connector definitions embedded in the
**TikTok Performance Tracker** Google Sheet (`1xou5AnzYbB_BozV46KP0FJjlVF0XozI4AhWKtFEjEeI`),
which refreshes daily at 8am ET from 4 BigQuery sources. Confirmed with the account owner on
2026-08-06.

## Sources

| Sheet tab | Table(s) | Grain | Role in this skill |
|---|---|---|---|
| TikTok UI Data | `wf-gcp-us-ae-adtech-prod.marketing_ad_costs.tbl_campaign_costs_tiktok_metrics_report` | ad, daily | Name/id lookup for joins; NOT used for same-day metrics (use TikTok MCP `report_integrated_get` instead — it's fresher) |
| Visits Data Ext | `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits` | session, daily | Visits, ATCs, PDP views, bounces, site-side orders/revenue |
| CD Revenue Ext | `wf-gcp-us-ae-mktg-prod.curated_order.tbl_fact_attributed_financials` (unnest `visit_info`) + `wf-gcp-us-ae-mktg-prod.analysis_paidsearch.tiktok_performance_col_curves` | click, click-date | Themis-modeled AENR/AEVC/gross revenue, credited back to click day, lag-curve adjusted |
| OD Revenue Ext | same `tbl_fact_attributed_financials` | click, order-date | Same Themis metrics credited to the day the order happened (no lag curve) |

**This skill only uses Visits Data Ext (Mid + Low funnel) and CD Revenue Ext's AENR field (Low
funnel supplementary only).** OD Revenue and the full TikTok UI Data table are documented here
for completeness but are not part of the morning checkup's read set — TikTok MCP already gives
same-day cost/engagement data, which is fresher than the GBQ mirror.

## Join key

Everything joins on TikTok's own `campaign_id` / `adgroup_id` / `ad_id`. In `tbl_dash_visits` and
`tbl_fact_attributed_financials`, these aren't columns — they're extracted by regex out of the
landing-page `event_url`'s query string (`adgroup_id=`, `ad_id=`, `campaign_id=`, or legacy
`utm_adgroup=` / `utm_content=` / `utm_campaign=`). **The account owner confirmed UTM parameters
changed during a transition period in the past few months — assume holes.** Fallback: join by
lowercased `campaignName`/`adgroupName` from the TikTok cost table
(`tbl_campaign_costs_tiktok_metrics_report`, filtered to `accountID = "7125498373565726721"`).

Always attempt id-match first, name-match second, and tag ad groups where neither works as
`no-match` rather than silently omitting them or fabricating a rate.

## Funnel classification (native TikTok fields — the authoritative method)

**Superseded approach:** an earlier version of this skill tried to classify funnel from the
`cmcode` embedded in landing-page tracking URLs (`TT49GTMMF`, `TT49VSA`, etc.), assuming it would
line up with TikTok's own `campaign_name`. **It does not.** Live campaign names use a completely
different, messier naming pattern (`LF`/`FF`/`BLS` suffixes, many campaigns with no suffix at
all — including the single biggest campaign by spend, "Evergreen VSA Broad Web" at $1.5M), and
`cmcode` isn't a native TikTok field at all — it only exists inside URL query strings. Verified
live against Wayfair US Search on 2026-08-06 and confirmed with the account owner:
- `LF` and `FF` suffixes are **both low-funnel content** — they're the two arms of a conversion
  lift study (narrow low-funnel audience vs. exposing the same low-funnel ads to full-funnel
  audiences). They are not different funnel stages.
- `BLS` = Brand Lift Study, a survey overlay layered on top of a campaign — not a funnel signal
  and not something to flag for content action.
- Campaigns with no suffix at all (like "Evergreen VSA Broad Web") can still be genuinely low
  funnel — confirmed by checking the underlying `optimization_goal`, which matched its `_LF`
  sibling campaign exactly (`VALUE` on both).

**Correct approach: use TikTok's own structured objective fields.** Verified empirically by
pulling `campaign_get` (`objective_type`, all 106 campaigns, all statuses) and `adgroup_get`
(`optimization_goal`) for representative campaigns on 2026-08-06:

| `objective_type` (campaign-level) | `optimization_goal` (ad-group-level, `WEB_CONVERSIONS` only) | Funnel | Evidence |
|---|---|---|---|
| `REACH`, `RF_REACH`, `VIDEO_VIEWS` | — | **Upper** | "GTM Reach", "Promo Reach", etc. all return `objective_type: REACH` |
| `TRAFFIC` | — | **Upper** (best fit) | "Evergreen Traffic", "Promo Traffic" — both currently `DISABLE`, low stakes either way |
| `WEB_CONVERSIONS` | `CONVERT` | **Mid** | "GTM View Content" campaign → ad groups named `*_VC` (View Content) all have `optimization_goal: CONVERT` |
| `WEB_CONVERSIONS` | `VALUE` | **Low** | "Evergreen VSA Broad Web LF" and its no-suffix sibling "Evergreen VSA Broad Web" → ad groups named `Spark_*` all have `optimization_goal: VALUE` on both campaigns |
| `PRODUCT_SALES`, `CATALOG_SALES` | — | **Low** | Catalog/DPA-style campaigns, straightforward purchase intent |
| `LEAD_GENERATION` | — | **Excluded** | Owner confirmed: different team, out of scope entirely |
| `WEB_CONVERSIONS` with any other `optimization_goal` | — | **Unresolved** | Flag for a manual call — don't guess |

`cmcode` still matters, but only for a **separate, later concern**: joining an ad group to its
BigQuery site-visit/revenue data (Stage 4 of the skill). It plays no role in funnel
classification anymore.

### Verification log (2026-08-06, live against 7125498373565726721)
- `video_watched_6s` confirmed as the correct 6-second video metric name — `six_second_video_views`
  was rejected by the API (`code 40002`); `video_watched_6s` returned real values (e.g. adgroup
  `1871339896643714`, "Spark_Couches_Broad_LF" → 135,992 six-second views, $33,619 spend,
  2026-07-30→08-05).
- `cost_per_video_watched_6s` is **not** a valid metric — compute manually as `spend /
  video_watched_6s`.
- Full `objective_type` spread seen across the account (106 campaigns, all statuses): `REACH`,
  `RF_REACH`, `VIDEO_VIEWS`, `TRAFFIC`, `WEB_CONVERSIONS`, `PRODUCT_SALES`, `CATALOG_SALES`,
  `LEAD_GENERATION`. No other values observed as of this date — if a new one appears in a future
  run, flag it for a manual call rather than assuming a funnel.

## Trend-based decay (recalibrated 2026-08-07)

**Superseded approach:** comparing one averaged 3-day window against the 14-day baseline. Verified
live against Wayfair US Search on 2026-08-07: this fired on 17 of 55 eligible ad groups (31%) from
pure day-to-day sampling noise on 3-day sample sizes, even though the true account-wide Low-funnel
ATC rate had only softened ~17% (aggregate recent 1.68% vs baseline 2.02% — a real, mild move, not
17 individual crises). The user confirmed: *"day to day noise is not desired ... want to see a
consistent decline or low performance over a few days before it should be red flagged."*

**Current approach:** pull the 3 most recent settled days **individually** (`GROUP BY date,
adgroup_id`, never pre-averaged) and compare each day's rate to the 14-day baseline separately.
Require the decline to hold on **all 3 of 3 days** before calling it 🔴 Check Today; 2-of-3 is
🟡 Watch only. Re-running the same 2026-08-07 data this way cut confirmed reds from 17 to ~7 on the
ad groups with full 3-day data captured, while every one of the 7 was a real, sustained decline
(verified spot-check: e.g. Spark_Bed_Broad_LF's ATC rate was 1.57%, 1.77%, 1.70% across Aug 3-5,
all below its 2.59% baseline — a real pattern, not a blip).

Same trend-persistence principle applies to Signal B (spend-drop, CTR-collapse): require the
anomaly on **both** yesterday and the day before to escalate to 🔴; a single bad day is 🟡 at most.
Delivery halt (`operation_status = ENABLE` with $0 spend) is the one exception — it's acute and
real the moment it happens, so it goes straight to 🔴 without waiting for a second day.

## Sustained low absolute performance vs funnel peers (Signal C — added 2026-08-10)

**Problem Signal A alone misses:** decay compares an ad group to **its own 14-day baseline**. An
ad group that has been weak for the entire baseline window — e.g. `Spark_BedroomFurniture_Broad_LF`
with persistently low ATC and CTR vs Evergreen VSA LF peers — never trips decay because it isn't
*getting worse*; it's just *staying bad*. User confirmed 2026-08-10: sitting low should flag too.

**Approach:** after computing per-ad-group primary KPIs for the recent 3 settled days, compute
**funnel peer median** primary KPI across all eligible id-matched ad groups in that funnel (same
run). Flag when an ad group is **persistently below peer median × threshold** (3-of-3 days), using
the same anti-noise persistence rule as Signal A.

| Funnel | Primary low check | Peer threshold |
|---|---|---|
| Upper | 6s VTR (TikTok-native, per day) | `< funnel_peer_median_vtr × 0.70` |
| Mid | PDP rate (BigQuery, per settled day) | `< funnel_peer_median_pdp × 0.75` |
| Low | ATC rate (BigQuery, per settled day) | `< funnel_peer_median_atc × 0.75` |

**CTR double-weak escalator (Low/Mid):** primary KPI 2-of-3 low + CTR below peer median × 0.75 on
both yesterday and day-before → 🔴 (catches groups weak on both business KPI and click efficiency).

**Peer set floor:** need ≥ 5 eligible ad groups in the funnel with sufficient data; otherwise skip
Signal C for that funnel.

Reason codes: `low-vtr`, `low-pdp`, `low-atc`, `low-ctr` (no-match CTR-only fallback).

Signal A (decay), Signal B (yesterday anomaly), and Signal C (sustained low vs peers) are
**independent** — list all applicable codes in the memo.

## Broken link / OOS risk — VTC drop (Signal D) and ad-level CTR/ATC gap (Signal E) (added 2026-08-11)

**Problem neither Signal A/B/C fully names:** ATC Rate (`ATCs / visits`) blends two separate
steps — click quality (did the ad get someone to the site at all) and product-page conversion
(did they cart once they saw the product). A wrong product link or an out-of-stock item breaks
specifically the second step, but a plain ATC-rate decay flag doesn't say *why* — the analyst
still has to guess whether it's creative fatigue, targeting drift, or a broken link. User
confirmed live 2026-08-07: `Spark_Bed_Broad_LF` was linking to a **sofa** product page — visits
and PDP views were normal, ATC rate collapsed. Isolating the PDP→cart step directly (VTC) points
straight at the likely cause instead of leaving it ambiguous.

**Signal D — VTC rate, ad-group level.** `VTC = ATCs / PDP_views`. Both fields are already
returned by the standard Mid/Low `tbl_dash_visits` query (see SQL above) — this is a zero-cost
derived metric, not a new pull. Apply the same two checks used elsewhere in this skill:

| Check | Threshold | Verdict |
|---|---|---|
| Decay vs own 14d baseline VTC | `< baseline_vtc × 0.75` on 3-of-3 recent settled days | 🔴 eligible |
| Decay vs own 14d baseline VTC | 2-of-3 days | 🟡 only |
| Sustained low vs funnel peer median VTC | `< funnel_peer_median_vtc × 0.75` on 3-of-3 days | 🔴 eligible |
| Sustained low vs funnel peer median VTC | 2-of-3 days | 🟡 only |

Data floor: baseline `PDP_views ≥ 100`, else mark `low-confidence` and skip Signal D for that ad
group. Reason codes: `vtc-decay`, `low-vtc`.

**Signal E — ad-level CTR/ATC gap, 🔴 groups only.** The user's second confirmed pattern: one ad
inside an otherwise-fine ad group gets clicks (interest is real) but produces almost no carts
from that ad specifically — a group-level average can hide this if the group's other ads are
fine. This is scoped to ad groups **already 🔴** from Signals A–D to avoid multiplying API calls
across every ad group in the account (this account has 300+ live ads — auditing all of them
individually every morning would blow the 2-4 minute runtime target for a check that's rarely
useful on healthy groups).

Procedure: pull ad-level TikTok CTR (`report_integrated_get`, `data_level: AUCTION_AD`,
`dimensions: ["ad_id"]`, filtered to the 🔴 ad group's `adgroup_id`) and ad-level BigQuery ATC
rate (extend the standard visits query with the `ad_id` regex extraction below, grouped by
`ad_id`), same recent settled window as the rest of the run. Flag an ad when its CTR is `≥` the
ad group's own average CTR `× 0.85` **and** its ad-level ATC rate is `<` the ad group's overall
ATC rate `× 0.50`, with `clicks ≥ 30` to filter out noise. Cap to top 3 offending ads per group
by spend. Reason code: `ad-link-risk`. Never promotes a bucket by itself — see Signal E's own
section in `SKILL.md` for the full rule.

### SQL: ad-level ATC rate (for Signal E, 🔴 groups only)

Same source and `cmcode` filter as the standard Mid/Low query, but extract **`ad_id`** instead
of (or in addition to) `adgroup_id`, and group by `ad_id`. Scope to a specific ad group by
filtering the extracted `adgroup_id` to the 🔴 group(s) under review — don't run this ungated
across the whole account.

```sql
WITH visits AS (
  SELECT
    SessionStartDate AS d,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_id=([^&]*)')), r'[{}]', '') AS agid,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]ad_id=([^&]*)')), r'[{}]', '') AS adid,
    COUNT(*) AS visits,
    SUM(AddedToCart) AS ATCs
  FROM `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits`
  WHERE cmcode IN {cmcode_list}
    AND sessionstartdate BETWEEN DATE('{recent_window_start}') AND DATE('{recent_window_end}')
    AND event_soid = 49
  GROUP BY ALL
)
SELECT
  agid AS adgroup_id,
  adid AS ad_id,
  SUM(visits) AS visits,
  SUM(ATCs) AS ATCs,
  SAFE_DIVIDE(SUM(ATCs), SUM(visits)) AS ad_atc_rate
FROM visits
WHERE agid IN ({flagged_adgroup_ids})
  AND adid IS NOT NULL AND adid != ''
GROUP BY 1, 2
ORDER BY adgroup_id, ad_id
```

Join this to the ad-level TikTok pull (`report_integrated_get` at `data_level: AUCTION_AD`,
`dimensions: ["ad_id"]`) on `ad_id` to get each ad's CTR and clicks alongside its site-side ATC
rate. Same `id-matched` / `no-match` tagging discipline applies — an ad with no BigQuery match
gets skipped for Signal E rather than assigned a fabricated rate.

## KPI formulas by funnel

| Funnel | Primary KPI | Formula | Supplementary |
|---|---|---|---|
| Upper | 6-Second VTR | `video_watched_6s / impressions` (TikTok-native; metric name confirmed live 2026-08-06) | Cost / 6s-View = `spend / video_watched_6s` (no direct `cost_per_*` metric exists — compute manually) |
| Mid | PDP Rate | `PDP_views / visits` (from `tbl_dash_visits`: `SUM(SawProductDisplayPage) / COUNT(*)`) | Cost / PDP = `spend / PDP_views`; CTR; VTC (below) |
| Low | ATC Rate | `ATCs / visits` (from `tbl_dash_visits`: `SUM(AddedToCart) / COUNT(*)`) | CTR; AENR click-date = `expectednetrevenue_themischampion + mediarevenue_themischampion` (summed from `tbl_fact_attributed_financials`); VTC (below) |
| Mid + Low | VTC (View-to-Cart, Signal D) | `ATCs / PDP_views` — isolates the PDP→cart step specifically | Both fields already returned by the standard Mid/Low `tbl_dash_visits` query above — no extra query. Distinct from ATC Rate, which blends click→visit *and* visit→cart. |

## SQL templates

All templates take `{account_id}` (default `7125498373565726721`), `{window_start}`,
`{window_end}` (inclusive, `YYYY-MM-DD`, account timezone `America/New_York`), and the fixed
`cmcode` list below (minus `TT49LEADS`, which should never appear in this skill's pulls).

```
cmcode_list = ('TT49BTSUF','TT49BTSMF','TT49NBAU','TT49VSA','TT49DPA','TT49GTMMF',
               'TT49VERIFIEDMF','TT49OUTDOORMF','TT49PROMOMF','TT49GTMUF','TT49VERIFIEDUF',
               'TT49OUTDOORUF','TT49PROMOUF','TT49OUTDOORLF','TT49VPROMOMF','TT49VPROMOUF',
               'TT49RMN')
```

### Mid/Low funnel: visits, PDP rate, ATC rate (id-match first, name fallback)

**Run this once for the Baseline 14d window** (aggregated as shown — a single comparison number is
fine for the baseline). **For the Recent 3d window, run the daily-grain variant further below
instead** — do not aggregate the 3 recent days together, or you lose the ability to tell a
persistent decline from one noisy day (see §Trend-based decay above).

```sql
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
  WHERE cmcode IN {cmcode_list}
    AND sessionstartdate BETWEEN DATE('{window_start}') AND DATE('{window_end}')
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
  WHERE accountID = "{account_id}"
    AND reportDate >= DATE('{window_start}') - 10
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
```

### Recent 3d window: daily-grain variant (do not aggregate across dates)

Same source, join, and `cmcode` list as above, but **keep `date` in the final `GROUP BY`** instead
of collapsing it — this is the query that actually powers the trend check in Stage 6:

```sql
WITH visits AS (
  SELECT
    SessionStartDate AS d,
    REGEXP_REPLACE(LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_id=([^&]*)')), r'[{}]', '') AS agid,
    COUNT(*) AS v,
    SUM(AddedToCart) AS a,
    SUM(SawProductDisplayPage) AS p
  FROM `wf-gcp-us-ae-sf-prod.curated_clickstream.tbl_dash_visits`
  WHERE cmcode IN {cmcode_list}
    AND sessionstartdate BETWEEN DATE('{recent_window_start}') AND DATE('{recent_window_end}')
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
  SAFE_DIVIDE(SUM(p), SUM(v)) AS pdp_rate
FROM visits
WHERE agid IS NOT NULL AND agid != ''
GROUP BY 1, 2
ORDER BY adgroup_id, date
```

Then, per ad group: compare each of the 3 returned `date` rows' `atc_rate`/`pdp_rate` against the
(separately-queried, aggregated) 14-day baseline rate. 3-of-3 days below `baseline × 0.75` = 🔴
eligible; 2-of-3 = 🟡 only. Fewer than 3 rows returned (thin/gapped data) → skip Signal A, mark
`low-confidence`, rely on Signal B.

### Low funnel supplementary: AENR (click-date)

```sql
WITH cd_revenue AS (
  SELECT
    v.campaign_info.cmcode AS cmcode,
    LOWER(REGEXP_EXTRACT(event_url, r'[\?&]adgroup_id=([^&]*)')) AS adgroup_id,
    SUM(v.expectednetrevenue_themischampion) + SUM(v.mediarevenue_themischampion) AS aenr
  FROM `wf-gcp-us-ae-mktg-prod.curated_order.tbl_fact_attributed_financials` faf
  LEFT JOIN UNNEST(faf.visit_info) v
  WHERE v.campaign_info.cmcode IN {cmcode_list}
    AND soid = 49
    AND clickdate BETWEEN DATE('{window_start}') AND DATE('{window_end}')
  GROUP BY 1, 2
)
SELECT cmcode, adgroup_id, SUM(aenr) AS aenr
FROM cd_revenue
GROUP BY 1, 2
```

Note: this is the **click-date, non-lag-curve-adjusted** AENR (simpler than the sheet's full
`cla_aenr`, which applies a carry-over-lag multiplier from `tiktok_performance_col_curves` for
revenue that hasn't fully accrued yet). Use the simple sum for a directional decay signal — this
is a supplementary metric, not the primary trigger, so the lag-curve adjustment isn't worth the
extra join for this skill's purpose.

## Performance notes

**`report_integrated_get` pagination (confirmed 2026-08-07, first live run):** default
`page_size` is `10` (max `1000`). The first end-to-end run of this skill against Wayfair US
Search took ~8 minutes instead of the expected 2-4, and the trace showed why: one report window
alone needed 8 sequential page pulls before `page_size: 1000` was added to SKILL.md's Stage 2
params. `campaign_get`/`adgroup_get`, by contrast, were already being called as single bulk pulls
(no `filtering`, whole account) and were not a bottleneck — don't "fix" those further. If a
future run is slow again, check `page_info.total_page` on the report calls first before assuming
it's a per-ad-group looping problem.

## Known limitations (be upfront about these in the memo)

1. **UTM holes.** Confirmed by the account owner: tracking parameters changed during a recent
   transition period. Expect a meaningful `no-match` rate. Report the match-quality breakdown
   every run so the gap is visible, not hidden.
2. **GBQ settlement lag.** Site visits and revenue in BigQuery are not same-day fresh. This skill
   never claims a BigQuery-sourced number is "yesterday's" — it's always labeled with the actual
   settled date range.
3. **AENR is a model, not cash.** Themis (`*_themischampion` fields) is Wayfair's internal
   attribution model — it's an expected/modeled figure, not confirmed settled revenue. Site-side
   `TotalOrders`/`TotalRevenue` from `tbl_dash_visits` are actual observed site behavior; prefer
   those over AENR when both are available and they disagree materially.
4. **Unrecognized `objective_type` or an unexpected `optimization_goal`** on a `WEB_CONVERSIONS`
   campaign gets flagged for a manual funnel call, never guessed.
