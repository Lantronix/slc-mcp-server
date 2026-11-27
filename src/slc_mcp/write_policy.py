"""Read-only mode and the write window.

Every tool is either a read tool (no effect on the device or on this server's
state) or a write tool. Two settings decide whether write tools are available:

- MCP_READ_ONLY: true registers read tools only. A call to a write tool by name
  is refused, and SLC_CLI_WRITE_ENABLED is treated as false. Default false.
- MCP_WRITES_UNTIL: whole epoch seconds, honored only when MCP_READ_ONLY is
  false, at most 7 days after start-up. Write tools work until that time and
  are refused after it. A time already in the past at start-up means read-only.

Both settings fail closed: a value that can't be used means read-only.
"""
from __future__ import annotations

import logging
import os
import re
import time
from collections.abc import Callable, Mapping

log = logging.getLogger(__name__)

READ_ONLY_ENV = "MCP_READ_ONLY"
WRITES_UNTIL_ENV = "MCP_WRITES_UNTIL"

# A write window longer than this from start-up is refused as a mistake.
MAX_WINDOW_SECONDS = 7 * 24 * 3600
# Epoch seconds stay below this until the year 2286; a larger value is almost
# certainly milliseconds.
MAX_EPOCH_SECONDS = 10_000_000_000

_TRUE = ("1", "true", "yes", "on")
_FALSE = ("", "0", "false", "no", "off")
_INTEGER = re.compile(r"[+-]?[0-9]+")

# Wall and monotonic clocks used for the write window. Tests replace them and
# call mark_start().
clock: Callable[[], float] = time.time
monotonic: Callable[[], float] = time.monotonic

_start_wall: float = clock()
_start_mono: float = monotonic()
_logged: set[tuple[str, str]] = set()


def mark_start() -> None:
    """Record the start-up time the write window is measured from."""
    global _start_wall, _start_mono
    _start_wall = clock()
    _start_mono = monotonic()


def _env(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _log_once(name: str, value: str, reason: str) -> None:
    if (name, value) not in _logged:
        _logged.add((name, value))
        log.error("%s=%r %s; write tools are off.", name, value, reason)


def read_only(env: Mapping[str, str] | None = None) -> bool:
    """True when MCP_READ_ONLY is set to a true value, or to anything unrecognized."""
    value = (_env(env).get(READ_ONLY_ENV) or "").strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    _log_once(READ_ONLY_ENV, value, "is not true or false")
    return True


def writes_until(env: Mapping[str, str] | None = None) -> int | None:
    """The write window's end in epoch seconds, or None when there is no window.

    A value that isn't a whole number of epoch seconds, is above 1e10 (likely
    milliseconds), or ends more than 7 days after start-up returns 0, a time in
    the past, so writes stay off. Nothing here raises on a bad value.
    """
    raw = (_env(env).get(WRITES_UNTIL_ENV) or "").strip()
    if not raw:
        return None
    if len(raw) > 20 or not _INTEGER.fullmatch(raw):
        _log_once(WRITES_UNTIL_ENV, raw, "is not a whole number of epoch seconds")
        return 0
    value = int(raw)
    if value > MAX_EPOCH_SECONDS:
        _log_once(WRITES_UNTIL_ENV, raw, "is above 1e10, so it looks like milliseconds, not seconds")
        return 0
    if value - _start_wall > MAX_WINDOW_SECONDS:
        _log_once(WRITES_UNTIL_ENV, raw, "is more than 7 days after start-up")
        return 0
    return value


def seconds_left(env: Mapping[str, str] | None = None) -> float | None:
    """Seconds until the write window closes: None with no window, 0 or less once closed.

    The window closes at the earlier of the wall-clock deadline and the same
    distance from start-up on the monotonic clock, so neither a wall-clock change
    nor a suspended host stretches it.
    """
    until = writes_until(env)
    if until is None:
        return None
    by_wall = until - clock()
    by_mono = (_start_mono + (until - _start_wall)) - monotonic()
    return min(by_wall, by_mono)


def writes_allowed(env: Mapping[str, str] | None = None) -> bool:
    """True when write tools may run right now."""
    if read_only(env):
        return False
    left = seconds_left(env)
    return left is None or left > 0


def describe(env: Mapping[str, str] | None = None) -> str:
    """One line for the start-up log saying whether write tools are on."""
    if read_only(env):
        return f"write tools off ({READ_ONLY_ENV} is true)"
    until = writes_until(env)
    if until is None:
        return "write tools on"
    if not writes_allowed(env):
        return f"write tools off ({WRITES_UNTIL_ENV} has passed or isn't valid)"
    try:
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(until))
    except (OverflowError, OSError, ValueError):
        stamp = str(until)
    return f"write tools on until {stamp} ({WRITES_UNTIL_ENV})"


def refusal(tool_name: str) -> str:
    """The error text for a write tool called while writes are off."""
    return (
        f"{tool_name} changes the device or the server, and this server is read-only "
        f"right now. Write tools are turned on by the server's operator ({READ_ONLY_ENV}, "
        f"{WRITES_UNTIL_ENV}), not by the client."
    )
