"""Safety-rail tests: max trade size, daily loss halt, SL/TP, approval queue."""
import asyncio

import pytest

from backend import config, store
from backend.engine.runner import StrategyRunner
from backend.engine.strategy import Context, Strategy

from .test_runner import BuyOnce, FakeBroker


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")


def make(broker, **limits):
    runner = StrategyRunner(lambda mode: broker)
    run = store.create_run("buy_once", "TEST", "1Day", {}, 10_000, "paper",
                           store.RiskLimits(**limits))
    return runner, run


def test_max_trade_size_caps_order():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, max_trade_size=500.0)  # $500 cap at $100/share -> 5 shares
    asyncio.run(runner._step(run.id, BuyOnce()))
    assert broker.orders[0].qty == 5
    assert any("capped" in (a.detail or "") for a in store.list_activity() if a.kind == "alert")


def test_orders_above_threshold_queue_for_approval():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, auto_approve_below=500.0)  # 10 sh * $100 = $1000 > $500
    asyncio.run(runner._step(run.id, BuyOnce()))

    assert broker.orders == []  # nothing executed
    pending = store.list_pending_orders()
    assert len(pending) == 1
    assert pending[0].qty == 10 and pending[0].notional == pytest.approx(1000.0)
    # run state unchanged until approval
    assert store.get_run(run.id).position == 0


def test_approving_pending_order_executes_it():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, auto_approve_below=500.0)
    asyncio.run(runner._step(run.id, BuyOnce()))
    pending = store.list_pending_orders()[0]

    asyncio.run(runner.execute_pending(pending))

    assert len(broker.orders) == 1
    r = store.get_run(run.id)
    assert r.position == 10 and r.cash == pytest.approx(9_000.0)
    assert store.get_pending_order(pending.id).status == "approved"


def test_small_orders_below_threshold_execute_autonomously():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, auto_approve_below=2_000.0)  # $1000 order <= $2000 -> auto
    asyncio.run(runner._step(run.id, BuyOnce()))
    assert len(broker.orders) == 1
    assert store.list_pending_orders() == []


def test_newer_intent_supersedes_stale_pending():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, auto_approve_below=500.0)
    asyncio.run(runner._step(run.id, BuyOnce()))
    broker.closes.append(100.0)
    asyncio.run(runner._step(run.id, BuyOnce()))  # still flat -> signals again

    pending = store.list_pending_orders()
    assert len(pending) == 1  # only the newest survives


def test_stop_loss_flattens_position():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, stop_loss_pct=5.0)
    asyncio.run(runner._step(run.id, BuyOnce()))  # buys 10 @ ~100
    assert store.get_run(run.id).position == 10

    broker.closes.append(94.0)  # -6% < -5% stop
    asyncio.run(runner._step(run.id, BuyOnce()))

    r = store.get_run(run.id)
    assert r.position == 0
    assert any("stop-loss" in (a.detail or "") for a in store.list_activity() if a.kind == "alert")


def test_take_profit_flattens_position():
    broker = FakeBroker([100.0] * 10)
    runner, run = make(broker, take_profit_pct=10.0)
    asyncio.run(runner._step(run.id, BuyOnce()))
    broker.closes.append(111.0)  # +11% > +10% target
    asyncio.run(runner._step(run.id, BuyOnce()))

    assert store.get_run(run.id).position == 0
    assert any("take-profit" in (a.detail or "") for a in store.list_activity() if a.kind == "alert")


class IntradayBroker(FakeBroker):
    """Minute-spaced bars so every bar lands on the same calendar day."""

    def get_bars(self, symbol, timeframe="1Min", start=None, end=None, limit=500):
        from datetime import datetime, timedelta, timezone

        from backend.broker.base import Bar

        t0 = datetime(2025, 1, 1, 15, 0, tzinfo=timezone.utc)
        return [
            Bar(time=t0 + timedelta(minutes=i), open=c, high=c, low=c, close=c, volume=1e6)
            for i, c in enumerate(self.closes)
        ]


def test_daily_loss_halts_and_flattens():
    broker = IntradayBroker([100.0] * 10)
    runner, run = make(broker, max_daily_loss=300.0)
    asyncio.run(runner._step(run.id, BuyOnce()))  # buy 10 @ 100; day anchored at ~10_000

    broker.closes.append(60.0)  # value 9_000+600=9_600? -> loss 10*40=400 >= 300
    asyncio.run(runner._step(run.id, BuyOnce()))

    r = store.get_run(run.id)
    assert r.status == "stopped"
    assert r.position == 0  # flattened on halt
    assert "Daily loss" in (r.error or "")
    assert any("HALTED" in (a.detail or "") for a in store.list_activity() if a.kind == "alert")
