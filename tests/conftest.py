import pytest
from pytest_httpserver import HTTPServer

FAKE_TOKEN = "fake-integration-token-xyz"

FAKE_GET_RESPONSES = {
    "/api/v2/system/status": {"status": "running", "uptime": 12345},
    "/api/v2/system/version": {"firmware": "9.7.0.0R10", "build": "12345"},
    "/api/v2/network/interfaces": {"interfaces": [{"name": "eth0", "ip": "10.0.0.1"}]},
    "/api/v2/system/ztp": {"enabled": False, "status": "complete"},
    "/api/v2/ports": {"ports": [{"id": 1, "label": "Port 1"}]},
    "/api/v2/ports/1/status": {"id": 1, "connected": True, "baud": 9600},
    "/api/v2/connections": {"connections": []},
    "/api/v2/managed_devices": {"devices": [{"id": "router-1"}]},
    "/api/v2/managed_devices/router-1/status": {"id": "router-1", "online": True},
    "/api/v2/cellular/status": {"modem": "present", "signal": -75},
    "/api/v2/firmware/version": {"version": "9.7.0.0R10"},
    "/api/v2/firmware/update_status": {"status": "idle"},
    "/api/v2/config/compare": {"diff": "none"},
}


@pytest.fixture()
def fake_slc(httpserver: HTTPServer):
    httpserver.expect_request(
        "/api/v2/user/login", method="POST"
    ).respond_with_json(
        {"token": FAKE_TOKEN, "expires_in": 3600, "user": {"username": "admin"}}
    )
    for path, body in FAKE_GET_RESPONSES.items():
        httpserver.expect_request(path, method="GET").respond_with_json(body)
    httpserver.expect_request(
        "/api/v2/firmware/check", method="POST"
    ).respond_with_json({"status": "checking"})
    httpserver.expect_request(
        "/api/v2/config/save", method="POST"
    ).respond_with_json(
        {"status": 200, "code": "SUCCESS", "message": ["2 out of 2 total groups saved"]}
    )
    return httpserver
