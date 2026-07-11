import os
import pytest
from unittest.mock import patch
from slc_mcp.providers import CredentialError
from slc_mcp.providers.env import EnvCredentialProvider, _device_key


def test_device_key_uppercases_and_replaces():
    assert _device_key("slc9000-dc-a") == "SLC9000_DC_A"
    assert _device_key("device.1") == "DEVICE_1"
    assert _device_key("MY_DEVICE") == "MY_DEVICE"


def test_per_device_env_vars():
    env = {
        "SLC_SLC9000_DC_A_IP": "10.0.0.1",
        "SLC_SLC9000_DC_A_USERNAME": "admin",
        "SLC_SLC9000_DC_A_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds["ip"] == "10.0.0.1"
    assert creds["username"] == "admin"
    assert creds["password"] == "secret"
    assert creds["totp_secret"] is None


def test_global_fallback():
    base = {k: v for k, v in os.environ.items() if not k.startswith("SLC_")}
    base.update({
        "SLC_DEFAULT_IP": "10.0.0.2",
        "SLC_USERNAME": "user",
        "SLC_PASSWORD": "pass",
    })
    with patch.dict(os.environ, base, clear=True):
        creds = EnvCredentialProvider().get_credentials("any-device")
    assert creds["ip"] == "10.0.0.2"
    assert creds["username"] == "user"


def test_missing_env_raises_credential_error():
    clean = {k: v for k, v in os.environ.items() if not k.startswith("SLC_")}
    with patch.dict(os.environ, clean, clear=True):
        with pytest.raises(CredentialError, match="Missing env vars"):
            EnvCredentialProvider().get_credentials("unknown-device")


def test_per_device_overrides_global():
    env = {
        "SLC_DEFAULT_IP": "10.0.0.99",
        "SLC_USERNAME": "global",
        "SLC_PASSWORD": "global",
        "SLC_MYDEV_IP": "10.0.0.5",
        "SLC_MYDEV_USERNAME": "specific",
        "SLC_MYDEV_PASSWORD": "specific",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("mydev")
    assert creds["ip"] == "10.0.0.5"
    assert creds["username"] == "specific"


def test_fallback_logs_warning(caplog):
    base = {k: v for k, v in os.environ.items() if not k.startswith("SLC_")}
    base.update({
        "SLC_DEFAULT_IP": "10.0.0.2",
        "SLC_USERNAME": "user",
        "SLC_PASSWORD": "pass",
    })
    with patch.dict(os.environ, base, clear=True):
        with caplog.at_level("WARNING", logger="slc_mcp.providers.env"):
            EnvCredentialProvider().get_credentials("typo-device")
    assert any("typo-device" in rec.message for rec in caplog.records)


def test_full_per_device_vars_no_warning(caplog):
    env = {
        "SLC_SLC9000_DC_A_IP": "10.0.0.1",
        "SLC_SLC9000_DC_A_USERNAME": "admin",
        "SLC_SLC9000_DC_A_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        with caplog.at_level("WARNING", logger="slc_mcp.providers.env"):
            EnvCredentialProvider().get_credentials("slc9000-dc-a")
    assert caplog.records == []


def test_known_device_ids_rejects_unknown():
    env = {"SLC_KNOWN_DEVICE_IDS": "slc9000-dc-a,slc9000-dc-b"}
    with patch.dict(os.environ, env, clear=False):
        with pytest.raises(CredentialError, match="SLC_KNOWN_DEVICE_IDS"):
            EnvCredentialProvider().get_credentials("typo-device")


def test_known_device_ids_allows_listed_id():
    env = {
        "SLC_KNOWN_DEVICE_IDS": "slc9000-dc-a,slc9000-dc-b",
        "SLC_SLC9000_DC_A_IP": "10.0.0.1",
        "SLC_SLC9000_DC_A_USERNAME": "admin",
        "SLC_SLC9000_DC_A_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        creds = EnvCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds["ip"] == "10.0.0.1"
