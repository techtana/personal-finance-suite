# Small local language models, and how to trust them with money

## 1. What this is and why the project needs it

The app can read a photo of a receipt, sort a bank export into categories, and answer a question
such as "when does my net worth reach $500,000?". It does this with a language model, a program
that predicts text. A small one runs on the owner's own desktop graphics card, so financial
documents do not go to a company's servers. Small models are cheap and private, but they also
make mistakes, and sometimes make up numbers. So the project never lets the model decide what
gets saved. Code fixes the shape of the answer, checks every value against the document, and
asks a person to review the rest. This page explains the pieces well enough that you can read
`importer/llm.py`, `importer/ai_tools.py`, `engine/assistant.py`, `ai/endpoints.py` and their
tests without looking anything up.

## 2. The ideas, built up from zero

### What a language model is

Think of the phone keyboard that suggests the next word. A language model is the same idea,
much larger. It has read a huge amount of text and learned which words tend to follow which. You
give it some text (the prompt) and it adds one small piece (a token, roughly a word or part of a
word) at a time until it stops. It does not look facts up. It continues the text in the way that
looks most likely. When the prompt is a receipt and the instruction "copy the total", the most
likely continuation is usually the total. Usually.

Two words you will see often. **Parameters** are the learned numbers inside the model. The
project's default model, `qwen3.5:9b`, has about nine billion of them, which is what "9B" means.
**Tokens** are the units the model reads and writes; prices and limits are counted in them.

The analogy: a very well-read assistant who answers from memory and instinct, never from a
reference book. The analogy fails in one place. A person who is unsure usually says so. A model
often sounds equally confident when it is right and when it is wrong.

### Running one on your own machine

A model is a big file of those parameters, called the **weights**. To use it, a program must load
the weights into memory and run the arithmetic. A graphics card (GPU) does that arithmetic far
faster than the main processor, but only if the weights fit in the card's own memory (video
memory, or VRAM). The owner's desktop has an RTX 3060 with 12 GB (`docs/design/ai-placement.md`,
from `nvidia-smi`). That document records that `qwen3.5:9b`, with vision, fits at the settings
the owner's other tools use.

**Ollama** is the program that does the loading and serves the model over a local web address,
by default `http://127.0.0.1:11434` (`LLM_BASE_URL`). The app sends it a request and gets text
back. Loading a model takes time and memory, so Ollama keeps one loaded and reuses it. That
matters for the next idea.

The repo docs do not say which compressed weight format (quantization) the Ollama tag uses, so
this page does not cover it. See open questions.

### The context window, and why `num_ctx` must match

The **context window** is how much text the model can hold in view at once: your instructions,
the document and its own answer, all counted in tokens. The setting is `num_ctx`, and the
project uses 32768 (`LLM_NUM_CTX`). A bigger window needs more memory, because the model keeps
working notes for every token in view.

Here is the catch. Ollama loads a model with a particular set of options. If the next request
arrives with different options, Ollama unloads the model and loads it again. The owner's personal
agent stack also uses this Ollama server and loads the model with `num_ctx` 32768. If the finance
app asked for 8192, the two would keep evicting each other, and every switch would cost a full
reload on a 12 GB card. The comment in `config.py` says it directly: match the stack's context
size "or Ollama reloads it". The cloud image in `deploy/ai-endpoint/Dockerfile` sets
`OLLAMA_KEEP_ALIVE=-1` so the model stays loaded.

### Why small models make things up

A model produces text that fits the pattern, not text that has been checked. This is called
**hallucination**. For a chat about history it is an annoyance. For a receipt it is a wrong
amount in your budget. Small models do it more, and they do it in a specific way that matters
here: they swap two digits, read the subtotal as the total, copy the year-to-date column instead
of this period's, or choose a plausible category that does not fit. The model is not lying. It
is continuing the pattern. So the design assumes every answer may be wrong and builds checks
around it.

### Constrained decoding: forcing the shape

The first defence is cheap and strong. You give the model a **JSON schema**, a description of
the exact shape you will accept: these fields, this one must be a whole number, this one must be
one of these five words. While the model writes, the server blocks any token that would break
the schema. This is **constrained decoding**. Ollama calls the request field `format`
(`importer/llm.py` puts the schema there). OpenAI-compatible servers call it
`response_format` with type `json_schema`, which the `openai` provider path uses when the server
honours it. An answer therefore cannot be broken JSON, and it cannot name a category outside the
list.

This guarantees shape, not truth. A model can return perfectly valid JSON containing a total of
80.00 when the receipt says 78.70. That is why the next layer exists. For servers that ignore the
schema, `extract_json` strips code fences and finds the JSON object inside chatter.

### Grounding: checking the value against the evidence

A **grounding check** asks one question: does this value appear in the source? If the model says
the receipt total is 80.00 and no "80.00" is printed on it, the answer is rejected. The checks
in `importer/ai_tools.py` are:

- An amount must appear in the document text (`amount_in_text`). For statement lines, it must
  appear on the model's own line number.
- A date must be one of the dates printed in the text (`_ground_date`).
- A card's last four digits must appear in the text.
- A category must be in the allowed list, and an income category cannot go on money going out.
- A column number must exist, and the column must look like what the model says (a "date
  column" must mostly hold dates).
- Sums must reconcile. On a receipt, subtotal plus tax plus tip must equal the total, and the
  items should add up to the subtotal. On a pay stub, gross pay minus deductions must equal net
  pay.

The sum checks catch what grounding cannot. A subtotal is printed on the receipt, so
"total = subtotal" passes the grounding check, but the arithmetic fails.

### One retry with the reason, then flag

`run_tool` in `importer/ai_tools.py` runs the loop. Ask, validate, and if the validator lists
problems, send those problems back as plain sentences and ask once more. The default is two
attempts (`attempts=2`). If the second answer still fails, the bad values are dropped and the
row is flagged for a human. Nothing is guessed. A model that is told "date_col must be a column
whose values are dates; columns that look like dates: 0 ('When')" can often fix itself, which is
cheaper than failing outright.

### Rules first, model second

The model is the last resort, not the first step. For a bank export the code reads standard
headers, dates, signs and known merchants with ordinary rules. For categories, `importer/categorize.py`
tries sources in order: a category you chose for this merchant before, what the model read off a
receipt, built-in keyword rules, the bank's own category column, and only then the model, once
per merchant and not per row. Whatever is still open is marked "uncategorized". Rules are free,
repeatable and never invent anything, so the model only sees the leftovers. This also means that
with `LLM_PROVIDER=off` most imports still work; only photos and odd layouts need the AI.

### The assistant pattern: the model picks, the app computes

For questions, the model is not allowed to do arithmetic or to know your numbers. In
`engine/assistant.py` there is a fixed menu of nine read-only lookups (balances, net worth on a
date, forecast for a month, when net worth crosses an amount, planned spending, planned income,
loans, insights, taxes). The model's only job is to pick one and fill in its arguments, using a
schema where the lookup name is an enum. The app runs the lookup against the user's records and
produces **facts**, label and value pairs. Then a second model call may word the answer. Before
the reply is shown, `numbers_grounded` checks that every number in it also appears in the facts,
the question or today's date. If not, the reply is thrown away and the plain facts are shown
instead. The model can phrase, but it cannot supply a number. Filters work the same way: dropdown
values are enums, and `clean_filter` drops anything the page does not offer. A drafted entry must
contain an amount that the user actually typed (`clean_draft`).

### Realtime and batch work

Some work has a person waiting: the assistant, the natural-language filter, "explain this". That
is **realtime**. Other work can wait: reading a folder of imported files. That is **batch**. The
difference decides where the work may run, because some places are slow to start. `get_client`
takes a `mode` of `"realtime"` or `"batch"` for this reason.

### Where the model runs, in order

`ai/endpoints.py` keeps an ordered list and sends each request to the first place that can take
it, falling to the next when one is down:

1. **home**: the owner's desktop. It runs `home_runner.py`, which asks the server for work.
2. **server**: a model on the same machine as the app.
3. **own-cloud**: a machine the owner rents, such as a Cloud Run service with a GPU.
4. **paid**: someone else's API, used only for the features listed for it (`assistant`,
   `import`).

Private hardware always goes first, whatever order the list was written in (test
`test_your_own_machines_come_before_a_paid_service_whatever_the_listed_order`).

```
 phone ──▶ server (queue in memory) ◀── long poll ── home_runner.py ──▶ Ollama ──▶ GPU
              │                           (starts at home)
              ├──▶ own cloud GPU (sleeps when idle; batch only)
              └──▶ paid API (only for features you list)
```

The home runner pulls. The server never connects into the home network. A request waits in the
server's memory (`ai/relay.py`) until the runner collects it and posts the answer back.

### One worked example: a receipt photo

You drop a photo of a restaurant receipt on the Import page. The sample receipt in the tests is
from "Cedar & Salt Kitchen": items 32.00, 12.50, 7.00 and 9.00, subtotal 60.50, tax 6.20, tip
12.00, total 78.70.

1. The import worker finds that the file is an image. A vision call (`transcribe`) turns the
   photo into text, line by line. If the result has no digit at all, it fails with "no readable
   text".
2. The code classifies the document and, for a receipt, runs its own rules on the text first
   (`receipt_heuristics`): the TOTAL line, dates, a card ending.
3. `read_receipt` asks the model for merchant, date, total, subtotal, tax, tip, items and a
   category. The category field is an enum of the allowed slugs. Temperature is 0, so the same
   input gives the same output.
4. The model answers `total: "80.00"`. The validator looks for 80.00 in the text, fails, and
   sends back: the total "isn't printed on the receipt; copy the amount next to TOTAL". If the
   second answer is 80.00 again, the value is dropped.
5. The rules' total, 78.70, is used. Test `test_receipt_total_not_on_the_receipt_is_rejected`
   checks that the stored amount is -7870 cents.
6. If the model had returned the subtotal 60.50 (it is printed, so grounding passes), the AI and
   rules disagree. The row gets the flag `ai_disagrees`, confidence drops, and the rules'
   total wins (`test_receipt_subtotal_read_as_total_is_caught_by_the_rules`).
7. If the model returns 78.70, the arithmetic 60.50 + 6.20 + 12.00 = 78.70 passes, and the row
   gets high confidence (`test_receipt_that_adds_up_is_trusted`).
8. Nothing is saved yet. You see a review table, and you click Import.

## 3. Rules of thumb and typical numbers

| Value | Number | Source |
|---|---|---|
| Default model | `qwen3.5:9b`, about nine billion parameters | project choice, `config.py` (`LLM_MODEL`) |
| Context window | 32768 tokens | project choice, `config.py` (`LLM_NUM_CTX`); matches the agent stack |
| Temperature | 0 (same input, same output) | project choice, `importer/llm.py` |
| Model "thinking" mode | off | project choice, `config.py` (`LLM_THINK`) |
| Tries per question | 2 (one retry with the reasons) | project choice, `importer/ai_tools.py` (`attempts`) |
| Merchants per categorize call | 25 | project choice, `importer/ai_tools.py` (`BATCH`) |
| Text sent per document | first 3500 (classify), 6000 (receipt, grant), 7000 (pay stub) characters | project choice, `importer/ai_tools.py` |
| Request timeout | 180 s; 300 s waiting for the home runner | project choice, `config.py` (`LLM_TIMEOUT`, `AI_RUNNER_TIMEOUT`) |
| Home runner counted as online | 45 s after its last request for work | project choice, `ai/relay.py` (`ONLINE_WINDOW`) |
| Owner's GPU | RTX 3060, 12 GB | `nvidia-smi`, as recorded in `docs/design/ai-placement.md` |

General rule of thumb, source not recorded in the repo: model weights need memory roughly equal to
the number of parameters times the bytes used per parameter, plus extra for the context window.
That is why a 9B model needs compressed weights to fit a 12 GB card.

Cost figures from `docs/design/ai-placement.md`. All are **time-sensitive estimates**. Prices were
checked on 2026-11-22 and will change; re-check before relying on them.

| Item | Figure in that file |
|---|---|
| Household import volume | 5-10 statements and 10-30 receipts or stubs a month, about 50 pages, 1-2k tokens in and 0.5k out each: about 0.1M tokens a month (an estimate) |
| Claude Haiku 5.5 | $0.10 in / $0.50 out per M tokens |
| Gemini 3.5 Flash-Lite | $0.30 / $2.50 per M tokens |
| Result at this volume | "a few cents a month" for either API |
| Cloud Run with an L4 GPU | "about $1.05/h with a minute minimum" |
| Local cost | electricity for a few minutes of GPU time a month |

## 4. Common misconceptions and edge cases

- **"The schema makes the answer correct."** It makes the answer well formed. A well-formed answer
  can still hold a wrong number. Grounding and sums do the checking.
- **"Temperature 0 means no mistakes."** It means the same input gives the same output. A wrong
  answer is then repeatably wrong, which is why the retry sends the reason and not just "try again".
- **"Grounding proves the value is right."** It proves the value is printed somewhere. The
  subtotal is printed. A pay stub's year-to-date net is printed. Only the arithmetic and the
  "take the CURRENT column" instruction catch those; see
  `test_payslip_ytd_net_is_replaced_by_the_amount_that_reconciles`.
- **Number checks are blunt.** `numbers_grounded` accepts any single digit without checking, so
  "one", "2 months" and so on pass. It checks numbers, not words. A reply could say "fell" when the
  value rose. The plain facts are always shown beside the worded reply.
- **Words in the reply are not checked at all.** Only numbers are. This is why the system prompt
  tells the model to give no advice and add nothing.
- **A model that is off or unreachable is not an error.** If it goes offline mid-file, rows fall
  back to rules and get flagged ("stopped responding"), as in
  `test_ai_going_offline_mid_file_falls_back_to_rules`.
- **A model error at home is not retried elsewhere.** An error answered by the home model is
  reported, because it would likely repeat; only an unreachable endpoint falls to the next
  (`test_a_model_error_at_home_is_reported_not_retried_elsewhere`).
- **Remote is refused by default.** The single `LLM_*` setup refuses any address that is not this
  computer unless `LLM_ALLOW_REMOTE=1` (`test_remote_hosts_are_refused_unless_allowed`). An entry
  you list in `AI_ENDPOINTS` is treated as your explicit choice and is allowed.
- **The free tier of a paid API may train on your data.** `docs/design/ai-placement.md` records
  that Gemini's free tier uses data to improve Google's products, so only a paid tier was
  considered acceptable.
- **A sleeping cloud GPU is not for the assistant.** It takes tens of seconds to minutes to wake
  (`deploy/ai-endpoint/deploy.sh`), so it is marked batch only and the app does not wake it just to
  ask whether it is there (`assume_up`).
- **Restarting the server drops waiting requests.** The queue is in memory only; the caller sees
  "not available".

## 5. How the project uses it

| Piece | Where |
|---|---|
| Client for one model (Ollama and OpenAI-compatible), schema, JSON repair, privacy gate | `importer/llm.py` |
| Narrow single-purpose tools and the ask-validate-retry loop | `importer/ai_tools.py` (`run_tool`, `read_receipt`, `read_payslip`, `map_columns`, `extract_statement_lines`, `categorize`) |
| Order of category sources, rules first | `importer/categorize.py` |
| Assistant lookups, number guardrail, filter and draft cleaning | `engine/assistant.py`, routes in `api/assistant.py` |
| Endpoint list, routing by realtime or batch, paid only for listed features | `ai/endpoints.py` |
| In-memory queue for the home computer | `ai/relay.py` |
| The program on the desktop that collects the work | `home_runner.py` (also started by the tray, `desktop/`) |
| Settings | `config.py`: `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_VISION_MODEL`, `LLM_API_KEY`, `LLM_NUM_CTX`, `LLM_TIMEOUT`, `LLM_THINK`, `LLM_ALLOW_REMOTE`, `AI_ENDPOINTS`, `AI_HOME_RUNNER`, `AI_RUNNER_TOKEN`, `AI_RUNNER_TIMEOUT` |

Tests that show the behaviour with a scripted stand-in model: `tests/test_import_ai_guardrails.py`
(wrong columns then the fix, an invented receipt total, a date not on the receipt, empty pay stub
amounts sent back, digits swapped on a statement line, an income category on spending, AI going
offline) and `tests/test_ai_endpoints.py` (no runner means "not available" at once, a runner
collects a request and returns the answer, a runner that goes quiet times out, a paid service
with no features is never used, bad `AI_ENDPOINTS` JSON turns AI off with a reason, a photo waits
for the home computer instead of failing, a text file does not wait for AI).

What was simplified or left out, and why:

- **The server VM runs no model.** `LLM_PROVIDER=off` is set by the deploy, because the VM is a
  1 GB machine. AI comes from the home runner or a listed endpoint.
- **One request at a time.** The cloud image sets `OLLAMA_NUM_PARALLEL=1` and the service
  concurrency is 1. One household does not need more.
- **No fine-tuning, no embeddings, no retrieval.** The tools are narrow prompts with schemas.
- **No speech input.** Browser dictation was left out because audio goes to the browser vendor
  (`docs/design/cloud-server-and-ai-endpoints.md`).
- **The private cloud endpoint is written but never deployed.**

Design record: [DECISIONS.md](../design/DECISIONS.md) and
[cloud-server-and-ai-endpoints.md](../design/cloud-server-and-ai-endpoints.md). The first
placement review is [ai-placement.md](../design/ai-placement.md), marked superseded but still
the source of the prices and volumes.

## 6. What we found

- **2026-11-22, placement review.** The AI features in the importer need little compute: about
  50 pages and 0.1M tokens a month for a household (an estimate, not a measurement). A
  GPU-less laptop could run the 9B model on the CPU, slowly ("minutes per page"). That is
  acceptable for batch work. Cost was not the reason to stay local; privacy was. At that volume
  either listed API would cost a few cents a month.
- **2026-11-22, why a 9B model is good enough.** The import plan states that every answer is
  grounded in the document, which is what makes a small model usable. This is a design argument,
  not a measured accuracy. See open question 1.
- **2026-11-23, decision.** The app moved to a private server. The privacy rule "no data leaves
  the user's device" became "data stays on machines the owner controls", with a paid API as the
  one exception, only for features the owner turns on.
- **2026-11-24, deployment state.** The home runner path and the app are deployed. The private
  cloud endpoint (`deploy/ai-endpoint/`) has never been run, and its script says it was written
  from documentation and needs a GPU quota.
- **What the tests prove.** The guardrail tests use a scripted model, so they show that wrong
  answers are caught. They do not measure how often the real model is wrong.

## 7. Open questions

1. How accurate is `qwen3.5:9b` on the owner's real documents? `ai-placement.md` suggests a small
   labelled set scored per field before considering a larger model. No result is recorded.
2. Which weight format (quantization) does the Ollama tag use, and what is the memory headroom on
   the 12 GB card with a 32768 context? Not recorded.
3. Should the importer get a per-batch "send this batch to a paid API" switch, default off?
   (Question 1 in `ai-placement.md`; the endpoint list now covers a per-feature version.)
4. Will the cloud endpoint ever be needed? It only matters when the home computer is off and a
   batch must finish.
5. Should the number guardrail also check words such as "rose" or "fell"?

## 8. Sources and further reading

- Ollama documentation, "Structured outputs": how the `format` field takes a JSON schema.
- OpenAI documentation, "Structured Outputs": the `response_format` with `json_schema` form that
  OpenAI-compatible servers copy.
- Anthropic, Claude API pricing, and Google, Gemini API pricing and Cloud Run pricing: the pages
  `docs/design/ai-placement.md` lists as its price sources, checked 2026-11-22.
- In this repo: `docs/design/ai-placement.md`, `docs/design/cloud-server-and-ai-endpoints.md`,
  `docs/design/plans/2026-11-22-import-statements-local-ai.md`, `deploy/README.md`.

## Changes

2026-11-24: first version.
