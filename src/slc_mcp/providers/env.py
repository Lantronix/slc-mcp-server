import logging
import os
import re

from slc_mcp.providers import CredentialError, CredentialProvider

log = logging.getLogger(__name__)


def _device_key(device_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", device_id).upper()


class EnvCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        known_raw = os.getenv("SLC_KNOWN_DEVICE_IDS")
        if known_raw:
            known = {d.strip() for d in known_raw.split(",") if d.strip()}
            if device_id not in known:
                raise CredentialError(
                    f"device_id {device_id!r} is not in SLC_KNOWN_DEVICE_IDS. "
                    f"Known device IDs: {', '.join(sorted(known)) or '(none configured)'}"
                )

        key = _device_key(device_id)
        ip = os.getenv(f"SLC_{key}_IP")
        username = os.getenv(f"SLC_{key}_USERNAME")
        password = os.getenv(f"SLC_{key}_PASSWORD")

        if ip is None or username is None or password is None:
            log.warning(
                "device_id %r has no (or only partial) per-device SLC_%s_* env vars; "
                "falling back to SLC_DEFAULT_IP/SLC_USERNAME/SLC_PASSWORD for missing "
                "fields. If %r was a typo, credentials for the wrong device may be used.",
                device_id, key, device_id,
            )

        ip = ip or os.getenv("SLC_DEFAULT_IP")
        username = username or os.getenv("SLC_USERNAME")
        password = password or os.getenv("SLC_PASSWORD")

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
