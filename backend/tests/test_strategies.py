from backend.builtin_strategies.rsi_reversion import RsiReversion
from backend.builtin_strategies.sma_cross import SmaCross
from backend.engine.backtest import run_backtest

from .conftest import make_df


def test_sma_cross_goes_long_in_uptrend_and_exits(trend_df):
    res = run_backtest(SmaCross(fast=5, slow=20), trend_df, initial_cash=100_000)
    assert res.stats.num_trades == 1
    t = res.trades[0]
    # entered during the rise, exited after the roll-over
    assert t.entry_time < t.exit_time
    assert t.pnl != 0
    # the rise is strong and the exit lags the peak only slightly — trade should win
    assert t.pnl > 0


def test_sma_cross_flat_market_no_trades():
    df = make_df([100.0] * 80)
    res = run_backtest(SmaCross(fast=5, slow=20), df)
    assert res.stats.num_trades == 0
    assert res.stats.final_equity == 100_000.0


def test_sma_validates_periods():
    import pytest

    with pytest.raises(ValueError, match="fast period must be"):
        SmaCross(fast=30, slow=10)


def test_rsi_buys_dip_and_exits_on_recovery():
    # flat, sharp dip, then recovery — classic mean-reversion setup
    closes = (
        [100.0] * 50
        + [100 - 3 * i for i in range(1, 8)]   # dip to 79
        + [79 + 4 * i for i in range(1, 12)]   # recover to 123
        + [123.0] * 5
    )
    df = make_df(closes)
    res = run_backtest(RsiReversion(period=14, buy_below=30, exit_above=55), df)
    assert res.stats.num_trades == 1
    assert res.trades[0].pnl > 0


def test_rsi_validates_thresholds():
    import pytest

    with pytest.raises(ValueError, match="buy_below"):
        RsiReversion(buy_below=60, exit_above=50)
