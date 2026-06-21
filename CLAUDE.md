# Project: llm-council

A multi-model **LLM Council** on LangGraph (retrieve → generate → rank(Borda) → chairman),
grounded in project docs via doc-RAG. Independent codebase — **no coilmem, no shared package**.

## Orientation (read these before non-trivial changes)
- `DEVELOPMENT.md` — architecture, decisions + rationale, extension guide, known limits.
- `DEVELOPMENT_JOURNEY.md` — how this came to be (the full cross-project history).
- `council-coilmem-decision.md` — why the council is its own repo (no coilmem).
- `reference/council-architecture.md` — the original council design rationale (3 stages, the
  4 modifications, when to use). Source-of-intent for the council itself.
- `README.md` — setup + run.

## Invariants — do not break without explicit intent
- **Stage 1 (generate) is independent.** Seats never see each other's current answers — that
  decorrelation is the point. Don't add cross-seat visibility in `generate`.
- **Grounding = project documents, NOT the council's own prior output.** Feeding back prior
  consensus anchors the seats and erodes diversity. (`rag.py` reads `docs/`; the `docs/` dir is
  the RAG corpus — keep non-corpus files like design docs in `reference/`.)
- **Ranking is blind + anonymized** (seeded shuffle, Borda); the `quality` eval's judge is
  **not** a seat.
- Seats/chairman/retrieve are **injected** — keep it that way so tests run offline.

## Workflow
- Run offline tests before and after changes: `python -m pytest` (no API keys; StubChat + fake
  embeddings). Tests encode intended behavior — change them deliberately.
- Live runs need provider keys in `.env`; they are construction-verified only (no keys were
  available during initial development).
- A council costs 2N+1 LLM calls vs 1 — more expensive by design. Don't present it as cheap.
