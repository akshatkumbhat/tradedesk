"""Live strategy runner — one async task per run, with risk rails.

Each run gets a cash allocation and tracks its own slice of the account, so
multiple strategies can trade the same account without stepping on each other.

Per closed bar, in order:
  1. daily-loss check   — value dropped more than max_daily_loss today -> flatten & halt
  2. stop-loss / take-profit — price crossed the level -> flatten
  3. strategy on_bar    — intents become orders
  4. per-order rails    — max_trade_size caps qty; orders above auto_approve_below
                          queue for manual approval instead of executing
"""
from __future__ import annotations

import asyncio
import math
from typing import Callable, Optional

import pandas as pd

from .. import store
from ..broker.base import Broker, OrderRequest
from .strategy import Context, Strategy

_POLL_SECONDS = {"1Min": 15, "5Min": 30, "15Min": 60, "1Hour": 120, "1Day": 600}
CASH_FRACTION = 0.95  # same sizing default as the backtester


class StrategyRunner:
    """Owns all live strategy tasks for the process."""

    def __init__(self, get_broker: Callable[[str], Broker]):
        self._get_broker = get_broker  # mode ("paper"|"live") -> Broker
        self._tasks: dict[str, asyncio.Task] = {}
        self._paused: set[str] = set()

    @property
    def active_run_ids(self) -> list[str]:
        return [rid for rid, t in self._tasks.items() if not t.done()]

    def is_paused(self, run_id: str) -> bool:
        return run_id in self._paused

    def start(self, run: store.Run, strategy: Strategy) -> None:
        if run.id in self._tasks and not self._tasks[run.id].done():
            raise RuntimeError(f"Run {run.id} already active")
        self._tasks[run.id] = asyncio.create_task(self._loop(run.id, strategy))

    def pause(self, run_id: str) -> None:
        if run_id not in self.active_run_ids:
            raise KeyError(f"Run {run_id} is not active")
        self._paused.add(run_id)
        store.set_run_status(run_id, "paused")
        store.log_activity("info", "Run paused", run_id=run_id)

    def resume(self, run_id: str) -> None:
        self._paused.discard(run_id)
        if run_id in self.active_run_ids:
            store.set_run_status(run_id, "running")
            store.log_activity("info", "Run resumed", run_id=run_id)

    async def stop(self, run_id: str) -> None:
        task = self._tasks.pop(run_id, None)
        self._paused.discard(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        run = store.get_run(run_id)
        if run.status in ("running", "paused"):
            store.set_run_status(run_id, "stopped")

    async def stop_all(self) -> None:
        for rid in list(self._tasks):
            await self.stop(rid)

    async def emergency_stop(self, flatten: bool) -> dict:
        """Kill switch: stop every run; optionally flatten each run's position at market."""
        flattened = []
        for rid in list(self._tasks):
            run = store.get_run(rid)
            await self.stop(rid)
            if flatten and run.position > 0:
                try:
                    broker = self._get_broker(run.mode)
                    order = await asyncio.to_thread(
                        broker.submit_order,
                        OrderRequest(symbol=run.symbol, qty=run.position, side="sell"),
                    )
                    store.update_run_state(rid, cash=run.cash + run.position * (order.filled_avg_price or run.entry_price),
                                           position=0.0, entry_price=0.0,
                                           last_bar_time=run.last_bar_time.isoformat() if run.last_bar_time else None)
                    flattened.append(run.symbol)
                except Exception as e:
                    store.log_activity("error", f"Emergency flatten failed: {e}", run_id=rid, symbol=run.symbol, mode=run.mode)
        store.log_activity("alert", f"EMERGENCY STOP — all runs stopped{', positions flattened: ' + ', '.join(flattened) if flattened else ''}")
        return {"stopped": True, "flattened": flattened}

    async def execute_pending(self, pending: store.PendingOrder, strategy_name: str = "") -> None:
        """Called when the user approves a queued order."""
        run = store.get_run(pending.run_id)
        broker = self._get_broker(run.mode)
        cash, position, entry_price = await self._execute(
            run, broker, pending.side, pending.qty, pending.est_price, strategy_name or run.strategy_id
        )
        store.update_run_state(run.id, cash=cash, position=position, entry_price=entry_price,
                               last_bar_time=run.last_bar_time.isoformat() if run.last_bar_time else None)
        store.set_pending_order_status(pending.id, "approved")

    # --- internals ---

    async def _loop(self, run_id: str, strategy: Strategy) -> None:
        run = store.get_run(run_id)
        poll = _POLL_SECONDS.get(run.timeframe, 60)
        store.log_activity("info", f"{strategy.name} started on {run.symbol} ({run.timeframe})",
                           run_id=run_id, symbol=run.symbol, mode=run.mode)
        try:
            while True:
                if run_id not in self._paused:
                    try:
                        halted = await self._step(run_id, strategy)
                        if halted:
                            break
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        store.log_activity("error", f"{type(e).__name__}: {e}", run_id=run_id,
                                           symbol=run.symbol, mode=run.mode)
                await asyncio.sleep(poll)
        except asyncio.CancelledError:
            store.log_activity("info", f"{strategy.name} stopped", run_id=run_id,
                               symbol=run.symbol, mode=run.mode)
            raise
        finally:
            self._tasks.pop(run_id, None)

    async def _step(self, run_id: str, strategy: Strategy) -> bool:
        """One evaluation. Returns True if the run halted itself (risk rail)."""
        run = store.get_run(run_id)
        broker = self._get_broker(run.mode)

        # Alpaca's `limit` truncates from the START of the window, so ask for the whole
        # default window (broker picks a per-timeframe start) and use the most recent bars.
        bars = await asyncio.to_thread(broker.get_bars, run.symbol, run.timeframe, None, None, 10_000)
        if len(bars) < strategy.warmup + 2:
            return False
        df = (
            pd.DataFrame([b.model_dump() for b in bars])
            .set_index("time")
            .sort_index()
            .tail(max(strategy.warmup + 60, 120))
        )

        latest = df.index[-1]
        if run.last_bar_time is not None and latest <= pd.Timestamp(run.last_bar_time):
            return False  # no new closed bar yet

        price = float(df["close"].iloc[-1])
        cash, position, entry_price = run.cash, run.position, run.entry_price

        # 1) daily loss rail
        value = cash + position * price
        today = str(latest.date())
        if run.day_date != today:
            store.set_run_day_anchor(run_id, today, value)
        elif run.max_daily_loss and run.day_start_value is not None:
            loss = run.day_start_value - value
            if loss >= run.max_daily_loss:
                if position > 0:
                    cash, position, entry_price = await self._execute(run, broker, "sell", position, price, strategy.name)
                store.update_run_state(run_id, cash=cash, position=position, entry_price=entry_price,
                                       last_bar_time=latest.isoformat())
                store.set_run_status(run_id, "stopped", error=f"Daily loss limit hit (−${loss:,.0f})")
                store.log_activity("alert", f"{strategy.name} HALTED: daily loss ${loss:,.0f} ≥ limit ${run.max_daily_loss:,.0f}",
                                   run_id=run_id, symbol=run.symbol, mode=run.mode)
                return True

        # 2) stop-loss / take-profit (position-level, checked on bar close)
        if position > 0 and entry_price > 0:
            change_pct = (price / entry_price - 1) * 100
            trigger = None
            if run.stop_loss_pct and change_pct <= -abs(run.stop_loss_pct):
                trigger = f"stop-loss ({change_pct:.1f}%)"
            elif run.take_profit_pct and change_pct >= abs(run.take_profit_pct):
                trigger = f"take-profit (+{change_pct:.1f}%)"
            if trigger:
                cash, position, entry_price = await self._execute(run, broker, "sell", position, price, strategy.name)
                store.log_activity("alert", f"{strategy.name}: {trigger} triggered on {run.symbol}",
                                   run_id=run_id, symbol=run.symbol, mode=run.mode)
                store.update_run_state(run_id, cash=cash, position=position, entry_price=entry_price,
                                       last_bar_time=latest.isoformat())
                return False

        # 3) strategy
        ctx = Context(df, len(df) - 1, cash=cash, position=position)
        strategy.on_bar(ctx)

        # 4) intents -> orders, through the rails
        for side, qty in ctx.intents:
            if side == "buy":
                if qty is None:
                    qty = math.floor((cash * CASH_FRACTION) / price)
                qty = min(qty, math.floor(cash / price)) if price > 0 else 0
            else:
                qty = position if qty is None else min(qty, position)
            if not qty or qty <= 0:
                continue

            # max trade size: cap the order's notional
            if run.max_trade_size and qty * price > run.max_trade_size:
                capped = math.floor(run.max_trade_size / price)
                store.log_activity("alert",
                                   f"{strategy.name}: order capped {qty} → {capped} sh by max trade size ${run.max_trade_size:,.0f}",
                                   run_id=run_id, symbol=run.symbol, mode=run.mode)
                qty = capped
                if qty <= 0:
                    continue

            # approval threshold: big orders queue instead of executing
            if run.auto_approve_below is not None and qty * price > run.auto_approve_below:
                store.create_pending_order(run_id, run.symbol, side, qty, price, run.mode)
                store.log_activity("alert",
                                   f"{strategy.name}: {side} {qty} {run.symbol} (~${qty * price:,.0f}) awaits your approval",
                                   run_id=run_id, symbol=run.symbol, side=side, qty=qty, price=price,
                                   status="pending", mode=run.mode)
                continue

            cash, position, entry_price = await self._execute(run, broker, side, qty, price, strategy.name,
                                                              cash=cash, position=position, entry_price=entry_price)

        store.update_run_state(run_id, cash=cash, position=position, entry_price=entry_price,
                               last_bar_time=latest.isoformat())
        return False

    async def _execute(
        self, run: store.Run, broker: Broker, side: str, qty: float, price: float, strategy_name: str,
        cash: Optional[float] = None, position: Optional[float] = None, entry_price: Optional[float] = None,
    ) -> tuple[float, float, float]:
        cash = run.cash if cash is None else cash
        position = run.position if position is None else position
        entry_price = run.entry_price if entry_price is None else entry_price

        order = await asyncio.to_thread(
            broker.submit_order, OrderRequest(symbol=run.symbol, qty=qty, side=side)
        )
        fill_price = order.filled_avg_price or price
        if side == "buy":
            entry_price = (
                fill_price if position == 0
                else (entry_price * position + fill_price * qty) / (position + qty)
            )
            cash -= qty * fill_price
            position += qty
        else:
            cash += qty * fill_price
            position -= qty
            if position == 0:
                entry_price = 0.0
        store.log_activity(
            "order", f"{strategy_name}: {side} {qty} {run.symbol} ({order.status})",
            run_id=run.id, symbol=run.symbol, side=side, qty=qty,
            price=fill_price, status=order.status, mode=run.mode,
        )
        return cash, position, entry_price
