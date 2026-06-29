import os
import contextlib
import pytest
from unittest.mock import patch

import slc_mcp.client as client
import slc_mcp.server as server
from slc_mcp.providers.env import EnvCredentialProvider


@pytest.fixture(autouse=True)
def reset_sessions():
    server._sessions.clear_all()
    yield
    server._sessions.clear_all()


def _setup(fake_slc) -> dict:
    host = f"127.0.0.1:{fake_slc.port}"
    return {
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_TESTDEV_IP": host,
        "SLC_TESTDEV_USERNAME": "admin",
        "SLC_TESTDEV_PASSWORD": "password",
        "SLC_VERIFY_SSL": "false",
    }


@contextlib.contextmanager
def _fake_device_ctx(fake_slc):
    with patch.object(client, "_SCHEME", "http"):
        with patch.object(client, "_VERIFY_SSL", False):
            with patch.object(client, "_PATH_PREFIX", "/api/v2"):
                with patch.dict(os.environ, _setup(fake_slc), clear=False):
                    server._sessions.set_provider(EnvCredentialProvider())
                    yield


def test_get_system_status(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_system_status("testdev")
    assert result["ok"] is True
    assert result["data"]["status"] == "running"


def test_get_system_version(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_system_version("testdev")
    assert result["ok"] is True
    assert result["data"]["firmware"] == "9.7.0.0R10"


def test_get_slc_ports(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_slc_ports("testdev")
    assert result["ok"] is True
    assert isinstance(result["data"]["ports"], list)
    assert len(result["data"]["ports"]) == 1


def test_get_slc_port_single(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_slc_port("testdev", "1")
    assert result["ok"] is True
    assert result["data"]["baud"] == 9600


def test_get_managed_devices(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_managed_devices("testdev")
    assert result["ok"] is True
    assert result["data"]["devices"][0]["id"] == "router-1"


def test_get_managed_device_single(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_managed_device("testdev", "router-1")
    assert result["ok"] is True
    assert result["data"]["online"] is True


def test_check_firmware_updates_via_get(fake_slc):
    """firmware/check must be GET, not POST."""
    with _fake_device_ctx(fake_slc):
        result = server.check_firmware_updates("testdev")
    assert result["ok"] is True
    assert "update_available" in result["data"]


def test_save_config_without_confirm_blocked(fake_slc):
    result = server.save_config("testdev", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_save_config_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.save_config("testdev", confirm=True)
    assert result["ok"] is True
    assert result["data"]["code"] == "SUCCESS"


def test_session_reused_across_calls(fake_slc):
    with _fake_device_ctx(fake_slc):
        server.get_system_status("testdev")
        server.get_system_version("testdev")
    login_calls = [
        req for req, _resp in fake_slc.log if req.path == "/api/v2/user/login" and req.method == "POST"
    ]
    assert len(login_calls) == 1


def test_get_sessions(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_sessions("testdev")
    assert result["ok"] is True
    assert result["data"]["sessions"][0]["id"] == "sess-1"


def test_get_session_single(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_session("testdev", "sess-1")
    assert result["ok"] is True
    assert result["data"]["username"] == "sysadmin"


def test_terminate_session_blocked_without_confirm(fake_slc):
    result = server.terminate_session("testdev", "sess-1", confirm=False)
    assert result["ok"] is False


def test_terminate_session_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.terminate_session("testdev", "sess-1", confirm=True)
    assert result["ok"] is True


def test_get_system_identity(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_system_identity("testdev")
    assert result["ok"] is True
    assert result["data"]["hostname"] == "slc9000"


def test_update_system_identity_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.update_system_identity("testdev", hostname="new-hostname", confirm=True)
    assert result["ok"] is True
    assert result["data"]["hostname"] == "new-hostname"


def test_reboot_device_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.reboot_device("testdev", confirm=True)
    assert result["ok"] is True


def test_get_firmware_bootbank(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_firmware_bootbank("testdev")
    assert result["ok"] is True
    assert result["data"]["bank"] == 1


def test_set_firmware_bootbank_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.set_firmware_bootbank("testdev", 2, confirm=True)
    assert result["ok"] is True
    assert result["data"]["bank"] == 2


def test_firmware_update_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.firmware_update("testdev", confirm=True)
    assert result["ok"] is True


def test_get_firmware_log(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_firmware_log("testdev")
    assert result["ok"] is True


def test_export_config_commands(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.export_config_commands("testdev")
    assert result["ok"] is True
    assert isinstance(result["data"]["commands"], list)


def test_apply_config_commands_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        with patch.dict("os.environ", {"SLC_CLI_WRITE_ENABLED": "true"}):
            result = server.apply_config_commands("testdev", ["set hostname slc9000"], confirm=True)
    assert result["ok"] is True


def test_restore_config_baseline_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.restore_config_baseline("testdev", confirm=True)
    assert result["ok"] is True


def test_get_sysadmin_user(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.get_sysadmin_user("testdev")
    assert result["ok"] is True
    assert result["data"]["username"] == "sysadmin"


def test_update_sysadmin_user_with_confirm(fake_slc):
    with _fake_device_ctx(fake_slc):
        result = server.update_sysadmin_user("testdev", allow_dialback=True, confirm=True)
    assert result["ok"] is True


def test_cellular_status_new_schema(fake_slc):
    """Cellular fixture uses current firmware schema fields."""
    with _fake_device_ctx(fake_slc):
        result = server.get_cellular_status("testdev")
    assert result["ok"] is True
    data = result["data"]
    assert "firmware_revision" in data
    assert "signal_strength" in data
    assert "imei" in data
    # Old fields should not be present
    assert "firmware_version" not in data
    assert "qmi_driver_version" not in data
    assert "modem_manager_version" not in data


def test_factory_reset_blocked_without_exact_string(fake_slc):
    result = server.factory_reset("testdev", confirm="yes")
    assert result["ok"] is False
    assert "FACTORY RESET" in result["error"]
