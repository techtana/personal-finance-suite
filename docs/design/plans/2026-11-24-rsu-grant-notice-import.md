# Read RSU grant notices into a Plan RSU grant

**Status:** done, PR #8 (merged 2026-11-24). Tested on a made-up sample notice, not a real one.

## Goal

Drop an RSU grant notice on Import and get one RSU grant in Plan, with the vest schedule taken from the notice.

## Approach

- `importer/equity.py` reads the notice with rules first; the model fills gaps. A model value is kept only if it appears in the document.
- The review card checks that the vest amounts add up to the granted units.
- You type the ticker. Grant notices don't print it.
- The result is one RSU rule with `schedule_source = "document"`. A grant number seen before is flagged as a duplicate. Undo removes the grant.
- A fix (commit `7df5044`) saves the ticker and keeps the file-reading steps out of **Settings → Activity**.

## Left out

Other grant-notice layouts, vest summaries, release confirmations and ESPP documents.
