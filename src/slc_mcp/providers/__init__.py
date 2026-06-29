from abc import ABC, abstractmethod
import os


class CredentialError(Exception):
    pass


class CredentialProvider(ABC):
    @abstractmethod
    def get_credentials(self, device_id: str) -> dict[str, str]:
        """Return {"ip": ..., "username": ..., "password": ...}.
        Raise CredentialError if device_id is unknown or creds are missing."""


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
    if name == "cyberark":
        from slc_mcp.providers.cyberark import CyberArkCredentialProvider
        return CyberArkCredentialProvider()
    raise CredentialError(
        f"Unknown provider: {name!r}. Set SLC_CREDENTIAL_PROVIDER to: env, percepxion, vault, aws, cyberark"
    )
