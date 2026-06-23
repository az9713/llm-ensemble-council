# llm-council — Development Journey & Context

Context for future work on this repo. Read alongside `README.md` (how to run) and
`council-coilmem-decision.md` (why this exists as its own codebase). This file is the "why
and how we got here" so the next change doesn't relearn it.

---

## 1. Origin

This codebase began as one experiment that wired a memory layer ("coilmem") into an LLM
Council. An honest assessment concluded the two don't belong together (a council is a rare,
cost-insensitive, diversity-dependent judgment tool; cross-session memory wants frequent,
related turns — and feeding a council its own prior consensus *anchors away* the diversity
that makes it work). Decision: **split into two independent codebases.** This repo is the
council, standalone — **no coilmem, no shared package**. Full backstory:
`council-coilmem-decision.md`.

Framework history worth knowing: we evaluated **pi** (TypeScript, hook-based, but no native
multi-agent) and **LangGraph**, and chose **LangGraph** (Python, native multi-agent graphs,
clean state). That choice is settled; don't relitigate without a reason.

## 2. What this is

A multi-model **LLM Council**: fan a question to several models in distinct roles → blind
anonymized peer-ranking (Borda) → a chairman synthesizes one answer (consensus / dissent /
confidence). Grounded in **project documents** via doc-RAG.

The source idea (an ensemble "council of LLMs") found the council beats the best *single*
model mainly on **open-ended design** (~1/3 of question types); the plain answer beats the
verbose write-up. Framing: *"a judgment call, not a calculator."* The eval is built to test
that honestly, not to flatter the council.

## 3. Architecture

```
retrieve ─→ generate ─→ rank ─→ chairman
(doc-RAG)   (parallel    (blind   (synthesis)
            role seats)  Borda)
```

| File | Role |
|---|---|
| `council/council.py` | the LangGraph graph + `Seat`, `build_council(seats, chairman, retrieve=None, ...)`, Borda (`borda`), seeded anonymization (`anonymize`), tolerant output parsing (`parse_order`/`parse_final`), `live_seats` |
| `council/rag.py` | `DocRAG` — document grounding via LangChain `InMemoryVectorStore`; embeddings **injectable** (fake in tests, local MiniLM live). `load_docs()` reads `docs/*.md`. **Deliberately not coilmem.** |
| `council/llm.py` | provider-agnostic `make_chat` (`init_chat_model`), `call()` (usage_metadata + tiktoken fallback, coerces Anthropic/Gemini list-content), `CostMeter`, `StubChat` |
| `council/config.py` | seats (`DEFAULT_SEAT_MODELS` × `ROLES`), key-aware selection (`available_seat_specs`/`resolve_model`), `chairman_model`/`judge_model`, `load_env()` |
| `council/demo.py` | runs the council over related questions grounded in `docs/` |
| `council/eval.py` | `cost_structure` (offline) + `quality` (live blind judge) |
| `docs/` | sample project-doc corpus for RAG |
| `tests/test_council.py` | offline suite (StubChat + fake embeddings) |

**Default models** (`config.py`; 3 labs × 2 models = decorrelation. Change freely — one string = one model):

| # | Role | Model | Lab |
|---|---|---|---|
| 1 | skeptic | `openai:gpt-4o` | OpenAI |
| 2 | domain expert | `anthropic:claude-sonnet-4-6` | Anthropic |
| 3 | contrarian | `google_genai:gemini-3.5-flash` | Google |
| 4 | first-principles journalist | `openai:gpt-4o-mini` | OpenAI |
| 5 | rigorous reasoner | `anthropic:claude-haiku-4-5-20251001` | Anthropic |
| 6 | red-teamer | `google_genai:gemini-3.1-flash-lite` | Google |
| — | Chairman (synthesis) | `anthropic:claude-sonnet-4-6` | override `COUNCIL_CHAIRMAN` |
| — | Judge (blind eval, not a seat) | `openai:gpt-4o` | override `COUNCIL_JUDGE` |

New model IDs are construction-verified only (no keys at dev time); `resolve_model` falls back to an available provider.

## 4. Key decisions & rationale (don't silently undo these)

- **Grounding = project documents, not the council's own prior output.** Feeding back prior
  consensus anchors the generators and erodes diversity. If you add memory, keep it source
  documents fed *equally* to all seats. This is the core lesson from the origin.
- **Stage 1 is independent.** Seats never see each other's current answers — that decorrelation
  is the whole value of an ensemble. Don't add cross-seat visibility in `generate`.
- **Blind, anonymized ranking + Borda.** Answers are seeded-shuffled and labeled A1..An so
  judges can't favor their own/by position. Borda is the tally; self-inclusion is on (anonymized).
- **Judge is not a seat** (in `quality`) — avoids a model grading itself.
- **Concise output by default** — evidence said verbose meta-output hurt scores.
- **Dependency injection** — seats/chairman/retrieve are passed in, so tests use `StubChat` +
  fake embeddings and run fully offline with no keys.
- **Key-aware seats** — `live` builds only seats whose provider key is set (not all three
  required), and `resolve_model` falls back to an available provider.

## 5. Honest caveats (carry into any feature work)

- **A council costs 2N+1 LLM calls vs 1.** It is strictly more expensive. `eval.py` reports
  the structural cost; the token *multiplier* it prints is indicative only (scales with answer
  length). Don't present it as cheap.
- **It only clearly wins on open-ended design.** Don't market it as a general accuracy boost.
- **Live is unverified end-to-end.** All tests/demos run offline with stubs. Real multi-model
  runs need provider keys; `make_chat`/`live_seats` are construction-verified only.

## 6. Verification status

- `python -m pytest` → **9 passed**, offline, no keys.
- `python -m council.demo` → answers grounded in 3 project docs (real local embeddings).
- `python -m council.eval` → cost structure prints; `live` adds blind-judge quality.

## 7. How to extend (common changes)

- **Add/change a seat:** edit `DEFAULT_SEAT_MODELS` and `ROLES` in `council/config.py`
  (paired by index). Model strings are `"provider:model"`.
- **Add a provider:** extend `PROVIDER_ENV` in `config.py`; `init_chat_model` handles the rest.
- **Change the doc corpus:** drop `.md`/`.txt` into `docs/` (or pass a dir to
  `rag.load_docs`). For larger corpora, swap `InMemoryVectorStore` for a persistent store in
  `rag.py` (keep the `retrieve(query, k) -> list[str]` contract — that's all the graph needs).
- **Swap RAG embeddings:** pass an embeddings object to `DocRAG(embeddings=...)`; default is
  local MiniLM (keyless, pulls torch).
- **Tune ranking:** Borda/self-inclusion live in `council.py` (`borda`, `anonymize`, `rank_node`).
- **Parallelize seats** (latency): `generate`/`rank` currently call seats sequentially —
  convert to async or LangGraph `Send` fan-out. Currently sequential for simplicity.

## 8. Known limitations / TODO

- Seats run sequentially (no parallel API calls yet).
- `quality` eval needs real keys; no offline quality signal (stubs are deterministic, not
  meaningful for quality).
- No persistence of runs (by design — the council doesn't remember; if you want a record,
  log outputs externally, do **not** feed them back into generators).
- `InMemoryVectorStore` re-embeds the corpus each process start; fine for small `docs/`.

## 9. Pointers

- `council-coilmem-decision.md` — why council and coilmem are separate.
- README — run/setup. Tests — `tests/test_council.py` mirror the intended behavior.
