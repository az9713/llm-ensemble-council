"""Provider-agnostic chat + token accounting for the council.

- `make_chat("openai:gpt-4o")` builds a real LangChain chat model (lazy import).
- `call(chat, messages)` returns (text, Usage), preferring provider usage_metadata
  and falling back to a local tiktoken count (so offline/stub runs still measure
  real input tokens).
- `StubChat` is a deterministic test double: it reports no usage_metadata, so call()
  counts the real assembled-prompt tokens with tiktoken — meaningful measurement
  without any API key.
- `CostMeter` accumulates tokens + call counts per stage for the eval.
"""
from dataclasses import dataclass, field
from typing import Optional

_ENC = None

# USD per 1M tokens (input, output). This is the calibration knob the $ budget rides on —
# VERIFY against current provider pricing before trusting the cap. June 2026 list prices.
PRICES = {
    "openai:gpt-4o": (2.50, 10.00),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "anthropic:claude-sonnet-4-6": (3.00, 15.00),
    "anthropic:claude-haiku-4-5-20251001": (1.00, 5.00),
    "google_genai:gemini-3.5-flash": (1.50, 9.00),
    "google_genai:gemini-3.1-flash-lite": (0.25, 1.50),
}
# Unknown model → priced high so the cap fails SAFE (trips early), never silently free.
DEFAULT_PRICE = (15.00, 75.00)


class BudgetExceeded(RuntimeError):
    """Raised mid-run when accumulated spend crosses the CostMeter's budget cap."""

    def __init__(self, spent: float, budget: float):
        self.spent, self.budget = spent, budget
        super().__init__(f"council run hit budget cap: spent ${spent:.4f} > ${budget:.2f}")


def _enc():
    global _ENC
    if _ENC is None:
        import tiktoken

        _ENC = tiktoken.get_encoding("o200k_base")
    return _ENC


def count_tokens(text: str) -> int:
    return len(_enc().encode(text or ""))


def make_chat(model_str: str, **kwargs):
    """Real chat model via LangChain. model_str like 'openai:gpt-4o',
    'anthropic:claude-sonnet-4-6', 'google_genai:gemini-3.5-flash'."""
    from langchain.chat_models import init_chat_model  # lazy: keeps tests light

    return init_chat_model(model_str, **kwargs)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


def _messages_text(messages) -> str:
    parts = []
    for m in messages:
        if isinstance(m, (tuple, list)) and len(m) == 2:
            parts.append(str(m[1]))
        else:
            parts.append(str(getattr(m, "content", m)))
    return "\n".join(parts)


def call(chat, messages):
    """Invoke a chat model with messages [(role, content), ...]. Returns (text, Usage)."""
    resp = chat.invoke(messages)
    text = getattr(resp, "content", str(resp))
    if isinstance(text, list):  # Anthropic/Gemini return content blocks, not a str
        text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
    um = getattr(resp, "usage_metadata", None)
    if um:
        return text, Usage(int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0)))
    # fallback: count real tokens locally (used by StubChat and providers w/o usage)
    return text, Usage(count_tokens(_messages_text(messages)), count_tokens(text))


class _StubResponse:
    def __init__(self, content):
        self.content = content
        self.usage_metadata = None  # forces call() to tiktoken-count the real prompt


class StubChat:
    """Deterministic offline test double. `responder(messages) -> str`."""

    def __init__(self, name, responder=None):
        self.name = name
        self._responder = responder or (lambda msgs: f"[{name}] {_messages_text(msgs)[:120]}")

    def invoke(self, messages):
        return _StubResponse(self._responder(messages))


@dataclass
class CostMeter:
    rows: list = field(default_factory=list)  # (stage, role, in_tok, out_tok, calls)
    budget_usd: Optional[float] = None        # None = no cap (offline/tests)
    prices: dict = field(default_factory=lambda: dict(PRICES))
    default_price: tuple = DEFAULT_PRICE
    usd: float = 0.0                          # running spend; priced when model is known

    def record(self, stage: str, role: str, usage: Usage, model: Optional[str] = None, calls: int = 1):
        self.rows.append((stage, role, usage.input_tokens, usage.output_tokens, calls))
        if model is not None:
            in_rate, out_rate = self.prices.get(model, self.default_price)
            self.usd += in_rate * usage.input_tokens / 1e6 + out_rate * usage.output_tokens / 1e6
        # ponytail: post-call abort — overshoot bounded to one call's cost. Strict bound =
        # max_tokens per call. At $5 vs a ~$0.20 run this is a runaway circuit breaker.
        if self.budget_usd is not None and self.usd > self.budget_usd:
            raise BudgetExceeded(self.usd, self.budget_usd)

    def cost_usd(self) -> float:
        return self.usd

    def total_tokens(self) -> int:
        return sum(i + o for _, _, i, o, _ in self.rows)

    def total_input_tokens(self) -> int:
        return sum(i for _, _, i, _, _ in self.rows)

    def total_calls(self) -> int:
        return sum(c for *_, c in self.rows)

    def by_stage(self) -> dict:
        agg = {}
        for stage, _role, i, o, c in self.rows:
            a = agg.setdefault(stage, [0, 0, 0])
            a[0] += i
            a[1] += o
            a[2] += c
        return {k: {"input": v[0], "output": v[1], "calls": v[2]} for k, v in agg.items()}
