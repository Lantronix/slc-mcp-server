import logging
import os

import requests

from slc_mcp.providers import CredentialError

log = logging.getLogger(__name__)


class PercepxionRegistry:
    def __init__(self) -> None:
        self._base_url = os.getenv("PERCEPXION_API_URL", "").rstrip("/")
        self._token: str | None = None

    def _login(self) -> str:
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
        return r.json()["token"]

    def get_device_ip(self, device_id: str) -> str:
        if not self._token:
            self._token = self._login()
        headers = {"x-mystq-token": self._token}
        r = requests.get(
            f"{self._base_url}/v3/device/get",
            params={"id": device_id},
            headers=headers,
            timeout=30,
        )
        if r.status_code == 401:
            self._token = self._login()
            headers = {"x-mystq-token": self._token}
            r = requests.get(
                f"{self._base_url}/v3/device/get",
                params={"id": device_id},
                headers=headers,
                timeout=30,
            )
        r.raise_for_status()
        data = r.json()
        ip = data.get("ip") or data.get("address")
        if not ip:
            raise CredentialError(f"Percepxion returned no IP for device {device_id!r}")
        return ip
