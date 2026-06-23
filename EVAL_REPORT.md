# Council Evaluation Report

**Date:** 2026-06-22
**Harness:** `python -m council.eval live`
**Budget:** $5.00 cap (not tripped)

This report records a live run of the council's evaluation harness and a critique of what
the numbers do — and do **not** — establish. It is deliberately not a flattering writeup;
the eval was built to test the council honestly, and this run did not favor it.

---

## 1. What the harness measures

The harness reports two independent things:

1. **Cost structure** (offline, keyless) — how many calls/tokens a council spends vs a single
   model. A council does **2N+1** LLM calls (N generate + N rank + 1 chairman) against 1 for a
   solo model. This is the *honest cost of a second opinion*: a council is strictly more expensive.
2. **Quality** (live) — a blind, independent **judge** (not a seat) ranks the council's final
   answer against each single model answering the same question alone. The council "wins" a
   category **only if it beats every single model** (rank 1 of N+1).

---

## 2. Run configuration

| Component | Value |
|---|---|
| Seats | 6 — `gpt-4o`, `claude-sonnet-4-6`, `gemini-3.5-flash`, `gpt-4o-mini`, `claude-haiku-4-5-20251001`, `gemini-3.1-flash-lite` |
| Chairman | `claude-sonnet-4-6` (synthesizer, not a seat) |
| Judge | `gpt-4o` (blind evaluator, not a seat) |
| Grounding | doc-RAG over the voice-notes-app corpus (`docs/`) — **applied to the council only** |
| Questions | 4 — factual, trade-off, risk, open-ended design |
| Candidates per question | 7 (1 council + 6 solo) |

---

## 3. Cost structure (offline, indicative)

| Metric | Single model | Council |
|---|---|---|
| Calls | 1 | 13 (2×6 + 1) |
| Tokens (stub) | 74 | 4,315 |

Token multiplier ≈ **58×** in this stub run (scales with answer length; the robust, run-independent
claim is the **13-calls-vs-1** structural cost, not the token ratio).

---

## 4. Quality result

> **The council won 0 of 4 categories.**

| Category | Council rank (of 7) | Outcome |
|---|---|---|
| factual | 3 | lost |
| trade-off | 6 | lost |
| risk | 3 | lost |
| open-ended design | 5 | lost |

The harness's own baseline expectation, lifted from the source project, is "expect the council to
win **~open-ended design only**." This run cleared even that bar downward — the council placed 5th
of 7 on the one category where it was most expected to win.

**Live cost of the quality run:** 80 calls, 223,983 tokens, **$0.7768** of the $5 cap.

---

## 5. Critique — why this is not a clean test of the council's value

The 0/4 is a real result, not a bug. But three confounds bias the comparison **against** the
council, so this run understates its value rather than fairly measuring it.

### 5.1 Grounding mismatch (the major confound)
The eval questions are generic (boiling point, startup growth, LLM-agent risks, meditation-app
retention), but the council seats were fed **doc-RAG retrieval from the voice-notes-app corpus** —
context irrelevant to every one of those questions. The solo models received the clean question with
no retrieval. So the council answered *carrying off-topic context the solos never saw*. Irrelevant
grounding can only dilute or distract; this handicaps the council on questions the corpus doesn't
cover. A fair test requires either (a) eval questions drawn from the same corpus, or (b) grounding
turned **off** for the council during the eval so both sides answer from the question alone.

### 5.2 Concise synthesis vs full essays
The chairman is prompted to *"be concise,"* and only its `answer` field is judged — the
`consensus`, `dissent`, and `confidence` it produces are discarded before judging. The solo models
return full-length answers. Since the judge rewards "specificity and usefulness," a deliberately
terse synthesis competes against six verbose essays under a rubric that favors length and detail.
The council's distinctive output (preserved dissent, explicit confidence) is invisible to the judge.

### 5.3 Statistical power
One run, four questions, a single fixed anonymization seed, one judge model. With 7 candidates per
question, rank is noisy. No error bars, no repeated trials, no judge ensemble. A single 0/4 should
not be read as a stable estimate of anything.

---

## 6. What this run *did* establish (cleanly)

- **All 6 seats + chairman + judge ran live** without error — the full multi-provider pipeline works
  end to end (OpenAI, Anthropic, Google).
- **The budget cap now covers the eval.** All 80 calls — council, solo, and judge — flowed through
  `CostMeter`; total spend was reported ($0.7768) and bounded by the $5 cap.

---

## 7. Recommendations for a fair re-test

1. **Remove the grounding confound** — run the eval with retrieval off (cleanest), or replace the
   question set with questions the `docs/` corpus actually grounds.
2. **Judge the full synthesis** — feed the chairman's consensus/dissent/confidence to the judge,
   not just the terse `answer`, so the council's actual product is what's evaluated.
3. **Increase power** — multiple runs with different seeds, more questions per category, and ideally
   a judge ensemble (rotate or average across judge models) to reduce single-judge bias.
4. **Report per-category over repeated trials**, with win-rate and variance, rather than a single
   pass/fail.

---

## 8. Honest conclusion

In its current configuration, the eval does **not** demonstrate that the council beats single
models — it shows the opposite, 0/4. But the configuration is biased against the council (irrelevant
grounding, a length-favoring rubric applied to a terse synthesis, tiny sample). The correct reading
is **"not yet demonstrated, and not fairly tested,"** not "councils don't work." The value of a
council — decorrelated answers, blind peer ranking, preserved minority warnings — is a real
mechanism; this harness, as run, doesn't isolate and measure it. Fixing the confounds in §7 is the
prerequisite to any claim in either direction.
