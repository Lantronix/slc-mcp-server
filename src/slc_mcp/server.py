import asyncio
import functools
import logging
import os
import re
import sys
import time
import weakref

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from mcp.types import ToolAnnotations

load_dotenv()
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)


mcp = FastMCP("slc-mcp-server")

from slc_mcp import cli_policy, client, write_policy
from slc_mcp.cli_policy import CLIPolicyViolation
from slc_mcp.providers import CredentialError, get_provider
from slc_mcp.session import SessionManager

_sessions = SessionManager()

# ---------------------------------------------------------------------------
# Read and write tools
# ---------------------------------------------------------------------------
# Every tool is declared with @read_tool or @write_tool, never with mcp.tool
# directly. A write tool changes the device, its sessions, or this server's own
# state. Read-only mode (MCP_READ_ONLY) registers read tools only, and the write
# window (MCP_WRITES_UNTIL) turns write tools off at a set time. See write_policy.

READ_ANNOTATIONS = ToolAnnotations(readOnlyHint=True)
WRITE_ANNOTATIONS = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

READ_TOOLS: set[str] = set()
WRITE_TOOLS: set[str] = set()

# Decided once, at import: write tools are registered only if writes are allowed
# at start-up. The write window can close them later; nothing reopens them
# without a restart.
write_policy.mark_start()
WRITES_AT_START = write_policy.writes_allowed()
log.info("slc-mcp-server: %s", write_policy.describe())


def read_tool(fn):
    """Register fn as a read tool (readOnlyHint true)."""
    READ_TOOLS.add(fn.__name__)
    mcp.tool(annotations=READ_ANNOTATIONS)(fn)
    return fn


def write_tool(fn):
    """Register fn as a write tool (readOnlyHint false, destructiveHint true).

    Not registered at all when writes are off at start-up. The returned function
    also refuses to run while writes are off, so a direct call is refused too.
    """
    name = fn.__name__
    WRITE_TOOLS.add(name)

    @functools.wraps(fn)
    def guarded(*args, **kwargs):
        if not write_policy.writes_allowed():
            return client._err(write_policy.refusal(name))
        return fn(*args, **kwargs)

    if WRITES_AT_START:
        mcp.tool(annotations=WRITE_ANNOTATIONS)(guarded)
    return guarded


def _write_gate(name: str) -> dict | None:
    """An error dict when writes are off. Multi-step write tools call it before each device write."""
    if not write_policy.writes_allowed():
        return client._err(write_policy.refusal(name))
    return None


# Sessions that have sent at least one message, so a tools/list_changed
# notification can reach each of them when the write window closes.
_live_sessions: weakref.WeakSet = weakref.WeakSet()


class WritePolicyMiddleware(Middleware):
    """Refuses write tool calls by name while writes are off.

    Runs before the tool lookup, so a client with a cached tool list gets a
    clear "read-only" error rather than "unknown tool".
    """

    async def on_message(self, context, call_next):
        _start_write_timer()
        ctx = context.fastmcp_context
        if ctx is not None and ctx.request_context is not None:
            try:
                _live_sessions.add(ctx.session)
            except (RuntimeError, TypeError):
                pass
        return await call_next(context)

    async def on_call_tool(self, context, call_next):
        name = context.message.name
        if name in WRITE_TOOLS and not write_policy.writes_allowed():
            raise ToolError(write_policy.refusal(name))
        return await call_next(context)

    async def on_list_tools(self, context, call_next):
        # Catches a window that closed while the timer slept (host suspend, clock change).
        if WRITES_AT_START and not _write_window_closed and not write_policy.writes_allowed():
            await close_write_window()
        return await call_next(context)


mcp.add_middleware(WritePolicyMiddleware())

_write_window_closed = False


async def close_write_window() -> None:
    """Disable every write tool and tell connected clients the tool list changed."""
    global _write_window_closed
    if _write_window_closed:
        return
    _write_window_closed = True
    mcp.disable(names=set(WRITE_TOOLS))
    log.info("slc-mcp-server: %s passed, write tools disabled", write_policy.WRITES_UNTIL_ENV)
    for session in list(_live_sessions):
        try:
            await session.send_tool_list_changed()
        except Exception as exc:  # a closed session must not stop the others
            log.debug("tools/list_changed not delivered: %s", exc)


async def enforce_write_window(sleep=asyncio.sleep, max_step: float = 60.0) -> None:
    """Wait for MCP_WRITES_UNTIL, then close the write window.

    Sleeps in steps of at most max_step seconds and re-reads both clocks after
    each, so a host clock change or suspend is honored.
    """
    if not WRITES_AT_START or write_policy.read_only():
        return
    if write_policy.seconds_left() is None:
        return
    while True:
        remaining = write_policy.seconds_left()
        if remaining is None or remaining <= 0:
            break
        await sleep(min(remaining, max_step))
    await close_write_window()


_write_timer: asyncio.Task | None = None


def _start_write_timer() -> None:
    """Start enforce_write_window once per event loop, on the first message.

    Started from middleware rather than a server lifespan, so an application
    that mounts mcp.http_app() without running its lifespan still works.
    """
    global _write_timer
    if not WRITES_AT_START or _write_window_closed:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _write_timer is not None and not _write_timer.done() and _write_timer.get_loop() is loop:
        return
    _write_timer = loop.create_task(enforce_write_window())

_SENSITIVE_CLI_PATTERN = re.compile(r"\b(password|secret|token|community|snmp)\b", re.IGNORECASE)


def _redact_command(cmd: str) -> str:
    """Redact an entire CLI command if it references a sensitive keyword."""
    return "[REDACTED]" if _SENSITIVE_CLI_PATTERN.search(cmd) else cmd


def _audit(tool_name: str, device_id: str, **details) -> None:
    """Greppable audit line for a device-modifying tool. Call only after the
    confirm/policy gate passes, right before the outbound device call."""
    detail_str = " ".join(f"{k}={v}" for k, v in details.items())
    log.info("AUDIT tool=%s device_id=%s %s", tool_name, device_id, detail_str)


def _check_cli_write(tool_name: str) -> dict | None:
    """Return an error dict if CLI write access is disabled, else return None."""
    if not cli_policy.cli_write_enabled():
        return client._err(
            f"{tool_name} sends write commands to the device. "
            "Set SLC_CLI_WRITE_ENABLED=true on the server to enable this tool."
        )
    return None


def _call_get(device_id: str, path: str) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.get(session, path)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


def _call_post(device_id: str, path: str, body: dict | None = None) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.post(session, path, body)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


def _call_put(device_id: str, path: str, body: dict | None = None) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.put(session, path, body)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


def _call_delete(device_id: str, path: str) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.delete(session, path)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


def _call_patch(device_id: str, path: str, body: dict | None = None) -> dict:
    try:
        session = _sessions.get_or_create(device_id)
    except CredentialError as exc:
        return client._err(str(exc))
    result = client.patch(session, path, body)
    if not result["ok"] and result.get("status_code") == 401:
        _sessions.invalidate(device_id)
    return result


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

@write_tool
def configure_provider(provider: str) -> dict:
    """Switch the active credential provider and clear all cached sessions.
    Valid values: env, percepxion, vault, aws, azure, cyberark, command."""
    if REMOTE_TRANSPORT:
        # One process serves every remote client: one of them must not change where the
        # credentials for all of them come from. Set SLC_CREDENTIAL_PROVIDER instead.
        return client._err(
            "configure_provider is disabled on the HTTP transports. Set "
            "SLC_CREDENTIAL_PROVIDER in the server's environment and restart it."
        )
    valid = ("env", "percepxion", "vault", "aws", "azure", "cyberark", "command")
    if provider not in valid:
        return client._err(
            f"Invalid provider {provider!r}. Valid values: {', '.join(valid)}"
        )
    previous = os.environ.get("SLC_CREDENTIAL_PROVIDER")
    os.environ["SLC_CREDENTIAL_PROVIDER"] = provider
    try:
        new_provider = get_provider()
    except CredentialError as exc:
        if previous is None:
            os.environ.pop("SLC_CREDENTIAL_PROVIDER", None)
        else:
            os.environ["SLC_CREDENTIAL_PROVIDER"] = previous
        return client._err(f"Provider {provider!r} failed to initialize: {exc}")
    _sessions.set_provider(new_provider)
    return client._ok({"provider": provider, "sessions_cleared": True})


# ---------------------------------------------------------------------------
# Auth & Sessions
# ---------------------------------------------------------------------------

@write_tool
def logout_device(device_id: str) -> dict:
    """Invalidate the current API session token for the device."""
    return _call_delete(device_id, "/user/login")


@read_tool
def get_sessions(device_id: str) -> dict:
    """List all active sessions (web UI, API, WebTerm) on the device."""
    return _call_get(device_id, "/sessions")


@read_tool
def get_session(device_id: str, session_id: str) -> dict:
    """Get details for a specific active session by session ID."""
    return _call_get(device_id, f"/sessions/{session_id}")


@write_tool
def terminate_session(device_id: str, session_id: str, confirm: bool = False) -> dict:
    """Forcibly terminate an active session by session ID. Requires confirm=True."""
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to terminate this session."}
    return _call_delete(device_id, f"/sessions/{session_id}")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@read_tool
def get_system_status(device_id: str) -> dict:
    """Get system status for an SLC device."""
    return _call_get(device_id, "/system/status")


@read_tool
def get_system_version(device_id: str) -> dict:
    """Get firmware and software version information for an SLC device."""
    return _call_get(device_id, "/system/version")


@read_tool
def get_system_identity(device_id: str) -> dict:
    """Get device identity: hostname, description, contact, location."""
    return _call_get(device_id, "/system/identity")


@write_tool
def update_system_identity(
    device_id: str,
    hostname: str | None = None,
    description: str | None = None,
    confirm: bool = False,
) -> dict:
    """Update device hostname or description. Requires confirm=True.

    Pass only the fields you want to change. Both are optional but at least one
    must be provided to have any effect.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to update system identity."}
    body = {k: v for k, v in {"hostname": hostname, "description": description}.items() if v is not None}
    return _call_post(device_id, "/system/identity", body)


@write_tool
def reboot_device(device_id: str, confirm: bool = False) -> dict:
    """Reboot the device. Requires confirm=True.

    Returns 400 if a firmware update is in progress. The device will be
    unreachable for approximately 60-90 seconds while it restarts.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to reboot the device."}
    _audit("reboot_device", device_id)
    return _call_post(device_id, "/system/reboot", {})


@read_tool
def get_ztp_status(device_id: str) -> dict:
    """Get Zero Touch Provisioning status for an SLC device."""
    return _call_get(device_id, "/system/ztp")


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

@read_tool
def get_network_interfaces(device_id: str) -> dict:
    """Get all network interface configurations and status for an SLC device."""
    return _call_get(device_id, "/network/interfaces")


# ---------------------------------------------------------------------------
# Ports & Connections
# ---------------------------------------------------------------------------

@read_tool
def get_slc_ports(device_id: str) -> dict:
    """Get all serial port configurations and status for an SLC device."""
    return _call_get(device_id, "/ports")


@read_tool
def get_slc_port(device_id: str, port_id: str) -> dict:
    """Get status for a single serial port on an SLC device.
    port_id: port number as a string, e.g. '1' or '16'."""
    return _call_get(device_id, f"/ports/{port_id}/status")


@read_tool
def get_connections(device_id: str) -> dict:
    """Get all active connections on an SLC device."""
    return _call_get(device_id, "/connections")


@read_tool
def get_managed_devices(device_id: str) -> dict:
    """Get inventory of all managed devices connected to an SLC device."""
    return _call_get(device_id, "/managed_devices")


@read_tool
def get_managed_device(device_id: str, managed_device_id: str) -> dict:
    """Get status of a single managed device connected to an SLC device."""
    return _call_get(device_id, f"/managed_devices/{managed_device_id}/status")


# ---------------------------------------------------------------------------
# Cellular
# ---------------------------------------------------------------------------

@read_tool
def get_cellular_status(device_id: str) -> dict:
    """Get cellular modem status for an SLC device.

    Returns current modem state including: firmware_revision, ipv4_address,
    ipv6_global, signal_strength, imei, iccid, model, serial_number,
    roaming_status, uptime, state, band, apn.
    """
    return _call_get(device_id, "/cellular/status")


# ---------------------------------------------------------------------------
# Firmware
# ---------------------------------------------------------------------------

@read_tool
def get_firmware_version(device_id: str) -> dict:
    """Get installed firmware version for an SLC device."""
    return _call_get(device_id, "/firmware/version")


@read_tool
def get_firmware_update_status(device_id: str) -> dict:
    """Get the status of an in-progress or completed firmware update."""
    return _call_get(device_id, "/firmware/update_status")


@read_tool
def check_firmware_updates(device_id: str) -> dict:
    """Check for available firmware updates on an SLC device."""
    return _call_get(device_id, "/firmware/check")


@read_tool
def get_firmware_bootbank(device_id: str) -> dict:
    """Get the active firmware boot bank (1 or 2). The device boots from the active bank."""
    return _call_get(device_id, "/firmware/bootbank")


@write_tool
def set_firmware_bootbank(device_id: str, bank: int, confirm: bool = False) -> dict:
    """Set the firmware boot bank for next reboot (1 or 2). Requires confirm=True.

    Change takes effect after the next reboot. Use reboot_device to apply immediately.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to change the boot bank."}
    return _call_put(device_id, "/firmware/bootbank", {"bank": bank})


@write_tool
def firmware_update(device_id: str, preserveconfig: bool = True, confirm: bool = False) -> dict:
    """Trigger a firmware update. Requires confirm=True.

    preserveconfig=True (default) carries the running config into the new firmware bank.
    preserveconfig=False starts from factory defaults after update.
    Monitor progress with get_firmware_update_status.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to initiate firmware update."}
    return _call_post(device_id, "/firmware/update", {"preserveconfig": preserveconfig})


@read_tool
def get_firmware_log(device_id: str) -> dict:
    """Get the log from the most recent firmware update operation."""
    return _call_get(device_id, "/firmware/log")


# ---------------------------------------------------------------------------
# Config Management
# ---------------------------------------------------------------------------

@write_tool
def save_config(device_id: str, confirm: bool = False) -> dict:
    """Save running configuration to non-volatile storage on an SLC device.
    Set confirm=True to proceed. Requires explicit confirmation to prevent accidental writes."""
    if not confirm:
        return client._err(
            "save_config writes to device storage. Call again with confirm=True to proceed."
        )
    return _call_post(device_id, "/config/save")


@read_tool
def export_config_commands(device_id: str) -> dict:
    """Export device configuration as a list of CLI commands that can be replayed.

    Useful for backup, drift detection, or applying config to another device via
    apply_config_commands.
    """
    return _call_get(device_id, "/config/commands")


@write_tool
def apply_config_commands(device_id: str, commands: list[str], confirm: bool = False) -> dict:
    """Apply a list of CLI commands to the device and return their output. Requires confirm=True.

    Commands execute synchronously and return output directly. Use this tool (not
    Percepxion's send_direct_cli_command) when you need to see command output.
    Percepxion CLI commands return only job status via its async MQTT system, not CLI output.

    Read-only commands (show, diag ping, etc.) are always permitted.
    Write commands require SLC_CLI_WRITE_ENABLED=true on the server.

    Example: apply_config_commands(device_id, ["show px status"])
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to apply configuration commands."}
    for cmd in commands:
        try:
            cli_policy.check_command(cmd)
        except CLIPolicyViolation as exc:
            return client._err(str(exc))
    _audit(
        "apply_config_commands",
        device_id,
        commands=[_redact_command(c) for c in commands],
    )
    return _call_post(device_id, "/config/batch", {"commands": "\n".join(commands)})


@write_tool
def restore_config_baseline(device_id: str, confirm: bool = False) -> dict:
    """Restore the device to its saved baseline configuration. Requires confirm=True.

    Returns 404 if no baseline has been saved. Returns 500 if the restore operation fails.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to restore baseline configuration."}
    return _call_post(device_id, "/config/baseline", {})


@read_tool
def export_config_for_edit(device_id: str) -> dict:
    """Export the full device configuration blob for editing.

    Returns the raw configuration structure. Edit the returned blob and apply
    changes via apply_config_commands or the device web UI.
    """
    return _call_post(device_id, "/config/edit", {})


@write_tool
def factory_reset(device_id: str, confirm: str = "") -> dict:
    """Reset device to factory defaults. Destructive and irreversible.

    Pass confirm='FACTORY RESET' (exact string) to execute.
    All configuration, logs, and saved baselines will be erased.
    """
    if confirm != "FACTORY RESET":
        return {"ok": False, "error": "Pass confirm='FACTORY RESET' (exact string) to execute factory reset."}
    _audit("factory_reset", device_id)
    return _call_post(device_id, "/config/factory_reset", {})


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@read_tool
def get_sysadmin_user(device_id: str) -> dict:
    """Get sysadmin account configuration (password policy, dialback settings)."""
    return _call_get(device_id, "/users/sysadmin")


@write_tool
def update_sysadmin_user(
    device_id: str,
    new_password: str | None = None,
    allow_dialback: bool | None = None,
    dialback_number: str | None = None,
    confirm: bool = False,
) -> dict:
    """Update sysadmin account settings. Requires confirm=True.

    Pass only the fields you want to change. allow_dialback is a boolean.
    At least one of new_password, allow_dialback, or dialback_number must be provided.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to update sysadmin account."}
    body: dict = {}
    if new_password is not None:
        body["password"] = new_password
    if allow_dialback is not None:
        body["allow_dialback"] = allow_dialback
    if dialback_number is not None:
        body["dialback_number"] = dialback_number
    _audit(
        "update_sysadmin_user",
        device_id,
        password_changed=new_password is not None,
        allow_dialback=allow_dialback,
        dialback_number_changed=dialback_number is not None,
    )
    return _call_patch(device_id, "/users/sysadmin", body)


# ---------------------------------------------------------------------------
# Percepxion Client
# ---------------------------------------------------------------------------

@read_tool
def get_px_status(device_id: str) -> dict:
    """Get Percepxion client status on the device.

    Returns client enable state, connection status, server URL, and last heartbeat.
    This is always allowed regardless of SLC_CLI_WRITE_ENABLED.
    """
    return _call_post(device_id, "/config/batch", {"commands": "show px status"})


@write_tool
def start_px_client(device_id: str, confirm: bool = False) -> dict:
    """Enable the Percepxion client. Requires confirm=True and SLC_CLI_WRITE_ENABLED=true.

    The client registers with the Percepxion cloud within ~30 seconds of starting.
    Use get_px_status to verify the connection.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to start the Percepxion client."}
    guard = _check_cli_write("start_px_client")
    if guard:
        return guard
    return _call_post(device_id, "/config/batch", {"commands": "set px client enable"})


@write_tool
def stop_px_client(device_id: str, confirm: bool = False) -> dict:
    """Disable the Percepxion client. Requires confirm=True and SLC_CLI_WRITE_ENABLED=true.

    The client disconnects from Percepxion cloud. Shutdown takes 60-120 seconds.
    Use get_px_status to verify the client has stopped.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to stop the Percepxion client."}
    guard = _check_cli_write("stop_px_client")
    if guard:
        return guard
    return _call_post(device_id, "/config/batch", {"commands": "set px client disable"})


@write_tool
def restart_px_client(
    device_id: str,
    confirm: bool = False,
    timeout_seconds: int = 120,
) -> dict:
    """Restart the Percepxion client. Requires confirm=True and SLC_CLI_WRITE_ENABLED=true.

    Sends disable, polls until the client reaches 'not running' state (up to timeout_seconds),
    then sends enable. Shutdown takes 60-120 seconds in practice; the default timeout is 120s.
    Returns an error if the client does not stop within timeout_seconds.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to restart the Percepxion client."}
    guard = _check_cli_write("restart_px_client")
    if guard:
        return guard

    gate = _write_gate("restart_px_client")
    if gate:
        return gate
    disable_result = _call_post(device_id, "/config/batch", {"commands": "set px client disable"})
    if not disable_result["ok"]:
        return disable_result

    elapsed = 0
    while elapsed < timeout_seconds:
        time.sleep(5)
        elapsed += 5
        status = _call_post(device_id, "/config/batch", {"commands": "show px status"})
        if not status["ok"]:
            return status
        messages = status.get("data", {}).get("message", [])
        output = "\n".join(messages) if isinstance(messages, list) else str(messages)
        if "Status of Client: not running" in output:
            break
    else:
        return client._err(
            f"Timeout: Percepxion client did not stop within {timeout_seconds}s. "
            "Try stop_px_client first and wait before calling restart_px_client again."
        )

    gate = _write_gate("restart_px_client")
    if gate:
        gate["error"] = (
            "The Percepxion client was stopped but not started again: " + gate["error"]
            + " Start it with start_px_client once writes are on."
        )
        return gate
    return _call_post(device_id, "/config/batch", {"commands": "set px client enable"})


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------

# Set by main() when an HTTP transport is used: configure_provider is then refused.
REMOTE_TRANSPORT = False


def build_http_app(
    transport: str,
    stateless_http: bool = False,
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    auth_token: str | None = None,
    validate_every_request: bool = False,
):
    """ASGI app for the remote transports.

    http: Streamable HTTP at /mcp. sse: legacy HTTP+SSE at /sse (messages under
    /messages/). both: one app serving both, so existing SSE clients keep working
    while new clients use Streamable HTTP. The Streamable HTTP app's lifespan
    starts the server lifespan and its session manager, which covers SSE too.

    auth_token adds bearer-token authentication to every route.
    validate_every_request makes the Host/Origin guard check every request
    (used for non-loopback binds) instead of FastMCP's loopback-only default.
    """
    from starlette.middleware import Middleware

    from slc_mcp.remote_security import HTTP_TRANSPORTS, BearerAuthMiddleware

    if transport not in HTTP_TRANSPORTS:
        raise ValueError(f"MCP_TRANSPORT must be stdio, http, sse or both, not {transport!r}")
    opts = {
        "allowed_hosts": allowed_hosts or None,
        "allowed_origins": allowed_origins or None,
        "host_origin_protection": True if validate_every_request else "auto",
        "middleware": [Middleware(BearerAuthMiddleware, token=auth_token)] if auth_token else None,
    }
    if transport == "sse":
        return mcp.http_app(path="/sse", transport="sse", **opts)
    app = mcp.http_app(path="/mcp", transport="http", stateless_http=stateless_http, **opts)
    if transport == "both":
        sse = mcp.http_app(path="/sse", transport="sse", **opts)
        app.router.routes.extend(sse.routes)
    return app


def main() -> None:
    """Run the server on the transport MCP_TRANSPORT names (stdio by default)."""
    global REMOTE_TRANSPORT
    from slc_mcp.remote_security import (
        RemoteConfigError,
        check_remote_settings,
        settings_from_env,
        transport_from_env,
    )

    try:
        cfg = transport_from_env()
        if cfg.transport in ("", "stdio"):
            mcp.run()
            return
        settings = settings_from_env(cfg.transport, cfg.host)
        check_remote_settings(settings)
        app = build_http_app(
            cfg.transport,
            stateless_http=cfg.stateless_http,
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
            auth_token=settings.token,
            validate_every_request=settings.remote_bind,
        )
    except (RemoteConfigError, ValueError) as e:
        log.error("refusing to start: %s", e)
        raise SystemExit(2) from e
    REMOTE_TRANSPORT = True

    import uvicorn

    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info", lifespan="on")


if __name__ == "__main__":
    main()
