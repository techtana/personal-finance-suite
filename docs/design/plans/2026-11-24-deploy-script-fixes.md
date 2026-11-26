# Deploy script fixes from the first real deploy

**Status:** done, PR #5 and PR #7 (both merged 2026-11-24). Used for the real redeploy on 2026-11-24.

## Goal

Make `deploy/deploy.sh` safe to run from the owner's PC, both the first time and again over an existing server.

## Approach

PR #5:

- Pick the project for this run only (`CLOUDSDK_CORE_PROJECT`), so the caller's default gcloud project is left alone. Before, `gcloud config set project` changed it silently.
- Turn off interactive prompts (`CLOUDSDK_CORE_DISABLE_PROMPTS=1`), so a hidden prompt can't stall the run.

PR #7:

- Update an existing server by stopping and starting the VM with new metadata, instead of `gcloud compute ssh`. SSH would have created an OS Login key, and it needs a network path the VM doesn't offer.
- Each run writes its own `deploy-id`; the startup script echoes it back when ready. The wait accepts only this run's id, so a "ready" left from the previous boot no longer ends the wait too early.
- The data disk is never touched. The app is offline for about two minutes.

## Left out

`deploy/ai-endpoint/deploy.sh` was not run.
