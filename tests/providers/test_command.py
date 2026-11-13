import json
import os
import shlex
import sys
from unittest.mock import patch

import pytest

from slc_mcp.providers import CredentialError, get_provider
from slc_mcp.providers.command import CommandCredentialProvider


def _py(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


ECHO_DEVICE = _py(
    "import json, os, sys; "
    "print(json.dumps({'ip': '10.0.0.9', 'username': sys.argv[1], "
    "'password': os.environ['SLC_DEVICE_ID'], 'totp_secret': 'JBSWY3DP'}))"
) + " user-{device_id}"


def test_get_provider_returns_command_provider():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_PROVIDER": "command", "SLC_CREDENTIAL_COMMAND": "true"}, clear=True):
        assert isinstance(get_provider(), CommandCredentialProvider)


def test_requires_command():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(CredentialError, match="SLC_CREDENTIAL_COMMAND"):
            CommandCredentialProvider()


def test_rejects_bad_timeout():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": "true", "SLC_CREDENTIAL_COMMAND_TIMEOUT": "0"}, clear=True):
        with pytest.raises(CredentialError, match="greater than 0"):
            CommandCredentialProvider()


def test_substitutes_device_id_and_sets_env():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": ECHO_DEVICE}, clear=True):
        creds = CommandCredentialProvider().get_credentials("slc9000-dc-a")
    assert creds == {
        "ip": "10.0.0.9",
        "username": "user-slc9000-dc-a",
        "password": "slc9000-dc-a",
        "totp_secret": "JBSWY3DP",
    }


def test_totp_secret_optional():
    cmd = _py("import json; print(json.dumps({'ip': '1.2.3.4', 'username': 'u', 'password': 'p'}))")
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": cmd}, clear=True):
        assert CommandCredentialProvider().get_credentials("dev1")["totp_secret"] is None


@pytest.mark.parametrize("bad", ["", "-rf", "a b", "a;b", "$(id)", "../x", "a" * 200])
def test_rejects_unsafe_device_ids(bad):
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": ECHO_DEVICE}, clear=True):
        with pytest.raises(CredentialError, match="not allowed"):
            CommandCredentialProvider().get_credentials(bad)


def test_honors_known_device_ids():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": ECHO_DEVICE, "SLC_KNOWN_DEVICE_IDS": "dev1,dev2"}, clear=True):
        provider = CommandCredentialProvider()
        assert provider.get_credentials("dev2")["ip"] == "10.0.0.9"
        with pytest.raises(CredentialError, match="SLC_KNOWN_DEVICE_IDS"):
            provider.get_credentials("dev3")


def test_missing_fields_reported_without_values():
    cmd = _py("import json; print(json.dumps({'ip': '1.2.3.4', 'password': 'leaked-secret'}))")
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": cmd}, clear=True):
        with pytest.raises(CredentialError) as exc:
            CommandCredentialProvider().get_credentials("dev1")
    assert "username" in str(exc.value)
    assert "leaked-secret" not in str(exc.value)


def test_non_json_output_hidden():
    cmd = _py("print('leaked-secret')")
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": cmd}, clear=True):
        with pytest.raises(CredentialError) as exc:
            CommandCredentialProvider().get_credentials("dev1")
    assert "JSON object" in str(exc.value)
    assert "leaked-secret" not in str(exc.value)


def test_failure_keeps_output_out_of_error(caplog):
    import logging
    cmd = _py("import sys; print('leaked-stdout'); sys.stderr.write('leaked-stderr'); sys.exit(2)")
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": cmd}, clear=True):
        with caplog.at_level(logging.WARNING, logger="slc_mcp.providers.command"):
            with pytest.raises(CredentialError) as exc:
                CommandCredentialProvider().get_credentials("dev1")
    msg = str(exc.value)
    assert "status 2" in msg
    assert "leaked-stdout" not in msg and "leaked-stderr" not in msg
    # stderr reaches the server log only, never the tool result
    assert "leaked-stderr" in caplog.text
    assert "leaked-stdout" not in caplog.text


def test_command_not_found():
    with patch.dict(os.environ, {"SLC_CREDENTIAL_COMMAND": "/nonexistent/secrets-cli {device_id}"}, clear=True):
        with pytest.raises(CredentialError, match="not found"):
            CommandCredentialProvider().get_credentials("dev1")


def test_timeout():
    with patch.dict(os.environ, {
        "SLC_CREDENTIAL_COMMAND": _py("import time; time.sleep(5)"),
        "SLC_CREDENTIAL_COMMAND_TIMEOUT": "0.5",
    }, clear=True):
        with pytest.raises(CredentialError, match="timed out"):
            CommandCredentialProvider().get_credentials("dev1")
