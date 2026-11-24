# Where the AI models run

> **Superseded on 2026-11-23** by [cloud-server-and-ai-endpoints.md](cloud-server-and-ai-endpoints.md): the app now runs on a private
> cloud server, and AI work goes to the home computer (through `home_runner.py`), the app's own machine, your own cloud
> endpoint or, only for named features, a paid API. Kept as the record of the first placement review; its prices and
> volume estimates still apply.

Checked 2026-11-22 with the `ai-placement` skill. `main` uses no AI. The AI work is on branch
`claude/local-ai-transaction-processor-e0cfb1` (commit 8b196b6, "import statements, receipts and
pay stubs with a local AI"), merged into `claude/ui-refactor-user-management-d37f15`. Prices
checked 2026-11-22 (sources at the end).

The app is a Flask server on `localhost` with a SQLite file; it already needs the owner's computer
to be on. The importer calls one local model through `importer/llm.py`: Ollama `qwen3.5:9b` by
default (the personal agent stack's model, on the desktop's RTX 3060, 12 GB), or any
OpenAI-compatible server. It refuses a non-local address unless `LLM_ALLOW_REMOTE=1`, matching the
PRD's goal G5 ("no data ever leaves the user's device").

| Need | Realtime or batch | Runs today | Recommendation | Main reason |
|---|---|---|---|---|
| Read photos and scanned PDFs (`ai_tools.transcribe`, vision) | Batch (import queue) | qwen3.5:9b vision, desktop GPU | **On-device, desktop GPU (keep).** Add Tesseract as a first pass for clean scans | Financial documents; the stated rule is local only. Volume is a few pages a month, so speed doesn't matter |
| Classify the document, map statement columns, extract statement lines, read receipts and pay stubs | Batch | qwen3.5:9b, desktop GPU | **On-device, desktop GPU (keep)** | Every answer is grounded (values must appear in the document), which makes a 9B model good enough; zero marginal cost |
| Categorize merchants (`categorize`, once per merchant, cached) | Batch | qwen3.5:9b after rules and learned mappings | **On-device (keep)** | Rules and the cache handle most rows; the model sees few calls |
| Optional fallback when the desktop is off or a document defeats the local model | Batch | none (`LLM_PROVIDER=off` → rules only) | **Paid API, opt-in per batch**: Claude Haiku 5.5 or Gemini 3.5 Flash-Lite (paid tier) through the existing `openai` provider path | Under a cent per document; only worth adding if the owner accepts the privacy trade for that batch |

## Notes per need

- **Volume.** A household imports perhaps 5-10 statements and 10-30 receipts or stubs a month,
  roughly 50 pages, 1-2k tokens in and 0.5k out each: about 0.1M tokens a month.
- **Local cost.** Electricity for a few minutes of GPU time a month. The model is already loaded
  for the agent stack (`LLM_NUM_CTX` matches it, so Ollama doesn't reload).
- **API cost for comparison.** Claude Haiku 5.5: $0.10 in / $0.50 out per M tokens; Gemini 3.5
  Flash-Lite: $0.30 / $2.50. Either is a few cents a month at this volume. Cost is not the reason
  to stay local; privacy and the PRD's G5 goal are. Gemini's *free* tier uses data to improve
  Google's products, so only its paid tier is acceptable for this data.
- **Private cloud** (Cloud Run L4 at about $1.05/h with a minute minimum, or a VM) brings no gain
  here: the app itself runs on the desktop, so the model is never needed when the desktop is off.
  It becomes relevant only if the app moves off the desktop (see question 2).
- **Tesseract first pass.** Clean bank PDFs mostly carry a text layer already (`pypdf`). For
  photographed receipts, Tesseract on the CPU is fast and deterministic; the vision model then only
  reads what Tesseract can't. Saves GPU time and makes results repeatable. Optional.
- **Device check.** qwen3.5:9b with vision fits a 12 GB RTX 3060 at the stack's settings. A laptop
  without a GPU could run it on the CPU, slowly (minutes per page): acceptable for a batch import,
  so a GPU-less laptop is a fallback, not a blocker.

## Open questions

1. Should the importer get a per-batch "send this batch to a paid API" switch (default off), for
   documents the local model fails on? Today `LLM_ALLOW_REMOTE` is global.
2. Will the app ever run somewhere other than the desktop (phone access, another computer)? If so,
   the model needs a reachable home (the desktop over Tailscale, or a private Cloud Run GPU) and
   this table changes.
3. Is the import accuracy good enough? A small labelled set of the owner's real documents, scored
   per field, would show whether qwen3.5:9b is falling short anywhere before considering a larger
   model (qwen3.6:35b-a3b is already in the stack).

## Sources (checked 2026-11-22)

- Claude API pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Gemini API pricing: https://aistudio.google.com/docs/pricing
- Cloud Run pricing: https://cloud.google.com/run/pricing
- Local hardware: `nvidia-smi` on the owner's desktop (RTX 3060, 12 GB).
