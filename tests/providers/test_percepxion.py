import os
import pytest
from unittest.mock import patch, MagicMock
from slc_mcp.providers import CredentialError


def test_percepxion_provider_builds_creds():
    mock_registry = MagicMock()
    mock_registry.get_device_ip.return_value = "10.5.0.10"
    env = {"SLC_USERNAME": "admin", "SLC_PASSWORD": "secret"}
    with patch("slc_mcp.providers.percepxion._registry", mock_registry):
        with patch.dict(os.environ, env, clear=False):
            from slc_mcp.providers.percepxion import PercepxionCredentialProvider
            creds = PercepxionCredentialProvider().get_credentials("dc-slc-01")
    assert creds["ip"] == "10.5.0.10"
    assert creds["username"] == "admin"
    mock_registry.get_device_ip.assert_called_once_with("dc-slc-01")


def test_percepxion_provider_missing_creds_raises():
    mock_registry = MagicMock()
    mock_registry.get_device_ip.return_value = "10.5.0.10"
    clean = {k: v for k, v in os.environ.items() if not k.startswith("SLC_")}
    with patch("slc_mcp.providers.percepxion._registry", mock_registry):
        with patch.dict(os.environ, clean, clear=True):
            from slc_mcp.providers.percepxion import PercepxionCredentialProvider
            with pytest.raises(CredentialError, match="Missing"):
                PercepxionCredentialProvider().get_credentials("dc-slc-01")


def test_registry_missing_env_raises():
    from slc_mcp.registry import PercepxionRegistry
    clean = {k: v for k, v in os.environ.items() if not k.startswith("PERCEPXION_")}
    with patch.dict(os.environ, clean, clear=True):
        registry = PercepxionRegistry()
        with pytest.raises(CredentialError, match="PERCEPXION_API_URL"):
            registry._login()
