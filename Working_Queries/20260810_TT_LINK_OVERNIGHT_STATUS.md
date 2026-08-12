# Overnight STATUS — TT Link (column F) fix
**Date:** 2026-08-10 (evening)  
**Sheet:** [TikTok Performance Tracker](https://docs.google.com/spreadsheets/d/1xou5AnzYbB_BozV46KP0FJjlVF0XozI4AhWKtFEjEeI) → tab **Evergreen VSA Web Broad - Ads (CLS Break Down)**

## Done (safe — metrics untouched)

1. **Diagnosed the cooked TT Link system**  
   Old column F used:
   ```
   FILTER(IMPORTRANGE(Spark Hub, "Spark!B:B"), Spark!L:L = D)
   ```
   Column D was not a reliable creative key, so many rows showed the same wrong video (or `#REF!`).

2. **Built a correct join**  
   `ad_id` → `creative_id` (from landing-page / visits) → TikTok URL (BigQuery masterlist)

3. **Added tab `Ad TikTok Link Lookup`** to the Performance Tracker  
   - ~712 Evergreen ads (90-day window)  
   - ~506 rows with TikTok links / ~216 unique videos  
   - Columns: ad_id, creative_id, ad_name, adgroup_name, …, **tiktok_link** (col J)

4. **Replaced ONLY column F** on that CLS Ads tab (190 cells)  
   New formula pattern:
   ```
   =IFERROR(XLOOKUP(C5&"",'Ad TikTok Link Lookup'!$A:$A,'Ad TikTok Link Lookup'!$J:$J,""),"")
   ```
   - Uses TikTok **ad_id** already in column C  
   - Did **not** edit Cost / ATC / ACNR / other metric columns  
   - Did **not** delete sheets or change other tabs’ logic

5. **Backup helper workbook** (also loaded):  
   https://docs.google.com/spreadsheets/d/1GeRcrNW-OB8QD0yHs0k2-kqgrzKm09N1ytnFFD5_p0s/edit

## Spot-check (after fix)

| Check | Result |
|--------|--------|
| Same `@anaphterly` video everywhere? | **No** (0 hits) |
| Sample Bed ads | Distinct creators (allison.bounds, eliziaamore, melinatesi, parkerstyle_, etc.) |
| Match vs BigQuery lookup | 15/15 on Bed sample |
| Ad rows with a link | **117** |
| Ad rows still blank | **~44** |
| Unique links showing | **81** |

Blank rows = ads with **no `creative_id` in visit URLs** (and not recoverable from masterlist overnight). Formula is fine; data is missing upstream.

## SQL / files in this project

- `Working_Queries/20260810_1646_evergreen_ad_tiktok_link_lookup.sql` (14d)  
- `Working_Queries/20260810_1708_evergreen_ad_tiktok_link_lookup_90d.sql` (90d — what’s in the sheet now)  
- Matching CSVs next to those SQL files  

## If you want to refresh later

```bash
bq query --use_legacy_sql=false --format=csv --max_rows=20000 \
  < Working_Queries/20260810_1708_evergreen_ad_tiktok_link_lookup_90d.sql \
  > Working_Queries/refresh.csv
```
Then paste into **Ad TikTok Link Lookup** (replace values). Column F formulas can stay.

## Optional morning follow-ups (not done)

1. Set Performance Tracker AI label to **Any AI can Edit** if you want Cursor MCP edits next time (Haley owns the file; “Allow AI Editing” alone wasn’t enough for MCP).  
2. Enrich the ~44 blank ads (TikTok landing URL / Spark Hub by handle) so every row gets a link.  
3. Same XLOOKUP pattern could later be applied to **Spark - Web Broad** (it had the same broken IMPORTRANGE pattern) — not touched tonight.

## Bottom line

TT Link column F is no longer keyed to a broken Spark Hub filter. It looks up **by ad_id** into a real creative→URL table. Most live creatives show the **correct unique video**; remaining blanks need creative_id backfill, not another formula patch.
