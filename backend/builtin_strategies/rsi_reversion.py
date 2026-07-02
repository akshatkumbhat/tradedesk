"""RSI mean-reversion — buy oversold dips, exit when RSI recovers."""
from __future__ import annotations

from ..engine.indicators import rsi
from ..engine.strategy import Context, Strategy


class RsiReversion(Strategy):
    id = "rsi_reversion"
    name = "RSI Mean Reversion"
    description = "Buys when RSI drops below the oversold threshold; exits once RSI recovers above the exit level."
    params = {"period": 14, "buy_below": 30, "exit_above": 55}

    def __init__(self, **overrides: float):
        super().__init__(**overrides)
        if not self.p["buy_below"] < self.p["exit_above"]:
            raise ValueError("buy_below must be < exit_above")
        # Wilder smoothing needs extra bars beyond `period` to stabilize.
        self.warmup = int(self.p["period"]) * 3

    def on_bar(self, ctx: Context) -> None:
        close = ctx.history()["close"]
        r = rsi(close, int(self.p["period"])).iloc[-1]
        if ctx.position == 0 and r < self.p["buy_below"]:
            ctx.buy()
        elif ctx.position > 0 and r > self.p["exit_above"]:
            ctx.close()
