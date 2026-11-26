# Google Cloud backups, restore points and Clear All Data

**Status:** done, PR #2 (merged 2026-11-24). Pruning changed in PR #4.

## Goal

No destructive action can lose data.

## Approach

- The whole SQLite file is copied to a Google Cloud Storage bucket as `finance_<UTC time>_<reason>.db`. Reasons: `scheduled`, `manual`, `before-clear`, `before-restore`, `before-import`.
- Credentials come from Application Default Credentials (`gcloud auth application-default login`). The app never stores them.
- A daily or weekly schedule, checked every 15 minutes in a background thread. The app removes only old scheduled backups.
- **Clear All Data** backs up first, and deletes nothing if the backup fails. You type a confirmation.
- **Restore** backs up the current data first.
- "Load Sample Data" was removed; the fixture moved to `tests/sample_data.py`.

## Outcome (2026-11-23)

PR #4 made the server add backups without deleting them (`BACKUP_PRUNE=bucket`). A lifecycle rule on the bucket now deletes old scheduled backups, so a compromised server cannot erase the history.
