import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend import config, store
from backend.broker.base import Account, Bar, Broker, Order, OrderRequest, Position
from backend.engine.runner import StrategyRunner
from backend.engine.strategy import Context, Strategy


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")


class FakeBroker(Broker):
    name = "fake"

    def __init__(self, closes):
        self.closes = list(closes)
        self.orders: list[OrderRequest] = []
        self._oid = 0

    def get_account(self):
        return Account(equity=100_000, cash=100_000, buying_power=100_000)

    def get_positions(self):
        return []

    def get_orders(self, limit=100):
        return []

    def get_bars(self, symbol, timeframe="1Day", start=None, end=None, limit=500):
        t0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return [
            Bar(time=t0 + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1e6)
            for i, c in enumerate(self.closes)
        ]

    def submit_order(self, req):
        self._oid += 1
        self.orders.append(req)
        return Order(
            id=str(self._oid), symbol=req.symbol, qty=req.qty, side=req.side,
            type=req.type, status="filled", filled_qty=req.qty,
            filled_avg_price=self.closes[-1],
        )


class BuyOnce(Strategy):
    id = "buy_once"
    name = "Buy Once"
    params = {}
    warmup = 0

    def on_bar(self, ctx: Context) -> None:
        if ctx.position == 0:
            ctx.buy(10)


def test_step_submits_order_on_new_bar_and_updates_state():
    broker = FakeBroker([100.0] * 10)
    runner = StrategyRunner(lambda mode: broker)
    run = store.create_run("buy_once", "TEST", "1Day", {}, 10_000, "paper")

    asyncio.run(runner._step(run.id, BuyOnce()))

    assert len(broker.orders) == 1
    assert broker.orders[0].side == "buy" and broker.orders[0].qty == 10
    r = store.get_run(run.id)
    assert r.position == 10
    assert r.cash == pytest.approx(10_000 - 10 * 100.0)
    assert r.last_bar_time is not None
    acts = [a for a in store.list_activity() if a.kind == "order"]
    assert len(acts) == 1 and acts[0].mode == "paper"


def test_step_is_idempotent_until_new_bar():
    broker = FakeBroker([100.0] * 10)
    runner = StrategyRunner(lambda mode: broker)
    run = store.create_run("buy_once", "TEST", "1Day", {}, 10_000, "paper")

    asyncio.run(runner._step(run.id, BuyOnce()))
    asyncio.run(runner._step(run.id, BuyOnce()))  # same bars -> no new order

    assert len(broker.orders) == 1

    broker.closes.append(101.0)  # a new bar closes
    strategy = BuyOnce()
    asyncio.run(runner._step(run.id, strategy))
    # position is 10 now, strategy buys only when flat -> still one order
    assert len(broker.orders) == 1
    assert store.get_run(run.id).position == 10


def test_sell_capped_at_run_position():
    class SellALot(Strategy):
        id = "sell_a_lot"
        name = "Sell A Lot"
        params = {}
        warmup = 0

        def on_bar(self, ctx):
            ctx.sell(9999)

    broker = FakeBroker([100.0] * 5)
    runner = StrategyRunner(lambda mode: broker)
    run = store.create_run("sell_a_lot", "TEST", "1Day", {}, 10_000, "paper")
    asyncio.run(runner._step(run.id, SellALot()))
    assert broker.orders == []  # flat run -> nothing to sell, no rogue short


def test_orphaned_runs_marked_stopped():
    store.create_run("buy_once", "TEST", "1Day", {}, 10_000, "paper")
    assert store.mark_orphaned_runs_stopped() == 1
    assert all(r.status == "stopped" for r in store.list_runs())
