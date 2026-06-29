"""CyberArk Central Credential Provider (CCP) integration.

Retrieves SLC device credentials via the AIM Web Service REST API.

Required env vars:
    CYBERARK_URL      Base URL of the CCP server (e.g. https://cyberark.internal)
    CYBERARK_APP_ID   Registered AppID with access to the safe
    CYBERARK_SAFE     Safe name where SLC device accounts live

Optional (mTLS, enabled automatically when both paths are set):
    CYBERARK_CERT_PATH   Path to client certificate (.pem or .crt)
    CYBERARK_KEY_PATH    Path to client private key (.pem)
    CYBERARK_VERIFY_SSL  Set to 'false' to disable server cert verification (lab use only)
"""

import os
import re

import requests

from slc_mcp.providers import CredentialError, CredentialProvider


class CyberArkCredentialProvider(CredentialProvider):
    def __init__(self) -> None:
        self._url = os.getenv("CYBERARK_URL", "").rstrip("/")
        self._app_id = os.getenv("CYBERARK_APP_ID", "")
        self._safe = os.getenv("CYBERARK_SAFE", "")
        self._cert_path = os.getenv("CYBERARK_CERT_PATH")
        self._key_path = os.getenv("CYBERARK_KEY_PATH")
        self._verify_ssl = os.getenv("CYBERARK_VERIFY_SSL", "true").lower() != "false"

        if not self._url or not self._app_id or not self._safe:
            raise CredentialError(
                "CyberArk provider requires CYBERARK_URL, CYBERARK_APP_ID, and CYBERARK_SAFE"
            )

    def _cert(self) -> tuple[str, str] | str | None:
        """Build cert arg for requests: tuple if separate cert+key, str if PEM bundle, None if not set."""
        if self._cert_path and self._key_path:
            return (self._cert_path, self._key_path)
        if self._cert_path:
            return self._cert_path  # PEM bundle with embedded key
        return None

    def get_credentials(self, device_id: str) -> dict[str, str]:
        params = {
            "AppID": self._app_id,
            "Safe": self._safe,
            "Object": device_id,
        }
        try:
            r = requests.get(
                f"{self._url}/AIMWebService/api/Accounts",
                params=params,
                cert=self._cert(),
                verify=self._verify_ssl,
                timeout=30,
            )
        except requests.exceptions.SSLError as exc:
            raise CredentialError(f"CyberArk mTLS error: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise CredentialError(f"CyberArk connection failed: {exc}") from exc

        if r.status_code == 404:
            raise CredentialError(
                f"CyberArk: no account found for object {device_id!r} in safe {self._safe!r}. "
                "Verify CYBERARK_SAFE and the object name match what's in the vault."
            )
        if r.status_code == 403:
            raise CredentialError(
                f"CyberArk: access denied for AppID {self._app_id!r}. "
                "Verify the AppID is allowed to access this safe and is registered on this host."
            )
        r.raise_for_status()

        data = r.json()
        username = data.get("UserName") or data.get("username")
        password = data.get("Content") or data.get("password")

        if not username or not password:
            raise CredentialError(
                f"CyberArk returned account for {device_id!r} but UserName or Content is missing. "
                f"Got keys: {list(data.keys())}"
            )

        # CyberArk's Address field is the device's management IP.
        # Fall back to per-device env var if CyberArk doesn't store it.
        ip = data.get("Address") or data.get("address")
        if not ip:
            key = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
            ip = os.getenv(f"SLC_{key}_IP") or os.getenv("SLC_DEFAULT_IP")
        if not ip:
            raise CredentialError(
                f"CyberArk returned no Address for {device_id!r}. "
                "Either store the IP in the CyberArk account's Address field, "
                "or set SLC_<DEVICE_ID>_IP / SLC_DEFAULT_IP."
            )

        return {"ip": ip, "username": username, "password": password, "totp_secret": None}
