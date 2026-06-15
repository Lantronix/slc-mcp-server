import os
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError
from slc_mcp.providers.vault import VaultCredentialProvider


def test_vault_missing_hvac_raises():
    import sys
    saved = sys.modules.pop("hvac", None)
    sys.modules["hvac"] = None  # type: ignore
    try:
        with pytest.raises(CredentialError, match="hvac is required"):
            VaultCredentialProvider().get_credentials("device-1")
    finally:
        if saved is not None:
            sys.modules["hvac"] = saved
        else:
            sys.modules.pop("hvac", None)


def test_vault_missing_env_raises():
    clean = {k: v for k, v in os.environ.items() if k not in ("VAULT_ADDR", "VAULT_TOKEN")}
    mock_hvac = MagicMock()
    with patch.dict(os.environ, clean, clear=True):
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            with pytest.raises(CredentialError, match="VAULT_ADDR"):
                VaultCredentialProvider().get_credentials("device-1")


def test_vault_returns_credentials():
    mock_hvac = MagicMock()
    mock_client = MagicMock()
    mock_hvac.Client.return_value = mock_client
    mock_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"ip": "10.1.1.1", "username": "admin", "password": "vaultpass"}}
    }
    env = {"VAULT_ADDR": "https://vault.example.com", "VAULT_TOKEN": "hvs.test"}
    with patch.dict(os.environ, env, clear=False):
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            creds = VaultCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds["ip"] == "10.1.1.1"
    assert creds["username"] == "admin"
    assert creds["password"] == "vaultpass"
    assert creds["totp_secret"] is None
    mock_client.secrets.kv.v2.read_secret_version.assert_called_once_with(path="slc/slc9000-dc-a")


def test_vault_missing_secret_field_raises():
    mock_hvac = MagicMock()
    mock_client = MagicMock()
    mock_hvac.Client.return_value = mock_client
    mock_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {"data": {"ip": "10.1.1.1", "username": "admin"}}
    }
    env = {"VAULT_ADDR": "https://vault.example.com", "VAULT_TOKEN": "hvs.test"}
    with patch.dict(os.environ, env, clear=False):
        with patch.dict("sys.modules", {"hvac": mock_hvac}):
            with pytest.raises(CredentialError, match="missing field"):
                VaultCredentialProvider().get_credentials("device-1")
