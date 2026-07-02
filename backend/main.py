"""Tradedesk backend — FastAPI app serving the local dashboard.

Run:  uv run uvicorn backend.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config, store
from .broker.alpaca import AlpacaBroker
from .broker.base import Broker
from .engine import registry
from .engine.backtest import BacktestResult, run_backtest
from .engine.runner import StrategyRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    stale = store.mark_orphaned_runs_stopped()
    if stale:
        store.log_activity("info", f"Marked {stale} run(s) from a previous session as stopped")
    yield
    await runner.stop_all()


app = FastAPI(title="Tradedesk", version="0.1.0", lifespan=lifespan)

# Dashboard dev server (Vite) runs on a different localhost port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def current_mode() -> str:
    return store.get_setting("mode", "paper")


@lru_cache
def _broker_for(mode: str) -> Broker:
    if mode == "live":
        if not config.has_live_keys():
            raise HTTPException(status_code=503, detail="Live keys (ALPACA_LIVE_API_KEY/SECRET) are not configured.")
        return AlpacaBroker(config.ALPACA_LIVE_API_KEY, config.ALPACA_LIVE_SECRET_KEY, paper=False)
    if not config.has_keys():
        raise HTTPException(
            status_code=503,
            detail="Alpaca API keys not configured. Copy .env.example to .env and add your paper keys.",
        )
    return AlpacaBroker(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)


def get_broker() -> Broker:
    """Broker for the mode the dashboard is currently in."""
    return _broker_for(current_mode())


def get_data_broker() -> Broker:
    """Market data always comes from the paper client — identical data, safer client."""
    return _broker_for("paper")


runner = StrategyRunner(_broker_for)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "broker": "alpaca",
        "keys_configured": config.has_keys(),
        "live_keys_configured": config.has_live_keys(),
        "mode": current_mode(),
    }


class ModeRequest(BaseModel):
    mode: str  # "paper" | "live"
    confirmation: str = ""


@app.post("/api/mode")
def set_mode(req: ModeRequest):
    if req.mode not in ("paper", "live"):
        raise HTTPException(status_code=422, detail="mode must be 'paper' or 'live'")
    if req.mode == "live":
        if not config.has_live_keys():
            raise HTTPException(
                status_code=422,
                detail="Live keys are not configured. Add ALPACA_LIVE_API_KEY / ALPACA_LIVE_SECRET_KEY to .env first.",
            )
        if req.confirmation != config.LIVE_CONFIRMATION_PHRASE:
            raise HTTPException(
                status_code=422,
                detail=f'Type "{config.LIVE_CONFIRMATION_PHRASE}" to confirm switching to real-money trading.',
            )
        store.log_activity("alert", "LIVE MODE ENABLED — new runs will trade real money", mode="live")
    else:
        store.log_activity("info", "Switched to paper mode")
    store.set_setting("mode", req.mode)
    return {"mode": req.mode}


@app.post("/api/emergency-stop")
async def emergency_stop(flatten: bool = Query(False)):
    return await runner.emergency_stop(flatten=flatten)


@app.get("/api/account")
def account():
    return get_broker().get_account()


@app.get("/api/positions")
def positions():
    return get_broker().get_positions()


@app.get("/api/orders")
def orders(limit: int = Query(100, le=500)):
    return get_broker().get_orders(limit=limit)


@app.get("/api/bars/{symbol}")
def bars(
    symbol: str,
    timeframe: str = Query("1Day"),
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = Query(500, le=10000),
):
    try:
        return get_data_broker().get_bars(symbol.upper(), timeframe, start, end, limit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/strategies")
def strategies():
    return registry.describe()


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: str
    timeframe: str = "1Day"
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    params: dict[str, float] = {}
    initial_cash: float = 100_000.0


@app.post("/api/backtest")
def backtest(req: BacktestRequest) -> BacktestResult:
    try:
        cls = registry.get_strategy(req.strategy_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        strategy = cls(**req.params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    bars = get_data_broker().get_bars(req.symbol.upper(), req.timeframe, req.start, req.end, limit=10_000)
    if len(bars) < max(strategy.warmup + 2, 10):
        raise HTTPException(
            status_code=422,
            detail=f"Not enough history for {req.symbol.upper()} ({len(bars)} bars; "
            f"strategy needs at least {strategy.warmup + 2}).",
        )
    df = pd.DataFrame([b.model_dump() for b in bars]).set_index("time").sort_index()
    try:
        return run_backtest(strategy, df, initial_cash=req.initial_cash)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# --- live runs (paper mode until M6) ---


class StartRunRequest(BaseModel):
    strategy_id: str
    symbol: str
    timeframe: str = "1Day"
    params: dict[str, float] = {}
    allocation: float = 10_000.0
    max_trade_size: Optional[float] = None
    max_daily_loss: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    auto_approve_below: Optional[float] = None  # None = fully autonomous


def _run_view(run: store.Run, json_mode: bool = False) -> dict:
    d = run.model_dump(mode="json" if json_mode else "python")
    d["active"] = run.id in runner.active_run_ids
    d["paused"] = runner.is_paused(run.id)
    return d


@app.get("/api/runs")
def list_runs():
    return [_run_view(r) for r in store.list_runs()]


@app.post("/api/runs")
async def start_run(req: StartRunRequest):
    # async so runner.start can create the task on the server's event loop
    get_broker()  # 503 early if keys are missing
    try:
        cls = registry.get_strategy(req.strategy_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    try:
        strategy = cls(**req.params)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if req.allocation <= 0:
        raise HTTPException(status_code=422, detail="allocation must be positive")

    mode = current_mode()
    limits = store.RiskLimits(
        max_trade_size=req.max_trade_size,
        max_daily_loss=req.max_daily_loss,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        # live runs default to approving EVERYTHING unless the user raises the threshold
        auto_approve_below=req.auto_approve_below if req.auto_approve_below is not None
        else (0.0 if mode == "live" else None),
    )
    run = store.create_run(req.strategy_id, req.symbol.upper(), req.timeframe, dict(strategy.p),
                           req.allocation, mode, limits)
    runner.start(run, strategy)
    return _run_view(run)


@app.post("/api/runs/{run_id}/pause")
def pause_run(run_id: str):
    try:
        runner.pause(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _run_view(store.get_run(run_id))


@app.post("/api/runs/{run_id}/resume")
def resume_run(run_id: str):
    runner.resume(run_id)
    return _run_view(store.get_run(run_id))


# --- manual approval queue ---


@app.get("/api/approvals")
def approvals():
    return store.list_pending_orders()


@app.post("/api/approvals/{order_id}/approve")
async def approve_order(order_id: int):
    try:
        pending = store.get_pending_order(order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if pending.status != "pending":
        raise HTTPException(status_code=409, detail=f"Order is already {pending.status}")
    await runner.execute_pending(pending)
    return {"status": "approved"}


@app.post("/api/approvals/{order_id}/reject")
def reject_order(order_id: int):
    try:
        pending = store.get_pending_order(order_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if pending.status != "pending":
        raise HTTPException(status_code=409, detail=f"Order is already {pending.status}")
    store.set_pending_order_status(order_id, "rejected")
    store.log_activity("info", f"Rejected: {pending.side} {pending.qty} {pending.symbol}",
                       run_id=pending.run_id, symbol=pending.symbol, mode=pending.mode)
    return {"status": "rejected"}


@app.delete("/api/runs/{run_id}")
async def stop_run(run_id: str):
    try:
        store.get_run(run_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await runner.stop(run_id)
    return _run_view(store.get_run(run_id))


@app.get("/api/activity")
def activity(limit: int = Query(200, le=1000)):
    return store.list_activity(limit)


# --- websocket: pushes dashboard state every few seconds ---


@app.websocket("/ws")
async def ws(socket: WebSocket):
    await socket.accept()
    try:
        while True:
            payload: dict = {
                "runs": [_run_view(r, json_mode=True) for r in store.list_runs()],
                "activity": [a.model_dump(mode="json") for a in store.list_activity(30)],
                "approvals": [p.model_dump(mode="json") for p in store.list_pending_orders()],
                "keys_configured": config.has_keys(),
                "live_keys_configured": config.has_live_keys(),
                "mode": current_mode(),
            }
            if config.has_keys():
                try:
                    broker = get_broker()
                    account, positions = await asyncio.gather(
                        asyncio.to_thread(broker.get_account),
                        asyncio.to_thread(broker.get_positions),
                    )
                    payload["account"] = account.model_dump()
                    payload["positions"] = [p.model_dump() for p in positions]
                except Exception:
                    pass  # keep pushing runs/activity even if the broker hiccups
            await socket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
