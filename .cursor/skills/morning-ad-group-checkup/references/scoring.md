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

Fill = yesterday spend ÷ **daily** budget (if ad group budget is 0, use campaign daily budget).

Slack **Delivery FLAG** only when: fill **&lt; 50%**, or $0 spend with budget ≥ **$50**.  
Do not Slack 50–79% or Under review. Does **not** count toward the top 10.

## Why-line format

One short clause led by primary code, e.g.:

- `atc-decay — ATC 0.9% vs 14d 2.0% — 3/3 below`
- `low-atc — ATC 0.5% vs LF peer 1.5% — 3/3 below`
- `ctr-collapse — CTR 1.1% vs 7d 2.0% — 2 days`
