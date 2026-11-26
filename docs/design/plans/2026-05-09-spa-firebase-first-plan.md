# First plan: a single-page app with cloud storage

**Status:** dropped 2026-05-11. Replaced by [the Flask + SQLite plan](2026-05-09-prd-srd-v1-flask-sqlite.md). No PR; commits `773d697`, `0ba7ebb`, `56700ed`, `a4d1ca3`.

## Goal

Replace an Excel planner with a browser app.

## Approach

- A React single-page app with client-side state.
- Data saved to the owner's Google Drive, signed in with Google OAuth (PKCE flow), commit `56700ed`.
- Then Firebase Auth and Firestore instead of PKCE and Drive, commit `a4d1ca3`.

## Outcome (2026-11-24)

Commit `bb0a1e9` (2026-05-11) rewrote the app in Flask with a local SQLite file and deleted the Firebase files. Nothing from this plan remains in the code. The header of `docs/PRD.md` v0.2 records the switch.
