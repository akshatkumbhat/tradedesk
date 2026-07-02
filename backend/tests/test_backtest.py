import pytest

from backend.engine.backtest import run_backtest
from backend.engine.strategy import Context, Strategy

from .conftest import make_df


class BuyBar1SellBar3(Strategy):
    """Deterministic fixture strategy: buy 10 shares on bar 1, sell on bar 3."""

    id = "fixture"
    params = {}
    warmup = 0

    def on_bar(self, ctx: Context) -> None:
        if ctx.i == 1:
            ctx.buy(10)
        elif ctx.i == 3:
            ctx.close()


def test_fills_at_next_open_and_pnl_is_exact():
    # closes: 100, 100, 110, 120, 130  -> opens: 100, 100, 100, 110, 120
    df = make_df([100.0, 100.0, 110.0, 120.0, 130.0])
    res = run_backtest(BuyBar1SellBar3(), df, initial_cash=10_000)

    # buy intent on bar1 fills at bar2 open (100); sell intent on bar3 fills at bar4 open (120)
    assert res.stats.num_trades == 1
    t = res.trades[0]
    assert t.entry_price == 100.0
    assert t.exit_price == 120.0
    assert t.qty == 10
    assert t.pnl == pytest.approx(200.0)
    assert res.stats.final_equity == pytest.approx(10_200.0)
    assert res.stats.total_return_pct == pytest.approx(2.0)


def test_equity_marked_to_close_while_holding():
    df = make_df([100.0, 100.0, 110.0, 120.0, 130.0])
    res = run_backtest(BuyBar1SellBar3(), df, initial_cash=10_000)
    # bar2: holding 10 shares bought at 100, close 110 -> equity 10_000 + 10*10
    assert res.equity_curve[2].equity == pytest.approx(10_100.0)


def test_default_buy_invests_95pct_whole_shares():
    class BuyAll(Strategy):
        id = "buyall"
        params = {}

        def on_bar(self, ctx):
            if ctx.i == 0:
                ctx.buy()

    df = make_df([50.0, 50.0, 50.0])
    res = run_backtest(BuyAll(), df, initial_cash=1_000)
    # 95% of 1000 = 950 -> 19 shares at open 50
    assert res.equity_curve[-1].equity == pytest.approx(1_000.0)  # flat price, no gain
    # position was 19 shares: check via equity if price moved
    df2 = make_df([50.0, 50.0, 60.0])
    res2 = run_backtest(BuyAll(), df2, initial_cash=1_000)
    assert res2.equity_curve[-1].equity == pytest.approx(1_000 + 19 * 10.0)


def test_sell_capped_at_position_never_short():
    class OverSell(Strategy):
        id = "oversell"
        params = {}

        def on_bar(self, ctx):
            if ctx.i == 0:
                ctx.buy(5)
            elif ctx.i == 1:
                ctx.sell(500)

    df = make_df([100.0, 100.0, 100.0, 100.0])
    res = run_backtest(OverSell(), df, initial_cash=10_000)
    assert res.stats.final_equity == pytest.approx(10_000.0)
    assert res.trades[0].qty == 5


def test_max_drawdown():
    class Hold(Strategy):
        id = "hold"
        params = {}

        def on_bar(self, ctx):
            if ctx.i == 0:
                ctx.buy(10)

    # buy 10 @100; peak close 120, trough 90 -> dd from 10_200 to 9_900 ~ 2.94%
    df = make_df([100.0, 100.0, 120.0, 90.0, 100.0])
    res = run_backtest(Hold(), df, initial_cash=10_000)
    assert res.stats.max_drawdown_pct == pytest.approx((10_200 - 9_900) / 10_200 * 100, rel=1e-6)


def test_unknown_param_rejected():
    from backend.builtin_strategies.sma_cross import SmaCross

    with pytest.raises(ValueError, match="Unknown param"):
        SmaCross(bogus=1)
