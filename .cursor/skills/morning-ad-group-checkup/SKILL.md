---
name: morning-ad-group-checkup
description: >
  Read-only morning triage for TikTok ad groups — funnel-aware version. Classifies every ad
  group as Upper/Mid/Low funnel from its campaign's objective_type (and optimization_goal for
  WEB_CONVERSIONS campaigns), then scores it on the KPI that actually matters for that funnel
  stage (6-Second VTR for UF, PDP Rate for MF, ATC Rate for LF), using
  same-day TikTok metrics for the "yesterday" pulse and settled BigQuery site/revenue data for
  the 3-day-vs-14-day decay check AND sustained low absolute performance vs funnel peers.
  Also flags broken-link / out-of-stock risk: a PDP-to-cart (VTC) rate drop at the ad group
  level, or a specific ad inside a group getting clicks (healthy CTR) but no carts.
  Not a creative rotation plan; flags creative follow-up for the
  creative associate when decay looks creative-driven.
  Triggers: morning checkup, morning analysis, daily ad group review, which ad groups need
  attention, struggling ad groups, ad group health check, daily triage, what should I check
  today, morning digest, PDP rate, ATC rate, 6 second VTR, broken link, out of stock, product
  link check.
  ❌ Do NOT use for: weekly exec memos (use weekly-account-business-review); creative
  retire/scale/rotate plans (use creative-fatigue-rotation-planner); executing budget/bid/pause
  changes (use ad-group-optimizer or manage-campaign). This skill never writes.
version: 2.6.0
---

# Morning Ad Group Checkup (read-only)

A **read-only** morning triage skill. It answers one question: **which ad groups need your
attention today, and why?** — judged against the metric that actually matters for that ad
group's funnel stage, not a generic CPA/CTR blend.

**Four independent flag reasons** — an ad group can trip any combination; do not treat decay
alone as sufficient:
1. **Getting worse** (Signal A/B) — trend vs its own history or yesterday vs 7-day avg
2. **Sitting low** (Signal C) — persistently weak vs **funnel peers**, even when flat (no decline)
3. **Broken link / OOS risk** (Signal D) — PDP-to-cart (VTC) rate drops even though clicks and
   PDP views look fine; classic signature of a link pointing at the wrong product or a product
   going out of stock
4. **Ad-level click/cart gap** (Signal E) — one specific ad inside an otherwise-normal ad group
   is getting clicks (CTR is fine) but producing almost no carts — points at that ad's own
   product link, not the ad group as a whole

An ad group that has been bad for weeks and is *still* bad belongs on the list just as much as
one that just fell off a cliff. And a group whose *overall* ATC rate looks fine can still be
hiding one broken ad dragging down volume — Signal E exists to catch that case.

**Default account:** Wayfair US Search (`7125498373565726721`). Override only when the user
names a different `advertiser_id`.

**Full data model, funnel map, and SQL templates:** see `references/data-model.md`. This file
is the operating procedure; that file is the contract for exact fields, joins, and formulas.

**Report home:** every run saves its memo as
`Documents/TikTok-Daily-Status/LATEST.md` (Stage 8) — always the single most
recent morning, sitting right at the top level so it's obvious which one is current. Older
days get archived into `past-reports/{date}.md` automatically — that subfolder is the place to
look back at history, not this chat. **When running in a cloud automation with a connected
repo, write `LATEST.md` and `past-reports/` at the repo root** (same relative layout) and commit
the change — do not attempt to write to a local `/Users/...` path that won't exist in that
environment.

**Creative is out of scope for execution.** When decay looks creative-driven, add a one-line
note: *"Possible creative refresh — route to creative associate."* Do not run library scans or
produce Retire/Scale/Watch creative lists.

## Tool chain

```
Stage 0: advertiser_info_get (currency, timezone, status)
Stage 1: confirm windows (defaults below; user can override)
Stage 2 (TikTok-native, real-time — drives the "yesterday" pulse):
  ① report_integrated_get — ad group, YESTERDAY
  ② report_integrated_get — ad group, PRIOR 7 DAYS (days −8 through −2)
  ③ report_integrated_get — ad group, RECENT 3 DAYS
  ④ report_integrated_get — ad group, BASELINE 14 DAYS (non-overlapping, ending day before recent)
Stage 3: classify every ad group into Upper / Mid / Low funnel via its campaign's
  `objective_type` (`campaign_get`) plus, for `WEB_CONVERSIONS` campaigns only, the ad group's
  `optimization_goal` (`adgroup_get`) — see references/data-model.md §Funnel classification.
  Drop `LEAD_GENERATION` campaigns entirely.
Stage 4 (BigQuery, settled data — drives the decay check only, NOT the same-day pulse):
  ⑤ Mid + Low funnel ad groups only → query tbl_dash_visits (PDP rate, ATC rate, visits)
     **per individual day** for the 3 RECENT SETTLED days (not pre-aggregated — see
     §Trend-based decay below), plus one aggregated BASELINE 14d window as the comparison point,
     joined to TikTok ids/names
  ⑥ Low funnel ad groups only → query tbl_fact_attributed_financials (click-date AENR) same windows
  ⑦ Tag each ad group's BigQuery join: id-matched / name-matched / no-match
Stage 5: adgroup_get — status, budget, bid settings for flagged groups only
Stage 6: score + classify ad groups → Check Today / Watch / Healthy (funnel-aware KPI;
  Signals A/B/C/D — decay, yesterday anomaly, sustained low vs peers, AND VTC/link-risk drop.
  VTC uses data already pulled in Stage 4 — no extra query.)
Stage 6B (🔴 groups only): ad-level CTR/ATC gap check (Signal E) — pull ad-level TikTok CTR +
  ad-level BigQuery ATC rate for each 🔴 group's top-spend ads, flag any single ad with healthy
  clicks but near-zero carts
Stage 7: render morning memo + prioritized check-up queue
Stage 8: archive the current LATEST.md into past-reports/, then save today's memo as the new
  Documents/TikTok-Daily-Status/LATEST.md
```

---

## 🔒 Read-only scope (one-strike rule)

NEVER call any write/spend tool — no `*_create` (except `report_task_create` for async reads),
`*_update`, `*_status_update`, `*_budget_update`, `*_delete`. On the BigQuery side, **SELECT only**
— never `CREATE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, or `DROP` (see BigQuery safety rules).
If asked to "check and pause the worst," produce the check-up list, then **refuse the pause** and
route to `ad-group-optimizer` or `manage-campaign`.

## What this skill is NOT for

| Out-of-scope intent | Route to |
|---|---|
| Weekly exec memo for stakeholders | `weekly-account-business-review` |
| Which creatives to retire or rotate | `creative-fatigue-rotation-planner` |
| Change budgets, bids, or pause ad groups | `ad-group-optimizer` |
| Why one campaign won't deliver / rejections | `diagnose-campaign-health` |
| Anything on a `LEAD_GENERATION` campaign | Different team — out of scope entirely |

## MCP backend

| Purpose | Tool / Source | Mechanism |
|---|---|---|
| Advertiser details | `advertiser_info_get` | TikTok MCP, L0 direct |
| Ad group reports (same-day) | `report_integrated_get` | TikTok MCP, L0 direct |
| Ad group settings / optimization_goal / funnel split | `adgroup_get` | TikTok MCP, `tool_execute` |
| Campaign objective_type / funnel classification | `campaign_get` | TikTok MCP, `tool_execute` |
| TikTok diagnosis hints (optional) | `tool_diagnosis_get` | TikTok MCP, `tool_execute` |
| Site visits / PDP / ATC rate (settled) | `tbl_dash_visits` | BigQuery MCP `execute_sql` (or `bq` CLI) |
| Click-date attributed revenue (AENR, settled) | `tbl_fact_attributed_financials` | BigQuery MCP `execute_sql` (or `bq` CLI) |
| TikTok cost/name lookup for joins | `tbl_campaign_costs_tiktok_metrics_report` | BigQuery MCP `execute_sql` |

> TikTok metric values are **strings** — parse to numbers. Paywalled metrics → `n/a`, never guess.
> BigQuery queries are read-only `SELECT`s only — see `references/data-model.md` for exact SQL.

---

## STAGE 0 — Advertiser

Use `7125498373565726721` (Wayfair US Search) unless the user specifies another id.
Confirm with `advertiser_info_get` → keep `currency`, `timezone`, `status`.
`40001` → ask user to authorize the account or provide another id.

## STAGE 1 — Windows (morning defaults)

```
Morning checkup windows (account timezone):
  Yesterday:        {yesterday} only                      [TikTok-native]
  7-day baseline:   the 7 days before yesterday ({d-8}…{d-2})  [TikTok-native]
  Recent window:    last 3 SETTLED days ({d-4} through {d-2})  [BigQuery — see note]
  Decay baseline:   the 14 days BEFORE the recent window       [BigQuery — non-overlapping]
```

**Why the BigQuery windows are shifted back one extra day vs the TikTok windows:** site-visit
and revenue data in GBQ is not same-day fresh the way the TikTok API is. Per the user's
confirmed handling, use TikTok's own spend/CTR/VTR as the primary "what happened yesterday"
trigger, and only pull GBQ figures for a window that has had time to settle (ending 2 days
before yesterday, i.e. `d-2`) so PDP Rate / ATC Rate / AENR aren't judged on incomplete data.
Label the BigQuery-sourced numbers with the settled date range they actually cover — don't imply
they're "yesterday's" numbers.

Defaults are fixed unless the user asks to change them. **Date sanity:** no future dates;
all windows non-overlapping.

## STAGE 2 — Pull TikTok-native data (real-time signal)

Open with: *"Running your morning ad group checkup — usually 2–4 minutes since it checks day-by-day
trends, not just yesterday..."*

**Report params (all four pulls):**
- `report_type = BASIC`
- `data_level = AUCTION_ADGROUP`
- `dimensions = ["adgroup_id"]`
- `metrics = ["spend","impressions","clicks","ctr","cpc","cpm","adgroup_name","campaign_name",
  "video_watched_6s"]` — `video_watched_6s` is the **confirmed, verified** metric name for
  6-second focused video views (live-tested against Wayfair US Search on 2026-08-06; returns
  real data, e.g. adgroup `1871339896643714` → 135,992 six-second views over 2026-07-30→08-05).
  There is **no** `cost_per_video_watched_6s` metric — TikTok rejects it (`code 40002`). Compute
  Cost / 6s-View manually: `spend / video_watched_6s`.
- `enable_total_metrics = true`
- **`page_size = 1000`** (the max) — **always set this explicitly.** `report_integrated_get`
  defaults to `page_size: 10` if omitted, which silently forces 7-8+ extra paginated round-trips
  per window on an account this size (confirmed live 2026-08-07: one window alone took 8 separate
  page pulls). With `page_size: 1000` every window here should return in a single call — this was
  the single biggest driver of an 8-minute run vs. the expected 2-4 minutes. Only paginate with
  `page` if `page_info.total_page > 1` even at 1000 (shouldn't happen at this account's size).

Compute **7-day daily average** from the prior-7-day pull: total each metric ÷ 7.

For accounts where sync range limits apply, use `report_task_create` → `report_task_check` →
`report_task_download` for the 14-day baseline pull only.

## STAGE 3 — Funnel classification (native TikTok fields — verified live 2026-08-06)

Classify using **`objective_type`** (campaign-level, via `campaign_get`) and, only for
`WEB_CONVERSIONS` campaigns, **`optimization_goal`** (ad-group-level, via `adgroup_get`). This
was verified empirically against live Wayfair US Search campaigns/ad groups — no name-parsing,
no cmcode dependency. Full detail in `references/data-model.md` §Funnel classification.

**Performance-critical — bulk pull, never loop per ad group:** both `campaign_get` and
`adgroup_get` return **every** campaign/ad group for the advertiser in a **single call** when
`filtering` is omitted — just set `page_size: 1000` (max) so nothing gets cut off by the default
page size of 10. That means Stage 3 needs exactly **two** calls total, account-wide:

```
campaign_get(advertiser_id, page_size=1000,
             fields=["campaign_id","campaign_name","objective_type","operation_status"])
adgroup_get(advertiser_id, page_size=1000,
            fields=["adgroup_id","campaign_id","adgroup_name","optimization_goal",
                     "operation_status","budget"])
```

Do this **once each**, then join/filter the results in memory against the ad groups from Stage 2
— never call `campaign_get`/`adgroup_get` again per individual ad group just to read
`objective_type`/`optimization_goal`. Calling either endpoint once per ad group instead of once
for the whole account is the single biggest cause of a slow run (dozens of extra round-trips
turn a 2–4 minute run into 8+ minutes for no benefit — the account only has ~106 campaigns, well
under the 1,000-row cap, so one page covers everything). If the account ever exceeds 1,000
campaigns or ad groups, paginate with `page` — but that shouldn't happen here.

| `objective_type` | `optimization_goal` (if `WEB_CONVERSIONS`) | Funnel | Primary KPI |
|---|---|---|---|
| `REACH`, `RF_REACH`, `VIDEO_VIEWS` | — | **Upper** | 6-Second VTR, Cost / 6s-View |
| `TRAFFIC` | — | **Upper** (best fit; all currently `DISABLE` — low stakes) | 6-Second VTR if available, else CTR/CPC |
| `WEB_CONVERSIONS` | `CONVERT` | **Mid** | PDP Rate, Cost / PDP (CTR supplementary) |
| `WEB_CONVERSIONS` | `VALUE` | **Low** | ATC Rate (CTR + AENR click-date supplementary) |
| `PRODUCT_SALES`, `CATALOG_SALES` | — | **Low** | ATC Rate (CTR + AENR click-date supplementary) |
| `LEAD_GENERATION` | — | — | **Exclude entirely** — different team |
| `WEB_CONVERSIONS` with an `optimization_goal` other than `CONVERT`/`VALUE` | — | Unresolved | Flag for manual call — do not guess Mid vs Low |

Upper-funnel ad groups need **no BigQuery join** — 6s VTR is native TikTok data. Only Mid and Low
funnel ad groups need Stage 4. Note: `cmcode` (the code embedded in landing-page tracking URLs,
e.g. `TT49GTMMF`) is a **separate, orthogonal concern** — it's only used later for the BigQuery
join to site visit/revenue data (Stage 4), never for funnel classification.

## STAGE 4 — Pull BigQuery data (settled signal, funnel-scoped)

Only for ad groups classified Mid or Low funnel in Stage 3, and only for the windows defined in
Stage 1 (3 individual RECENT SETTLED days / Baseline 14d aggregate).

**Pull the 3 recent days separately (`GROUP BY date, adgroup_id`), never pre-aggregated into one
window.** The whole point of Stage 6's trend check is to tell a real multi-day decline apart from
one noisy day — that's impossible if the 3 days are already averaged together before you see them.

- **Mid funnel** → query `tbl_dash_visits` for `visits`, `PDP_views` (→ PDP Rate = PDP_views/visits)
  per day, plus one aggregated 14d baseline
- **Low funnel** → query `tbl_dash_visits` for `visits`, `ATCs` (→ ATC Rate = ATCs/visits) per day,
  plus one aggregated 14d baseline; `tbl_fact_attributed_financials` (click-date view) for AENR
  stays aggregated (supplementary only, doesn't need day-by-day)

Use the exact SQL templates in `references/data-model.md` §SQL templates — join priority is
**adgroup_id match first, name-based fallback second**.

**The user has confirmed UTM tagging has holes from a recent transition period — assume some ad
groups will not join.** For every ad group queried, tag the join outcome:
- `id-matched` — joined cleanly on `adgroup_id`
- `name-matched` — no id match, joined by lowercased adgroup/campaign name instead
- `no-match` — zero BigQuery rows despite TikTok spend

`no-match` ad groups get scored on **TikTok-native metrics only** (CTR as the fallback signal)
with a `data-gap` reason code — never silently substitute a 0% PDP/ATC rate for missing data.

## STAGE 5 — Enrich flagged groups

Stage 3's single bulk `adgroup_get` call already captured `operation_status` and `budget` for
every ad group — reuse that same response here, do **not** re-call `adgroup_get` for flagged
groups just to get fields you already have. Only make a fresh call if a specific flagged group
needs a field that bulk pull didn't request (e.g. current `bid_price`) — and even then, batch it:
pass all such ad group IDs in one `adgroup_ids` filter (up to 100 per call) rather than one call
per group. Optionally `tool_diagnosis_get` for 🔴 groups only — append as a secondary line, never
override the skill's own classification.

## STAGE 6 — Score and classify

### Data floors

- **Yesterday floor (TikTok-native, Signal B):** `yesterday spend ≥ $25` OR `yesterday
  impressions ≥ 500` to be eligible for "Check Today." Below floor → "thin data — skipped"
  unless status is ENABLE with $0 spend (possible delivery halt).
- **Decay floor (BigQuery, Signal A, Mid/Low only):** `baseline visits ≥ 200` to trust PDP/ATC
  rate decay. Below that, rely on Signal B (TikTok-native) only and mark low-confidence.
- **Upper funnel decay floor:** `baseline impressions ≥ 3,000` (6s VTR needs volume to be stable).

### Signal A — funnel-aware decay, TREND-BASED not single-window (recalibrated 2026-08-07)

**Why this changed:** the original design compared one averaged 3-day window against the 14-day
baseline. Dry-run against live Wayfair US Search data on 2026-08-07 showed this fires on **day-to-
day noise, not real problems** — 17 of 55 eligible ad groups (31%) tripped a "decay" flag from a
single averaged window, even though the account-wide Low-funnel ATC rate had only softened ~17%
(a real but mild move). Individual ad groups cross a flat 25%-worse line constantly just from
sampling noise on 3-day sample sizes. Requiring the decline to **persist across each of the 3
recent settled days individually**, rather than judging one blended average, cut confirmed red
flags roughly in half on the same data — from 17 to ~7 — while keeping every one of the real,
sustained declines. The user confirmed: *"day to day noise is not desired ... want to see a
consistent decline or low performance over a few days before it should be red flagged."*

Compare each of the **3 individual recent settled days** against the 14-day baseline rate
(same ratio threshold as before, 25% worse = ratio < 0.75), then count how many of the 3 days
cross that line:

- **Upper funnel** (TikTok-native, use the last 3 full days' `video_watched_6s`/`impressions` per
  day vs the 7-day baseline VTR): 3-of-3 days `< baseline_6s_vtr × 0.70` (30% worse, wider band
  since Upper decay floor already requires higher volume) OR persistent cost/6s-view inflation
- **Mid funnel:** 3-of-3 days `recent_pdp_rate < baseline_pdp_rate × 0.75`
- **Low funnel:** 3-of-3 days `recent_atc_rate < baseline_atc_rate × 0.75`
- **`no-match` ad groups (any funnel):** fall back to the same 3-of-3 logic on `ctr < baseline_ctr
  × 0.70` instead

If fewer than 3 settled days of data exist for an ad group (new launch, recent data gap), do not
red-flag on Signal A at all — mark `low-confidence` and rely on Signal B only.

| Days below threshold (of 3) | Verdict |
|---|---|
| 3 of 3 | Decay confirmed — eligible for 🔴 Check Today |
| 2 of 3 | Eligible for 🟡 Watch only, never 🔴 |
| 0–1 of 3 | No decay signal |

CTR decay and AENR-click-date remain supplementary context shown alongside a flagged ad group,
never a standalone trigger.

### Signal B — yesterday vs 7-day average (TikTok-native, all funnels, also trend-gated)

Same persistence principle applies here: a single bad day is `🟡 Watch` at most; **two
consecutive days** (yesterday AND the day before) escalates to `🔴 Check Today`. The one exception
is delivery halt, which is acute and real the moment it happens — no need to wait a second day.

- **Delivery halt (immediate, single-day):** `operation_status = ENABLE` but yesterday spend = 0
  while 7d avg > $50/day → straight to 🔴, no persistence check needed
- **Spend drop:** yesterday spend `< 7d_avg_spend × 0.60` (≥40% below normal) **on both yesterday
  and the day before** → 🔴; on yesterday only → 🟡
- **CTR collapse:** yesterday CTR `< 7d_avg_ctr × 0.70` with material spend, **on both yesterday
  and the day before** → 🔴; on yesterday only → 🟡

### Signal C — sustained low absolute performance vs funnel peers (added 2026-08-10)

**Why this exists:** Signal A only catches ad groups **getting worse vs their own 14-day
baseline**. An ad group can sit **persistently weak** — low ATC *and* low CTR — without a 3-day
*descent* and still deserve a flag. Confirmed live 2026-08-10: `Spark_BedroomFurniture_Broad_LF`
had poor ATC and CTR vs Evergreen VSA LF peers but scored Healthy because its rates were flat,
not declining. The user confirmed: *"it's not just going down consistently that matters — if it
is sitting low that is bad and should be flagged too."*

**Principle:** compare each ad group to **funnel peer median** (same funnel, same run), not only
to its own history. Use the **primary funnel KPI** first; CTR is a secondary escalator for
Low/Mid funnel groups that are weak on both.

**Step 1 — compute funnel peer medians** (after all eligible ad groups in that funnel are
scored; Mid/Low use id-matched BigQuery recent settled days, Upper uses TikTok-native last 3
full days):

| Funnel | Peer median input |
|---|---|
| Upper | Median 6s VTR across eligible Upper ad groups (each group's 3-day average) |
| Mid | Median PDP rate across eligible Mid ad groups (each day's rate, pooled across recent 3 settled days) |
| Low | Median ATC rate across eligible Low ad groups (each day's rate, pooled across recent 3 settled days) |

Also compute **funnel peer median CTR** (TikTok-native, yesterday) for Low/Mid supplementary use.

Minimum peer set: **≥ 5 eligible ad groups** in the funnel with sufficient data; if fewer, skip
Signal C for that funnel and mark `low-confidence`.

**Step 2 — per-ad-group low check** (same 3-of-3 / 2-of-3 persistence as Signal A):

Compare each **individual recent settled day** (Mid/Low) or **individual recent full day**
(Upper) against `funnel_peer_median × threshold`:

| Funnel | Primary KPI low threshold |
|---|---|
| Upper | `6s_vtr < funnel_peer_median_vtr × 0.70` |
| Mid | `pdp_rate < funnel_peer_median_pdp × 0.75` |
| Low | `atc_rate < funnel_peer_median_atc × 0.75` |

| Days below peer threshold (of 3) | Verdict |
|---|---|
| 3 of 3 | Sustained low — eligible for 🔴 Check Today |
| 2 of 3 | Eligible for 🟡 Watch only, never 🔴 on Signal C alone |
| 0–1 of 3 | No sustained-low signal |

**Step 3 — CTR double-weak escalator (Low/Mid only):** If primary KPI is **2-of-3** low (🟡 on
Signal C) **and** CTR is below `funnel_peer_median_ctr × 0.75` on **both** yesterday and the day
before → escalate to 🔴. This catches groups like Bedroom Furniture that are bad on ATC *and*
CTR even when ATC alone is only 2-of-3 below peers.

**`no-match` ad groups:** apply the same 3-of-3 logic using CTR vs funnel peer median CTR only;
reason code `low-ctr` + `data-gap`.

**Show both numbers in the memo** when Signal C fires: the ad group's rate, the funnel peer
median, and how far below (e.g. "ATC 0.9% vs LF peer median 2.4% — 3/3 days below").

Signal C and Signal A are **independent** — an ad group can flag on decay only, low-only, or
both. List all applicable reason codes in the Why column.

### Signal D — VTC (PDP-to-cart) drop: broken link / OOS risk (added 2026-08-11)

**Why this exists:** ATC Rate (Signal A/C) is `ATCs / visits` — it blends two separate steps:
did the visitor reach a product page, and once there, did they add to cart. A wrong product
link or an out-of-stock item breaks specifically the **second** step. The user confirmed this
live: a bed ad group was linking to a **sofa** product page — visits and PDP views looked
normal, but almost nobody carted once they landed, because the product shown wasn't what the ad
promised. ATC Rate alone flags this eventually, but conflates it with a click-quality problem;
VTC isolates it and names the likely cause directly.

**Formula:** `VTC rate = ATCs / PDP_views` — for both Mid and Low funnel ad groups. **No new
query needed** — the Stage 4 `tbl_dash_visits` pull already returns both `ATCs` and `PDP_views`
per day; VTC is computed in memory from data you already have.

**Step 1 — decay vs own 14-day baseline** (same trend-persistence rule as Signal A): compare
each of the 3 individual recent settled days' VTC rate to the 14-day baseline VTC rate.

| Days below `baseline_vtc × 0.75` (of 3) | Verdict |
|---|---|
| 3 of 3 | Link/OOS risk confirmed — eligible for 🔴 Check Today |
| 2 of 3 | Eligible for 🟡 Watch only |
| 0–1 of 3 | No signal |

**Step 2 — sustained low vs funnel peers** (same pattern as Signal C): compute funnel peer
median VTC rate (Mid + Low pooled, or per-funnel if the split matters — default to per-funnel to
match Signal C). Flag `< funnel_peer_median_vtc × 0.75` on 3-of-3 recent settled days → eligible
🔴; 2-of-3 → 🟡 only.

**Data floor:** require baseline `PDP_views ≥ 100` to trust the ratio; below that, mark
`low-confidence` and skip Signal D for that ad group (small-sample VTC swings wildly).

**Reason codes:** `vtc-decay` (own-baseline drop), `low-vtc` (sustained low vs peers). Always
show both the ad group's VTC rate and the comparison point when this fires (e.g. "VTC 4.1% vs
14d baseline 11.3% — 3/3 days below; check product link/stock on the landing PDP").

**This is a diagnostic pointer, not a creative call.** When Signal D fires, the recommended next
step is always: open the ad group's destination URL(s) in Ads Manager and confirm the linked
product still exists, matches the ad, and is in stock — the same playbook that fixed
`Spark_Bed_Broad_LF` on 2026-08-07. Do not route this to the creative associate; it's a
link/catalog issue, not a creative-fatigue one.

### Signal E — ad-level CTR/ATC gap (added 2026-08-11)

**Why this exists:** the user confirmed a second failure pattern: within one ad group, a
**specific ad** can be pulling healthy clicks while its own landing product is broken or
out-of-stock — high CTR (people are interested) paired with almost no carts from that ad
specifically. Ad-group-level metrics can hide this if the group's other ads are performing
normally and dilute the average. This signal drills one level down from ad group to individual
ad, but **only for ad groups that already flagged 🔴** in Stages A–D — running this for every ad
group in the account would multiply the number of TikTok/BigQuery calls and blow the 2-4 minute
runtime target for limited extra signal (a healthy ad group's individual ads are rarely worth
auditing one by one).

**Stage 6B procedure (🔴 groups only, run after initial Stage 6 classification):**

1. For each 🔴 ad group, pull ad-level TikTok data: `report_integrated_get`, `data_level:
   AUCTION_AD`, `dimensions: ["ad_id"]`, `filtering: [{field_name: "adgroup_ids", filter_type:
   "IN", filter_value: [adgroup_id]}]`, `metrics: ["spend","clicks","ctr","impressions","ad_name"]`,
   over the same **recent 3 settled days** window (align with the BigQuery window below). Batch
   multiple 🔴 ad groups into fewer calls with `adgroup_ids` IN-filter where the API allows it,
   rather than one call per group.
2. Pull ad-level BigQuery ATC data for the same 🔴 ad groups' ads: extend the standard
   `tbl_dash_visits` query with the **ad_id** regex extraction (`r'[\?&]ad_id=([^&]*)'` — already
   used in the AENR template in `references/data-model.md`), grouped by `ad_id` instead of
   `adgroup_id`, same recent settled window. Compute `ad_atc_rate = ATCs / visits` per `ad_id`.
3. Keep only ads with **material clicks** in the window (`clicks ≥ 30`) — thin-traffic ads are
   too noisy to call out by name.
4. Flag an ad when **both**: its CTR is at or above the ad group's own average CTR × 0.85 (it's
   not a low-interest ad) **and** its ad-level ATC rate is below the ad group's overall ATC rate
   × 0.50 (carting at less than half the group's normal rate). Cap to the **top 3 offending ads
   per ad group** by spend to keep the memo readable.

**Reason code:** `ad-link-risk`. Surface as a sub-line under the ad group's row in the 🔴 table
(never its own top-level row) — e.g. "⚠️ ad-level: `{ad_name}` — CTR 2.1% (normal) but ATC rate
0.3% vs group's 1.8% — check this ad's specific product link/stock."

**Scope discipline:** Signal E never promotes a 🟡 or ✅ ad group to a different bucket by
itself — it's a same-bucket diagnostic detail on an ad group that's already 🔴 for another
reason. If a 🟡 or ✅ ad group's underlying ads look worth auditing, say so as a one-line note
rather than running the full Stage 6B pull for it.

### Confidence floor

On low-volume ad groups (below the decay floor for their funnel, or with fewer than 3 settled days
of BigQuery data), show **absolute numbers** and mark **low confidence** — do not fire hard alarms
on noise, and never let a `low-confidence` tag alone push a group into 🔴.

### Classify each eligible ad group into ONE bucket

| Bucket | Criteria |
|---|---|
| **🔴 Check Today** | Signal A decay on 3-of-3 recent days OR Signal B anomaly on 2-of-2 recent days OR Signal C sustained low on 3-of-3 recent days vs funnel peers OR Signal C 2-of-3 low + CTR double-weak escalator OR Signal D (VTC) decay/sustained-low on 3-of-3 recent days OR delivery halt; AND material yesterday spend or impressions |
| **🟡 Watch** | Signal A decay on 2-of-3 days OR Signal B anomaly on yesterday only OR Signal C sustained low on 2-of-3 days vs funnel peers OR Signal D (VTC) decay/sustained-low on 2-of-3 days OR thin decay data OR `no-match` with CTR softening |
| **✅ Healthy** | No triggers; or below materiality floor |

Signal E never changes a bucket — it only adds an ad-level sub-note to ad groups already 🔴 from
Signals A–D (see Stage 6B above).

Tag each flagged group with **reason codes**: `vtr-decay` / `pdp-decay` / `atc-decay` /
`low-vtr` / `low-pdp` / `low-atc` / `low-ctr` / `vtc-decay` / `low-vtc` / `ad-link-risk` /
`spend-drop` / `delivery-halt` / `ctr-collapse` / `data-gap` / `low-confidence`.

**Spend needing attention** = sum of yesterday spend on 🔴 Check Today groups.

### Output length

Render the 🔴 Check Today table sorted by yesterday spend, descending. Show the **top 10** rows;
if more than 10 qualify, add a line: *"+{N} more 🔴 — full list available on request."* Never
silently truncate without saying so.

### Campaign clustering check

Before rendering, group the 🔴 (and 🟡) list by `campaign_name`. If **3 or more flagged ad groups
share one campaign**, don't present them as N independent problems — add a one-line callout above
the table: *"{N} of today's flags are on {campaign_name} — likely one shared cause (creative,
landing page, or a campaign-level setting change), not {N} separate issues."* This was confirmed
live on 2026-08-07: 8 of 9 confirmed 🔴 groups shared the `Evergreen VSA Broad Web LF/FF` campaign
pair, which is a materially different story than 9 scattered problems.

## STAGE 7 — Render morning memo

```
☀️ Morning Ad Group Checkup — {advertiser_name} ({advertiser_id}) · {currency}
{today's date} · Yesterday = {yesterday} · BigQuery settled through {d-2}

HEADLINE: {1 sentence — e.g. "3 ad groups need a check today; $X spent there yesterday."}

Account pulse (yesterday vs 7-day daily avg, TikTok-native)
  Spend        {y}     vs avg {avg}     {▲/▼ X%}
  CTR          …
  By funnel: Upper {n} groups · Mid {n} groups · Low {n} groups ({n} excluded: LEAD_GENERATION)

🔴 Check today ({N} ad groups, showing top 10 by spend)
  | Ad group | Campaign | Funnel | Why | Yesterday spend |
  |---|---|---|---|---|
  | …
  {if N > 10: "+{N-10} more 🔴 — full list available on request."}
  {for each 🔴 group with a Signal E hit: "⚠️ ad-level: {ad_name} — CTR {x}% (normal) but ATC
  rate {y}% vs group's {z}% — check this ad's product link/stock."}

🟡 Watch ({N}) — condensed; ad group names + reason codes only unless asked for detail

✅ Healthy / skipped ({M} below floor or no triggers)

Spend on 🔴 groups yesterday: ${spend_needing_attention}

Data quality
  · BigQuery join: {X} id-matched · {Y} name-matched · {Z} no-match (TikTok-only fallback used)
  · If Z is large, flag it plainly — UTM tagging gaps mean some ad groups can't be judged on
    PDP/ATC rate yet.

Notes for creative associate (if any)
  · {ad group} — possible creative-driven decay; not a rotation plan.

Assumptions & limits
  · TikTok windows same-day fresh; BigQuery windows settled through {d-2} (revenue/visits lag).
  · Funnel-aware KPIs: UF=6s VTR, MF=PDP Rate, LF=ATC Rate. LEAD_GENERATION campaigns excluded.
  · Flags fire on **decay** (vs own baseline), **yesterday anomaly**, **sustained low vs funnel
    peers**, or a **PDP-to-cart (VTC) drop** — not decay alone.
  · Low-volume / no-match groups marked low-confidence; paywalled metrics show n/a.
  · Signal E (ad-level CTR/ATC gap) only runs on 🔴 groups — a healthy-looking ad group could
    still hide one broken ad if its group-level averages never dipped below Signal A/C/D
    thresholds; ask for a manual ad-level check on any specific group if unsure.
  · This skill changes nothing in Ads Manager or BigQuery.

Do next (prioritized)
  1. [Today] Open 🔴 #1 in Ads Manager → check delivery, budget, bid, targeting
  2. …
  · `vtc-decay` / `low-vtc` / `ad-link-risk` groups → check the destination URL(s) first (product
    still exists, matches the ad, in stock) before touching budget, bid, or creative — same
    playbook that fixed Spark_Bed_Broad_LF on 2026-08-07
  · Budget/bid changes → ad-group-optimizer
  · Delivery/rejection issues → diagnose-campaign-health
  · Creative refresh → creative associate (creative-fatigue-rotation-planner for their workflow)
```

If every bucket is empty, say so honestly and still show account pulse + skipped counts.

## STAGE 8 — Save the report (LATEST.md + archive)

Goal: `LATEST.md` at the top level of `Documents/TikTok-Daily-Status/` (or the repo root, when
running as a cloud automation against the connected repo) is **always** the most recent
morning's memo, so it's obvious at a glance which one is current — never buried in a dated
subfolder. Older days live in `past-reports/`. This is a plain file save only — not a BigQuery
or TikTok call, and not a change to any ad account.

Steps, in order:

1. Use `{yesterday}` (the date the report is actually about, not today's run date) as the date
   label throughout — both in the memo header and for archiving.
2. Check whether `LATEST.md` already exists at the repo root.
   - **If it exists and its date (read the memo's own date line) is a *different* day** than
     today's `{yesterday}` → move it (don't delete it) to `past-reports/{that old date}.md`
     first. This is the archive step — it's what keeps history in `past-reports/` instead of
     piling up at the top level.
   - **If it exists and is already for the same `{yesterday}`** (a same-morning re-run) → skip
     archiving, it's about to be overwritten anyway.
   - If no `LATEST.md` exists yet (first run ever), skip archiving.
3. Write today's rendered memo to `LATEST.md` at the repo root, overwriting whatever was there.
4. **When running as a cloud automation:** commit and push the change on the connected branch
   (e.g. `main`) so the update is visible in GitHub. Use a short commit message like "Morning
   checkup {yesterday}". Do not force-push or rewrite history.
5. Do not ask permission for any of this — it's a routine save for a read-only workflow (it
   changes nothing in Ads Manager or BigQuery, only this repo's own report files).
6. Mention in chat/Slack, briefly: *"Saved as LATEST.md (yesterday's report moved to
   past-reports/{old date}.md)"* — or just *"Saved as LATEST.md"* if there was nothing to archive.

This is the durable home for every morning's memo — see the folder's own `README.md` for how to
browse `past-reports/`.

## Error codes

| Code | Trigger | Action |
|---|---|---|
| `E101_NO_ACCOUNT` | Can't resolve advertiser | Ask for `advertiser_id` |
| `E102_NO_PERMISSION` | `40001` | Surface; ask to authorize |
| `E103_NO_DATA` | No ad group spend yesterday and no 7d baseline | Report honestly; don't fabricate |
| `E104_API_FAIL` | 4xx/5xx | Surface raw code + message; retry once on 5xx |
| `E105_BQ_UNAVAILABLE` | BigQuery MCP/CLI fails | Fall back to TikTok-native-only scoring for Mid/Low funnel groups; label clearly as degraded mode |

## Worked example prompts

- *"Morning ad group checkup"*
- *"Which ad groups need attention today?"*
- *"Run my daily TikTok triage for Wayfair US Search"*
