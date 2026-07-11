from unittest.mock import patch

import pytest

from slc_mcp import cli_policy
from slc_mcp.cli_policy import CLIPolicyViolation, check_command


def test_empty_command_rejected():
    with pytest.raises(CLIPolicyViolation, match="Empty command"):
        check_command("")


def test_whitespace_only_command_rejected():
    with pytest.raises(CLIPolicyViolation, match="Empty command"):
        check_command("   ")


def test_embedded_newline_rejected():
    with pytest.raises(CLIPolicyViolation, match="embedded newlines"):
        check_command("show version\nreload\nwrite erase")


def test_embedded_carriage_return_rejected():
    with pytest.raises(CLIPolicyViolation, match="embedded newlines"):
        check_command("show version\rreload")


def test_embedded_newline_rejected_even_with_write_and_yolo_flags_absent():
    # Confirms the newline check runs before deny-list / read-prefix checks,
    # so it can't be routed around by a command that would otherwise be blocked anyway.
    with pytest.raises(CLIPolicyViolation, match="embedded newlines"):
        check_command("show version\nreload")


def test_plain_read_command_allowed():
    check_command("show version")


def test_plain_write_command_blocked_without_write_enabled():
    with pytest.raises(CLIPolicyViolation, match="write access is disabled"):
        check_command("set hostname foo", write_enabled=False)


def test_plain_write_command_allowed_with_write_enabled():
    check_command("set hostname foo", write_enabled=True)


def test_deny_list_command_blocked_even_with_write_enabled():
    with pytest.raises(CLIPolicyViolation, match="blocked by the built-in deny list"):
        check_command("reload", write_enabled=True)


def test_deny_list_matches_with_arguments():
    with pytest.raises(CLIPolicyViolation, match="blocked by the built-in deny list"):
        check_command("write erase startup-config", write_enabled=True)


def test_command_exceeding_max_length_rejected():
    with pytest.raises(CLIPolicyViolation, match="exceeds maximum length"):
        check_command("show " + "a" * 600, max_length=512)


def test_yolo_bypasses_all_checks_except_empty_and_length():
    # Even under yolo mode, a deny-listed command with an embedded newline
    # should still be rejected by the newline check, since it runs before the yolo return.
    with pytest.raises(CLIPolicyViolation, match="embedded newlines"):
        check_command("show version\nreload", yolo=True)


def test_yolo_allows_plain_deny_listed_command():
    check_command("reload", yolo=True)


def test_permit_list_restricts_to_allowlisted_commands():
    with pytest.raises(CLIPolicyViolation, match="not in the permitted command list"):
        check_command("show version", write_enabled=True, permit=frozenset({"show hostname"}))


def test_permit_list_allows_matching_command():
    check_command("show hostname", write_enabled=True, permit=frozenset({"show hostname"}))


def test_cli_write_enabled_env_var(monkeypatch):
    monkeypatch.delenv("SLC_CLI_WRITE_ENABLED", raising=False)
    assert cli_policy.cli_write_enabled() is False
    monkeypatch.setenv("SLC_CLI_WRITE_ENABLED", "true")
    assert cli_policy.cli_write_enabled() is True
