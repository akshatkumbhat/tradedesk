"""Example custom strategy — copy this file to write your own.

Any Strategy subclass in this folder is auto-discovered: it appears on the
Strategies page and in the Backtest picker (refresh the browser after adding
a file). The same code runs in backtests and live paper runs.

The rules:
- give it a unique `id`, a `name`, and a `params` dict of tunable numbers
- set `warmup` to how many bars you need before trading decisions make sense
- implement on_bar(ctx); it runs once per closed bar with:
      ctx.history(n)  -> DataFrame of the last n bars (open/high/low/close/volume)
      ctx.price       -> current close
      ctx.position    -> shares this run currently holds
      ctx.buy(qty)    -> buy (qty=None invests ~95% of the run's cash)
      ctx.sell(qty)   -> sell (qty=None sells everything)
      ctx.close()     -> flatten
  Orders fill at the NEXT bar's open in backtests, at market in live runs.
"""
from backend.engine.strategy import Context, Strategy


class Momentum(Strategy):
    id = "example_momentum"
    name = "Momentum (example)"
    description = "Buys when price is up more than threshold% over the lookback window; exits when momentum fades."
    params = {"lookback": 20, "enter_pct": 5.0, "exit_pct": 0.0}

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.warmup = int(self.p["lookback"]) + 1

    def on_bar(self, ctx: Context) -> None:
        closes = ctx.history(int(self.p["lookback"]) + 1)["close"]
        change_pct = (closes.iloc[-1] / closes.iloc[0] - 1) * 100

        if ctx.position == 0 and change_pct > self.p["enter_pct"]:
            ctx.buy()
        elif ctx.position > 0 and change_pct < self.p["exit_pct"]:
            ctx.close()
