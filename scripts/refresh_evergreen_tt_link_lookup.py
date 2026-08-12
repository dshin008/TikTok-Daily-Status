#!/usr/bin/env python3
"""
Refresh Evergreen TT Link lookup on the TikTok Performance Tracker.

Source of truth for the video URL:
  TikTok Ads API tiktok_item_id (per ad) → masterlist /video/{id} URL
  (NOT visit creative_id — that collapses many Spark ads onto one wrong video.)

Typical automated run (agent or human):
  1) Pull ads from TikTok Ads (ad_get) for the three Evergreen campaigns
     and save as JSON list under Working_Queries/_tt_link_refresh/ads_*.json
     (each file = raw API response OR a list of {ad_id, tiktok_item_id, ...}).
  2) python3 scripts/refresh_evergreen_tt_link_lookup.py

Requires: gcloud auth (Sheets), bq CLI (BigQuery), network.
"""

from __future__ import annotations

import csv
import json
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "Working_Queries"
STAGING = WORK / "_tt_link_refresh"
ADS_DIR = STAGING / "ads_json"

SHEET_ID = "1xou5AnzYbB_BozV46KP0FJjlVF0XozI4AhWKtFEjEeI"
LOOKUP_TAB = "Ad TikTok Link Lookup"
ADVERTISER_ID = "7125498373565726721"

# Default Evergreen campaigns (skill/agent should also pull BTS + View Content —
# full ID list is exported at runtime from BigQuery via CAMPAIGN_SQL).
CAMPAIGN_IDS = [
    "1845522176114754",  # Evergreen VSA Broad Web
    "1871338571302274",  # Evergreen VSA Broad Web LF
    "1871339683323985",  # Evergreen VSA Broad Web FF
]

# Ads included in the lookup (spend + TikTok item map).
ADS_SQL = f"""
SELECT
  CAST(adid AS STRING) AS ad_id,
  ANY_VALUE(adName) AS ad_name,
  ANY_VALUE(adgroupName) AS adgroup_name,
  ANY_VALUE(CAST(adgroupID AS STRING)) AS adgroup_id,
  ANY_VALUE(CAST(campaignID AS STRING)) AS campaign_id,
  ANY_VALUE(campaignName) AS campaign_name,
  ROUND(SUM(spend), 2) AS spend_90d
FROM `wf-gcp-us-ae-adtech-prod.marketing_ad_costs.tbl_campaign_costs_tiktok_metrics_report`
WHERE accountID = '{ADVERTISER_ID}'
  AND reportDate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND (
    campaignName LIKE 'Evergreen VSA Broad Web%'
    OR campaignName LIKE '%BTS%'
    OR REGEXP_CONTAINS(LOWER(campaignName), r'view content|\\bvca\\b|_vc|_vca')
  )
GROUP BY 1
ORDER BY spend_90d DESC
"""

CAMPAIGN_SQL = f"""
SELECT
  CAST(campaignID AS STRING) AS campaign_id,
  ANY_VALUE(campaignName) AS campaign_name,
  COUNT(DISTINCT adid) AS ads,
  ROUND(SUM(spend), 2) AS spend_90d
FROM `wf-gcp-us-ae-adtech-prod.marketing_ad_costs.tbl_campaign_costs_tiktok_metrics_report`
WHERE accountID = '{ADVERTISER_ID}'
  AND reportDate >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
  AND (
    campaignName LIKE 'Evergreen VSA Broad Web%'
    OR campaignName LIKE '%BTS%'
    OR REGEXP_CONTAINS(LOWER(campaignName), r'view content|\\bvca\\b|_vc|_vca')
  )
GROUP BY 1
ORDER BY spend_90d DESC
"""

HEADER = [
    "ad_id",
    "creative_id",
    "ad_name",
    "adgroup_name",
    "adgroup_id",
    "campaign_id",
    "campaign_name",
    "spend_90d",
    "creator",
    "tiktok_link",
    "tiktok_item_id",
    "refreshed_date",
]


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def bq_csv(sql: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [
            "bq",
            "query",
            "--use_legacy_sql=false",
            "--project_id=wf-gcp-us-ae-mktg-rpt",
            "--format=csv",
            "--max_rows=100000",
            sql,
        ]
    )
    out_path.write_text(proc.stdout)
    if proc.stderr.strip():
        # bq prints job wait lines to stderr
        pass


def export_evergreen_ads() -> Path:
    out = STAGING / "scope_ads_90d.csv"
    print("Exporting Evergreen + BTS + View Content ads (90d) from BigQuery…")
    bq_csv(ADS_SQL, out)
    n = max(0, len(out.read_text().splitlines()) - 1)
    print(f"  → {n} ads → {out}")
    return out


def export_campaign_ids() -> list[str]:
    out = STAGING / "scope_campaigns_90d.csv"
    print("Exporting campaign IDs for TikTok ad_get…")
    bq_csv(CAMPAIGN_SQL, out)
    ids = []
    with out.open() as f:
        for row in csv.DictReader(f):
            cid = (row.get("campaign_id") or "").strip()
            if cid:
                ids.append(cid)
    print(f"  → {len(ids)} campaigns → {out}")
    return ids


def export_masterlist_links() -> Path:
    out = STAGING / "masterlist_video_links.csv"
    sql = """
SELECT
  REGEXP_EXTRACT(Campaign_or_Link, r'/video/([0-9]+)') AS tiktok_item_id,
  ANY_VALUE(Filename_or_Creator) AS creator,
  ANY_VALUE(Campaign_or_Link) AS tiktok_link
FROM `wf-gcp-us-ae-mktg-prod.analysis_paidsearch.creative_assets_id_masterlist`
WHERE Campaign_or_Link LIKE '%tiktok.com%/video/%'
GROUP BY 1
"""
    print("Exporting masterlist video links from BigQuery…")
    bq_csv(sql, out)
    n = max(0, len(out.read_text().splitlines()) - 1)
    print(f"  → {n} videos → {out}")
    return out


def _iter_ad_objects(payload) -> list[dict]:
    """Normalize raw ad_get responses or plain lists into ad dicts."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        data = payload.get("data") or payload
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            return [x for x in data["list"] if isinstance(x, dict)]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    return []


def load_item_ids_from_ads_json() -> dict[str, dict]:
    ADS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(ADS_DIR.glob("*.json"))
    if not files:
        raise SystemExit(
            f"No TikTok ad JSON found in {ADS_DIR}\n"
            "Save ad_get responses there first (one JSON file per page/batch).\n"
            f"Campaigns: {', '.join(CAMPAIGN_IDS)}\n"
            f"Advertiser: {ADVERTISER_ID}\n"
            "Fields needed: ad_id, tiktok_item_id (identity_id optional)."
        )
    by_ad: dict[str, dict] = {}
    for path in files:
        payload = json.loads(path.read_text())
        for ad in _iter_ad_objects(payload):
            ad_id = str(ad.get("ad_id") or "").strip()
            if not ad_id:
                continue
            by_ad[ad_id] = {
                "tiktok_item_id": str(ad.get("tiktok_item_id") or "").strip(),
                "identity_id": str(ad.get("identity_id") or "").strip(),
                "ad_name_api": ad.get("ad_name") or "",
                "operation_status": ad.get("operation_status") or "",
            }
    print(f"Loaded TikTok item map for {len(by_ad)} ads from {len(files)} JSON file(s)")
    with_item = sum(1 for v in by_ad.values() if v["tiktok_item_id"])
    print(f"  → {with_item} have tiktok_item_id")
    return by_ad


def build_lookup(ads_csv: Path, master_csv: Path, item_map: dict[str, dict]) -> Path:
    master: dict[str, dict] = {}
    with master_csv.open() as f:
        for row in csv.DictReader(f):
            vid = (row.get("tiktok_item_id") or "").strip()
            if vid:
                master[vid] = row

    evergreen = list(csv.DictReader(ads_csv.open()))
    out_rows = []
    today = str(date.today())
    for e in evergreen:
        api = item_map.get(e["ad_id"], {})
        item = api.get("tiktok_item_id", "")
        m = master.get(item, {})
        if m.get("tiktok_link"):
            link = m["tiktok_link"]
        elif item:
            link = f"https://www.tiktok.com/video/{item}"
        else:
            link = ""
        out_rows.append(
            {
                "ad_id": e["ad_id"],
                "creative_id": "",  # intentionally blank — visit creative_id is unreliable
                "ad_name": e.get("ad_name", ""),
                "adgroup_name": e.get("adgroup_name", ""),
                "adgroup_id": e.get("adgroup_id", ""),
                "campaign_id": e.get("campaign_id", ""),
                "campaign_name": e.get("campaign_name", ""),
                "spend_90d": e.get("spend_90d", ""),
                "creator": m.get("creator", ""),
                "tiktok_link": link,
                "tiktok_item_id": item,
                "refreshed_date": today,
            }
        )

    out = STAGING / f"{date.today().strftime('%Y%m%d')}_evergreen_ad_tiktok_link_lookup_itemid.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(out_rows)

    linked = sum(1 for r in out_rows if r["tiktok_link"])
    unique = len({r["tiktok_link"] for r in out_rows if r["tiktok_link"]})
    print(f"Built lookup: {len(out_rows)} rows, {linked} with links, {unique} unique videos")
    print(f"  → {out}")
    return out


def sheets_token() -> str:
    return run(["gcloud", "auth", "print-access-token"]).stdout.strip()


def sheets_http(method: str, url: str, token: str, body=None):
    ctx = ssl._create_unverified_context()
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()[:2000]
        raise RuntimeError(f"Sheets API {e.code}: {err}") from e


def write_lookup_sheet(lookup_csv: Path) -> None:
    rows = list(csv.DictReader(lookup_csv.open()))
    values = [HEADER] + [[r.get(c, "") for c in HEADER] for r in rows]
    token = sheets_token()
    print(f"Writing {len(rows)} rows to sheet tab '{LOOKUP_TAB}'…")

    # Ensure grid is large enough (Connected Sheets / default grids are often 1000 rows)
    meta_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"?fields=sheets.properties"
    )
    meta = sheets_http("GET", meta_url, token)
    sheet_id = None
    for s in meta.get("sheets") or []:
        props = s.get("properties") or {}
        if props.get("title") == LOOKUP_TAB:
            sheet_id = props.get("sheetId")
            break
    if sheet_id is None:
        raise RuntimeError(f"Tab '{LOOKUP_TAB}' not found")
    need_rows = max(2000, len(values) + 50)
    sheets_http(
        "POST",
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate",
        token,
        {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {
                                "rowCount": need_rows,
                                "columnCount": max(26, len(HEADER) + 2),
                            },
                        },
                        "fields": "gridProperties.rowCount,gridProperties.columnCount",
                    }
                }
            ]
        },
    )

    clear_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
        + urllib.parse.quote(f"'{LOOKUP_TAB}'!A:L", safe="")
        + ":clear"
    )
    sheets_http("POST", clear_url, token, {})

    chunk = 500
    for i in range(0, len(values), chunk):
        part = values[i : i + chunk]
        start_row = i + 1
        put_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
            + urllib.parse.quote(f"'{LOOKUP_TAB}'!A{start_row}", safe="")
            + "?valueInputOption=RAW"
        )
        sheets_http(
            "PUT",
            put_url,
            token,
            {"values": part, "majorDimension": "ROWS"},
        )
        print(f"  wrote rows starting at {start_row} ({len(part)} lines)")

    # Ensure CLS column F looks up this tab (A=ad_id, J=tiktok_link)
    cls_url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
        + urllib.parse.quote(
            "'Evergreen VSA Web Broad - Ads (CLS Break Down)'!C5:C400",
            safe="",
        )
    )
    cls = sheets_http("GET", cls_url, token)
    n = len(cls.get("values") or [])
    if n:
        formulas = [
            [
                f"=IFERROR(XLOOKUP(C{r}&\"\",'{LOOKUP_TAB}'!$A:$A,'{LOOKUP_TAB}'!$J:$J,\"\"),\"\")"
            ]
            for r in range(5, 5 + n)
        ]
        f_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
            + urllib.parse.quote(
                "'Evergreen VSA Web Broad - Ads (CLS Break Down)'!F5",
                safe="",
            )
            + "?valueInputOption=USER_ENTERED"
        )
        sheets_http(
            "PUT",
            f_url,
            token,
            {"values": formulas, "majorDimension": "ROWS"},
        )
        print(f"  refreshed {n} CLS column F XLOOKUP formulas")


def wire_view_content_and_bts_tt_links(token: str | None = None) -> None:
    """Add TT Link XLOOKUPs on View Content - Ads (col Q) and BTS ad-ID sections (col C)."""
    token = token or sheets_token()
    lookup = LOOKUP_TAB

    # --- View Content - Ads: header row 8, Ad ID in col B, TT Link in col Q ---
    vc_title = "View Content - Ads"
    vc = sheets_http(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
        + urllib.parse.quote(f"'{vc_title}'!B8:B80", safe=""),
        token,
    ).get("values") or []
    # Row 8 is header; write TT Link header in Q8
    sheets_http(
        "PUT",
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
        + urllib.parse.quote(f"'{vc_title}'!Q8", safe="")
        + "?valueInputOption=RAW",
        token,
        {"values": [["TT Link"]], "majorDimension": "ROWS"},
    )
    q_formulas = []
    for i, row in enumerate(vc):
        sheet_row = 8 + i
        ad = row[0].strip() if row else ""
        if i == 0:
            continue  # header already written
        if ad.isdigit() and len(ad) >= 10:
            q_formulas.append(
                [
                    f"=IFERROR(XLOOKUP(B{sheet_row}&\"\",'{lookup}'!$A:$A,'{lookup}'!$J:$J,\"\"),\"\")"
                ]
            )
        else:
            q_formulas.append([""])
    if q_formulas:
        sheets_http(
            "PUT",
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
            + urllib.parse.quote(f"'{vc_title}'!Q9", safe="")
            + "?valueInputOption=USER_ENTERED",
            token,
            {"values": q_formulas, "majorDimension": "ROWS"},
        )
        print(f"  View Content - Ads: wrote TT Link formulas for {sum(1 for r in q_formulas if r[0])} ad rows")

    # --- BTS `26 - Full Funnel: scan col D for Ad ID headers / numeric ad ids ---
    bts_title = "BTS `26 - Full Funnel"
    bts = sheets_http(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/"
        + urllib.parse.quote(f"'{bts_title}'!D1:D250", safe=""),
        token,
    ).get("values") or []
    updates = []  # list of (row, value) for col C
    for i, row in enumerate(bts):
        sheet_row = i + 1
        val = row[0].strip() if row else ""
        if val == "Ad ID":
            updates.append((sheet_row, "TT Link"))
        elif val.isdigit() and len(val) >= 10:
            updates.append(
                (
                    sheet_row,
                    f"=IFERROR(XLOOKUP(D{sheet_row}&\"\",'{lookup}'!$A:$A,'{lookup}'!$J:$J,\"\"),\"\")",
                )
            )
    if updates:
        # Write in contiguous chunks where possible
        data = []
        # Use batch update via individual ranges for simplicity
        body_data = []
        for sheet_row, value in updates:
            body_data.append(
                {
                    "range": f"'{bts_title}'!C{sheet_row}",
                    "majorDimension": "ROWS",
                    "values": [[value]],
                }
            )
        sheets_http(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values:batchUpdate",
            token,
            {
                "valueInputOption": "USER_ENTERED",
                "data": body_data,
            },
        )
        print(f"  BTS Full Funnel: wrote {len(updates)} TT Link headers/formulas in col C")


def main() -> int:
    STAGING.mkdir(parents=True, exist_ok=True)
    print("=== TT Link refresh (tiktok_item_id) — Evergreen + BTS + View Content ===")
    campaign_ids = export_campaign_ids() or CAMPAIGN_IDS
    print(f"Pull these campaign_ids via TikTok ad_get before running (or ensure ads_json is fresh):")
    print(",".join(campaign_ids))
    ads_csv = export_evergreen_ads()
    master_csv = export_masterlist_links()
    item_map = load_item_ids_from_ads_json()
    lookup_csv = build_lookup(ads_csv, master_csv, item_map)
    write_lookup_sheet(lookup_csv)
    print("Wiring TT Link on View Content - Ads and BTS tabs…")
    wire_view_content_and_bts_tt_links()
    print("DONE — Ad TikTok Link Lookup updated from tiktok_item_id.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(e.stdout or "", file=sys.stderr)
        print(e.stderr or "", file=sys.stderr)
        raise SystemExit(e.returncode)
