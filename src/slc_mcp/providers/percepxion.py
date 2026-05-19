import os
import re

from slc_mcp.providers import CredentialProvider, CredentialError
from slc_mcp.registry import PercepxionRegistry

_registry = PercepxionRegistry()


class PercepxionCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        ip = _registry.get_device_ip(device_id)
        key = re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()
        username = os.getenv(f"SLC_{key}_USERNAME") or os.getenv("SLC_USERNAME")
        password = os.getenv(f"SLC_{key}_PASSWORD") or os.getenv("SLC_PASSWORD")
        if not username or not password:
            raise CredentialError(
                f"Missing SLC_{key}_USERNAME/PASSWORD or SLC_USERNAME/PASSWORD "
                f"for Percepxion provider"
            )
        return {"ip": ip, "username": username, "password": password}
