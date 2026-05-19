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


@mcp.tool()
def get_system_status(device_id: str) -> dict:
    """Get system status for an SLC device."""
    return _call_get(device_id, "/system/status")


@mcp.tool()
def get_system_version(device_id: str) -> dict:
    """Get firmware and software version information for an SLC device."""
    return _call_get(device_id, "/system/version")


@mcp.tool()
def get_network_interfaces(device_id: str) -> dict:
    """Get all network interface configurations and status for an SLC device."""
    return _call_get(device_id, "/network/interfaces")


@mcp.tool()
def get_ztp_status(device_id: str) -> dict:
    """Get Zero Touch Provisioning status for an SLC device."""
    return _call_get(device_id, "/system/ztp")


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
    """Trigger a check for available firmware updates on an SLC device."""
    return _call_post(device_id, "/firmware/check")


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
def get_cellular_status(device_id: str) -> dict:
    """Get cellular modem status for an SLC device."""
    return _call_get(device_id, "/cellular/status")


@mcp.tool()
def compare_config(device_id: str) -> dict:
    """Compare running config against saved config on an SLC device."""
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
