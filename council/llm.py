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

_ENC = None


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
    'anthropic:claude-opus-4-8', 'google_genai:gemini-2.0-flash'."""
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

    def record(self, stage: str, role: str, usage: Usage, calls: int = 1):
        self.rows.append((stage, role, usage.input_tokens, usage.output_tokens, calls))

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
