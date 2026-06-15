import os
import re

from slc_mcp.providers import CredentialProvider, CredentialError


def _device_key(device_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()


class EnvCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        key = _device_key(device_id)
        ip = os.getenv(f"SLC_{key}_IP") or os.getenv("SLC_DEFAULT_IP")
        username = os.getenv(f"SLC_{key}_USERNAME") or os.getenv("SLC_USERNAME")
        password = os.getenv(f"SLC_{key}_PASSWORD") or os.getenv("SLC_PASSWORD")
        missing = [
            name
            for name, val in [
                (f"SLC_{key}_IP or SLC_DEFAULT_IP", ip),
                (f"SLC_{key}_USERNAME or SLC_USERNAME", username),
                (f"SLC_{key}_PASSWORD or SLC_PASSWORD", password),
            ]
            if not val
        ]
        if missing:
            raise CredentialError(
                f"Missing env vars for {device_id!r}: {', '.join(missing)}"
            )
        totp_secret = os.getenv(f"SLC_{key}_TOTP_SECRET") or os.getenv("SLC_TOTP_SECRET") or None
        return {"ip": ip, "username": username, "password": password, "totp_secret": totp_secret}
