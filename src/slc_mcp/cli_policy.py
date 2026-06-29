import os
import re


class CLIPolicyViolation(Exception):
    pass


DEFAULT_DENY_COMMANDS: frozenset[str] = frozenset(
    {
        "factory-reset",
        "write erase",
        "erase startup-config",
        "erase flash",
        "reload",
        "reboot",
        "format",
        "shutdown",
        "power off",
        "reset system",
        "init 0",
        "halt",
    }
)

_READ_PREFIXES = (
    "show",
    "get",
    "list",
    "display",
    "status",
    "ping",
    "traceroute",
    "whois",
    "version",
    "help",
    "?",
    "dir",
    "more",
    "type",
    "diag",
)


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name, "").lower()
    if val in ("true", "1", "yes"):
        return True
    if val in ("false", "0", "no"):
        return False
    return default


def cli_write_enabled() -> bool:
    return _env_bool("SLC_CLI_WRITE_ENABLED", False)


def check_command(
    command: str,
    *,
    write_enabled: bool | None = None,
    yolo: bool | None = None,
    max_length: int | None = None,
    deny: frozenset[str] | None = None,
    permit: frozenset[str] | None = None,
) -> None:
    """Validate a CLI command against server policy. Raises CLIPolicyViolation if blocked.

    All keyword args override their corresponding env var for testability.
    """
    _write = write_enabled if write_enabled is not None else _env_bool("SLC_CLI_WRITE_ENABLED", False)
    _yolo = yolo if yolo is not None else _env_bool("SLC_CLI_YOLO", False)
    _max = max_length if max_length is not None else int(os.getenv("SLC_CLI_MAX_LENGTH", "512"))
    _deny = deny if deny is not None else (
        DEFAULT_DENY_COMMANDS
        | {c.strip().lower() for c in os.getenv("SLC_CLI_DENY_COMMANDS", "").split(",") if c.strip()}
    )
    _permit_raw = os.getenv("SLC_CLI_PERMIT_COMMANDS", "")
    _permit = permit if permit is not None else {
        c.strip().lower() for c in _permit_raw.split(",") if c.strip()
    }

    if not command or not command.strip():
        raise CLIPolicyViolation("Empty command is not allowed.")

    if len(command) > _max:
        raise CLIPolicyViolation(
            f"Command exceeds maximum length of {_max} characters ({len(command)} given)."
        )

    if _yolo:
        return

    normalized = re.sub(r"\s+", " ", command.strip().lower())

    for blocked in _deny:
        if normalized == blocked or normalized.startswith(blocked + " "):
            raise CLIPolicyViolation(
                f"Command '{command}' is blocked by the built-in deny list. "
                "Set SLC_CLI_DENY_COMMANDS to customize or SLC_CLI_YOLO=true to disable all filtering."
            )

    is_read = any(normalized == p or normalized.startswith(p + " ") for p in _READ_PREFIXES)

    if not _write and not is_read:
        raise CLIPolicyViolation(
            f"Command '{command}' is a write command and write access is disabled. "
            "Set SLC_CLI_WRITE_ENABLED=true on the server to allow write commands."
        )

    if _permit:
        if not any(normalized == p or normalized.startswith(p + " ") for p in _permit):
            raise CLIPolicyViolation(
                f"Command '{command}' is not in the permitted command list. "
                "See SLC_CLI_PERMIT_COMMANDS to configure the allowlist."
            )
