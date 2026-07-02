# Tradedesk

Local-first trading software. Python/FastAPI backend + React dashboard, connected to Alpaca (paper by default). Everything runs and stays on your machine — the only network calls are to your broker.

## Quick start

```sh
# 1. keys (free): https://app.alpaca.markets -> Paper account -> API Keys
cp .env.example .env            # paste keys in

# 2. backend (http://localhost:8000)
uv run uvicorn backend.main:app --port 8000

# 3. dashboard (http://localhost:5173)
cd frontend && npm run dev
```

Tests: `uv run pytest backend/tests`

## System design

```
Browser (React dashboard) ── /api + /ws (localhost proxy) ──> FastAPI backend
                                                                 │
                                              ┌──────────────────┼────────────────┐
                                        StrategyRunner      Backtester        SQLite
                                        (async task/run)    (bar replay)   (runs, activity)
                                                 │
                                          Broker interface
                                                 │
                                          Alpaca adapter ──> Alpaca API (paper | live)
```

- **Broker abstraction** (`backend/broker/base.py`): all broker-specific code lives in one adapter class. Adding Binance/IBKR/Coinbase = one new file implementing `get_account / get_positions / get_bars / submit_order / get_orders`.
- **One strategy API everywhere**: `on_bar(ctx)` sees history up to the current bar and calls `ctx.buy/sell/close`. Identical in backtests and live runs — a backtested strategy runs unmodified.
- **Per-run allocation**: each running strategy gets its own cash slice and position tracking, so several strategies share one account without collisions.
- **Fill semantics** (backtest): signal on close, fill at next bar's open, long-only, ~95%-of-cash default sizing. Live runs mirror this with market orders.

## Folder structure

```
tradedesk/
├── backend/
│   ├── main.py                  # FastAPI app: REST + /ws websocket
│   ├── config.py                # .env loading; paper-mode default
│   ├── store.py                 # SQLite: runs + activity log
│   ├── broker/
│   │   ├── base.py              # Broker ABC + Bar/Account/Position/Order models
│   │   └── alpaca.py            # Alpaca adapter (IEX free data feed)
│   ├── engine/
│   │   ├── strategy.py          # Strategy base class + Context
│   │   ├── backtest.py          # bar-replay backtester + stats
│   │   ├── runner.py            # live runner: one async task per run
│   │   ├── loader.py            # discovers user strategies in strategies/
│   │   ├── registry.py          # built-ins + discovered, id-collision safe
│   │   └── indicators.py        # SMA, RSI (Wilder)
│   ├── builtin_strategies/      # SMA crossover, RSI mean-reversion
│   └── tests/                   # 23 pytest tests
├── strategies/                  # YOUR strategies — drop .py files here
│   └── example_momentum.py      # commented template
├── frontend/src/
│   ├── App.tsx                  # layout + page switch + ws bootstrap
│   ├── api.ts                   # typed API client
│   ├── store.ts                 # zustand store + websocket client
│   ├── components/              # Sidebar, Header, CandleChart, EquityChart…
│   └── pages/                   # Overview, Strategies, Chart, Backtest, Activity
├── .env                         # broker keys (gitignored, local only)
└── tradedesk.db                 # SQLite (gitignored, local only)
```

## Database schema (SQLite, `tradedesk.db`)

```sql
runs (                            -- one row per strategy run
  id TEXT PK, strategy_id, symbol, timeframe,
  params TEXT (json), allocation REAL,
  status TEXT,                    -- running | stopped | error
  error TEXT, mode TEXT,          -- paper | live
  started_at, stopped_at,
  cash REAL, position REAL, entry_price REAL,   -- the run's slice of the account
  last_bar_time TEXT              -- idempotency: one evaluation per closed bar
)
activity (                        -- append-only audit log
  id INTEGER PK, run_id, time, kind,   -- order | info | error
  symbol, side, qty, price, status, mode, detail
)
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, keys present, paper/live mode |
| GET | `/api/account` | equity, cash, buying power |
| GET | `/api/positions` | open positions w/ unrealized P&L |
| GET | `/api/orders` | broker order history |
| GET | `/api/bars/{symbol}` | OHLCV candles (`timeframe`, `start`, `end`, `limit`) |
| GET | `/api/strategies` | built-in + discovered strategies (+ load errors) |
| POST | `/api/backtest` | run a backtest → stats, equity curve, trades |
| GET/POST | `/api/runs` | list / start a live run |
| DELETE | `/api/runs/{id}` | stop a run |
| GET | `/api/activity` | audit log |
| WS | `/ws` | pushes account, positions, runs, activity every 5s |

## GUI layout

Sidebar (Overview · Strategies · Chart · Backtest · Activity) + header with Paper/Live badge and backend-connection dot. Apple-style: `#f5f5f7` canvas, white rounded-2xl cards, SF system font, `#0071e3` accent, system green/red for P&L.

- **Overview** — equity/cash/buying-power cards, positions table
- **Strategies** — one card per strategy: params, symbol/timeframe/allocation, Start; active runs show live position + Stop
- **Chart** — candlesticks + volume (lightweight-charts), symbol search, timeframe switch
- **Backtest** — strategy/symbol/params → stat tiles (return, CAGR, Sharpe, max DD, win rate), equity curve, trade list
- **Activity** — every order/info/error, paper vs live tagged

## Writing your own strategy

Copy `strategies/example_momentum.py`, rename the class and `id`, edit `on_bar`. Refresh the browser — it appears on the Strategies page and in the Backtest picker. Broken files are skipped and the error shown in the UI.

## Safety

- **Paper by default.** Live mode requires separate live keys in `.env` AND typing `TRADE LIVE` in the dashboard. Without live keys, live mode cannot be enabled at all.
- **Manual approval**: live runs queue every order for your one-click approval; raise "auto-approve under $X" per run to let small orders through autonomously. Paper runs are autonomous unless you set a threshold.
- **Per-run rails** (all optional): max trade size ($ cap per order), max daily loss ($ — flattens and halts the run), stop-loss %, take-profit % (checked each closed bar).
- **Emergency stop**: header "Stop All" halts every strategy, optionally selling all positions at market.
- **Alerts**: rail trips, approvals, and halts pop as in-app toasts and land in the Activity log.
- Keys live in `.env` on this machine only; all history is in a local SQLite file.

Endpoints added by the safety layer: `POST /api/mode`, `POST /api/emergency-stop`, `POST /api/runs/{id}/pause|resume`, `GET /api/approvals`, `POST /api/approvals/{id}/approve|reject`.
