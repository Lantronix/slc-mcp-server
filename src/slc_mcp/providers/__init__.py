from abc import ABC, abstractmethod
import os


class CredentialError(Exception):
    pass


class CredentialProvider(ABC):
    @abstractmethod
    def get_credentials(self, device_id: str) -> dict[str, str]:
        """Return {"ip": ..., "username": ..., "password": ...}.
        Raise CredentialError if device_id is unknown or creds are missing."""


def read_env_secret(name: str) -> str | None:
    """Return env var ``name``, or the first line of the file named by ``name_FILE``.

    The ``_FILE`` form is the Docker and Kubernetes secrets convention. Setting
    both forms is an error, so a stale variable can't silently win.
    """
    value = os.getenv(name)
    path = (os.getenv(f"{name}_FILE") or "").strip()
    if not path:
        return value or None
    if value:
        raise CredentialError(f"Set {name} or {name}_FILE, not both.")
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline().rstrip("\r\n")
    except OSError as exc:
        raise CredentialError(f"{name}_FILE can't be read: {exc}") from exc
    return first or None


def get_provider() -> CredentialProvider:
    name = os.getenv("SLC_CREDENTIAL_PROVIDER", "env").lower()
    if name == "env":
        from slc_mcp.providers.env import EnvCredentialProvider
        return EnvCredentialProvider()
    if name == "percepxion":
        from slc_mcp.providers.percepxion import PercepxionCredentialProvider
        return PercepxionCredentialProvider()
    if name == "vault":
        from slc_mcp.providers.vault import VaultCredentialProvider
        return VaultCredentialProvider()
    if name == "aws":
        from slc_mcp.providers.aws import AWSCredentialProvider
        return AWSCredentialProvider()
    if name == "azure":
        from slc_mcp.providers.azure import AzureKeyVaultCredentialProvider
        return AzureKeyVaultCredentialProvider()
    if name == "cyberark":
        from slc_mcp.providers.cyberark import CyberArkCredentialProvider
        return CyberArkCredentialProvider()
    if name == "command":
        from slc_mcp.providers.command import CommandCredentialProvider
        return CommandCredentialProvider()
    raise CredentialError(
        f"Unknown provider: {name!r}. Set SLC_CREDENTIAL_PROVIDER to: env, percepxion, vault, aws, azure, cyberark, command"
    )
