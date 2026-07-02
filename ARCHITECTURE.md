# Architecture

This document explains how Tradedesk is put together and, more importantly, *why* — the contracts, trade-offs, and failure-mode thinking behind each piece.

## Design principles

1. **Local-first is a security posture, not a deployment detail.** Keys, strategy IP, and trade history are the crown jewels; they stay in `.env` and a local SQLite file. The attack surface is one outbound HTTPS connection to the broker.
2. **Research-to-production parity.** The most expensive bug class in algo trading is "backtest said X, live did Y." One strategy API, one sizing rule, one fill contract — shared by the backtester and the live runner.
3. **The execution path enforces safety; strategies are untrusted.** A strategy can be wrong, slow, or buggy — it cannot exceed its allocation, breach a risk limit, or crash the process.
4. **Boring persistence.** SQLite + append-only logging + idempotent migrations. No ORM, no message queue, no daemon zoo — a single-user desk does not need them, and every removed moving part is a failure mode eliminated.

## System overview

```
frontend (React/Vite, :5173)
   │  REST: queries & commands          (proxied same-origin in dev)
   │  WS  : state fan-out every 5s      (account, positions, runs, activity, approvals)
   ▼
backend/main.py (FastAPI, :8000)
   ├── engine/backtest.py      bar-replay simulator (pure function of strategy + bars)
   ├── engine/runner.py        StrategyRunner — one asyncio task per live run + risk rails
   ├── engine/registry.py      built-ins ∪ user strategies (id-collision safe)
   │      └── engine/loader.py hot-discovery of strategies/*.py, quarantines broken files
   ├── broker/base.py          Broker ABC + pydantic models (the only broker contract)
   │      └── broker/alpaca.py Alpaca adapter (paper + live clients)
   └── store.py                SQLite: runs, activity, settings, pending_orders
```

## The strategy contract

```python
class Strategy:
    id, name, description: str
    params: dict[str, float]      # defaults; instances override via kwargs
    warmup: int                   # bars to skip before first evaluation

    def on_bar(self, ctx: Context) -> None: ...
```

`Context` exposes `history(n)` (bars up to and including the current one — never future bars), `price`, `position`, `cash`, and intent methods `buy(qty=None)` / `sell(qty=None)` / `close()`.

**Fill semantics — the invariant everything hangs on:**

> Strategies observe a *closed* bar and emit intents. Intents fill at the **next** bar's open (backtest) or at market immediately after the bar closes (live).

This makes lookahead bias structurally impossible in backtests and keeps live behavior as close to the simulation as a market order allows. `buy(None)` means "invest ~95% of available cash in whole shares" — one sizing rule, implemented identically in both engines.

## Backtester (`engine/backtest.py`)

A deliberate non-goal: cleverness. It is a plain forward replay —

1. Fill last bar's intents at this bar's open (long-only; sells capped at position — no accidental shorts).
2. Mark equity to close.
3. If past warmup, call `on_bar`; queue intents.

Round-trip trades are paired on position-flat; stats (CAGR, Sharpe annualized by median bar spacing, max drawdown, win rate) are computed from the equity series. Output is a pydantic `BacktestResult` that serializes straight to the API.

Indicators recompute over the visible history each bar — O(n²) but instant at daily/hourly scale. This was chosen consciously: correctness and readability first, incremental computation when minute-scale backtests demand it.

## Live runner (`engine/runner.py`)

`StrategyRunner` owns one asyncio task per run. Each tick (poll interval scales with timeframe):

```
fetch bars ──▶ new closed bar? ──▶ risk rails ──▶ on_bar ──▶ intents ──▶ rails ──▶ orders
                    │ no                                                        │
                    └── sleep                                        SQLite state update
```

Ordering is deliberate — rails run **before and after** the strategy:

1. **Daily-loss check** (before): if the run's marked value has dropped ≥ `max_daily_loss` since the day's anchor, flatten at market, halt the run, alert. The strategy never gets a say.
2. **Stop-loss / take-profit** (before): position-level exits checked against entry price.
3. **Strategy evaluation**: sees exactly what a backtest would.
4. **Per-order rails** (after): notional cap via `max_trade_size`; orders above `auto_approve_below` are diverted to the approval queue instead of the broker.

**Idempotency.** `last_bar_time` is persisted per run; a bar is evaluated at most once, across restarts. Alpaca's `limit` parameter truncates from the *start* of a time window — the runner therefore fetches the full window and tails it (a real bug found in live verification, now regression-tested).

**Failure containment.** A strategy exception is logged to the activity feed and retried next bar. Task cancellation is the only way a run stops. On process start, runs left `running` by a crash are marked stopped (`mark_orphaned_runs_stopped`) so the UI never lies about what is executing.

### Per-run allocation model

Runs do not share state. Each gets `allocation` dollars of virtual cash and tracks `cash / position / entry_price` in its own row. Ten strategies can trade one brokerage account concurrently; each sizes against its slice, and a runaway strategy's blast radius is its allocation. The trade-off — the broker's account-level position is the *sum* of run slices, so per-run P&L attribution stays app-side — is exactly what a multi-strategy desk wants.

### Approval queue (graduated autonomy)

Orders above a run's `auto_approve_below` threshold become rows in `pending_orders` instead of broker calls. The dashboard surfaces them for one-click approve/reject; approval executes through the same `_execute` path as autonomous orders (one code path, one audit format). A newer intent from the same run **supersedes** its stale pending order — the market has moved on, and executing a stale signal is worse than skipping it. Live runs default to `auto_approve_below = 0` (approve everything); paper runs default to unlimited autonomy.

## Broker abstraction (`broker/`)

`Broker` is a five-method ABC (`get_account`, `get_positions`, `get_bars`, `submit_order`, `get_orders`) with pydantic models as the currency. Everything Alpaca-specific — enums, request objects, the free IEX data feed, paper/live endpoints — lives in `alpaca.py` (~130 lines). A Binance or IBKR adapter is one new file; nothing upstream changes.

Adapters are synchronous by design: FastAPI runs sync endpoints in its threadpool, and the runner wraps calls in `asyncio.to_thread`. Broker SDKs are overwhelmingly sync; pretending otherwise buys complexity, not throughput, at single-user scale.

Live and paper are **separate broker instances with separate credentials**. Market data always flows through the paper client — identical data, and the live client's only job is orders.

## Persistence (`store.py`)

Four tables: `runs` (strategy, params, allocation, risk limits, live cash/position state), `activity` (append-only audit log: orders, alerts, errors, lifecycle), `settings` (key-value; currently the paper/live mode), `pending_orders` (approval queue).

Schema evolution is a `_MIGRATIONS` list of `(table, column, type)` applied idempotently on connect — a deliberate 10-line answer where Alembic would be overkill for an embedded single-user database.

## Mode switching & the live lock

The paper/live mode is a runtime setting, deliberately **not** a config value — a config typo must never mean real money. Enabling live requires, server-side enforced: (1) a separate `ALPACA_LIVE_*` key pair present in `.env`, and (2) the literal confirmation phrase `TRADE LIVE` in the request body. Without both, `POST /api/mode` returns 422. Dropping back to paper is always one click. Runs snapshot their mode at creation; flipping the global switch never silently re-targets an existing run.

## Frontend

React + TypeScript + Tailwind v4, kept intentionally thin: one zustand store, a typed API client, and a websocket that fans server state out every 5 seconds (with reconnect/backoff). Commands go over REST; state comes back over the socket — the UI never computes trading state, it renders what the backend asserts.

Charts are TradingView's `lightweight-charts` (candles + volume, equity curves). Alerts are in-app toasts driven by the same activity stream that lands in SQLite — the notification and the audit record are the same fact.

## Testing philosophy

31 tests, biased toward **hand-verifiable arithmetic** over snapshots:

- Backtester: exact entry/exit prices and P&L on constructed bar sequences; equity marked-to-close mid-trade; sizing math; drawdown against manual computation.
- Rails, via a scripted fake broker: notional capping, approval diversion (run state untouched until approval), approve-executes, supersede-on-new-signal, SL/TP triggers, daily-loss halt-and-flatten, the no-short invariant.
- Runner: fill-once-per-bar idempotency across restarts, orphan recovery.
- Loader: discovery, broken-file quarantine with surfaced errors, duplicate-id rejection.

End-to-end behavior (real Alpaca sandbox orders, websocket flows, UI states) is verified with Playwright and live API checks rather than mocks pretending to be the world.
