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
    import subprocess, re
    result = subprocess.run(
        ["grep", "-c", "@mcp.tool", "src/slc_mcp/server.py"],
        capture_output=True, text=True
    )
    assert int(result.stdout.strip()) == 16
