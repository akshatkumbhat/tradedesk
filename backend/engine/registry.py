"""Strategy registry — built-ins plus user strategies discovered in strategies/."""
from __future__ import annotations

from .. import config
from ..builtin_strategies.rsi_reversion import RsiReversion
from ..builtin_strategies.sma_cross import SmaCross
from . import loader
from .strategy import Strategy

_BUILTINS: list[type[Strategy]] = [SmaCross, RsiReversion]


def all_strategies() -> tuple[list[type[Strategy]], list[str]]:
    """(strategies, load_errors). User files are re-scanned on every call so new
    drops show up without a restart; built-ins win id collisions."""
    strategies = list(_BUILTINS)
    seen = {cls.id for cls in strategies}
    discovered, errors = loader.discover(config.STRATEGIES_DIR)
    for cls in discovered:
        if cls.id in seen:
            errors.append(f"{cls.__name__}: duplicate strategy id {cls.id!r} — skipped")
            continue
        seen.add(cls.id)
        strategies.append(cls)
    return strategies, errors


def get_strategy(strategy_id: str) -> type[Strategy]:
    strategies, _ = all_strategies()
    for cls in strategies:
        if cls.id == strategy_id:
            return cls
    raise KeyError(f"Unknown strategy: {strategy_id!r}")


def describe() -> dict:
    strategies, errors = all_strategies()
    return {
        "strategies": [
            {
                "id": cls.id,
                "name": cls.name,
                "description": cls.description,
                "params": cls.params,
                "builtin": cls in _BUILTINS,
            }
            for cls in strategies
        ],
        "errors": errors,
    }
