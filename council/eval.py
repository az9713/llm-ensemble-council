"""Evaluation harness for the council. Two honest measurements:

  1. cost_structure — a council does 2N+1 LLM calls vs 1 for a single model. The honest
     cost of a second opinion (a council is MORE expensive). Keyless (stub + tiktoken).
  2. quality        — a blind independent judge (not a seat) ranks the council answer vs
     each single model alone; council "wins" only if it beats EVERY single model. Needs keys.

Run: `python -m council.eval`        (cost structure, offline, no keys)
     `python -m council.eval live`   (also runs quality with real models)
"""
import json
import os
import re
import sys

from .config import chairman_model, judge_model, load_env
from .council import Seat, anonymize, build_council, live_seats, parse_order, run_council
from .llm import BudgetExceeded, CostMeter, StubChat, call, make_chat
from .rag import DocRAG, load_docs


# --- 1. cost structure --------------------------------------------------------

def _stub_seat_responder(text):
    def r(messages):
        joined = " ".join(str(m[1]) for m in messages)
        if '"order"' in joined or "best-to-worst" in joined:
            seen = []
            for lab in re.findall(r"A\d+", joined):
                if lab not in seen:
                    seen.append(lab)
            return json.dumps({"order": seen})
        return text
    return r


def cost_structure(question="Design a retention feature for a meditation app.", n_seats=6):
    seats = [Seat(f"s{i}", f"role{i}", StubChat(f"s{i}", _stub_seat_responder(f"answer {i} " * 20)))
             for i in range(n_seats)]
    chair = StubChat("chair", lambda m: json.dumps(
        {"answer": "synthesized " * 30, "consensus": "", "dissent": "", "confidence": "medium"}))
    cost = CostMeter()
    graph = build_council(seats, chair, retrieve=None, cost=cost)
    run_council(graph, question)
    _, single = call(seats[0].chat, [("system", "answer the question"), ("human", question)])
    council_tokens = cost.total_tokens()
    mult = council_tokens / single.total if single.total else float("inf")
    return {"council_tokens": council_tokens, "council_calls": cost.total_calls(),
            "single_tokens": single.total, "multiplier": mult, "by_stage": cost.by_stage()}


def print_cost_structure(c):
    print("\n=== 1. Cost structure: council vs single model (honest — a council costs MORE) ===")
    print(f"  structural cost:  {c['council_calls']} LLM calls vs 1  (2N+1 — the robust claim)")
    print(f"  single model:     {c['single_tokens']} tokens, 1 call")
    print(f"  council:          {c['council_tokens']} tokens, {c['council_calls']} calls")
    print(f"  token multiplier: ~{c['multiplier']:.0f}x  (indicative only — scales with answer length)")
    print(f"  by stage:         {c['by_stage']}")


# --- 2. quality (live) --------------------------------------------------------

QUESTION_SET = [
    {"q": "What is the boiling point of water at sea level, in Celsius?", "cat": "factual", "answer": "100"},
    {"q": "Should a seed-stage startup prioritize growth or profitability?", "cat": "trade-off"},
    {"q": "What are the main risks of giving an LLM agent write access to production systems?", "cat": "risk"},
    {"q": "Design a community feature for a meditation app that increases 30-day retention.", "cat": "open-ended design"},
]

JUDGE_SYS = "You are an impartial judge. Rank anonymized answers best-to-worst by correctness, specificity, and usefulness."
JUDGE_USER = """Question:
{q}

Answers:
{answers}

Return ONLY JSON: {{"order": [labels best-to-worst]}}."""


def quality(seats, chairman, judge, retrieve=None, cost=None, chair_model=None, judge_name=None):
    """Blind-judge council vs each single model. Council 'wins' iff it beats every single.
    All calls (council + solo + judge) flow through `cost` so a budget cap covers the eval."""
    cost = cost if cost is not None else CostMeter()
    results = []
    for item in QUESTION_SET:
        q = item["q"]
        graph = build_council(seats, chairman, retrieve=retrieve, cost=cost, chairman_model=chair_model)
        council_answer = run_council(graph, q)["final"]["answer"]
        candidates = [("council", council_answer)]
        for s in seats:
            text, usage = call(s.chat, [("system", f"You are a {s.role}."), ("human", q)])
            cost.record("single", s.role, usage, model=s.name)
            candidates.append((s.name, text))
        labels, label2idx = anonymize(len(candidates), seed=0)
        block = "\n\n".join(f"{lab}:\n{candidates[label2idx[lab]][1]}" for lab in labels)
        order_text, usage = call(judge, [("system", JUDGE_SYS), ("human", JUDGE_USER.format(q=q, answers=block))])
        cost.record("judge", "judge", usage, model=judge_name)
        order = parse_order(order_text, labels)
        ranked = [candidates[label2idx[lab]][0] for lab in order]
        rank = ranked.index("council")
        results.append({"cat": item["cat"], "won": rank == 0, "council_rank": rank, "n": len(candidates)})
    return results


def print_quality(results):
    print("\n=== 2. Quality: council vs every single model (blind judge) ===")
    for r in results:
        print(f"  [{r['cat']:>18}] council ranked {r['council_rank'] + 1}/{r['n']} "
              f"-> {'WON' if r['won'] else 'lost'}")
    wins = sum(1 for r in results if r["won"])
    print(f"  council won {wins}/{len(results)} categories "
          "(source's finding: expect ~open-ended design only)")


def main(live=False):
    load_env()
    print_cost_structure(cost_structure())
    if live:
        seats = live_seats()
        chair_model = chairman_model()
        chairman = make_chat(chair_model)
        judge_name = judge_model()
        judge = make_chat(judge_name)
        rag = DocRAG().index(load_docs())
        budget = os.environ.get("COUNCIL_BUDGET_USD")  # same cap as a council run
        cost = CostMeter(budget_usd=float(budget) if budget else None)
        try:
            print_quality(quality(seats, chairman, judge, retrieve=rag.retrieve, cost=cost,
                                  chair_model=chair_model, judge_name=judge_name))
        except BudgetExceeded as e:
            print(f"\n!! Quality eval ABORTED: {e}")
        usd = f", ${cost.cost_usd():.4f}" if budget else ""
        print(f"\n  eval cost: {cost.total_calls()} calls, {cost.total_tokens()} tokens{usd}")
    else:
        print("\n=== 2. Quality ===\n  (skipped — needs provider keys; run `python -m council.eval live`)")


if __name__ == "__main__":
    main(live=(len(sys.argv) > 1 and sys.argv[1] == "live"))
