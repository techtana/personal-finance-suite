# v1: a local Flask app with one SQLite file

**Status:** done 2026-05-11 (commit `bb0a1e9`, no PR). Several non-goals were reversed later; see the Outcome note.

The full plan lives in [docs/PRD.md](../../PRD.md) (product) and [docs/SRD.md](../../SRD.md) (software), both v0.2 of 2026-05-09. This page summarises them.

## Goal

Replace a slow Excel planner with a self-hosted app. You enter what you know (salary, RSU vests, ESPP purchases, bills, loans), the app projects your net worth, and from time to time you check it against real balances (PRD §1–2).

## Approach

- One SQLite file, `instance/finance.db`; Flask, Jinja2 and Alpine.js; runs on `localhost` (SRD §1–2).
- Objects: one-off, recurring and blanket transactions, RSU grants, ESPP plans, accounts, loans (PRD §5.1).
- A projection engine with what-if: leave chosen items out by id (SRD §5).
- Divergence: compare projected and recorded balances, and flag a gap above a threshold (PRD G3).
- Export and import everything as JSON; back up by copying the file (PRD F7).
- Money in minor units (cents), ISO dates, nanoid ids ([BUILD_SUMMARY.md](../../../BUILD_SUMMARY.md)).

## Phases

Phases 1–5 in [BUILD_SUMMARY.md](../../../BUILD_SUMMARY.md), all ticked.

## Left out (PRD §3 non-goals)

Bank pulls, receipt scanning, a tax engine, several users, a native phone app, cloud sync, sign-in.

## Outcome (2026-11-24)

- Receipts and statements: now imported ([import plan](2026-11-22-import-statements-local-ai.md)).
- Tax engine: added, for planning estimates ([tax plan](2026-11-22-tax-treatments-taxes-page.md)).
- Cloud sync and remote access: replaced by one private server ([cloud plan](2026-11-23-private-cloud-server-ai-endpoints.md)).
- Sign-in: still none in the app; Tailscale decides who gets in.
- Alembic migrations (SRD §3.3): not used. The app creates tables and adds missing columns at startup (PR #1).
- CDN scripts (SRD §2): replaced by pinned local copies (PR #3).
- Still true: no bank pulls and no native phone app (the installable web app covers phones).
