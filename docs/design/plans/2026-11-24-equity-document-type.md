# Recognise stock-plan documents

**Status:** done, PR #6 (merged 2026-11-24). Reading grant notices followed in PR #8.

## Goal

Stop RSU and stock-plan summaries from failing on Import as if they were receipts.

## Approach

- A new document type, `equity`, chosen both by rules and by the model.
- Lines such as "total" and "tax" on these documents no longer send them down the receipt path.
- Pay stubs and brokerage statements are read as before.
- When such a document can't be read, the message points to the Plan page, where a grant can be added by hand.

## Left out

Reading the documents into Plan entries. Taken up by [the RSU grant notice plan](2026-11-24-rsu-grant-notice-import.md).
