# LLM Council — Architecture Understanding

My understanding of the ensemble ("council of LLMs") sketched in the video, before any implementation. Source: `transcript.txt` (Karpathy-inspired council), cross-checked against `gpt5.5_summary.txt`.

## One-line idea

Instead of trusting one model's answer, convene several different models on the **same** question, have them anonymously rank each other, then have a final "chairman" model write one synthesized answer. Inspired by ML ensembles (many weak learners > one strong learner).

## The three stages

| Stage | What happens | Key property |
|---|---|---|
| **1. Independent answering** | Every council model answers the same question in parallel, each in an assigned **role**. | Models don't see each other yet — independent perspectives. |
| **2. Blind peer ranking** | Each model is shown all answers (its own included), **anonymized**, and ranks them. | Anonymization stops models favoring their own provider/family. |
| **3. Chairman synthesis** | One designated model takes all answers + rankings and writes the single final answer. | Surfaces consensus *and* dissent; assigns a confidence (low/med/high). |

## The four modifications the video adds to the vanilla council

The plain Karpathi version is just "ask many, eyeball results." This version changes:

1. **Real leaderboard** — tally the stage-2 rankings into actual scores, not vibes.
2. **Roles per seat** — each model gets a distinct persona (skeptic, domain expert, contrarian, journalist / "first-principles journalist", rigorous reasoner, red-teamer). Goal: force *diverse* answers, not six near-identical ones.
3. **Chairman preserves disagreement** — surface common ground *and* dissent rather than averaging everything into mush.
4. **Measure it** — actually benchmark whether the council beats single models.

## Council composition (as shown)

- ~6 models from ~6 different labs, all called at once.
- Each call routed through **Vercel AI Gateway**: one API key, OpenAI-compatible, "one string = one model" so you swap models by changing a string. Gives failover/retry on rate limits + a shared usage/latency/cost dashboard. Listed as no-markup (gateway effectively free).
- Example roles named: GPT 5.5 = first-principles journalist; another = rigorous reasoner; another = red-teamer/skeptic; plus contrarian, domain expert. Chairman in the demo = Opus 4.8.

## Data flow

```
User question
    │
    ▼
[Stage 1] fan out in parallel → model A (role 1)
                                model B (role 2)
                                ...        each returns its own answer
    │
    ▼
[Stage 2] anonymize + shuffle all answers
          → each model ranks all answers
          → tally rankings into leaderboard
    │
    ▼
[Stage 3] chairman gets: winner + all answers + rankings
          → final answer
          → consensus / dissent
          → confidence (low / med / high)
```

## How it was evaluated

- Council final answer vs. **each individual model answering alone**.
- Judged by an **independent model not in the council**, ranking blindly.
- Responses anonymized, shuffled, format-controlled; factual questions graded against a known answer.
- Strict bar: council "wins" only if it beats **every** single model.

## Results (the surprising part)

| Question type | Council outcome |
|---|---|
| Factual / checkable | No advantage — strong models already got it right |
| Trade-off questions | Lost |
| Risk questions | Lost |
| Open-ended design | **Won** |

- Won roughly **1 of 3** question categories.
- **Plain final answer beat the verbose full write-up every time** — the meta-output (rankings, dissent, commentary) hurt scores.

## When it's worth it

- **Use:** high stakes, no single right answer, research/strategy/genuine trade-off, when you'd want a second opinion.
- **Skip:** simple lookup, latency-sensitive, cost-sensitive, or there's a checkable right answer.
- Framing: *"It's a judgment call, not a calculator."* Used as a calculator = paying cost for no gain.

## Open questions for implementation (not decided here)

- Exact ranking → leaderboard scoring (Borda? average rank? points?).
- Whether models rank their own answer or it's excluded.
- Output format toggle (plain answer vs. full write-up) — evidence says default to plain.
- Which model is chairman, and whether it's in the answering pool.
- How roles are assigned to models (fixed mapping vs. per-question).
