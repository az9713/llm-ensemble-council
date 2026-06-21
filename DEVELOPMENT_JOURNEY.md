# Development Journey — from BrightData research to two projects

The full arc, 2026-06-20 → 2026-06-21: starting from BrightData MCP web research, through an
idea brainstorm and validation, a memory-MVP (coilmem), an upgrade exploration that tried and
discarded several framework paths, an LLM-Council experiment, an honest reassessment, and
finally a split into **two independent codebases**.

This doc lives in `brightdata_me` (the origin/archive). The two product repos each carry their
own focused `DEVELOPMENT.md`. Read this for the *whole* story, including the paths not taken.

---

## Phase 1 — BrightData research (3 prompts)

The work originated in `~/Downloads/brightdata_me`, where a BrightData MCP server was already
configured (`brightdata-setup.md`): `search_engine` ✅ and `scrape_as_markdown` ✅, with the
key gotcha being `WEB_UNLOCKER_ZONE` must match the real zone (`web_unlocker1`).

**Prompt 1 — "where do we go from here with brightdata".**
Assessment: the plumbing was already done and verified; the next move was a *use case*, not more
setup. Offered three directions (ad-hoc use, a small repeatable script, harden config) and
recommended just using it.

**Prompt 2 — "Use Bright Data MCP Discover and Search Engine to find 10 current AI-agent product
ideas with source evidence."** → `reports/idea_brainstorm.md`, `data/idea_candidates.json`.
- `discover` returned empty on this account/plan (both attempts). `search_engine` + a deep
  `scrape_as_markdown` of a ranked listicle (preuve.ai) carried the research instead. This
  fallback (one good source page > many SERP snippets) became a recurring pattern.
- Produced 10 agentic product ideas, each with buyer + catalyst + a source quote.
- **Honest flag raised at the time:** most evidence traced to a single strong source — breadth
  without independent verification.

**Prompt 3 — "Validate the top 3 ideas … pick the best for a solo 1–3 day MVP."** →
`specs/mvp_spec.md`, `specs/build_plan.md`.
- Re-scraped competitor density for the top 3. Verdict: agent-observability and vertical-agent-
  builder were **oversaturated**; the source's "underserved" labels were stale.
- The one buildable wedge: **shared memory for *multi-agent* systems** — every shipped memory
  tool (Mem0, Zep, Letta, Cognee) targets *single-agent/conversational* memory. That gap became
  the product: **coilmem**, a workspace-level `shared` scope + per-agent `private` scope.

## Phase 2 — coilmem MVP

Built the MVP from the spec (`/goal`): `coilmem/` (`store.py` scope rule, `embed.py`, `app.py`
FastAPI service), tests, README. **13 tests** green offline.
- The scope rule (an agent sees `shared` + its own `private`, never another agent's `private`)
  is one SQL predicate — that's the product.
- "Refactor so env vars come from `./.env`" → `coilmem/config.py` `load_env()` (no python-dotenv
  dep) + `.env.example`.
- "Is it too much a toy demo?" → honest assessment: it proved the *mechanism* but not the
  *value* (no real agents, no measured token savings). That critique set up Phase 3.

## Phase 3 — Upgrade exploration (paths tried, most discarded)

Goal: a realistic multi-agent demo with real embeddings and a measured before/after, on a
recognized framework. Researched options with parallel agents:
- **pi** (github.com/earendil-works/pi): TypeScript, hook-based, **no native multi-agent**.
  Clean integration seam (`transformContext`) but a different language and single-agent.
- **Frameworks:** LangGraph (native multi-agent, Python, clean memory `Store`), CrewAI, ADK,
  AutoGen. Token truth = provider `usage_metadata`; keyless embeddings = local all-MiniLM-L6-v2.

Direction churned across several user turns: **pi-first → LangChain → (read
`~/Downloads/ensemble_llm_PE/`) → LLM Council on LangGraph**. Landed on LangGraph (Python,
native multi-agent, reuses coilmem directly).

## Phase 4 — LLM Council experiment (coilmem as cross-session memory)

Read the council sketch (`ensemble_llm_PE/`): fan-out to multi-model seats → blind Borda
ranking → chairman synthesis; wins over the best single model mainly on open-ended design;
*"a judgment call, not a calculator."*

Built it on LangGraph in `integrations/council/` (5 phases): multi-provider embedder + dim
guard, `llm.py` (providers + token accounting + StubChat), the council graph, a cross-session
demo, and an eval. **24 tests** green offline. coilmem was wired in as **cross-session project
memory** (store each decision, recall to ground later questions).

## Phase 5 — The honest reassessment (the pivot)

Asked directly: *does applying shared context to the council make sense?* Conclusion: **weak
fit.** Reasons (now preserved in `council-coilmem-decision.md`):
1. Frequency mismatch — a council is rare/high-stakes; memory wants frequent related turns.
2. Anchoring — feeding the council its own prior consensus erodes the diversity that makes an
   ensemble work.
3. It used only coilmem's *non-novel* half (`shared` = plain RAG); the `private` wedge went
   unused.
4. No metric isolated memory's value; token savings is the wrong KPI for a cost-insensitive
   council.

Captured the assessment in `council-coilmem-decision.md` and pointed `CLAUDE.md` at it before
building further. **Decision: pursue both ideas as separate projects.**

## Phase 6 — Split into two independent codebases

Created two sibling, **completely independent** git repos (no shared package, no cross-repo
imports). `brightdata_me` left intact as the archive.

- **`~/Downloads/llm-council`** — the council, **without coilmem**, **with document-RAG**
  grounding (LangChain `InMemoryVectorStore` over project docs — grounding without the
  self-consensus anchoring). `retrieve → generate → rank(Borda) → chairman`. **9 tests** green.
- **`~/Downloads/coilmem`** — the memory library + a **researcher → critic → writer** team on
  LangGraph that shares one coilmem workspace over many turns, exercising **both** `shared` and
  `private` scopes. Honest measurement: memory-vs-naive input tokens **plus a quality-parity
  guardrail**. **18 tests** green.

A review pass caught and fixed real issues before finishing: the parity guardrail was checking a
bare `"private scratch"` string (tripping on the writer's *own* allowed notes) — fixed to be
author/role-based; a stale "coilmem" docstring in the council repo; and the 73.5% token figure
was reframed as a *naive-full-replay ceiling*, not a typical saving.

## Recurring principles (held throughout)

- **Honesty over flattery:** every phase surfaced caveats (single-source evidence, "toy"
  mechanism, council cost, metric-doesn't-isolate, savings-vs-ceiling). The pivots came from
  taking those seriously.
- **Offline-first:** stubs (`StubChat`) + fake/local embeddings → every suite runs with no API
  keys. Live paths are construction-verified only (no provider keys in this environment).
- **The fallback that worked:** when `discover` failed, scrape one strong source; when live
  LLMs weren't available, stub them but measure real tokens.

## Where things live now

| Artifact | Location |
|---|---|
| BrightData setup + gotchas | `brightdata_me/brightdata-setup.md` |
| Idea research | `brightdata_me/reports/idea_brainstorm.md`, `data/idea_candidates.json` |
| coilmem product spec | `brightdata_me/specs/` (and copied into the coilmem repo) |
| Council ⇄ coilmem decision | `council-coilmem-decision.md` (in archive + both repos) |
| Original combined build | `brightdata_me/coilmem/`, `brightdata_me/integrations/council/` (archive) |
| **Project 1 (council)** | `~/Downloads/llm-council/` — see its `DEVELOPMENT.md` |
| **Project 2 (coilmem)** | `~/Downloads/coilmem/` — see its `DEVELOPMENT.md` |

From here, the two repos are developed individually in their own roots; this archive is the
historical record of how they came to be.
