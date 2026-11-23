"""Drop-a-file import: bank statements, receipts and pay stubs into the ledger.

Layers, from most to least trusted:
  parsing / extract    deterministic readers and value parsers (no AI)
  taxonomy, statements rules: header names, keywords, sign and date-format checks
  documents            receipts and pay stubs, read by rules and by the AI, cross-checked
  ai_tools             narrow AI jobs with JSON-schema answers and validators
  matching             duplicates, transfers and accounts, checked against the database
  pipeline             stages everything for review; commit and undo
"""
