import json
import os
import re
from urllib.parse import urlparse

from slc_mcp.providers import CredentialError, CredentialProvider

try:
    from azure.core.exceptions import (  # type: ignore
        AzureError,
        ClientAuthenticationError,
        HttpResponseError,
        ResourceNotFoundError,
    )
    from azure.identity import DefaultAzureCredential  # type: ignore
    from azure.keyvault.secrets import SecretClient  # type: ignore
except ImportError:
    SecretClient = None  # type: ignore
    DefaultAzureCredential = None  # type: ignore
    AzureError = ClientAuthenticationError = HttpResponseError = ResourceNotFoundError = None  # type: ignore

_NAME_OK = re.compile(r"^[A-Za-z0-9-]+$")


def secret_name_for(device_id: str, prefix: str = "slc-") -> str:
    """Key Vault secret name for a device: prefix + device_id with every character
    other than a letter, digit or '-' replaced by '-' (slc9000.dc_a -> slc-slc9000-dc-a)."""
    return prefix + re.sub(r"[^A-Za-z0-9-]", "-", device_id)


class AzureKeyVaultCredentialProvider(CredentialProvider):
    """Read per-device SLC credentials from Azure Key Vault.

    Env vars:
        AZURE_KEYVAULT_URL            Vault URL, e.g. https://my-vault.vault.azure.net
        AZURE_KEYVAULT_SECRET_PREFIX  Secret name prefix (default "slc-"). Each device's
                                      secret is prefix + device_id, with characters Key
                                      Vault doesn't allow replaced by '-'.

    Each secret holds a JSON object with ip, username, password and an optional
    totp_secret. Authentication uses DefaultAzureCredential (managed identity,
    workload identity, AZURE_CLIENT_ID / AZURE_TENANT_ID / AZURE_CLIENT_SECRET, or
    az login); the identity needs the "Key Vault Secrets User" role on the vault.
    Secret values never appear in error messages.
    """

    def __init__(self) -> None:
        if SecretClient is None or DefaultAzureCredential is None:
            raise CredentialError(
                "azure-identity and azure-keyvault-secrets are required for the azure provider: "
                "pip install 'slc-mcp-server[azure]'"
            )
        url = (os.getenv("AZURE_KEYVAULT_URL") or "").strip()
        if not url:
            raise CredentialError("AZURE_KEYVAULT_URL must be set when using the azure provider.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise CredentialError(
                f"AZURE_KEYVAULT_URL must be an https URL like https://my-vault.vault.azure.net, got {url!r}"
            )
        prefix = os.getenv("AZURE_KEYVAULT_SECRET_PREFIX", "slc-")
        if prefix and not _NAME_OK.match(prefix):
            raise CredentialError(
                "AZURE_KEYVAULT_SECRET_PREFIX may contain only letters, digits and '-'"
            )
        self.vault_url = url
        self.prefix = prefix
        self._client = SecretClient(vault_url=url, credential=DefaultAzureCredential())

    def get_credentials(self, device_id: str) -> dict[str, str]:
        if not device_id:
            raise CredentialError("device_id is required")
        name = secret_name_for(device_id, self.prefix)
        if len(name) > 127:
            raise CredentialError(
                f"Key Vault secret name for {device_id!r} would exceed 127 characters"
            )
        where = f"secret {name!r} in {self.vault_url}"
        try:
            secret = self._client.get_secret(name)
        except ResourceNotFoundError as exc:
            raise CredentialError(
                f"Azure Key Vault: {where} not found (device_id {device_id!r})."
            ) from exc
        except ClientAuthenticationError as exc:
            raise CredentialError(
                "Azure Key Vault: no usable Azure identity. Configure managed identity, "
                "AZURE_CLIENT_ID/AZURE_TENANT_ID/AZURE_CLIENT_SECRET, or run 'az login'."
            ) from exc
        except HttpResponseError as exc:
            if getattr(exc, "status_code", None) == 403:
                raise CredentialError(
                    f"Azure Key Vault: access denied to {where}. Grant the identity the "
                    "'Key Vault Secrets User' role or a get-secret access policy."
                ) from exc
            raise CredentialError(
                f"Azure Key Vault request failed for {where} (HTTP {getattr(exc, 'status_code', '?')})"
            ) from exc
        except AzureError as exc:
            raise CredentialError(
                f"Azure Key Vault: can't reach {self.vault_url} ({type(exc).__name__}). "
                "Check AZURE_KEYVAULT_URL, DNS and network access to the vault."
            ) from exc

        try:
            data = json.loads(secret.value or "")
        except json.JSONDecodeError as exc:
            raise CredentialError(f"Azure Key Vault {where} must hold a JSON object") from exc
        if not isinstance(data, dict):
            raise CredentialError(f"Azure Key Vault {where} must hold a JSON object")
        for field in ("ip", "username", "password"):
            if not data.get(field):
                raise CredentialError(f"Azure Key Vault {where} missing field: {field!r}")
        return {
            "ip": str(data["ip"]),
            "username": str(data["username"]),
            "password": str(data["password"]),
            "totp_secret": str(data["totp_secret"]) if data.get("totp_secret") else None,
        }
