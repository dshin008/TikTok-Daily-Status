# Scoring card (thresholds)

Use this file for exact numbers. `SKILL.md` is the operating procedure.

## Primary KPIs by funnel

| Funnel | How classified | Primary KPI |
|---|---|---|
| Upper | `REACH` / `RF_REACH` / `VIDEO_VIEWS` (and `TRAFFIC` best-fit) | 6-Second VTR |
| Mid | `WEB_CONVERSIONS` + `CONVERT` | PDP Rate = PDP_views / visits |
| Low | `WEB_CONVERSIONS` + `VALUE`, or `PRODUCT_SALES` / `CATALOG_SALES` | ATC Rate = ATCs / visits |

Exclude `LEAD_GENERATION` entirely. Full funnel map + SQL → `data-model.md`.

## Windows

| Window | Source | Purpose |
|---|---|---|
| Yesterday | TikTok | Pulse + CTR / delivery-halt |
| Prior 7d (d-8…d-2) | TikTok | CTR baseline |
| Recent 3 **settled** days | BigQuery (Mid/Low) or TikTok (Upper) | Decay + below-peers (day-by-day) |
| Baseline 14d before recent | BigQuery / TikTok | Own-history comparison |

Never average the 3 recent days before scoring — compare **each day** to the threshold.

## Materiality

- Eligible for 🔴 if yesterday spend ≥ **$25** **or** impressions ≥ **500**
- Mid/Low decay needs baseline visits ≥ **200**
- Upper decay needs baseline impressions ≥ **3,000**
- Soft volume → do not force into 🔴 on noise alone

## Path 1 — Decay (getting worse)

Compare each of the 3 recent days to **own baseline × 0.75** (Upper VTR: × **0.70**).

| Days below | Result |
|---|---|
| **3 of 3** | 🔴 |
| 2 of 3 | Internal watch only — **not** Slack |
| 0–1 | No decay flag |

Reason codes: `vtr-decay` / `pdp-decay` / `atc-decay`.

### CTR collapse (TikTok, all funnels)

Yesterday **and** day-before CTR both `< 7d avg CTR × 0.70` with material spend → 🔴 (`ctr-collapse`).

### Delivery halt

`ENABLE` + yesterday spend **$0** + 7d avg spend **> $50/day** → 🔴 (`delivery-halt`).  
Do **not** flag intentional budget cuts (spend-drop vs 7d).

## Path 2 — Below peers (consistent struggle)

Peer set = other **eligible** ad groups in the **same funnel** this run (median of their recent-day primary KPI). Need ≥ **5** peers or skip this path.

| Funnel | Below-peer if |
|---|---|
| Upper | 6s VTR `< peer median × 0.70` |
| Mid | PDP `< peer median × 0.75` |
| Low | ATC `< peer median × 0.75` |

| Days below | Result |
|---|---|
| **3 of 3** | 🔴 |
| 2 of 3 | Not Slack (unless Mid/Low **and** CTR also `< peer CTR × 0.75` both yesterday and day-before → escalate to 🔴) |
| 0–1 | No below-peer flag |

Reason codes: `low-vtr` / `low-pdp` / `low-atc`.

### Absolute floor (Low funnel only)

Stops “everyone is bad so peer median collapses” from hiding chronic underperformers:

- If yesterday spend ≥ **$150** and ATC `< **1.0%** on **3 of 3** settled days → 🔴 (`low-atc`) even if peer median is also soft.

## Do not use for the list

| Signal | Rule |
|---|---|
| VTC | Never alone; never lead Why |
| Spend-drop vs 7d | Never (budget cuts) |
| Ad-level (old Signal E) | **Never** — clutter |
| Watch / Do-next | Never in Slack |

## Delivery fill (optional Slack block, not a list Why)

**Only groups that should be delivering.** If Ads Manager shows **Paused** or **Ended**, or
yesterday spend is $0 because the group is off — **skip**. A $0 budget on a paused/ended group
is expected, not a launch bug.

### Eligibility (check before fill math)

Include **only** when **all** are true:

| Gate | Rule |
|---|---|
| Ad group on | `operation_status = ENABLE` |
| Campaign on | parent campaign `operation_status = ENABLE` |
| Not paused/ended | `secondary_status` is **not** `ADGROUP_STATUS_DISABLE`, `ADGROUP_STATUS_CAMPAIGN_DISABLE`, or `ADGROUP_STATUS_RF_TIME_DONE` |
| Has a budget | resolved daily budget **> $0** (see below) |

**Skip entirely** (never Delivery FLAG) when `operation_status = DISABLE`, Ads Manager status
is **Paused** or **Ended**, or resolved daily budget is **$0**. Do not infer a budget for
off groups.

Use `secondary_status` from Stage 3 `adgroup_get` — do **not** request `primary_status`
(TikTok returns 40002). Full status map → `adgroup-delivery-watch` skill.

**In-scope delivery states** (when ENABLE + budget > 0): Active
(`ADGROUP_STATUS_DELIVERY_OK`), Partial delivery (`ADGROUP_STATUS_REVIEW_PARTIALLY_APPROVED`),
Under review (`ADGROUP_STATUS_AUDIT`, `ADGROUP_STATUS_REAUDIT`). Under review may show $0
until approved — do not FLAG those as underspend.

### Fill math (eligible groups only)

Fill = yesterday spend ÷ **daily** budget. If ad group `budget` is 0, use campaign daily budget
(CBO). If both resolve to $0 → **skip** (not eligible).

Slack **Delivery FLAG** only when eligible **and**: fill **&lt; 50%**, or fill **&lt; 20%**, or
$0 spend with budget ≥ **$50**. Do not Slack 50–79% or Under review. Does **not** count toward
the top 10.

## Why-line format

One short clause led by primary code, e.g.:

- `atc-decay — ATC 0.9% vs 14d 2.0% — 3/3 below`
- `low-atc — ATC 0.5% vs LF peer 1.5% — 3/3 below`
- `ctr-collapse — CTR 1.1% vs 7d 2.0% — 2 days`
