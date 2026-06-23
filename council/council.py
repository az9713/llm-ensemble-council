"""LLM Council on LangGraph: retrieve -> generate -> rank -> chairman.

Stage 1 (generate) is deliberately independent: seats never see each other's current
answers; they only see relevant *project documents* retrieved via doc-RAG (NOT the
council's own prior output — that would anchor away the diversity a council needs).
Stage 2 ranks anonymized answers (blind) and tallies with Borda count. Stage 3 the
chairman synthesizes.

Grounding is an injected `retrieve(question, k) -> list[str]` callable (see rag.py);
pass None for an ungrounded council. Token accounting flows through a shared CostMeter.
Seats/chairman are injected, so tests pass StubChat and live runs pass real models.
"""
import json
import random
import re
from dataclasses import dataclass
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from .llm import CostMeter, call


@dataclass
class Seat:
    name: str
    role: str
    chat: object  # has .invoke(messages)


class State(TypedDict, total=False):
    question: str
    recalled: list
    recalled_block: str
    answers: list
    rankings: list
    labels: list
    leaderboard: list
    final: dict


# --- prompts (structured artifacts, per council-architecture.md) ---------------

GEN_SYS = "You are the {role} in a multi-model council. Do not mention other agents. Do not hedge generically."
GEN_USER = """Question:
{q}

{ctx}

Produce:
1. Your direct answer
2. Key assumptions
3. Strongest argument for your position
4. Strongest argument against your position
5. Failure modes
6. What evidence would change your mind"""

RANK_SYS = "You are judging anonymized answers to the same question. Rank them by correctness, specificity, awareness of constraints, handling of trade-offs, actionability, and failure-mode awareness."
RANK_USER = """Question:
{q}

Answers:
{answers}

Return ONLY a JSON object: {{"order": [labels best-to-worst]}}, e.g. {{"order": ["A2","A1","A3"]}}."""

CHAIR_SYS = "You are the chairman synthesizer. Preserve genuine dissent; do not average away minority warnings. Be concise."
CHAIR_USER = """Question:
{q}

Candidate answers (with peer Borda scores):
{candidates}

Return ONLY a JSON object:
{{"answer": "...", "consensus": "...", "dissent": "...", "confidence": "low|medium|high"}}"""


# --- helpers (pure, unit-tested) ----------------------------------------------

def anonymize(n: int, seed: int = 0):
    """Return (labels, label_to_index). labels A1..An map to a seeded shuffle of
    answer indices, so judges can't tell who wrote what or rely on position."""
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    labels = [f"A{i + 1}" for i in range(n)]
    return labels, {labels[i]: idx[i] for i in range(n)}


def borda(orders, labels) -> dict:
    """Borda count: in a best-to-worst order of n labels, position p scores n-1-p."""
    n = len(labels)
    score = {lab: 0 for lab in labels}
    for order in orders:
        for p, lab in enumerate(order):
            if lab in score:
                score[lab] += (n - 1 - p)
    return score


def _extract_json(text: str):
    """Best-effort: parse the first JSON object/array in model output."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"(\{.*\}|\[.*\])", text or "", re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            return None
    return None


def parse_order(text: str, labels) -> list:
    """Extract a best-to-worst label order, tolerant of messy model output.
    Missing labels are appended in original order so every label is ranked."""
    data = _extract_json(text)
    order = []
    if isinstance(data, dict) and isinstance(data.get("order"), list):
        order = [str(x) for x in data["order"]]
    elif isinstance(data, list):
        order = [str(x) for x in data]
    else:  # fallback: first occurrence of each label token in the text
        seen = []
        for tok in re.findall(r"A\d+", text or ""):
            if tok not in seen:
                seen.append(tok)
        order = seen
    order = [lab for lab in order if lab in labels]
    for lab in labels:  # append any the model dropped
        if lab not in order:
            order.append(lab)
    return order


def parse_final(text: str) -> dict:
    data = _extract_json(text)
    if isinstance(data, dict) and "answer" in data:
        return {
            "answer": str(data.get("answer", "")).strip(),
            "consensus": str(data.get("consensus", "")).strip(),
            "dissent": str(data.get("dissent", "")).strip(),
            "confidence": str(data.get("confidence", "unknown")).strip().lower(),
        }
    return {"answer": (text or "").strip(), "consensus": "", "dissent": "", "confidence": "unknown"}


# --- graph builder ------------------------------------------------------------

def build_council(
    seats: list,
    chairman_chat,
    retrieve: Optional[Callable] = None,
    k: int = 4,
    seed: int = 0,
    cost: Optional[CostMeter] = None,
    chairman_model: Optional[str] = None,  # model string, for $ pricing of the chairman call
):
    cost = cost if cost is not None else CostMeter()

    def retrieve_node(state: State):  # stage 0: ground seats in project documents
        docs = retrieve(state["question"], k) if retrieve is not None else []
        block = ("## Relevant project documents\n" + "\n".join(f"- {d}" for d in docs)) if docs else ""
        return {"recalled": docs, "recalled_block": block}

    def generate_node(state: State):  # stage 1: independent answers
        q, ctx = state["question"], state.get("recalled_block", "")
        answers = []
        for seat in seats:
            msgs = [("system", GEN_SYS.format(role=seat.role)), ("human", GEN_USER.format(q=q, ctx=ctx))]
            text, usage = call(seat.chat, msgs)
            cost.record("generate", seat.role, usage, model=seat.name)
            answers.append({"seat": seat.name, "role": seat.role, "text": text})
        return {"answers": answers}

    def rank_node(state: State):  # stage 2: blind peer ranking + Borda tally
        answers, q = state["answers"], state["question"]
        labels, label2idx = anonymize(len(answers), seed)
        block = "\n\n".join(f"{lab}:\n{answers[label2idx[lab]]['text']}" for lab in labels)
        orders = []
        for seat in seats:  # each seat is also a judge
            msgs = [("system", RANK_SYS), ("human", RANK_USER.format(q=q, answers=block))]
            text, usage = call(seat.chat, msgs)
            cost.record("rank", seat.role, usage, model=seat.name)
            orders.append(parse_order(text, labels))
        scores = borda(orders, labels)
        leaderboard = [
            {
                "seat": answers[label2idx[lab]]["seat"],
                "role": answers[label2idx[lab]]["role"],
                "label": lab,
                "borda": scores[lab],
                "text": answers[label2idx[lab]]["text"],
            }
            for lab in labels
        ]
        leaderboard.sort(key=lambda x: x["borda"], reverse=True)
        return {"labels": labels, "rankings": orders, "leaderboard": leaderboard}

    def chairman_node(state: State):  # stage 3: synthesis
        q, lb = state["question"], state["leaderboard"]
        candidates = "\n\n".join(f"[Borda {e['borda']}] {e['text']}" for e in lb)
        msgs = [("system", CHAIR_SYS), ("human", CHAIR_USER.format(q=q, candidates=candidates))]
        text, usage = call(chairman_chat, msgs)
        cost.record("chairman", "chairman", usage, model=chairman_model)
        return {"final": parse_final(text)}

    g = StateGraph(State)
    g.add_node("retrieve", retrieve_node)
    g.add_node("generate", generate_node)
    g.add_node("rank", rank_node)
    g.add_node("chairman", chairman_node)
    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "rank")
    g.add_edge("rank", "chairman")
    g.add_edge("chairman", END)
    compiled = g.compile()
    compiled.cost = cost  # expose meter for the eval
    return compiled


def run_council(graph, question: str) -> dict:
    return graph.invoke({"question": question})


def live_seats(specs=None) -> list:
    """Build real provider-backed seats. Defaults to only seats whose provider key
    is set, so `live` runs with whatever keys you have (not all three required)."""
    from .config import available_seat_specs
    from .llm import make_chat

    if specs is None:
        specs = available_seat_specs()
    if not specs:
        raise RuntimeError(
            "no provider keys set — add OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY to .env"
        )
    return [Seat(model, role, make_chat(model)) for model, role in specs]
