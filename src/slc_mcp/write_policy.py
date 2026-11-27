"""Read-only mode and the write window.

Every tool is either a read tool (no effect on the device or on this server's
state) or a write tool. Two settings decide whether write tools are available:

- MCP_READ_ONLY: true registers read tools only. A call to a write tool by name
  is refused, and SLC_CLI_WRITE_ENABLED is treated as false. Default false.
- MCP_WRITES_UNTIL: epoch seconds, honored only when MCP_READ_ONLY is false.
  Write tools work until that time and are refused after it. A time already in
  the past at start-up means read-only.

Both settings fail closed: a value that can't be parsed means read-only.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping

log = logging.getLogger(__name__)

READ_ONLY_ENV = "MCP_READ_ONLY"
WRITES_UNTIL_ENV = "MCP_WRITES_UNTIL"

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("", "0", "false", "no", "off")

# Wall clock used for the write window. Tests replace it.
clock: Callable[[], float] = time.time


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def read_only(env: Mapping[str, str] | None = None) -> bool:
    """True when MCP_READ_ONLY is set to a true value, or to anything unrecognized."""
    value = (_env(env).get(READ_ONLY_ENV) or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    log.error("%s=%r is not true or false; running read-only.", READ_ONLY_ENV, value)
    return True


class _Invalid:
    pass


_INVALID = _Invalid()


def _parse_writes_until(env: Mapping[str, str] | None) -> float | None | _Invalid:
    raw = (_env(env).get(WRITES_UNTIL_ENV) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return _INVALID
    if value != value or value in (float("inf"), float("-inf")):
        return _INVALID
    return value


def writes_until(env: Mapping[str, str] | None = None) -> float | None:
    """The write window's end in epoch seconds, or None when there is no window.

    An unparseable value returns 0.0, a time in the past, so writes stay off.
    """
    value = _parse_writes_until(env)
    if isinstance(value, _Invalid):
        log.error(
            "%s=%r is not a number of epoch seconds; write tools are off.",
            WRITES_UNTIL_ENV,
            _env(env).get(WRITES_UNTIL_ENV),
        )
        return 0.0
    return value


def writes_allowed(env: Mapping[str, str] | None = None, now: float | None = None) -> bool:
    """True when write tools may run right now."""
    if read_only(env):
        return False
    until = writes_until(env)
    if until is None:
        return True
    return (clock() if now is None else now) < until


def describe(env: Mapping[str, str] | None = None) -> str:
    """One line for the start-up log saying whether write tools are on."""
    if read_only(env):
        return f"write tools off ({READ_ONLY_ENV} is true)"
    until = writes_until(env)
    if until is None:
        return "write tools on"
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(until))
    if clock() >= until:
        return f"write tools off ({WRITES_UNTIL_ENV} {stamp} has passed)"
    return f"write tools on until {stamp} ({WRITES_UNTIL_ENV})"


def refusal(tool_name: str) -> str:
    """The error text for a write tool called while writes are off."""
    return (
        f"{tool_name} changes the device or the server, and this server is read-only "
        f"right now. Write tools are turned on by the server's operator ({READ_ONLY_ENV}, "
        f"{WRITES_UNTIL_ENV}), not by the client."
    )
