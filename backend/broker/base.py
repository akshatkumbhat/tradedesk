"""Broker abstraction — every broker (Alpaca today, others later) implements this interface.

Methods are synchronous; FastAPI runs them in its threadpool and the strategy
runner wraps them with asyncio.to_thread.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

Side = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]


class Bar(BaseModel):
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class Account(BaseModel):
    equity: float
    cash: float
    buying_power: float
    currency: str = "USD"
    paper: bool = True


class Position(BaseModel):
    symbol: str
    qty: float
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pl: float
    unrealized_pl_pct: float


class OrderRequest(BaseModel):
    symbol: str
    qty: float
    side: Side
    type: OrderType = "market"
    limit_price: Optional[float] = None


class Order(BaseModel):
    id: str
    symbol: str
    qty: float
    side: Side
    type: OrderType
    status: str
    filled_qty: float = 0.0
    filled_avg_price: Optional[float] = None
    submitted_at: Optional[datetime] = None


class Broker(ABC):
    """Interface every broker adapter implements."""

    name: str

    @abstractmethod
    def get_account(self) -> Account: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def get_bars(
        self,
        symbol: str,
        timeframe: str,  # "1Min" | "5Min" | "15Min" | "1Hour" | "1Day"
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 500,
    ) -> list[Bar]: ...

    @abstractmethod
    def submit_order(self, req: OrderRequest) -> Order: ...

    @abstractmethod
    def get_orders(self, limit: int = 100) -> list[Order]: ...
