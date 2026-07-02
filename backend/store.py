"""SQLite persistence — runs and the activity log. Everything stays on disk locally."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    params TEXT NOT NULL,          -- json
    allocation REAL NOT NULL,
    status TEXT NOT NULL,          -- running | stopped | error
    error TEXT,
    mode TEXT NOT NULL,            -- paper | live
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    cash REAL NOT NULL,            -- unspent slice of the allocation
    position REAL NOT NULL DEFAULT 0,
    entry_price REAL NOT NULL DEFAULT 0,
    last_bar_time TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT,
    time TEXT NOT NULL,
    kind TEXT NOT NULL,            -- order | info | error | alert
    symbol TEXT,
    side TEXT,
    qty REAL,
    price REAL,
    status TEXT,
    mode TEXT NOT NULL DEFAULT 'paper',
    detail TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pending_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    time TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    qty REAL NOT NULL,
    est_price REAL NOT NULL,
    notional REAL NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'   -- pending | approved | rejected | superseded
);
"""

# columns added after the first release; applied idempotently on connect
_MIGRATIONS = [
    ("runs", "max_trade_size", "REAL"),           # $ cap per order (0/NULL = off)
    ("runs", "max_daily_loss", "REAL"),           # $ loss within a day that halts the run
    ("runs", "stop_loss_pct", "REAL"),            # % below entry that flattens
    ("runs", "take_profit_pct", "REAL"),          # % above entry that flattens
    ("runs", "auto_approve_below", "REAL"),       # orders <= this $ skip approval (NULL = all auto)
    ("runs", "day_date", "TEXT"),                 # daily-loss tracking anchor
    ("runs", "day_start_value", "REAL"),
]


class RiskLimits(BaseModel):
    max_trade_size: Optional[float] = None      # $ notional cap per order
    max_daily_loss: Optional[float] = None      # $ drop within a day that halts the run
    stop_loss_pct: Optional[float] = None       # exit if price falls this % below entry
    take_profit_pct: Optional[float] = None     # exit if price rises this % above entry
    auto_approve_below: Optional[float] = None  # orders <= this $ auto-execute; None = all auto


class Run(BaseModel):
    id: str
    strategy_id: str
    symbol: str
    timeframe: str
    params: dict[str, float]
    allocation: float
    status: str
    error: Optional[str] = None
    mode: str
    started_at: datetime
    stopped_at: Optional[datetime] = None
    cash: float
    position: float
    entry_price: float
    last_bar_time: Optional[datetime] = None
    max_trade_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    auto_approve_below: Optional[float] = None
    day_date: Optional[str] = None
    day_start_value: Optional[float] = None


class PendingOrder(BaseModel):
    id: int
    run_id: str
    time: datetime
    symbol: str
    side: str
    qty: float
    est_price: float
    notional: float
    mode: str
    status: str


class ActivityItem(BaseModel):
    id: int
    run_id: Optional[str]
    time: datetime
    kind: str
    symbol: Optional[str] = None
    side: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    status: Optional[str] = None
    mode: str = "paper"
    detail: Optional[str] = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    for table, column, sqltype in _MIGRATIONS:
        cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sqltype}")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_run(r: sqlite3.Row) -> Run:
    d = dict(r)
    d["params"] = json.loads(d["params"])
    return Run(**d)


def create_run(
    strategy_id: str, symbol: str, timeframe: str, params: dict, allocation: float, mode: str,
    limits: Optional[RiskLimits] = None,
) -> Run:
    run_id = uuid.uuid4().hex[:12]
    lim = limits or RiskLimits()
    with _connect() as c:
        c.execute(
            "INSERT INTO runs (id, strategy_id, symbol, timeframe, params, allocation, status, mode, started_at, cash,"
            " max_trade_size, max_daily_loss, stop_loss_pct, take_profit_pct, auto_approve_below)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, strategy_id, symbol, timeframe, json.dumps(params), allocation, "running", mode, _now(), allocation,
             lim.max_trade_size, lim.max_daily_loss, lim.stop_loss_pct, lim.take_profit_pct, lim.auto_approve_below),
        )
    return get_run(run_id)


def get_run(run_id: str) -> Run:
    with _connect() as c:
        row = c.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown run {run_id!r}")
    return _row_to_run(row)


def list_runs(active_only: bool = False) -> list[Run]:
    q = "SELECT * FROM runs" + (" WHERE status = 'running'" if active_only else "") + " ORDER BY started_at DESC"
    with _connect() as c:
        return [_row_to_run(r) for r in c.execute(q).fetchall()]


def update_run_state(run_id: str, *, cash: float, position: float, entry_price: float, last_bar_time: Optional[str]) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE runs SET cash=?, position=?, entry_price=?, last_bar_time=? WHERE id=?",
            (cash, position, entry_price, last_bar_time, run_id),
        )


def set_run_status(run_id: str, status: str, error: Optional[str] = None) -> None:
    with _connect() as c:
        c.execute(
            "UPDATE runs SET status=?, error=?, stopped_at=? WHERE id=?",
            (status, error, _now() if status != "running" else None, run_id),
        )


def mark_orphaned_runs_stopped() -> int:
    """On startup: anything still 'running' from a previous process is stale."""
    with _connect() as c:
        cur = c.execute("UPDATE runs SET status='stopped', stopped_at=? WHERE status='running'", (_now(),))
        return cur.rowcount


def log_activity(
    kind: str,
    detail: str = "",
    *,
    run_id: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    qty: Optional[float] = None,
    price: Optional[float] = None,
    status: Optional[str] = None,
    mode: str = "paper",
) -> None:
    with _connect() as c:
        c.execute(
            "INSERT INTO activity (run_id, time, kind, symbol, side, qty, price, status, mode, detail)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (run_id, _now(), kind, symbol, side, qty, price, status, mode, detail),
        )


def list_activity(limit: int = 200) -> list[ActivityItem]:
    with _connect() as c:
        rows = c.execute("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [ActivityItem(**dict(r)) for r in rows]


# --- settings ---


def get_setting(key: str, default: str) -> str:
    with _connect() as c:
        row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as c:
        c.execute("INSERT INTO settings (key, value) VALUES (?,?)"
                  " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def set_run_day_anchor(run_id: str, day_date: str, day_start_value: float) -> None:
    with _connect() as c:
        c.execute("UPDATE runs SET day_date=?, day_start_value=? WHERE id=?", (day_date, day_start_value, run_id))


# --- pending orders (manual approval queue) ---


def create_pending_order(run_id: str, symbol: str, side: str, qty: float, est_price: float, mode: str) -> PendingOrder:
    with _connect() as c:
        # a newer intent supersedes any still-pending order for the same run
        c.execute("UPDATE pending_orders SET status='superseded' WHERE run_id=? AND status='pending'", (run_id,))
        cur = c.execute(
            "INSERT INTO pending_orders (run_id, time, symbol, side, qty, est_price, notional, mode)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (run_id, _now(), symbol, side, qty, est_price, qty * est_price, mode),
        )
        row = c.execute("SELECT * FROM pending_orders WHERE id = ?", (cur.lastrowid,)).fetchone()
    return PendingOrder(**dict(row))


def get_pending_order(order_id: int) -> PendingOrder:
    with _connect() as c:
        row = c.execute("SELECT * FROM pending_orders WHERE id = ?", (order_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown pending order {order_id}")
    return PendingOrder(**dict(row))


def list_pending_orders() -> list[PendingOrder]:
    with _connect() as c:
        rows = c.execute("SELECT * FROM pending_orders WHERE status='pending' ORDER BY id DESC").fetchall()
    return [PendingOrder(**dict(r)) for r in rows]


def set_pending_order_status(order_id: int, status: str) -> None:
    with _connect() as c:
        c.execute("UPDATE pending_orders SET status=? WHERE id=?", (status, order_id))
