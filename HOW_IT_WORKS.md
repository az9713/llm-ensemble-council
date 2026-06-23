# How the LLM Council Works

A walkthrough of the architecture and — the part you asked about specifically — **how the
LLMs actually communicate with each other**. Short version: they mostly *don't*, and that
restraint is the whole design.

> Source of truth: `council/council.py` (the graph), `council/llm.py` (model plumbing),
> `council/rag.py` (grounding), `council/config.py` (composition), `council/eval.py` /
> `council/demo.py` (entry points). This doc describes what those files do as of reading.

---

## The one-paragraph version

A *council* is several different LLMs ("seats"), each from a different lab, answering the
**same** question **independently**. None of them sees any other's answer while writing.
Then every seat re-reads all the answers **anonymized** and ranks them blind; the ranks are
tallied with a **Borda count**. Finally a separate **chairman** model reads the Borda-scored
answers and synthesizes a final verdict that preserves dissent. A document-RAG step grounds
every seat in the *project's own docs* (not in each other, and not in the council's prior
output). Cost is honestly tracked: a council costs **2N+1 LLM calls** vs 1 for a single model.

---

## The pipeline (a LangGraph state machine)

`build_council()` wires four nodes into a linear `StateGraph` and compiles it:

```
START → retrieve → generate → rank → chairman → END
        (stage 0)  (stage 1)  (stage 2) (stage 3)
```

State flows as a `TypedDict` dict that each node adds keys to (`question` → `recalled` →
`answers` → `leaderboard` → `final`). LangGraph here is used as a simple, inspectable
sequential pipeline — there are no branches or loops; the value is the typed, named-stage
structure and the shared state object.

```
                       ┌─────────────── docs/ (project markdown) ───────────────┐
                       │                                                        │
                       ▼                                                        │
   question ──► [retrieve]  doc-RAG: top-k relevant doc chunks                  │
                       │     (grounding context — same for all seats)           │
                       ▼                                                        │
                  ┌────────────────── [generate] STAGE 1 ──────────────────┐   │
                  │  seat 1 ─┐                                              │   │
                  │  seat 2 ─┤  each seat answers the SAME question,        │   │
                  │  seat 3 ─┼─ ALONE, seeing only the question + docs.     │◄──┘
                  │   ...    │  NO seat sees another seat's answer.         │
                  │  seat N ─┘  → N independent structured answers          │
                  └───────────────────────┬──────────────────────────────┘
                                          ▼
                  ┌────────────────── [rank] STAGE 2 ─────────────────────┐
                  │  answers are SHUFFLED + relabeled A1..An (anonymized) │
                  │  every seat re-reads ALL answers, blind, and ranks    │
                  │  them best-to-worst → Borda count tallies the votes   │
                  └───────────────────────┬──────────────────────────────┘
                                          ▼
                  ┌──────────────── [chairman] STAGE 3 ───────────────────┐
                  │  a SEPARATE model reads the Borda-scored answers and  │
                  │  writes {answer, consensus, dissent, confidence}      │
                  └───────────────────────┬──────────────────────────────┘
                                          ▼
                                    final verdict
```

---

## Stage by stage

### Stage 0 — `retrieve` (grounding)

`retrieve_node` calls an injected `retrieve(question, k)` callable and formats the returned
doc chunks into a `## Relevant project documents` block. The default implementation is
`DocRAG` in `rag.py`: a LangChain `InMemoryVectorStore` over the `*.md`/`*.txt` files in
`docs/`, queried by similarity search. Embeddings are injectable — tests pass a deterministic
fake; live runs default to local `all-MiniLM-L6-v2` (keyless, no API call).

**Why it grounds in docs and not in the council itself:** feeding the council's own prior
consensus back in would anchor the seats toward agreement and erode the diversity that makes
a council worth the cost. Grounding in *external* project documents gives consistency
*without* collapsing the spread of opinions. (Pass `retrieve=None` for an ungrounded council.)

### Stage 1 — `generate` (independent answers) — **the core invariant**

`generate_node` loops over the seats and asks each one the same question with the same doc
context. **This is where the "no communication" rule lives.** Each seat gets:

- a system prompt fixing its *role* (`skeptic`, `contrarian`, `red-teamer`, …) and telling it
  *"Do not mention other agents"*;
- the question + the retrieved docs.

It does **not** get any other seat's answer. The loop just collects N independent responses.
Each answer is a *structured artifact*, not a blob — the prompt forces six fields:

1. direct answer · 2. key assumptions · 3. strongest argument for · 4. strongest argument
against · 5. failure modes · 6. what evidence would change my mind.

Decorrelated, structured answers are what make the downstream ranking meaningful. If seats
saw each other here, they'd converge — so the design forbids it.

### Stage 2 — `rank` (blind peer review + Borda) — **the only "communication"**

This is the *one* place answers cross between agents, and it is deliberately **indirect and
anonymized**:

1. `anonymize(n, seed)` does a **seeded shuffle** of the answers and relabels them `A1..An`.
   Because the shuffle is seeded, it's reproducible, but no judge can tell *who* wrote `A1`
   or rely on position (the author isn't at a fixed slot).
2. Every seat is now also a **judge**: it re-reads *all* the anonymized answers and returns a
   best-to-worst order as JSON (`{"order": ["A2","A1",...]}`). `parse_order` is tolerant of
   messy output and appends any labels the model dropped so every answer stays ranked.
3. `borda(orders, labels)` tallies: in an order of *n* labels, position *p* scores *n−1−p*.
   Sum across all judges → a Borda score per answer → a sorted `leaderboard`.

So agents influence each other **only** through anonymous, aggregated votes — never by seeing
"Seat 3 (Claude) said X." That's what keeps the ranking about *content*, not reputation or
order.

### Stage 3 — `chairman` (synthesis)

`chairman_node` is a **separate** model (not one of the seats). It reads the answers tagged
with their Borda scores and returns strict JSON:
`{answer, consensus, dissent, confidence}`. Its system prompt explicitly says *"Preserve
genuine dissent; do not average away minority warnings"* — the chairman is a synthesizer, not
a vote-counter that flattens the minority. `parse_final` defensively coerces the output.

---

## Who talks to whom (communication summary)

| From → To | Stage | What crosses | Can A see B's identity? |
|---|---|---|---|
| docs → all seats | retrieve | shared grounding context | n/a |
| seat → (nobody) | generate | **nothing** — fully isolated | — |
| seats → seats (as judges) | rank | **anonymized** answers only | **No** (shuffled, relabeled) |
| answers + Borda → chairman | chairman | scored answers (anonymized) | No |

The deliberate non-communication in stage 1 plus the anonymized, aggregated communication in
stage 2 is the entire point. A council that let seats chat would just be one model talking to
itself in different voices.

---

## The plumbing that makes it testable

`council/llm.py` keeps the council provider-agnostic and offline-testable:

- **`call(chat, messages)`** invokes any LangChain chat model and returns `(text, Usage)`. It
  prefers the provider's real `usage_metadata`; if absent, it counts tokens locally with
  `tiktoken`. So even a stub run produces *real* token measurements.
- **`StubChat`** is a deterministic test double with a pluggable `responder(messages) → str`.
  It reports no usage metadata, which forces `call()` to tiktoken-count the real assembled
  prompt — meaningful cost numbers with zero API keys.
- **`CostMeter`** accumulates `(stage, role, in_tok, out_tok, calls)` rows so the eval can
  report cost by stage.

Everything the council needs — seats, chairman, `retrieve` — is **injected** into
`build_council`. That's why `python -m pytest` runs fully offline: tests pass `StubChat` seats
and a fake embeddings object; live runs pass real `init_chat_model` instances.

## Composition (`config.py`)

Seats are "one string = one model." The default is **6 seats across 3 labs** (OpenAI,
Anthropic, Google) each paired with a role from `ROLES`. `available_seat_specs()` keeps only
the seats whose provider key is actually set, so a live run works with *whatever* keys you
have rather than demanding all three. The chairman and the eval's judge are configurable via
`COUNCIL_CHAIRMAN` / `COUNCIL_JUDGE` env vars and fall back to an available provider.

---

## How it's evaluated (`eval.py`) — two honest measurements

1. **Cost structure** (offline, keyless): a council does **2N+1** LLM calls (N generate +
   N rank + 1 chairman) versus 1 for a single model. This is reported as the robust claim;
   the token multiplier is shown but flagged as indicative (it scales with answer length).
   **A council is more expensive by design** — it's the cost of a real second opinion.
2. **Quality** (live, needs keys): a **blind, independent judge — explicitly *not* one of the
   seats** — ranks the council's final answer against each single seat-model answering alone.
   The council only "wins" a question if it beats **every** single model. The expected finding
   (per the source design) is that the council mainly wins on **open-ended design** questions,
   not on simple factual ones — exactly where decorrelated perspectives + synthesis pay off.

---

## Design invariants (don't break these without intent)

These come straight from the code's structure and the project's `CLAUDE.md`:

- **Stage 1 is independent.** Seats never see each other's current answers. The decorrelation
  *is* the value. Don't add cross-seat visibility in `generate`.
- **Grounding = project documents, not the council's own prior output.** Feeding back
  consensus anchors the seats and erodes diversity. `docs/` is the RAG corpus; design docs
  live in `reference/` so they don't pollute it.
- **Ranking is blind + anonymized** (seeded shuffle + Borda); the quality eval's judge is
  **not** a seat.
- **Seats / chairman / retrieve are injected** — keep it that way so tests run offline.

---

## TL;DR mental model

> Ask N different experts the same question *in separate rooms* (grounded in your project's
> docs). Collect their structured answers, *strip the name tags*, and have each expert grade
> all the answers blind. Tally the grades. Hand the graded stack to a chair who writes the
> final call **and keeps the dissent on the record.** The cost is 2N+1 calls — that's the
> price of a real second opinion, paid honestly.
