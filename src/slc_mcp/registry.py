import logging
import os

import requests

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)


class PercepxionRegistry:
    def __init__(self) -> None:
        self._base_url = os.getenv("PERCEPXION_API_URL", "").rstrip("/")
        self._auth_token: str | None = None
        self._csrf_token: str | None = None

    def _login(self) -> tuple[str, str]:
        username = os.getenv("PERCEPXION_USERNAME")
        password = os.getenv("PERCEPXION_PASSWORD")
        if not self._base_url or not username or not password:
            raise CredentialError(
                "Percepxion provider requires PERCEPXION_API_URL, PERCEPXION_USERNAME, PERCEPXION_PASSWORD"
            )
        r = requests.post(
            f"{self._base_url}/v2/user/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        token = data.get("token")
        csrf = data.get("csrf_token")
        if not token or not csrf:
            raise CredentialError(
                f"Percepxion login succeeded but token/csrf_token missing. Got keys: {list(data.keys())}"
            )
        return token, csrf

    def _headers(self) -> dict[str, str]:
        return {
            "x-mystq-token": self._auth_token or "",
            "x-csrf-token": self._csrf_token or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _fetch_device(self, device_id: str) -> requests.Response:
        return requests.post(
            f"{self._base_url}/v3/device/get",
            json={"device_id": [device_id]},
            headers=self._headers(),
            timeout=30,
        )

    def get_device_ip(self, device_id: str) -> str:
        if not self._auth_token:
            self._auth_token, self._csrf_token = self._login()

        r = self._fetch_device(device_id)
        if r.status_code == 401:
            self._auth_token, self._csrf_token = self._login()
            r = self._fetch_device(device_id)

        r.raise_for_status()
        data = r.json()

        # Response may wrap devices in results or search_results
        candidates = data.get("results") or data.get("search_results") or []
        device = candidates[0] if candidates else data
        attrs = device.get("attributes", {}) or {}

        ip = (
            device.get("ip_address")
            or device.get("ip")
            or device.get("address")
            or attrs.get("ip_address")
            or attrs.get("management_ip")
            or attrs.get("ip")
        )
        if not ip:
            raise CredentialError(
                f"Percepxion returned no IP for device {device_id!r}. "
                f"Device keys: {list(device.keys())}, attribute keys: {list(attrs.keys())}"
            )
        return ip
