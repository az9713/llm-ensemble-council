# llm-ensemble-council

A multi-model **LLM Council** on LangGraph: fan a question out to several models in distinct
roles → blind anonymized peer-ranking (Borda) → a chairman synthesizes one answer with
consensus / dissent / confidence. Grounded in **project documents** via doc-RAG.

Independent codebase (no coilmem, no shared package). Design context:
[`council-coilmem-decision.md`](council-coilmem-decision.md). Source sketch: an
ensemble-of-LLMs ("council") — wins over the best single model mainly on open-ended design;
*"a judgment call, not a calculator."*

**Does it actually work?** That question — the subject of the video
[*Does LLM Council/Fusion Actually Work?*](https://www.youtube.com/watch?v=oalFPYvsx9Y&t=123s) —
is tested here, not assumed. A live blind-judge evaluation with an honest critique of its
confounds is in [`EVAL_REPORT.md`](EVAL_REPORT.md); the architecture walkthrough is in
[`HOW_IT_WORKS.md`](HOW_IT_WORKS.md).

## Pipeline

![LLM Council communication flow: a question is grounded via doc-RAG, fanned out to six independent role seats (3 labs × 2 models), peer-ranked blind by Borda, then synthesized by a chairman into a final answer with dissent; the blind judge sits outside the flow (eval only).](architecture.png)

```
retrieve ─→ generate ─→ rank ─→ chairman
(doc-RAG)   (parallel    (blind,  (synthesis:
            role seats)  Borda)    answer + dissent + confidence)
```

Stage 1 stays **independent** — seats see only retrieved *project docs* (`./docs`), never each
other's answers or the council's own prior output (which would anchor away diversity).

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; or .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set at least one provider key for live runs
```

## Run

Offline (no API key — stub LLMs + real local embeddings):
```bash
python -m pytest              # full suite
python -m council.demo        # answers grounded in ./docs
python -m council.eval        # cost-structure metric
```

Live (real multi-model council; needs provider keys in .env):
```bash
python -m council.demo live
python -m council.eval live   # adds the blind-judge quality eval
```

Seats live in `council/config.py` (`DEFAULT_SEAT_MODELS` × `ROLES`); seat selection is
key-aware (`available_seat_specs`), so `live` runs with whatever providers you have.

## Honest notes

- A council costs **2N+1 LLM calls** vs 1 for a single model — it is *more* expensive
  (`eval.py` prints the structure). Use it for high-stakes judgment calls, not lookups.
- Grounding is over **source documents**, not the council's own conclusions — consistency
  without anchoring.

## Files

`council/council.py` (graph + Borda + parsing), `council/rag.py` (doc-RAG via LangChain
`InMemoryVectorStore`), `council/llm.py` (providers + token accounting + StubChat),
`council/config.py` (seats/roles + `.env`), `council/demo.py`, `council/eval.py`.
Docs corpus: `docs/`. Tests: `tests/test_council.py`.
