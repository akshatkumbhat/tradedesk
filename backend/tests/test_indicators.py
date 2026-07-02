import numpy as np
import pandas as pd

from backend.engine.indicators import rsi, sma


def test_sma_matches_hand_computation():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = sma(s, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 2.0
    assert out.iloc[4] == 4.0


def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 200, 50))
    down = pd.Series(np.linspace(200, 100, 50))
    assert rsi(up, 14).iloc[-1] == 100.0  # all gains
    assert rsi(down, 14).iloc[-1] == 0.0  # all losses


def test_rsi_flat_then_drop_goes_oversold():
    closes = pd.Series([100.0] * 30 + [100.0 - 2 * i for i in range(1, 11)])
    r = rsi(closes, 14)
    assert r.iloc[-1] < 30
