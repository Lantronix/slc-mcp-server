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
    "/api/v2/cellular/status": {
        "firmware_revision": "SWI9X50C_01.08.04.00",
        "signal_strength": -73,
        "imei": "359072060033456",
        "iccid": "8901260852388901234",
        "model": "MC7455",
        "serial_number": "LQ807390040310",
        "roaming_status": False,
        "uptime": 3600,
        "state": "connected",
        "band": "LTE B4",
        "apn": "internet",
        "ipv4_address": "10.20.30.40",
        "ipv6_global": None,
    },
    "/api/v2/firmware/version": {"version": "9.7.0.0R10"},
    "/api/v2/firmware/update_status": {"status": "idle"},
    "/api/v2/firmware/check": {"update_available": False, "current_version": "9.7.0.0R10"},
    "/api/v2/config/compare": {"diff": "none"},
    "/api/v2/firmware/bootbank": {"bank": 1},
    "/api/v2/firmware/log": {"log": "Update completed successfully."},
    "/api/v2/sessions": {"sessions": [{"id": "sess-1", "type": "api"}]},
    "/api/v2/sessions/sess-1": {"id": "sess-1", "type": "api", "username": "sysadmin"},
    "/api/v2/system/identity": {"hostname": "slc9000", "description": "Lab device"},
    "/api/v2/users/sysadmin": {"username": "sysadmin", "allow_dialback": False},
    "/api/v2/config/commands": {"commands": ["set hostname slc9000"]},
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
        "/api/v2/config/save", method="POST"
    ).respond_with_json(
        {"status": 200, "code": "SUCCESS", "message": ["2 out of 2 total groups saved"]}
    )
    httpserver.expect_request(
        "/api/v2/system/reboot", method="POST"
    ).respond_with_json({"status": "rebooting"})
    httpserver.expect_request(
        "/api/v2/config/batch", method="POST"
    ).respond_with_json({"status": "ok", "output": "hostname set"})
    httpserver.expect_request(
        "/api/v2/config/baseline", method="POST"
    ).respond_with_json({"status": "ok"})
    httpserver.expect_request(
        "/api/v2/config/edit", method="POST"
    ).respond_with_json({"config": {}})
    httpserver.expect_request(
        "/api/v2/config/factory_reset", method="POST"
    ).respond_with_json({"status": "ok"})
    httpserver.expect_request(
        "/api/v2/firmware/update", method="POST"
    ).respond_with_json({"status": "updating"})
    httpserver.expect_request(
        "/api/v2/firmware/bootbank", method="PUT"
    ).respond_with_json({"bank": 2})
    httpserver.expect_request(
        "/api/v2/system/identity", method="POST"
    ).respond_with_json({"hostname": "new-hostname"})
    httpserver.expect_request(
        "/api/v2/users/sysadmin", method="PATCH"
    ).respond_with_json({"username": "sysadmin", "allow_dialback": True})
    httpserver.expect_request(
        "/api/v2/sessions/sess-1", method="DELETE"
    ).respond_with_data("", status=204)
    httpserver.expect_request(
        "/api/v2/user/login", method="DELETE"
    ).respond_with_data("", status=204)

    return httpserver
