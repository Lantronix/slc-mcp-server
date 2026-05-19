import pytest
import responses as resp_lib
from unittest.mock import patch
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
        with pytest.raises(CredentialError, match="Login failed"):
            client.login("10.0.0.1", "admin", "wrong")


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
    assert "re-authenticate" in result["error"]


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
