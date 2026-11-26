# Then vs. Now

**Status:** done 2026-11-22 (commit `0aa992e`), merged with PR #3.

## Goal

For each decision (an RSU grant, an ESPP purchase, an asset bought), show what it was worth when you decided, when you received it, and today. The owner was first offered a wireframe (`docs/wireframes-v3/08-then-vs-now.html`) and asked for the real page.

## Approach

- `engine/lookback.py` values each item on the three dates.
- Share prices are typed in by hand (`PricePoint`); an asset has a `decided_date`.
- PR #3 moved price entry onto the Balances page.

## Left out

An automatic share-price feed (PRD §8).
