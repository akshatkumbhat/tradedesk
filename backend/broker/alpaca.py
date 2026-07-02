"""Alpaca adapter. Paper endpoint by default; live only via the runtime toggle (M6).

Market data uses the free IEX feed so no paid data subscription is required.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, LimitOrderRequest, MarketOrderRequest

from .base import Account, Bar, Broker, Order, OrderRequest, Position

_TIMEFRAMES = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}


class AlpacaBroker(Broker):
    name = "alpaca"

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.paper = paper
        self._trading = TradingClient(api_key, secret_key, paper=paper)
        self._data = StockHistoricalDataClient(api_key, secret_key)

    def get_account(self) -> Account:
        a = self._trading.get_account()
        return Account(
            equity=float(a.equity),
            cash=float(a.cash),
            buying_power=float(a.buying_power),
            currency=a.currency or "USD",
            paper=self.paper,
        )

    def get_positions(self) -> list[Position]:
        out = []
        for p in self._trading.get_all_positions():
            out.append(
                Position(
                    symbol=p.symbol,
                    qty=float(p.qty),
                    avg_entry_price=float(p.avg_entry_price),
                    current_price=float(p.current_price or 0),
                    market_value=float(p.market_value or 0),
                    unrealized_pl=float(p.unrealized_pl or 0),
                    unrealized_pl_pct=float(p.unrealized_plpc or 0) * 100,
                )
            )
        return out

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "1Day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[Bar]:
        tf = _TIMEFRAMES.get(timeframe)
        if tf is None:
            raise ValueError(f"Unsupported timeframe {timeframe!r}; use one of {list(_TIMEFRAMES)}")
        if start is None:
            # sensible default window per timeframe
            days = {"1Min": 2, "5Min": 7, "15Min": 14, "1Hour": 60, "1Day": 365 * 2}[timeframe]
            start = datetime.now(timezone.utc) - timedelta(days=days)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=tf,
            start=start,
            end=end,
            limit=limit,
            feed="iex",  # free feed — no SIP subscription needed
        )
        bars = self._data.get_stock_bars(req).data.get(symbol, [])
        return [
            Bar(time=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.volume)
            for b in bars
        ]

    def submit_order(self, req: OrderRequest) -> Order:
        side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL
        if req.type == "limit":
            alpaca_req = LimitOrderRequest(
                symbol=req.symbol, qty=req.qty, side=side,
                time_in_force=TimeInForce.DAY, limit_price=req.limit_price,
            )
        else:
            alpaca_req = MarketOrderRequest(
                symbol=req.symbol, qty=req.qty, side=side, time_in_force=TimeInForce.DAY,
            )
        return self._to_order(self._trading.submit_order(alpaca_req))

    def get_orders(self, limit: int = 100) -> list[Order]:
        req = GetOrdersRequest(status="all", limit=limit)
        return [self._to_order(o) for o in self._trading.get_orders(req)]

    @staticmethod
    def _to_order(o) -> Order:
        return Order(
            id=str(o.id),
            symbol=o.symbol,
            qty=float(o.qty or 0),
            side=o.side.value,
            type=o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
            status=o.status.value if hasattr(o.status, "value") else str(o.status),
            filled_qty=float(o.filled_qty or 0),
            filled_avg_price=float(o.filled_avg_price) if o.filled_avg_price else None,
            submitted_at=o.submitted_at,
        )
