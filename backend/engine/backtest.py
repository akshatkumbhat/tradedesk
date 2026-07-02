"""Bar-replay backtester.

Semantics:
- Strategy signals on bar close; intents fill at the NEXT bar's open.
- buy(None) invests CASH_FRACTION of available cash in whole shares.
- Long-only for now (sells are capped at the current position).
- Equity is marked to close each bar.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

import pandas as pd
from pydantic import BaseModel

from .strategy import Intent, Context, Strategy

CASH_FRACTION = 0.95


class Trade(BaseModel):
    entry_time: datetime
    exit_time: datetime
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float


class EquityPoint(BaseModel):
    time: datetime
    equity: float


class Stats(BaseModel):
    start: datetime
    end: datetime
    initial_cash: float
    final_equity: float
    total_return_pct: float
    cagr_pct: Optional[float]
    sharpe: Optional[float]
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: Optional[float]


class BacktestResult(BaseModel):
    strategy_id: str
    params: dict[str, float]
    stats: Stats
    equity_curve: list[EquityPoint]
    trades: list[Trade]


def run_backtest(
    strategy: Strategy,
    df: pd.DataFrame,
    initial_cash: float = 100_000.0,
    commission: float = 0.0,
) -> BacktestResult:
    """df: columns open/high/low/close/volume, DatetimeIndex ascending."""
    if len(df) < 2:
        raise ValueError("Need at least 2 bars to backtest")

    cash = initial_cash
    position = 0.0
    entry_price = 0.0
    entry_time = None
    pending: list[Intent] = []
    trades: list[Trade] = []
    curve: list[EquityPoint] = []

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    times = df.index

    for i in range(len(df)):
        # 1) fill intents queued on the previous bar, at this bar's open
        for side, qty in pending:
            price = float(opens[i])
            if side == "buy":
                if qty is None:
                    qty = math.floor((cash * CASH_FRACTION) / price)
                qty = min(qty, math.floor(cash / price)) if price > 0 else 0
                if qty and qty > 0:
                    if position == 0:
                        entry_price = price
                        entry_time = times[i]
                    else:
                        # average in
                        entry_price = (entry_price * position + price * qty) / (position + qty)
                    cash -= qty * price + commission
                    position += qty
            else:  # sell
                qty = position if qty is None else min(qty, position)
                if qty and qty > 0:
                    cash += qty * price - commission
                    position -= qty
                    if position == 0 and entry_time is not None:
                        pnl = (price - entry_price) * qty - 2 * commission
                        trades.append(
                            Trade(
                                entry_time=entry_time,
                                exit_time=times[i],
                                qty=qty,
                                entry_price=entry_price,
                                exit_price=price,
                                pnl=pnl,
                                return_pct=(price / entry_price - 1) * 100,
                            )
                        )
                        entry_time = None
        pending = []

        # 2) mark equity at close
        equity = cash + position * float(closes[i])
        curve.append(EquityPoint(time=times[i], equity=equity))

        # 3) let the strategy react to this bar
        if i >= strategy.warmup and i < len(df) - 1:  # last bar's intents could never fill
            ctx = Context(df, i, cash, position)
            strategy.on_bar(ctx)
            pending = ctx.intents

    return BacktestResult(
        strategy_id=strategy.id,
        params=dict(strategy.p),
        stats=_stats(curve, trades, initial_cash),
        equity_curve=curve,
        trades=trades,
    )


def _stats(curve: list[EquityPoint], trades: list[Trade], initial_cash: float) -> Stats:
    eq = pd.Series([p.equity for p in curve], index=[p.time for p in curve])
    final = float(eq.iloc[-1])
    total_return = final / initial_cash - 1

    days = max((eq.index[-1] - eq.index[0]).total_seconds() / 86400, 0)
    cagr = None
    if days >= 1 and final > 0:
        cagr = (final / initial_cash) ** (365.25 / days) - 1

    rets = eq.pct_change().dropna()
    sharpe = None
    if len(rets) > 2 and float(rets.std()) > 0:
        # annualize by median bar spacing
        dt_sec = float(pd.Series(eq.index).diff().dt.total_seconds().median())
        periods_per_year = (365.25 * 86400) / dt_sec if dt_sec > 0 else 252
        sharpe = float(rets.mean() / rets.std() * math.sqrt(periods_per_year))

    peak = eq.cummax()
    max_dd = float(((eq - peak) / peak).min()) * -100

    wins = sum(1 for t in trades if t.pnl > 0)
    win_rate = (wins / len(trades) * 100) if trades else None

    return Stats(
        start=curve[0].time,
        end=curve[-1].time,
        initial_cash=initial_cash,
        final_equity=final,
        total_return_pct=total_return * 100,
        cagr_pct=cagr * 100 if cagr is not None else None,
        sharpe=sharpe,
        max_drawdown_pct=max_dd,
        num_trades=len(trades),
        win_rate_pct=win_rate,
    )
