"""Budget cap: pins the per-token $ math AND the trip, per money-path discipline."""
import pytest

from council.llm import DEFAULT_PRICE, BudgetExceeded, CostMeter, Usage


def test_cost_usd_exact():
    # gpt-4o = $2.50/1M input, $10.00/1M output. Exact figures catch a 1000x slip.
    m = CostMeter()
    m.record("generate", "skeptic", Usage(1_000_000, 0), model="openai:gpt-4o")
    assert m.cost_usd() == pytest.approx(2.50)
    m.record("generate", "skeptic", Usage(0, 1_000_000), model="openai:gpt-4o")
    assert m.cost_usd() == pytest.approx(12.50)


def test_unknown_model_uses_conservative_default():
    m = CostMeter()
    m.record("generate", "x", Usage(1_000_000, 0), model="who:dis")
    assert m.cost_usd() == pytest.approx(DEFAULT_PRICE[0])  # fail-safe high, not free


def test_budget_trips_and_reports_spend():
    m = CostMeter(budget_usd=4.0)
    m.record("generate", "x", Usage(1_000_000, 0), model="openai:gpt-4o")  # $2.50, under
    with pytest.raises(BudgetExceeded) as ei:
        m.record("generate", "x", Usage(1_000_000, 0), model="openai:gpt-4o")  # ->$5.00 > $4
    assert ei.value.spent == pytest.approx(5.00)
    assert ei.value.budget == 4.0


def test_no_model_and_no_budget_is_free_and_silent():
    # offline/stub path: model=None -> $0, never raises (keeps the offline suite green).
    m = CostMeter()
    m.record("generate", "x", Usage(9_999_999, 9_999_999))
    assert m.cost_usd() == 0.0
