"""SMA crossover — long when the fast average crosses above the slow, flat on the cross down."""
from __future__ import annotations

from ..engine.indicators import sma
from ..engine.strategy import Context, Strategy


class SmaCross(Strategy):
    id = "sma_cross"
    name = "SMA Crossover"
    description = "Buys when the fast moving average crosses above the slow; exits on the cross back down."
    params = {"fast": 10, "slow": 30}

    def __init__(self, **overrides: float):
        super().__init__(**overrides)
        if self.p["fast"] >= self.p["slow"]:
            raise ValueError("fast period must be < slow period")
        self.warmup = int(self.p["slow"]) + 1

    def on_bar(self, ctx: Context) -> None:
        close = ctx.history()["close"]
        fast = sma(close, int(self.p["fast"]))
        slow = sma(close, int(self.p["slow"]))
        f_now, f_prev = fast.iloc[-1], fast.iloc[-2]
        s_now, s_prev = slow.iloc[-1], slow.iloc[-2]
        if ctx.position == 0 and f_prev <= s_prev and f_now > s_now:
            ctx.buy()
        elif ctx.position > 0 and f_prev >= s_prev and f_now < s_now:
            ctx.close()
