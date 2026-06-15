from unittest.mock import patch, MagicMock
import slc_mcp.server as server


def test_configure_provider_valid():
    with patch.object(server._sessions, "set_provider"):
        with patch("slc_mcp.server.get_provider", return_value=MagicMock()):
            result = server.configure_provider("env")
    assert result["ok"] is True
    assert result["data"]["provider"] == "env"
    assert result["data"]["sessions_cleared"] is True


def test_configure_provider_invalid():
    result = server.configure_provider("bogus")
    assert result["ok"] is False
    assert "Invalid provider" in result["error"]


def test_configure_provider_all_valid_values():
    for p in ("env", "percepxion", "vault", "aws"):
        with patch.object(server._sessions, "set_provider"):
            with patch("slc_mcp.server.get_provider", return_value=MagicMock()):
                result = server.configure_provider(p)
        assert result["ok"] is True


def test_save_config_requires_confirm():
    result = server.save_config("any-device", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_save_config_confirm_true_calls_device():
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {"code": "SUCCESS"}}) as mock_post:
        result = server.save_config("device-1", confirm=True)
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/config/save")


def test_get_system_status_delegates():
    with patch.object(server, "_call_get", return_value={"ok": True, "data": {}}) as mock_get:
        server.get_system_status("d1")
    mock_get.assert_called_once_with("d1", "/system/status")


def test_get_slc_port_uses_correct_path():
    with patch.object(server, "_call_get", return_value={"ok": True, "data": {}}) as mock_get:
        server.get_slc_port("d1", "5")
    mock_get.assert_called_once_with("d1", "/ports/5/status")


def test_get_managed_device_uses_correct_path():
    with patch.object(server, "_call_get", return_value={"ok": True, "data": {}}) as mock_get:
        server.get_managed_device("d1", "router-1")
    mock_get.assert_called_once_with("d1", "/managed_devices/router-1/status")


def test_credential_error_returns_err():
    from slc_mcp.providers import CredentialError
    with patch.object(server._sessions, "get_or_create", side_effect=CredentialError("no creds")):
        result = server.get_system_status("missing-device")
    assert result["ok"] is False
    assert "no creds" in result["error"]


def test_tool_count():
    import subprocess
    result = subprocess.run(
        ["grep", "-c", "@mcp.tool", "src/slc_mcp/server.py"],
        capture_output=True, text=True,
        cwd="/mnt/c/Users/rhogg/Projects/git/slc-mcp-server",
    )
    assert int(result.stdout.strip()) == 33


# ---------------------------------------------------------------------------
# factory_reset guard
# ---------------------------------------------------------------------------

def test_factory_reset_wrong_string_blocked():
    result = server.factory_reset("device-1", confirm="yes")
    assert result["ok"] is False
    assert "FACTORY RESET" in result["error"]


def test_factory_reset_no_confirm_blocked():
    result = server.factory_reset("device-1")
    assert result["ok"] is False


def test_factory_reset_correct_string_passes_through():
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {}}) as mock_post:
        result = server.factory_reset("device-1", confirm="FACTORY RESET")
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/config/factory_reset", {})


# ---------------------------------------------------------------------------
# reboot_device guard
# ---------------------------------------------------------------------------

def test_reboot_device_requires_confirm():
    result = server.reboot_device("device-1", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_reboot_device_confirm_passes_body():
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {"status": "rebooting"}}) as mock_post:
        result = server.reboot_device("device-1", confirm=True)
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/system/reboot", {})


# ---------------------------------------------------------------------------
# apply_config_commands guard
# ---------------------------------------------------------------------------

def test_apply_config_commands_requires_confirm():
    result = server.apply_config_commands("device-1", ["set hostname foo"], confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_apply_config_commands_passes_commands_list():
    cmds = ["set hostname foo", "set description bar"]
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {"status": "ok"}}) as mock_post:
        result = server.apply_config_commands("device-1", cmds, confirm=True)
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/config/batch", {"commands": cmds})


# ---------------------------------------------------------------------------
# restore_config_baseline guard
# ---------------------------------------------------------------------------

def test_restore_config_baseline_requires_confirm():
    result = server.restore_config_baseline("device-1", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_restore_config_baseline_confirm_calls_correct_path():
    with patch.object(server, "_call_post", return_value={"ok": True, "data": {}}) as mock_post:
        result = server.restore_config_baseline("device-1", confirm=True)
    assert result["ok"] is True
    mock_post.assert_called_once_with("device-1", "/config/baseline", {})


# ---------------------------------------------------------------------------
# firmware check is now GET
# ---------------------------------------------------------------------------

def test_check_firmware_updates_uses_get():
    with patch.object(server, "_call_get", return_value={"ok": True, "data": {"update_available": False}}) as mock_get:
        server.check_firmware_updates("d1")
    mock_get.assert_called_once_with("d1", "/firmware/check")


# ---------------------------------------------------------------------------
# terminate_session guard
# ---------------------------------------------------------------------------

def test_terminate_session_requires_confirm():
    result = server.terminate_session("device-1", "sess-1", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_terminate_session_confirm_calls_delete():
    with patch.object(server, "_call_delete", return_value={"ok": True, "data": {}}) as mock_delete:
        result = server.terminate_session("device-1", "sess-1", confirm=True)
    assert result["ok"] is True
    mock_delete.assert_called_once_with("device-1", "/sessions/sess-1")


# ---------------------------------------------------------------------------
# set_firmware_bootbank guard
# ---------------------------------------------------------------------------

def test_set_firmware_bootbank_requires_confirm():
    result = server.set_firmware_bootbank("device-1", 2, confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_set_firmware_bootbank_calls_put():
    with patch.object(server, "_call_put", return_value={"ok": True, "data": {"bank": 2}}) as mock_put:
        result = server.set_firmware_bootbank("device-1", 2, confirm=True)
    assert result["ok"] is True
    mock_put.assert_called_once_with("device-1", "/firmware/bootbank", {"bank": 2})


# ---------------------------------------------------------------------------
# update_sysadmin_user guard
# ---------------------------------------------------------------------------

def test_update_sysadmin_user_requires_confirm():
    result = server.update_sysadmin_user("device-1", new_password="newpass", confirm=False)
    assert result["ok"] is False
    assert "confirm=True" in result["error"]


def test_update_sysadmin_user_builds_body_from_non_none():
    with patch.object(server, "_call_patch", return_value={"ok": True, "data": {}}) as mock_patch:
        server.update_sysadmin_user("device-1", allow_dialback=True, confirm=True)
    mock_patch.assert_called_once_with("device-1", "/users/sysadmin", {"allow_dialback": True})


def test_update_sysadmin_user_excludes_none_fields():
    with patch.object(server, "_call_patch", return_value={"ok": True, "data": {}}) as mock_patch:
        server.update_sysadmin_user(
            "device-1", new_password="pw", allow_dialback=None, dialback_number=None, confirm=True
        )
    args = mock_patch.call_args[0]
    assert "allow_dialback" not in args[2]
    assert args[2] == {"password": "pw"}
