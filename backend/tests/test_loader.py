import textwrap

import pytest

from backend import config
from backend.engine import loader, registry
from backend.engine.backtest import run_backtest

from .conftest import make_df

GOOD = textwrap.dedent(
    """
    from backend.engine.strategy import Context, Strategy

    class BuyAndHold(Strategy):
        id = "buy_hold_test"
        name = "Buy & Hold"
        params = {}

        def on_bar(self, ctx):
            if ctx.position == 0:
                ctx.buy()
    """
)

BROKEN = "this is not valid python ("

DUPLICATE_ID = textwrap.dedent(
    """
    from backend.engine.strategy import Strategy

    class Impostor(Strategy):
        id = "sma_cross"   # collides with the built-in
        params = {}
        def on_bar(self, ctx): pass
    """
)


@pytest.fixture
def strat_dir(tmp_path, monkeypatch):
    d = tmp_path / "strategies"
    d.mkdir()
    monkeypatch.setattr(config, "STRATEGIES_DIR", d)
    return d


def test_discovers_strategy_from_file(strat_dir):
    (strat_dir / "buy_hold.py").write_text(GOOD)
    found, errors = loader.discover(strat_dir)
    assert errors == []
    assert [c.id for c in found] == ["buy_hold_test"]
    # and it actually backtests
    res = run_backtest(found[0](), make_df([100.0, 100.0, 110.0]))
    assert res.equity_curve[-1].equity > 100_000


def test_broken_file_is_skipped_with_error(strat_dir):
    (strat_dir / "broken.py").write_text(BROKEN)
    (strat_dir / "buy_hold.py").write_text(GOOD)
    found, errors = loader.discover(strat_dir)
    assert [c.id for c in found] == ["buy_hold_test"]
    assert len(errors) == 1 and "broken.py" in errors[0]


def test_underscore_files_ignored(strat_dir):
    (strat_dir / "_wip.py").write_text(BROKEN)
    found, errors = loader.discover(strat_dir)
    assert found == [] and errors == []


def test_registry_merges_and_rejects_duplicate_ids(strat_dir):
    (strat_dir / "impostor.py").write_text(DUPLICATE_ID)
    (strat_dir / "buy_hold.py").write_text(GOOD)
    desc = registry.describe()
    ids = [s["id"] for s in desc["strategies"]]
    assert ids.count("sma_cross") == 1  # built-in kept, impostor dropped
    assert "buy_hold_test" in ids
    assert any("duplicate strategy id" in e for e in desc["errors"])
    custom = next(s for s in desc["strategies"] if s["id"] == "buy_hold_test")
    assert custom["builtin"] is False


def test_registry_get_finds_user_strategy(strat_dir):
    (strat_dir / "buy_hold.py").write_text(GOOD)
    assert registry.get_strategy("buy_hold_test").name == "Buy & Hold"
