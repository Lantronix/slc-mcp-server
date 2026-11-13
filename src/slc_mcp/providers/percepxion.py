import re

from slc_mcp.providers import CredentialProvider, CredentialError, read_env_secret
from slc_mcp.registry import PercepxionRegistry

_registry = PercepxionRegistry()


class PercepxionCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        ip = _registry.get_device_ip(device_id)
        key = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
        username = read_env_secret(f"SLC_{key}_USERNAME") or read_env_secret("SLC_USERNAME")
        password = read_env_secret(f"SLC_{key}_PASSWORD") or read_env_secret("SLC_PASSWORD")
        if not username or not password:
            raise CredentialError(
                f"Missing SLC_{key}_USERNAME/PASSWORD or SLC_USERNAME/PASSWORD "
                f"for Percepxion provider"
            )
        totp_secret = (
            read_env_secret(f"SLC_{key}_TOTP_SECRET") or read_env_secret("SLC_TOTP_SECRET") or None
        )
        return {"ip": ip, "username": username, "password": password, "totp_secret": totp_secret}
