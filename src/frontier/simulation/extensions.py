"""Stages loaded by name rather than by import — ARCH ADR-13.

A system whose existence must not be inferable cannot appear in the import graph of the thing
that runs it. Optional stages are therefore named in configuration and resolved at runtime, so
`tick.py` never mentions them and neither does a stack trace pasted into a public bug report.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any

log = logging.getLogger(__name__)


def load(paths: tuple[str, ...]) -> tuple[Any, ...]:
    """Resolve `package.module:factory` entries, skipping any that are not installed."""
    stages: list[Any] = []
    for path in paths:
        module_name, _, factory_name = path.partition(":")
        try:
            module = import_module(module_name)
        except ModuleNotFoundError:
            log.debug("optional stage not installed", extra={"stage": module_name})
            continue
        stages.append(getattr(module, factory_name or "stage")())
    return tuple(stages)
