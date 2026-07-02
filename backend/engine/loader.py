"""Discovers user strategies: any Strategy subclass in a .py file under strategies/.

Files are re-scanned on every call, so dropping a new file in the folder makes it
appear in the dashboard without restarting the backend. A broken file never takes
the app down — it's skipped and reported.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .strategy import Strategy


def discover(directory: Path) -> tuple[list[type[Strategy]], list[str]]:
    """Returns (strategy classes, human-readable load errors)."""
    found: list[type[Strategy]] = []
    errors: list[str] = []
    if not directory.is_dir():
        return found, errors

    for path in sorted(directory.glob("*.py")):
        if path.name.startswith("_"):
            continue
        module_name = f"tradedesk_user_strategies.{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            # register so dataclasses/pickling/inspect inside user code behave
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as e:
            errors.append(f"{path.name}: {type(e).__name__}: {e}")
            sys.modules.pop(module_name, None)
            continue

        for obj in vars(module).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Strategy)
                and obj is not Strategy
                and obj.__module__ == module_name  # defined here, not imported
            ):
                found.append(obj)

    return found, errors
