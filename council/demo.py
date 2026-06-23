"""Council demo: answer related questions, each grounded in retrieved PROJECT DOCS.

Grounding comes from doc-RAG over ./docs (not the council's own prior output), so seats
stay independent and diverse. Offline (default): stub LLMs + real local embeddings. Live:
`python -m council.demo live` (needs provider keys in .env).
"""
import json
import os
import re
import sys

from .config import ROLES, chairman_model, load_env
from .council import Seat, build_council, live_seats, run_council
from .llm import BudgetExceeded, CostMeter, StubChat, make_chat
from .rag import DocRAG, load_docs

QUESTIONS = [
    "What overall architecture should we use for the voice-notes app?",
    "Which database and storage layout best fit our needs?",
    "What is the single biggest risk we should de-risk first?",
]


def _question_of(text):
    m = re.search(r"Question:\s*\n(.+)", text)
    return m.group(1).strip() if m else text[:60]


def _stub_responder(role):
    def r(messages):
        text = " ".join(str(m[1]) for m in messages)
        if '"order"' in text or "best-to-worst" in text:
            seen = []
            for lab in re.findall(r"A\d+", text):
                if lab not in seen:
                    seen.append(lab)
            return json.dumps({"order": seen})
        return f"As the {role}, on '{_question_of(text)}': grounded in the project docs, I'd choose pragmatically."
    return r


def _stub_seats():
    return [Seat(f"stub-{i}", role, StubChat(f"stub-{i}", _stub_responder(role)))
            for i, role in enumerate(ROLES[:3])]


def _stub_chairman():
    def r(messages):
        q = _question_of(" ".join(str(m[1]) for m in messages))
        return json.dumps({
            "answer": f"Recommended approach for '{q}': the pragmatic option grounded in the docs.",
            "consensus": "seats broadly agree, anchored to the project constraints",
            "dissent": "the red-teamer flags the real-time sync complexity",
            "confidence": "medium",
        })
    return StubChat("chair", r)


def main(live=False):
    load_env()
    rag = DocRAG().index(load_docs())  # real local embeddings; keyless

    chair_model = None
    if live:
        seats = live_seats()
        chair_model = chairman_model()
        chairman = make_chat(chair_model)
    else:
        seats = _stub_seats()
        chairman = _stub_chairman()

    budget = os.environ.get("COUNCIL_BUDGET_USD")  # $ cap across this session; unset = no cap
    budget_usd = float(budget) if budget else None

    print(f"=== Council ({'LIVE' if live else 'OFFLINE stub LLMs + local embeddings'}), "
          f"grounded in {len(load_docs())} project docs"
          + (f", budget ${budget_usd:.2f} ===" if budget_usd is not None else " ===") + "\n")
    cost = CostMeter(budget_usd=budget_usd)
    try:
        for i, q in enumerate(QUESTIONS, 1):
            graph = build_council(seats, chairman, retrieve=rag.retrieve, cost=cost,
                                  chairman_model=chair_model)
            out = run_council(graph, q)
            print(f"--- Q{i}: {q}")
            print(f"  retrieved {len(out.get('recalled', []))} doc chunk(s) for grounding")
            final = out["final"]
            print(f"  ANSWER:    {final['answer']}")
            print(f"  DISSENT:   {final['dissent']}")
            print(f"  CONFIDENCE:{final['confidence']}\n")
    except BudgetExceeded as e:
        print(f"\n!! ABORTED: {e} (no final answer for the in-flight question)\n")
    usd = f", ${cost.cost_usd():.4f}" if budget_usd is not None else ""
    print(f"=== cost: {cost.total_calls()} calls, {cost.total_tokens()} tokens{usd} ===")


if __name__ == "__main__":
    main(live=(len(sys.argv) > 1 and sys.argv[1] == "live"))
