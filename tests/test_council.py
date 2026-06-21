"""Tests for the council (offline — StubChat + fake embeddings; no network/keys).
Run: python -m pytest
"""
import hashlib
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from council import eval as cev
from council import llm
from council.council import Seat, anonymize, borda, build_council, parse_order, run_council
from council.rag import DocRAG


class FakeEmbeddings:
    """Deterministic bag-of-words embeddings for offline RAG tests (no torch)."""
    dim = 64

    def _vec(self, text):
        v = [0.0] * self.dim
        for tok in text.lower().split():
            tok = "".join(c for c in tok if c.isalnum())
            if tok:
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        return v

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


# --- provider + token accounting ----------------------------------------------

def test_call_counts_real_tokens_for_stub():
    chat = llm.StubChat("seat1", responder=lambda msgs: "a deterministic answer")
    text, usage = llm.call(chat, [("system", "you are a seat"), ("human", "the question")])
    assert text == "a deterministic answer"
    assert usage.input_tokens > 0 and usage.output_tokens > 0


def test_costmeter_aggregates():
    cm = llm.CostMeter()
    cm.record("generate", "skeptic", llm.Usage(100, 20))
    cm.record("chairman", "chairman", llm.Usage(300, 50))
    assert cm.total_calls() == 2
    assert cm.total_tokens() == 470


# --- council helpers ----------------------------------------------------------

def test_borda_tally():
    labels = ["A1", "A2", "A3"]
    assert borda([["A1", "A2", "A3"], ["A1", "A3", "A2"]], labels) == {"A1": 4, "A2": 1, "A3": 1}


def test_anonymize_deterministic_and_bijective():
    labels1, m1 = anonymize(4, seed=0)
    _, m2 = anonymize(4, seed=0)
    assert labels1 == ["A1", "A2", "A3", "A4"]
    assert m1 == m2
    assert sorted(m1.values()) == [0, 1, 2, 3]


def test_parse_order_tolerant():
    labels = ["A1", "A2", "A3"]
    assert parse_order('{"order":["A3","A1","A2"]}', labels) == ["A3", "A1", "A2"]
    assert parse_order('{"order":["A2"]}', labels) == ["A2", "A1", "A3"]
    assert parse_order("I rank A3 then A1 then A2", labels) == ["A3", "A1", "A2"]


# --- full council run (ungrounded; retrieve=None) -----------------------------

def _seat_responder(answer_text):
    def r(messages):
        text = " ".join(str(m[1]) for m in messages)
        if '"order"' in text or "best-to-worst" in text:
            seen = []
            for lab in re.findall(r"A\d+", text):
                if lab not in seen:
                    seen.append(lab)
            return json.dumps({"order": seen})
        return answer_text
    return r


def _chairman_responder(messages):
    return json.dumps({"answer": "FINAL synthesized recommendation", "consensus": "agree",
                       "dissent": "the red-teamer flags a risk", "confidence": "medium"})


def test_full_council_run_offline():
    seats = [
        Seat("s1", "skeptic", llm.StubChat("s1", _seat_responder("microservices answer"))),
        Seat("s2", "domain expert", llm.StubChat("s2", _seat_responder("monolith answer"))),
        Seat("s3", "contrarian", llm.StubChat("s3", _seat_responder("serverless answer"))),
    ]
    chair = llm.StubChat("chair", _chairman_responder)
    cost = llm.CostMeter()
    graph = build_council(seats, chair, retrieve=None, cost=cost)
    out = run_council(graph, "What architecture should we choose?")
    assert out["final"]["answer"] == "FINAL synthesized recommendation"
    assert len(out["leaderboard"]) == 3
    bordas = [e["borda"] for e in out["leaderboard"]]
    assert bordas == sorted(bordas, reverse=True)
    assert cost.total_calls() == 3 + 3 + 1  # generate + rank + chairman (no remember)


def test_council_grounds_in_retrieved_docs():
    captured = {}

    def retrieve(question, k):
        captured["q"] = question
        return ["doc: the database is Postgres", "doc: storage is S3"]

    seats = [Seat("s1", "skeptic", llm.StubChat("s1", _seat_responder("ans")))]
    chair = llm.StubChat("chair", _chairman_responder)
    graph = build_council(seats, chair, retrieve=retrieve)
    out = run_council(graph, "what database?")
    assert captured["q"] == "what database?"
    assert "Postgres" in out["recalled_block"]


# --- doc-RAG ------------------------------------------------------------------

def test_docrag_retrieves_relevant():
    rag = DocRAG(embeddings=FakeEmbeddings())
    rag.index([
        "postgres is our primary database",
        "kubernetes autoscaling configuration",
        "office coffee machine schedule",
    ])
    hits = rag.retrieve("what database do we use", k=2)
    assert any("postgres" in h.lower() for h in hits)


# --- cost structure (eval) ----------------------------------------------------

def test_cost_structure_multiplier_gt_one():
    c = cev.cost_structure(n_seats=6)
    assert c["council_calls"] == 6 + 6 + 1
    assert c["multiplier"] > 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
