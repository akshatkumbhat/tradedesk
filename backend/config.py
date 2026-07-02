"""App configuration — loaded from .env at the project root. Keys never leave this machine."""
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
_env = dotenv_values(ROOT / ".env")

ALPACA_API_KEY = _env.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = _env.get("ALPACA_SECRET_KEY", "")

# Live trading uses a SEPARATE key pair, generated deliberately from Alpaca's
# live (real-money) account. Absent keys = live mode cannot be enabled at all.
ALPACA_LIVE_API_KEY = _env.get("ALPACA_LIVE_API_KEY", "")
ALPACA_LIVE_SECRET_KEY = _env.get("ALPACA_LIVE_SECRET_KEY", "")

# The app always STARTS in paper mode; switching to live happens at runtime only,
# through the dashboard's typed-confirmation flow, and never survives in config.
LIVE_CONFIRMATION_PHRASE = "TRADE LIVE"

DB_PATH = ROOT / "tradedesk.db"
STRATEGIES_DIR = ROOT / "strategies"


def has_keys() -> bool:
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def has_live_keys() -> bool:
    return bool(ALPACA_LIVE_API_KEY and ALPACA_LIVE_SECRET_KEY)
