import numpy as np
import pandas as pd
import pytest


def make_df(closes, start="2025-01-01", freq="D"):
    """Build an OHLCV frame where each bar opens at the previous close (first opens at its close)."""
    closes = np.asarray(closes, dtype=float)
    opens = np.concatenate([[closes[0]], closes[:-1]])
    idx = pd.date_range(start, periods=len(closes), freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) * 1.001,
            "low": np.minimum(opens, closes) * 0.999,
            "close": closes,
            "volume": np.full(len(closes), 1e6),
        },
        index=idx,
    )


@pytest.fixture
def trend_df():
    """60 flat bars then 60 rising then 60 falling — SMA cross must go long then exit."""
    closes = [100.0] * 60 + [100.0 + i for i in range(1, 61)] + [160.0 - 1.5 * i for i in range(1, 61)]
    return make_df(closes)
