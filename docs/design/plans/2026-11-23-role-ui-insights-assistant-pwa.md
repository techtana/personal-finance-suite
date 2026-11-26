# Pages by role, Insights, AI assistant, phone layout and installable app

**Status:** done, PR #3 (merged 2026-11-24).

## Goal

Make it obvious what you can edit and what is computed. Add guidance, an optional assistant, and a layout that works on a phone.

## Approach

- Navigation grouped by role, not by data type. **Your picture** (Overview, Forecast, Then vs. Now, Taxes) is view only. **Your inputs** (Plan, Balances, Import) is the only place to edit. **Guidance** (Insights) explains what the app notices. Old addresses redirect.
- The same search, filter and sort on every list, kept in the page address.
- The assistant answers a question, turns words into a filter, explains an insight, or drafts a Plan entry. The model only picks a read-only lookup and words the reply. A reply with a number the lookup did not produce is thrown away. It never saves anything.
- On a phone: a bottom tab bar, bottom-sheet forms, 44 px touch targets.
- Installable web app: manifest, service worker and offline page. The service worker never caches `/api/`, so no financial data is stored on the phone.
- Alpine.js and Chart.js are pinned in `static/vendor/`; Tailwind is compiled ahead of time. No CDN at run time.
- Phone access over HTTPS through Tailscale Serve, not an open network address, because the app has no sign-in.

## Left out

The install prompt was not tried on a real phone.
