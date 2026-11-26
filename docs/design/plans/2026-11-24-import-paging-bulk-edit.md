# Paged import review and bulk change

**Status:** done, PR #9 (merged 2026-11-24).

## Goal

Keep the Import review page light on large files, and let you change many rows at once. A file with more than 3,000 rows made the page load every row at once.

## Approach

- The review loads one page of rows at a time (`GET /api/imports/<id>/rows`, at most 200 per request), with **Previous** and **Next**.
- `GET /api/imports/<id>?rows=0` returns an import without its rows; the counts per section are computed on the server.
- **Bulk change** (`POST /api/imports/<id>/rows/bulk`) acts on chosen rows, or on every row that matches the current filter or search, not just the visible page. It can set the action, category, account or date, or flip the sign. Rows the change doesn't fit are skipped and counted.
- On a 3,000-row file the first response went from about 1.3 MB to about 25 KB.

## Left out

The server still loads all rows of an import to count them and match duplicates.
