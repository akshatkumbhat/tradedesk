"""Strategy base class and the Context passed to on_bar.

The same Strategy code runs in backtests and (from Milestone 4) live: on_bar
sees history up to the current bar and expresses intent via ctx.buy/sell/close.
Intents are filled at the NEXT bar's open — no lookahead.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

Intent = tuple[str, Optional[float]]  # ("buy" | "sell", qty or None)


class Context:
    """What a strategy sees on each bar."""

    def __init__(self, df: pd.DataFrame, i: int, cash: float, position: float):
        self._df = df
        self.i = i
        self.cash = cash
        self.position = position
        self.intents: list[Intent] = []

    def history(self, n: Optional[int] = None) -> pd.DataFrame:
        """Bars up to and including the current one (last n if given)."""
        h = self._df.iloc[: self.i + 1]
        return h.tail(n) if n is not None else h

    @property
    def price(self) -> float:
        """Current bar's close."""
        return float(self._df["close"].iloc[self.i])

    @property
    def time(self):
        return self._df.index[self.i]

    # --- intents (filled at next bar's open) ---

    def buy(self, qty: Optional[float] = None) -> None:
        """Buy qty shares; qty=None invests ~95% of available cash."""
        self.intents.append(("buy", qty))

    def sell(self, qty: Optional[float] = None) -> None:
        """Sell qty shares; qty=None sells the entire position."""
        self.intents.append(("sell", qty))

    def close(self) -> None:
        """Flatten the position."""
        self.sell(None)


class Strategy:
    """Subclass this. Declare `params` defaults; instances may override via kwargs.

    class MyStrat(Strategy):
        id = "my_strat"
        name = "My Strategy"
        params = {"lookback": 20}

        def on_bar(self, ctx: Context) -> None:
            ...
    """

    id: str = "unnamed"
    name: str = "Unnamed"
    description: str = ""
    params: dict[str, float] = {}
    warmup: int = 0  # bars to skip before on_bar is first called

    def __init__(self, **overrides: float):
        unknown = set(overrides) - set(type(self).params)
        if unknown:
            raise ValueError(f"Unknown param(s) for {self.id}: {sorted(unknown)}")
        self.p = {**type(self).params, **overrides}

    def on_bar(self, ctx: Context) -> None:
        raise NotImplementedError
