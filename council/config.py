"""Council composition + .env loader. Edit seats freely — "one string = one model"."""
import os
from pathlib import Path


def load_env(path: str = ".env") -> None:
    """Minimal .env loader (no python-dotenv dep). Real env vars win (setdefault)."""
    p = Path(path)
    if not p.is_file():
        alt = Path(__file__).resolve().parent.parent / ".env"
        if not alt.is_file():
            return
        p = alt
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
    # langchain-google-genai authenticates via GOOGLE_API_KEY (else Google Cloud ADC); mirror
    # our GEMINI_API_KEY so the google_genai seats use the same key the config already checks.
    gem = os.environ.get("GEMINI_API_KEY")
    if gem and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gem


ROLES = [
    "skeptic",
    "domain expert",
    "contrarian",
    "first-principles journalist",
    "rigorous reasoner",
    "red-teamer",
]

# 6 seats across providers (different labs = the point of a council). Edit as needed.
DEFAULT_SEAT_MODELS = [
    "openai:gpt-4o",
    "anthropic:claude-sonnet-4-6",
    "google_genai:gemini-3.5-flash",
    "openai:gpt-4o-mini",
    "anthropic:claude-haiku-4-5-20251001",
    "google_genai:gemini-3.1-flash-lite",
]


PROVIDER_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google_genai": "GEMINI_API_KEY",
}


def _has_key(model_str: str) -> bool:
    provider = model_str.split(":", 1)[0]
    return bool(os.environ.get(PROVIDER_ENV.get(provider, "")))


def available_seat_specs():
    """Only seats whose provider key is actually set — so `live` runs with whatever
    keys you have, instead of crashing because one of three is missing."""
    return [(m, r) for m, r in zip(DEFAULT_SEAT_MODELS, ROLES) if _has_key(m)]


def resolve_model(preferred: str) -> str:
    """Use `preferred` if its key is set, else fall back to an available provider."""
    if _has_key(preferred):
        return preferred
    specs = available_seat_specs()
    return specs[0][0] if specs else preferred


def chairman_model() -> str:
    return resolve_model(os.environ.get("COUNCIL_CHAIRMAN", "anthropic:claude-sonnet-4-6"))


def judge_model() -> str:
    return resolve_model(os.environ.get("COUNCIL_JUDGE", "openai:gpt-4o"))
