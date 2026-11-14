import json
import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

import slc_mcp.providers.azure as az
from slc_mcp.providers import CredentialError, get_provider
from slc_mcp.providers.azure import AzureKeyVaultCredentialProvider, secret_name_for

# CI doesn't install the Azure SDK, so these tests patch the module's SDK names.


class _AzBase(Exception):
    pass


class _AzErr(_AzBase):
    def __init__(self, msg="", status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class _AzNotFound(_AzErr):
    pass


class _AzAuth(_AzErr):
    pass


ENV = {"AZURE_KEYVAULT_URL": "https://example-vault.vault.azure.net"}


def _provider(env=ENV, secret_value=None, error=None):
    client = MagicMock()
    if error is not None:
        client.get_secret.side_effect = error
    else:
        client.get_secret.return_value = MagicMock(value=secret_value)
    stack = ExitStack()
    for target, value in [
        ("SecretClient", MagicMock(return_value=client)),
        ("DefaultAzureCredential", MagicMock()),
        ("ResourceNotFoundError", _AzNotFound),
        ("ClientAuthenticationError", _AzAuth),
        ("HttpResponseError", _AzErr),
        ("AzureError", _AzBase),
    ]:
        stack.enter_context(patch.object(az, target, value))
    stack.enter_context(patch.dict(os.environ, env, clear=True))
    return stack, client


def _creds(device_id="slc9000-dc-a", **kw):
    stack, client = _provider(**kw)
    with stack:
        return client, AzureKeyVaultCredentialProvider().get_credentials(device_id)


GOOD = json.dumps({"ip": "10.3.3.3", "username": "admin", "password": "azpass", "totp_secret": "JBSWY3DP"})


def test_secret_name_mapping():
    assert secret_name_for("slc9000-dc-a") == "slc-slc9000-dc-a"
    assert secret_name_for("slc9000.dc_a") == "slc-slc9000-dc-a"
    assert secret_name_for("DEV1", "lab-") == "lab-DEV1"


def test_get_provider_returns_azure():
    stack, _ = _provider(env=dict(ENV, SLC_CREDENTIAL_PROVIDER="azure"), secret_value=GOOD)
    with stack:
        assert isinstance(get_provider(), AzureKeyVaultCredentialProvider)


def test_reads_device_secret():
    client, creds = _creds(secret_value=GOOD)
    client.get_secret.assert_called_once_with("slc-slc9000-dc-a")
    assert creds == {"ip": "10.3.3.3", "username": "admin", "password": "azpass", "totp_secret": "JBSWY3DP"}


def test_custom_prefix_and_optional_totp():
    value = json.dumps({"ip": "10.3.3.4", "username": "u", "password": "p"})
    client, creds = _creds("dev1", env=dict(ENV, AZURE_KEYVAULT_SECRET_PREFIX="lab-slc-"), secret_value=value)
    client.get_secret.assert_called_once_with("lab-slc-dev1")
    assert creds["totp_secret"] is None


def test_sdk_missing():
    with patch.object(az, "SecretClient", None), patch.dict(os.environ, ENV, clear=True):
        with pytest.raises(CredentialError, match=r"slc-mcp-server\[azure\]"):
            AzureKeyVaultCredentialProvider()


@pytest.mark.parametrize("url", ["", "http://example-vault.vault.azure.net", "example-vault"])
def test_rejects_bad_url(url):
    stack, _ = _provider(env={"AZURE_KEYVAULT_URL": url})
    with stack:
        with pytest.raises(CredentialError, match="AZURE_KEYVAULT_URL"):
            AzureKeyVaultCredentialProvider()


def test_rejects_bad_prefix():
    stack, _ = _provider(env=dict(ENV, AZURE_KEYVAULT_SECRET_PREFIX="slc_"))
    with stack:
        with pytest.raises(CredentialError, match="PREFIX"):
            AzureKeyVaultCredentialProvider()


def test_rejects_overlong_name():
    with pytest.raises(CredentialError, match="127"):
        _creds("a" * 130, secret_value=GOOD)


@pytest.mark.parametrize("error,match", [
    (_AzNotFound("nope", 404), "not found"),
    (_AzAuth("no credential"), "az login"),
    (_AzErr("forbidden", 403), "Key Vault Secrets User"),
    (_AzErr("boom", 500), "HTTP 500"),
    (_AzBase("Failed to resolve host"), "can't reach"),
])
def test_error_mapping(error, match):
    with pytest.raises(CredentialError, match=match):
        _creds(error=error)


@pytest.mark.parametrize("value,match", [
    ("leaked-secret", "JSON object"),
    ('["leaked-secret"]', "JSON object"),
    (json.dumps({"ip": "1.2.3.4", "password": "leaked-secret"}), "username"),
])
def test_bad_secret_value_hidden(value, match):
    with pytest.raises(CredentialError) as exc:
        _creds(secret_value=value)
    assert match in str(exc.value)
    assert "leaked-secret" not in str(exc.value)
