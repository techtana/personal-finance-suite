# Where the AI models run (first review)

**Status:** done 2026-11-22; superseded 2026-11-23 by the [private cloud server plan](2026-11-23-private-cloud-server-ai-endpoints.md). Kept in the repo by PR #11.

The review itself is [docs/design/ai-placement.md](../ai-placement.md).

## Goal

Decide where each AI need of the importer should run: on the owner's desktop, on a private cloud GPU, or through a paid API.

## Approach and findings

- At the time the app ran on the owner's desktop, so the desktop GPU (12 GB) and the agent stack's Ollama were the natural home for reading documents and categorizing merchants.
- A paid API was suggested as an optional, per-batch fallback. It was not built.
- A private cloud GPU was judged to add cost without benefit while the app lived on the desktop.

## Outcome (2026-11-23)

Once the app moved to a private cloud server, the desktop became one AI endpoint among several (through `home_runner.py`). The review's prices and volume estimates still apply.
