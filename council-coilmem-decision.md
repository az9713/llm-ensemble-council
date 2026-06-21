# Council vs coilmem — Decision & Implementation Context

**Date:** 2026-06-21. Status: **decision pending** before further implementation.
Owner: simon. This doc is the source of truth for *why we paused* and *how to proceed
in either direction*.

---

## TL;DR

Two individually-sound ideas — an **LLM Council** (multi-model ensemble) and **coilmem**
(shared/private memory for multi-agent systems) — were stapled together. **The join is
weak.** Before building more, pick the goal, because the two goals diverge:

- **Direction A — Showcase the council** (a credible LangGraph multi-agent system).
- **Direction B — Validate coilmem's wedge** (shared+private memory that earns its keep).

The council is close to the *worst-fit host* for proving coilmem. coilmem is a detour for
proving the council. Choose one as primary.

---

## The honest assessment (why applying coilmem to the council is a weak fit)

1. **Frequency mismatch.** Cross-session memory pays off when queries are frequent and
   related (long, turn-by-turn workloads). A council is rare and high-stakes ("a judgment
   call, not a calculator") — convened a handful of times per project. With ~5 stored
   decisions, top-k retrieval ≈ "include all 5"; the retrieval machinery barely earns its
   keep. The eval's "52% smaller context" used a **synthetic 20-decision project**, which is
   *not* how a council is actually used.

2. **The payload anchors away the council's point.** The council's value is decorrelated,
   diverse perspectives. coilmem stores the chairman's *synthesized consensus* and feeds it
   back into the next round's generators → answers drift toward prior rulings → diversity
   erodes across sessions. Shared context can *corrode* the mechanism that makes a council
   work (slow-acting version of the stage-1 independence objection).

3. **It uses only the non-novel half of coilmem.** coilmem's actual wedge is the
   **private + shared scope split for persistent agents**. Council seats are stateless
   personas — no reason for cross-session *private* memory. So only the `shared` scope is
   used, which is just a vector store. **A plain RAG store does the identical job.** This
   build validates "wire a memory store into LangGraph," not coilmem's distinctive idea.

4. **No metric isolates the question.** Token cost is the wrong lens (council is
   cost-insensitive and already ~2N+1 calls — grounding tokens are rounding error). Quality-
   vs-single-model tests the *council*, not the *memory*. To answer "does memory help the
   council" you'd need council-with-memory vs council-without on a session of related
   questions — and per #2 that result could be **negative**.

**Verdict:** keep them as separate artifacts. The earlier researcher→writer / persistent-
chat framing is a far better vehicle for coilmem; the council is a fine standalone showcase.

---

## What is already built (codebase state, all offline-verified)

**coilmem core** (`coilmem/`, stdlib-only core):
- `store.py` — SQLite store; the scope rule (an agent sees `shared` + own `private`, never
  another agent's `private`) is the product. Dim guard: one `EMBED_PROVIDER` per DB.
- `embed.py` — pluggable: `local` (all-MiniLM-L6-v2, 384-dim, keyless default), `openai`
  (text-embedding-3-small, 1536), `gemini` (text-embedding-004, 768). Heavy imports lazy.
- `app.py` — FastAPI service (POST/GET/DELETE /memory, /memory/search, X-API-Key).
- `config.py` — `load_env()` reads `./.env` (setdefault; real env + tests win).
- `tests/test_store.py` — scope invariant, dim guard, etc.

**Council integration** (`integrations/council/`):
- `llm.py` — `make_chat` (init_chat_model "provider:model"), `call` (usage_metadata +
  tiktoken fallback; coerces Anthropic/Gemini list-content), `CostMeter`, `StubChat`.
- `council.py` — LangGraph DAG `recall → generate → rank(Borda) → chairman → remember`;
  `Seat`, `anonymize`, `borda`, `parse_order/parse_final`, `live_seats` (key-aware).
- `memory.py` — coilmem `recall`/`remember` for a workspace (reader sees shared only).
- `config.py` — seats (`DEFAULT_SEAT_MODELS` × `ROLES`), `available_seat_specs`,
  `resolve_model`, `chairman_model`/`judge_model`.
- `demo.py` — cross-session demo (recall grounds later Qs). `eval.py` — grounding-size,
  cost-structure, live blind-judge quality.
- `tests/test_council.py` — Borda, anonymize, parsing, full offline run, memory effect, cost.

**Run:** `python -m pytest` (24 passed, keyless) · `python -m integrations.council.demo` ·
`python -m integrations.council.eval` · append `live` for real models (needs keys).

**Verification status:** offline **fully verified**; live **construction-verified only**
(no real API keys were available — `... live` end-to-end is unrun).

---

## Facts & gotchas to carry forward (true in either direction)

- **coilmem's novel wedge = shared+private scopes for *persistent* agents.** If a design
  doesn't use `private`, it isn't exercising coilmem's distinctive value — it's RAG.
- **Council facts (from `~/Downloads/ensemble_llm_PE/`):** one-shot; wins over best single
  model only on **open-ended design** (~1/3 categories); plain answer beats verbose; strict
  bar = beat *every* single model; judge must be a model *not* in the council.
- **Framework history:** chose **LangGraph** over **pi** (pi = TypeScript, 64k★, hook-based
  but **no native multi-agent** → would need 2 processes + TS bridge) and over framework-
  agnostic. LangGraph is Python, native multi-agent, reuses coilmem directly.
- **Multi-provider** via `init_chat_model("openai:…"/"anthropic:…"/"google_genai:…")`;
  seats are key-aware (`available_seat_specs` builds only providers whose key is set).
- **Embeddings:** one provider per DB (dims differ; dim guard enforces). Anthropic has **no**
  embeddings API → use `local`/openai/gemini.
- **Token measurement:** prefer provider `usage_metadata`; tiktoken (`o200k_base`) fallback
  makes offline/stub runs measure real prompt tokens.
- **Metric honesty:** the memory metric measures **grounding-context size** (top-k vs full
  history), *not* a quality-held-equal saving. Cost = **2N+1 calls** (robust); token
  multiplier is indicative (scales with answer length).
- **Env:** project has a **BrightData** token only (`.env.txt`); **no LLM/OpenAI keys**
  confirmed → all live validation is currently blocked on obtaining provider keys.

---

## Direction A — Showcase the council (LangGraph multi-agent)

**Goal:** a credible, runnable multi-model council; coilmem is incidental.

- **Keep:** the whole `integrations/council/` graph.
- **Change:** stop feeding the council its own prior *consensus*. If grounding is wanted,
  retrieve **project facts / source docs / constraints (doc-RAG)** fed equally to all seats —
  grounding without anchoring. coilmem's `shared` scope can hold those docs, but a plain
  vector store is equivalent (don't oversell coilmem here).
- **Add:** run the **live blind-judge quality eval** (`eval.py live`) on the source's
  question categories; parallelize seat calls (asyncio) for latency; output plain answer by
  default (evidence: verbose hurts).
- **Success metric:** council beats every single model, especially on open-ended design.
- **Risks:** cost (2N+1 calls); needs ≥1 provider key (ideally 2–3 labs for real diversity).

---

## Direction B — Validate coilmem's shared-context wedge

**Goal:** prove shared+private memory adds value. **Drop the council.**

- **Workload that fits:** long-running, frequent, related turns — e.g. a persistent
  researcher→writer pair (or small team) over many turns, or a single persistent chat agent.
  This is where retrieval beats full-history replay *and* where `private` vs `shared` matters.
- **Use BOTH scopes:** agents keep `private` working memory; promote shared findings to
  `shared`. Demonstrate cross-agent transfer + private isolation under real use.
- **Measure honestly (the part missing today):** memory-ON vs memory-OFF over a real session,
  with a **quality-parity guardrail** — assert the agent still produces the required facts on
  retrieval, so "smaller context" is a genuine saving, not dropped-needed-context. Report
  context growth (bounded vs O(n)) *and* held-equal quality.
- **Reuse:** `coilmem/store.py`, `embed.py`, and `integrations/council/llm.py`
  (CostMeter, call, providers) — all directly applicable.
- **Success metric:** equal task quality with bounded input context as the session grows.

---

## If both: hybrid (more work, two artifacts)

Council + **doc-RAG** (facts, not self-consensus) as artifact 1; a separate coilmem
chat/team demo (Direction B) as artifact 2. Don't conflate them into one claim.

---

## Resolve before coding

1. **Which goal is primary — A (showcase council) or B (validate coilmem)?** Decides everything.
2. **Do we have provider API keys (OpenAI / Anthropic / Gemini)?** All *live* validation is
   blocked without at least one. (Project currently has only a BrightData token.)

## Pointers

- Approved plan (council build): `~/.claude/plans/give-a-plan-to-kind-aurora.md`
- Council source sketch: `~/Downloads/ensemble_llm_PE/` (`council-architecture.md`, `gpt5.5_summary.txt`)
- coilmem product spec / wedge: `specs/mvp_spec.md`, `specs/build_plan.md`
- BrightData MCP setup: `brightdata-setup.md`
