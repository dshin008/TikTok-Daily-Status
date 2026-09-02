---
name: morning-ad-group-checkup
description: >
  Read-only morning triage for TikTok ad groups. Flags the top 10 groups David should open
  today — either new decay vs their own baseline, or consistent struggle below funnel peers
  (or Low-funnel absolute ATC floor). Funnel KPIs: Upper=6s VTR, Mid=PDP Rate, Low=ATC Rate.
  Slack is the primary deliverable (short numbered list). No ad-level flags. No Watch/Do-next
  essay. Optional Delivery FLAG (spend vs daily budget) after the list.
  Triggers: morning checkup, daily ad group review, which ad groups need attention, struggling
  ad groups, morning digest.
  ❌ Not for: weekly WBR, creative rotation plans, executing budget/bid/pause changes.
version: 3.0.0
---

# Morning Ad Group Checkup (read-only)

**Product goal:** David logs on and immediately sees which ad groups are having a hard time.

An ad group qualifies for the list if **either**:
1. **New decay** — primary KPI fell vs its own recent baseline for 3 straight days, **or**
2. **Consistent struggle** — primary KPI sits below funnel peers for 3 straight days (Low funnel
   also has a simple absolute ATC floor — see `references/scoring.md`)

**Slack = the deliverable.** Top 10 numbered flags. Nothing else required to read.

**Default account:** Wayfair US Search (`7125498373565726721`).

**Details live in references — do not reinvent them:**
- `references/scoring.md` — thresholds, reason codes, floors
- `references/data-model.md` — funnel map, SQL, joins

## Hard bans

- **No ad-level rows or sub-lines** (old Signal E) — clutter
- **No 🟡 Watch / Do-next** sections in Slack
- **No markdown tables** in Slack (use numbered bullets)
- **No spend-drop vs 7d** as a Why (intentional budget cuts)
- **No VTC-led Why** (VTC is not a list reason)
- **No custom Python scoring engine** — apply `scoring.md` to MCP/query results in-context
- Read-only: never pause ads, change budgets, or run non-`SELECT` SQL

## Stages (keep it linear)

```
0  Advertiser confirm
1  Windows (yesterday TikTok; BQ recent 3 settled + 14d baseline) — see scoring.md
2  TikTok reports: yesterday, prior 7d, recent 3d, baseline 14d (ad group grain, page_size 1000)
3  Funnel classify via campaign objective_type (+ optimization_goal for WEB_CONVERSIONS)
   Drop LEAD_GENERATION. Bulk campaign_get + adgroup_get once each.
4  BigQuery Mid/Low: daily PDP/ATC for 3 settled days + 14d baseline (SQL in data-model.md)
5  Score with scoring.md → 🔴 list (decay OR below-peers OR delivery-halt / CTR-collapse)
5B Optional: delivery fill vs daily budget → FLAG rows only (not part of top 10 Why)
6  Sort 🔴 by yesterday spend → take top 10
7  Slack (Stage 7B) first, then short LATEST.md archive
8  Archive old LATEST.md → write new → commit/push (prefer main; say so in Slack if push fails)
```

Target runtime: **under 15 minutes**. If stuck, ship the best top-N already scored — do not debug scripts.

## Funnel → KPI (summary)

| Funnel | Primary KPI |
|---|---|
| Upper | 6-Second VTR |
| Mid | PDP Rate |
| Low | ATC Rate |

Exact classification table → `data-model.md`. Thresholds → `scoring.md`.

## Slack (Stage 7B)

Post to `#tik-tok-daily-checkup` when running as the morning automation.

```
☀️ *Morning checkup* · {date}

*{N} flagged* · top 10 below (${spend_on_top10} yday) · account spend {y} vs 7d {avg} ({▲/▼X%})

{optional: "3 of top 10 are on {campaign} — likely shared cause."}

1. *{ad_group}* — {campaign} · {funnel} · ${spend}
   {one short Why — decay or below-peers / CTR / delivery-halt}
…
10. …

{only if Delivery FLAGs:}
*Delivery FLAG* · spend vs daily budget
• *{ad_group}* — {campaign} · ${yday} of ${budget} ({fill}%)

Full memo: LATEST.md
```

- Max **10** items; fewer is fine — do not pad
- Why must name the **primary KPI problem** (ATC / PDP / 6s VTR / CTR / delivery-halt)

## LATEST.md (short archive)

Headline, pulse, top 10 (table OK here), join-quality one-liner, Delivery FLAG counts if any.  
No Watch. No Do-next. No ad-level block.

## Pre-publish check

1. ≤10 Slack items  
2. No Watch / Do-next / ad-level / VTC-led Why / spend-drop Why / pipe tables  
3. Every listed group has a real decay **or** below-peers (or CTR / delivery-halt) reason  
4. Message is scannable (~45 lines or fewer)
