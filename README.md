# TikTok Daily Status — home base

This folder is where the **morning ad group checkup** lives — one saved report per day, so
you always have a home to come back to instead of scrolling through old chats.

## What's in here

- **`LATEST.md`** — always **today's** report, sitting right here at the top level. No date
  hunting — if you just ran the checkup, this file is it. Gets overwritten each morning.
- **`past-reports/`** — every previous day's report, archived here automatically the moment a
  newer one replaces it in `LATEST.md`. Named `YYYY-MM-DD.md`. This is your history — `LATEST.md`
  itself never accumulates, it's just today.
- **`TikTok_Daily_Status.xlsx`** — the older manual Excel log (predates the checkup skill).
  Untouched; kept separate on purpose so the two don't collide.

## How to run a checkup

Each morning, open a chat in Cursor (any chat — doesn't have to be this one) and type:

> **Morning ad group checkup**

Takes about 2–4 minutes (it checks day-by-day trends, not just yesterday, to avoid flagging
normal noise). When it's done you'll get the memo in chat, and `LATEST.md` will be updated —
yesterday's version automatically slides into `past-reports/` first, so nothing is lost.

## Catching up on history

To see how a specific ad group or campaign has trended, just open a handful of files in
`past-reports/` in date order (plus `LATEST.md` for today) — each one is short and skimmable.
If you want a rollup across many days (e.g. "how has campaign X looked over the last two
weeks"), ask the agent in chat to read the relevant files and summarize the trend — it can do
that directly, no need to read them all yourself.

## Related

- Skill definition: `~/.cursor/skills/morning-ad-group-checkup/SKILL.md`
- Data model / SQL reference: `~/.cursor/skills/morning-ad-group-checkup/references/data-model.md`
