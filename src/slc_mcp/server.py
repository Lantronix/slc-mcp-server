import logging
import os
import sys

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

mcp = FastMCP("slc-mcp-server")

from slc_mcp import client
from slc_mcp.providers import CredentialError, get_provider
from slc_mcp.session import SessionManager

_sessions = SessionManager()


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

@mcp.tool()
def configure_provider(provider: str) -> dict:
    """Switch the active credential provider and clear all cached sessions.
    Valid values: env, percepxion, vault, aws."""
    valid = ("env", "percepxion", "vault", "aws")
    if provider not in valid:
        return client._err(
            f"Invalid provider {provider!r}. Valid values: {', '.join(valid)}"
        )
    os.environ["SLC_CREDENTIAL_PROVIDER"] = provider
    _sessions.set_provider(get_provider())
    return client._ok({"provider": provider, "sessions_cleared": True})


# ---------------------------------------------------------------------------
# Auth & Sessions
# ---------------------------------------------------------------------------

@mcp.tool()
def logout_device(device_id: str) -> dict:
    """Invalidate the current API session token for the device."""
    return _call_delete(device_id, "/user/login")


@mcp.tool()
def get_sessions(device_id: str) -> dict:
    """List all active sessions (web UI, API, WebTerm) on the device."""
    return _call_get(device_id, "/sessions")


@mcp.tool()
def get_session(device_id: str, session_id: str) -> dict:
    """Get details for a specific active session by session ID."""
    return _call_get(device_id, f"/sessions/{session_id}")


@mcp.tool()
def terminate_session(device_id: str, session_id: str, confirm: bool = False) -> dict:
    """Forcibly terminate an active session by session ID. Requires confirm=True."""
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to terminate this session."}
    return _call_delete(device_id, f"/sessions/{session_id}")


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@mcp.tool()
def get_system_status(device_id: str) -> dict:
    """Get system status for an SLC device."""
    return _call_get(device_id, "/system/status")


@mcp.tool()
def get_system_version(device_id: str) -> dict:
    """Get firmware and software version information for an SLC device."""
    return _call_get(device_id, "/system/version")


@mcp.tool()
def get_system_identity(device_id: str) -> dict:
    """Get device identity: hostname, description, contact, location."""
    return _call_get(device_id, "/system/identity")


@mcp.tool()
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


@mcp.tool()
def reboot_device(device_id: str, confirm: bool = False) -> dict:
    """Reboot the device. Requires confirm=True.

    Returns 400 if a firmware update is in progress. The device will be
    unreachable for approximately 60-90 seconds while it restarts.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to reboot the device."}
    return _call_post(device_id, "/system/reboot", {})


@mcp.tool()
def get_ztp_status(device_id: str) -> dict:
    """Get Zero Touch Provisioning status for an SLC device."""
    return _call_get(device_id, "/system/ztp")


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

@mcp.tool()
def get_network_interfaces(device_id: str) -> dict:
    """Get all network interface configurations and status for an SLC device."""
    return _call_get(device_id, "/network/interfaces")


# ---------------------------------------------------------------------------
# Ports & Connections
# ---------------------------------------------------------------------------

@mcp.tool()
def get_slc_ports(device_id: str) -> dict:
    """Get all serial port configurations and status for an SLC device."""
    return _call_get(device_id, "/ports")


@mcp.tool()
def get_slc_port(device_id: str, port_id: str) -> dict:
    """Get status for a single serial port on an SLC device.
    port_id: port number as a string, e.g. '1' or '16'."""
    return _call_get(device_id, f"/ports/{port_id}/status")


@mcp.tool()
def get_connections(device_id: str) -> dict:
    """Get all active connections on an SLC device."""
    return _call_get(device_id, "/connections")


@mcp.tool()
def get_managed_devices(device_id: str) -> dict:
    """Get inventory of all managed devices connected to an SLC device."""
    return _call_get(device_id, "/managed_devices")


@mcp.tool()
def get_managed_device(device_id: str, managed_device_id: str) -> dict:
    """Get status of a single managed device connected to an SLC device."""
    return _call_get(device_id, f"/managed_devices/{managed_device_id}/status")


@mcp.tool()
def port_action(device_id: str, port_id: str, action: str) -> dict:
    """Send an action to a serial port or connected managed device.

    This endpoint exists in the API specification but is not yet implemented in firmware.
    """
    return {
        "ok": False,
        "error": "port_action endpoint exists in the API specification but is not yet implemented in firmware.",
    }


# ---------------------------------------------------------------------------
# Cellular
# ---------------------------------------------------------------------------

@mcp.tool()
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

@mcp.tool()
def get_firmware_version(device_id: str) -> dict:
    """Get installed firmware version for an SLC device."""
    return _call_get(device_id, "/firmware/version")


@mcp.tool()
def get_firmware_update_status(device_id: str) -> dict:
    """Get the status of an in-progress or completed firmware update."""
    return _call_get(device_id, "/firmware/update_status")


@mcp.tool()
def check_firmware_updates(device_id: str) -> dict:
    """Check for available firmware updates on an SLC device."""
    return _call_get(device_id, "/firmware/check")


@mcp.tool()
def get_firmware_bootbank(device_id: str) -> dict:
    """Get the active firmware boot bank (1 or 2). The device boots from the active bank."""
    return _call_get(device_id, "/firmware/bootbank")


@mcp.tool()
def set_firmware_bootbank(device_id: str, bank: int, confirm: bool = False) -> dict:
    """Set the firmware boot bank for next reboot (1 or 2). Requires confirm=True.

    Change takes effect after the next reboot. Use reboot_device to apply immediately.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to change the boot bank."}
    return _call_put(device_id, "/firmware/bootbank", {"bank": bank})


@mcp.tool()
def firmware_update(device_id: str, preserveconfig: bool = True, confirm: bool = False) -> dict:
    """Trigger a firmware update. Requires confirm=True.

    preserveconfig=True (default) carries the running config into the new firmware bank.
    preserveconfig=False starts from factory defaults after update.
    Monitor progress with get_firmware_update_status.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to initiate firmware update."}
    return _call_post(device_id, "/firmware/update", {"preserveconfig": preserveconfig})


@mcp.tool()
def get_firmware_log(device_id: str) -> dict:
    """Get the log from the most recent firmware update operation."""
    return _call_get(device_id, "/firmware/log")


# ---------------------------------------------------------------------------
# Config Management
# ---------------------------------------------------------------------------

@mcp.tool()
def compare_config(device_id: str) -> dict:
    """Compare running config against saved config on an SLC device.

    This endpoint exists in the API specification but is not yet implemented in firmware.
    The device will return an error response.
    """
    return _call_get(device_id, "/config/compare")


@mcp.tool()
def save_config(device_id: str, confirm: bool = False) -> dict:
    """Save running configuration to non-volatile storage on an SLC device.
    Set confirm=True to proceed. Requires explicit confirmation to prevent accidental writes."""
    if not confirm:
        return client._err(
            "save_config writes to device storage. Call again with confirm=True to proceed."
        )
    return _call_post(device_id, "/config/save")


@mcp.tool()
def export_config_commands(device_id: str) -> dict:
    """Export device configuration as a list of CLI commands that can be replayed.

    Useful for backup, drift detection, or applying config to another device via
    apply_config_commands.
    """
    return _call_get(device_id, "/config/commands")


@mcp.tool()
def apply_config_commands(device_id: str, commands: list[str], confirm: bool = False) -> dict:
    """Apply a list of CLI configuration commands to the device. Requires confirm=True.

    Commands execute synchronously and return output directly. Use this tool (not
    Percepxion's send_direct_cli_command) when you need to see command output.
    Percepxion CLI commands return only job status via its async job system, not CLI output.

    Example: apply_config_commands(device_id, ["set hostname slc9000-lab"])
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to apply configuration commands."}
    return _call_post(device_id, "/config/batch", {"commands": commands})


@mcp.tool()
def restore_config_baseline(device_id: str, confirm: bool = False) -> dict:
    """Restore the device to its saved baseline configuration. Requires confirm=True.

    Returns 404 if no baseline has been saved. Returns 500 if the restore operation fails.
    """
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to restore baseline configuration."}
    return _call_post(device_id, "/config/baseline", {})


@mcp.tool()
def export_config_for_edit(device_id: str) -> dict:
    """Export the full device configuration blob for editing.

    Returns the raw configuration structure. Edit the returned blob and apply
    changes via apply_config_commands or the device web UI.
    """
    return _call_post(device_id, "/config/edit", {})


@mcp.tool()
def factory_reset(device_id: str, confirm: str = "") -> dict:
    """Reset device to factory defaults. Destructive and irreversible.

    Pass confirm='FACTORY RESET' (exact string) to execute.
    All configuration, logs, and saved baselines will be erased.
    """
    if confirm != "FACTORY RESET":
        return {"ok": False, "error": "Pass confirm='FACTORY RESET' (exact string) to execute factory reset."}
    return _call_post(device_id, "/config/factory_reset", {})


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@mcp.tool()
def get_sysadmin_user(device_id: str) -> dict:
    """Get sysadmin account configuration (password policy, dialback settings)."""
    return _call_get(device_id, "/users/sysadmin")


@mcp.tool()
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
    return _call_patch(device_id, "/users/sysadmin", body)
