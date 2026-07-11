import os
import logging

import requests
import urllib3

try:
    import pyotp as pyotp
except ImportError:
    pyotp = None  # type: ignore[assignment]

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("SLC_REQUEST_TIMEOUT", "30"))
_PATH_PREFIX = os.getenv("SLC_API_PATH_PREFIX", "/api/v2")
_VERIFY_SSL = os.getenv("SLC_VERIFY_SSL", "true").lower() not in ("false", "0", "no")
_SCHEME = os.getenv("SLC_URL_SCHEME", "https")

if not _VERIFY_SSL:
    log.warning(
        "SLC_VERIFY_SSL is disabled, TLS certificate verification is OFF. "
        "Only use this for lab devices with self-signed certificates; never in production."
    )
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


def _extract_error_message(response: requests.Response) -> str:
    try:
        body = response.json()
        return (
            body.get("error")
            or body.get("message")
            or body.get("description")
            or f"HTTP {response.status_code}"
        )
    except Exception:
        return f"HTTP {response.status_code}"


def login(ip: str, username: str, password: str, totp_secret: str | None = None) -> str:
    """POST /user/login, return token string. Handles 2FA challenge if device requires it.
    Raises CredentialError on failure."""
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
        if r.status_code == 401:
            raise CredentialError(f"Authentication failed for {ip}: invalid username or password.")
        if r.status_code == 403:
            raise CredentialError(
                f"Access denied for {ip}: account may be locked or have insufficient permissions."
            )
        if r.status_code == 503:
            raise CredentialError(
                f"Authentication service unavailable on {ip}: device may still be starting up."
            )
        raise CredentialError(f"Login failed for {ip}: HTTP {r.status_code}")

    data = r.json()

    if data.get("challenge_required"):
        challenge_type = data.get("challenge_type", "")
        if challenge_type in ("passcode", "tokencode"):
            if not totp_secret:
                raise CredentialError(
                    "2FA is enabled on this device. "
                    "Set SLC_{DEVICE_ID}_TOTP_SECRET in your environment with the device TOTP secret."
                )
            if pyotp is None:
                raise CredentialError(
                    "pyotp is required for 2FA: pip install pyotp"
                )
            code = pyotp.TOTP(totp_secret).now()
            try:
                r2 = requests.post(
                    url,
                    json={
                        "username": username,
                        "password": password,
                        "challenge_id": data["challenge_id"],
                        "challenge_state": data["challenge_state"],
                        "challenge_code": code,
                    },
                    timeout=_TIMEOUT,
                    verify=_VERIFY_SSL,
                )
            except requests.exceptions.ConnectionError:
                raise CredentialError(f"Connection refused to {ip} during 2FA challenge")
            except requests.exceptions.Timeout:
                raise CredentialError(f"Connection timed out to {ip} during 2FA challenge")
            if not r2.ok:
                raise CredentialError(f"2FA login failed for {ip}: HTTP {r2.status_code}")
            data = r2.json()
        else:
            raise CredentialError(
                f"2FA challenge type '{challenge_type}' requires manual setup. "
                "Complete 2FA configuration via the device web UI before using the MCP server."
            )

    token = data.get("token")
    if not token:
        raise CredentialError(f"Login failed: {data}")
    return token


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
        return _err(
            "Authentication failed (HTTP 401). Credentials may be invalid or the session expired. "
            "Check the credential provider configuration.",
            401,
        )
    if r.status_code == 403:
        return _err(
            f"Access denied (HTTP 403). The credentials used do not have sufficient permissions "
            f"for this operation on {session.ip}. Check the user role configuration on the device.",
            403,
        )
    if not r.ok:
        return _err(_extract_error_message(r), r.status_code)
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
        return _err(
            "Authentication failed (HTTP 401). Credentials may be invalid or the session expired. "
            "Check the credential provider configuration.",
            401,
        )
    if r.status_code == 403:
        return _err(
            f"Access denied (HTTP 403). The credentials used do not have sufficient permissions "
            f"for this operation on {session.ip}. Check the user role configuration on the device.",
            403,
        )
    if not r.ok:
        return _err(_extract_error_message(r), r.status_code)
    return _ok(r.json())


def put(session, path: str, body: dict | None = None) -> dict:
    try:
        r = requests.put(
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
        return _err(
            "Authentication failed (HTTP 401). Credentials may be invalid or the session expired. "
            "Check the credential provider configuration.",
            401,
        )
    if r.status_code == 403:
        return _err(
            f"Access denied (HTTP 403). The credentials used do not have sufficient permissions "
            f"for this operation on {session.ip}. Check the user role configuration on the device.",
            403,
        )
    if not r.ok:
        return _err(_extract_error_message(r), r.status_code)
    return _ok(r.json())


def delete(session, path: str) -> dict:
    try:
        r = requests.delete(
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
        return _err(
            "Authentication failed (HTTP 401). Credentials may be invalid or the session expired. "
            "Check the credential provider configuration.",
            401,
        )
    if r.status_code == 403:
        return _err(
            f"Access denied (HTTP 403). The credentials used do not have sufficient permissions "
            f"for this operation on {session.ip}. Check the user role configuration on the device.",
            403,
        )
    if not r.ok:
        return _err(_extract_error_message(r), r.status_code)
    # DELETE may return 204 No Content
    if r.status_code == 204 or not r.content:
        return _ok({})
    return _ok(r.json())


def patch(session, path: str, body: dict | None = None) -> dict:
    try:
        r = requests.patch(
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
        return _err(
            "Authentication failed (HTTP 401). Credentials may be invalid or the session expired. "
            "Check the credential provider configuration.",
            401,
        )
    if r.status_code == 403:
        return _err(
            f"Access denied (HTTP 403). The credentials used do not have sufficient permissions "
            f"for this operation on {session.ip}. Check the user role configuration on the device.",
            403,
        )
    if not r.ok:
        return _err(_extract_error_message(r), r.status_code)
    return _ok(r.json())
