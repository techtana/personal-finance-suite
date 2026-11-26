# Import statements, receipts and pay stubs with a local AI

**Status:** done 2026-11-22 (commit `8b196b6`), merged with PR #3. Extended by PR #6, PR #8 and PR #9.

## Goal

Turn bank and card exports, PDF statements, receipts and pay stubs into entries. Nothing is saved before you review it, and every import can be undone.

## Approach

1. **Rules first.** Code reads OFX, standard CSV headers, dates, amounts, signs, known merchants and transfers.
2. **Memory next.** A column layout or a merchant category you chose before is reused.
3. **The AI fills gaps** through narrow tools: read a photo, tell the document type, map columns, find transactions, read a receipt, read a pay stub, categorize a merchant. Each answer must match a JSON schema.
4. **Every answer is checked.** Amounts must appear in the document, dates must be printed on it, receipts must add up, pay stubs must reconcile. A rejected answer goes back once with the reason; after that it is dropped and flagged.
5. **You review** every row, then click **Import**.

The model client uses only the Python standard library. It reuses the Ollama server that the owner's agent stack already runs, so the one 12 GB GPU holds one model, not two. A non-local address is refused unless `LLM_ALLOW_REMOTE=1`, because the documents are financial.

## Left out

Not stated in the commit. Photos and scanned PDFs need the AI; everything else works with rules only.

Background: [file import and matching](../../knowledge/file-import-and-matching.md), [small local models](../../knowledge/small-local-models.md).
