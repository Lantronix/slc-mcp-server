import os
import logging

import requests
import urllib3

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("SLC_REQUEST_TIMEOUT", "30"))
_PATH_PREFIX = os.getenv("SLC_API_PATH_PREFIX", "/api/v2")
_VERIFY_SSL = os.getenv("SLC_VERIFY_SSL", "false").lower() not in ("false", "0", "no")
_SCHEME = os.getenv("SLC_URL_SCHEME", "https")

if not _VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _url(ip: str, path: str) -> str:
    return f"{_SCHEME}://{ip}{_PATH_PREFIX}{path}"


def _ok(data: dict) -> dict:
    return {"ok": True, "data": data}


def _err(message: str, status_code: int = 0) -> dict:
    result: dict = {"ok": False, "error": message}
    if status_code:
        result["status_code"] = status_code
    return result


def login(ip: str, username: str, password: str) -> str:
    """POST /user/login, return token string. Raise CredentialError on failure."""
    url = _url(ip, "/user/login")
    try:
        r = requests.post(
            url,
            json={"username": username, "password": password},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        raise CredentialError(f"Connection refused to {ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        raise CredentialError(f"Connection timed out to {ip}")
    if not r.ok:
        raise CredentialError(f"Login failed for {ip}: HTTP {r.status_code}")
    return r.json()["token"]


def get(session, path: str) -> dict:
    try:
        r = requests.get(
            _url(session.ip, path),
            headers={"X-auth-token": session.token},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        return _err(f"Connection refused to {session.ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        return _err(f"Connection timed out to {session.ip}")
    if r.status_code == 401:
        return _err("Session expired, retry to re-authenticate.", 401)
    if not r.ok:
        return _err(f"HTTP {r.status_code}", r.status_code)
    return _ok(r.json())


def post(session, path: str, body: dict | None = None) -> dict:
    try:
        r = requests.post(
            _url(session.ip, path),
            headers={
                "X-auth-token": session.token,
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=_TIMEOUT,
            verify=_VERIFY_SSL,
        )
    except requests.exceptions.ConnectionError:
        return _err(f"Connection refused to {session.ip}, is the device reachable?")
    except requests.exceptions.Timeout:
        return _err(f"Connection timed out to {session.ip}")
    if r.status_code == 401:
        return _err("Session expired, retry to re-authenticate.", 401)
    if not r.ok:
        return _err(f"HTTP {r.status_code}", r.status_code)
    return _ok(r.json())
