import pytest
import responses as resp_lib
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import slc_mcp.client as client


@dataclass
class FakeSession:
    ip: str = "10.0.0.1"
    token: str = "test-token-abc"
    valid: bool = True


def test_ok_envelope():
    result = client._ok({"key": "value"})
    assert result == {"ok": True, "data": {"key": "value"}}


def test_err_envelope_no_code():
    result = client._err("something failed")
    assert result == {"ok": False, "error": "something failed"}
    assert "status_code" not in result


def test_err_envelope_with_code():
    result = client._err("not found", 404)
    assert result == {"ok": False, "error": "not found", "status_code": 404}


def test_url_builds_correctly():
    url = client._url("10.0.0.1", "/system/status")
    assert url.startswith("https://10.0.0.1")
    assert url.endswith("/system/status")


@resp_lib.activate
def test_login_success():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={"token": "tok123", "expires_in": 3600, "user": {"username": "admin"}},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        token = client.login("10.0.0.1", "admin", "password")
    assert token == "tok123"


@resp_lib.activate
def test_login_failure_raises():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={"error": "invalid credentials"},
        status=401,
    )
    from slc_mcp.providers import CredentialError
    with patch.object(client, "_VERIFY_SSL", False):
        with pytest.raises(CredentialError, match="Authentication failed"):
            client.login("10.0.0.1", "admin", "wrong")


@resp_lib.activate
def test_login_2fa_totp_success():
    """Challenge returned with totp_secret provided -> second POST -> token extracted."""
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={
            "challenge_required": True,
            "challenge_type": "tokencode",
            "challenge_id": "chall-123",
            "challenge_state": "pending",
        },
        status=200,
    )
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={"token": "tok-2fa", "expires_in": 3600},
        status=200,
    )
    mock_totp = MagicMock()
    mock_totp.now.return_value = "123456"
    with patch.object(client, "_VERIFY_SSL", False):
        with patch.object(client, "pyotp") as mock_pyotp_mod:
            mock_pyotp_mod.TOTP.return_value = mock_totp
            token = client.login("10.0.0.1", "admin", "password", totp_secret="JBSWY3DPEHPK3PXP")
    assert token == "tok-2fa"


@resp_lib.activate
def test_login_2fa_no_totp_secret_raises():
    """Challenge returned but no totp_secret -> CredentialError with env var instruction."""
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={
            "challenge_required": True,
            "challenge_type": "passcode",
            "challenge_id": "chall-456",
            "challenge_state": "pending",
        },
        status=200,
    )
    from slc_mcp.providers import CredentialError
    with patch.object(client, "_VERIFY_SSL", False):
        with pytest.raises(CredentialError, match="TOTP_SECRET"):
            client.login("10.0.0.1", "admin", "password", totp_secret=None)


@resp_lib.activate
def test_login_2fa_pin_setup_challenge_raises():
    """PIN setup challenge type -> CredentialError with web UI instruction."""
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/user/login",
        json={
            "challenge_required": True,
            "challenge_type": "pin_setup",
            "challenge_id": "chall-789",
            "challenge_state": "setup",
        },
        status=200,
    )
    from slc_mcp.providers import CredentialError
    with patch.object(client, "_VERIFY_SSL", False):
        with pytest.raises(CredentialError, match="web UI"):
            client.login("10.0.0.1", "admin", "password", totp_secret="JBSWY3DPEHPK3PXP")


@resp_lib.activate
def test_get_success():
    resp_lib.add(
        resp_lib.GET,
        "https://10.0.0.1/api/v2/system/status",
        json={"status": "ok"},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is True
    assert result["data"]["status"] == "ok"


@resp_lib.activate
def test_get_401_returns_err():
    resp_lib.add(
        resp_lib.GET,
        "https://10.0.0.1/api/v2/system/status",
        json={},
        status=401,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert result["status_code"] == 401
    assert "401" in result["error"]


@resp_lib.activate
def test_get_error_body_parsed():
    """Non-2xx responses parse error field from response body."""
    resp_lib.add(
        resp_lib.GET,
        "https://10.0.0.1/api/v2/firmware/check",
        json={"error": "INVALID_URI", "message": "Not found"},
        status=404,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.get(FakeSession(), "/firmware/check")
    assert result["ok"] is False
    assert result["status_code"] == 404
    assert result["error"] == "INVALID_URI"


@resp_lib.activate
def test_post_success():
    resp_lib.add(
        resp_lib.POST,
        "https://10.0.0.1/api/v2/config/save",
        json={"status": 200, "code": "SUCCESS", "message": ["2 out of 2 total groups saved"]},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.post(FakeSession(), "/config/save", {})
    assert result["ok"] is True
    assert result["data"]["code"] == "SUCCESS"


@resp_lib.activate
def test_put_success():
    resp_lib.add(
        resp_lib.PUT,
        "https://10.0.0.1/api/v2/firmware/bootbank",
        json={"bank": 2},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.put(FakeSession(), "/firmware/bootbank", {"bank": 2})
    assert result["ok"] is True
    assert result["data"]["bank"] == 2


@resp_lib.activate
def test_delete_204_returns_ok():
    resp_lib.add(
        resp_lib.DELETE,
        "https://10.0.0.1/api/v2/user/login",
        body="",
        status=204,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.delete(FakeSession(), "/user/login")
    assert result["ok"] is True
    assert result["data"] == {}


@resp_lib.activate
def test_patch_success():
    resp_lib.add(
        resp_lib.PATCH,
        "https://10.0.0.1/api/v2/users/sysadmin",
        json={"username": "sysadmin", "allow_dialback": True},
        status=200,
    )
    with patch.object(client, "_VERIFY_SSL", False):
        result = client.patch(FakeSession(), "/users/sysadmin", {"allow_dialback": True})
    assert result["ok"] is True
    assert result["data"]["allow_dialback"] is True


def test_get_connection_refused():
    import requests.exceptions
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError()):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert "Connection refused" in result["error"]


def test_get_timeout():
    import requests.exceptions
    with patch("requests.get", side_effect=requests.exceptions.Timeout()):
        result = client.get(FakeSession(), "/system/status")
    assert result["ok"] is False
    assert "timed out" in result["error"]
