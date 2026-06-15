import os

from slc_mcp.providers import CredentialProvider, CredentialError


class VaultCredentialProvider(CredentialProvider):
    def get_credentials(self, device_id: str) -> dict[str, str]:
        try:
            import hvac
        except ImportError:
            raise CredentialError(
                "hvac is required for the vault provider: pip install hvac"
            )
        addr = os.getenv("VAULT_ADDR")
        token = os.getenv("VAULT_TOKEN")
        if not addr or not token:
            raise CredentialError(
                "VAULT_ADDR and VAULT_TOKEN are required for the vault provider"
            )
        vault_client = hvac.Client(url=addr, token=token)
        path = f"slc/{device_id}"
        try:
            secret = vault_client.secrets.kv.v2.read_secret_version(path=path)
            data = secret["data"]["data"]
        except Exception as exc:
            raise CredentialError(
                f"Vault read failed for secret/slc/{device_id}: {exc}"
            ) from exc
        for field in ("ip", "username", "password"):
            if not data.get(field):
                raise CredentialError(
                    f"Vault secret secret/slc/{device_id} missing field: {field!r}"
                )
        return {
            "ip": data["ip"],
            "username": data["username"],
            "password": data["password"],
            "totp_secret": data.get("totp_secret") or None,
        }
