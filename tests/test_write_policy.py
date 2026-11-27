"""Read and write tools, read-only mode (MCP_READ_ONLY) and the write window (MCP_WRITES_UNTIL).

Read-only mode is decided when the server module is imported, so the tests that
need a server started read-only run it in a fresh interpreter (tools/list and a
refused write call only). Everything else
runs in-process against the module-level server with the in-memory MCP client.
No device is contacted.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.messages import MessageHandler

import slc_mcp.server as server
from slc_mcp import cli_policy, write_policy
from slc_mcp.cli_policy import CLIPolicyViolation

EXPECTED_WRITE_TOOLS = {
    "configure_provider",
    "logout_device",
    "terminate_session",
    "update_system_identity",
    "reboot_device",
    "set_firmware_bootbank",
    "firmware_update",
    "save_config",
    "apply_config_commands",
    "restore_config_baseline",
    "factory_reset",
    "update_sysadmin_user",
    "start_px_client",
    "stop_px_client",
    "restart_px_client",
}

EXPECTED_READ_TOOLS = {
    "get_sessions",
    "get_session",
    "get_system_status",
    "get_system_version",
    "get_system_identity",
    "get_ztp_status",
    "get_network_interfaces",
    "get_slc_ports",
    "get_slc_port",
    "get_connections",
    "get_managed_devices",
    "get_managed_device",
    "get_cellular_status",
    "get_firmware_version",
    "get_firmware_update_status",
    "check_firmware_updates",
    "get_firmware_bootbank",
    "get_firmware_log",
    "export_config_commands",
    "export_config_for_edit",
    "get_sysadmin_user",
    "get_px_status",
}

POLICY_ENV = ("MCP_READ_ONLY", "MCP_WRITES_UNTIL", "SLC_CLI_WRITE_ENABLED", "SLC_CLI_YOLO")


@pytest.fixture(autouse=True)
def _clean_policy_env(monkeypatch):
    for name in POLICY_ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def fresh_visibility(monkeypatch):
    """Let a test close the write window without leaving write tools disabled for later tests."""
    monkeypatch.setattr(server.mcp, "_transforms", list(server.mcp._transforms))
    monkeypatch.setattr(server, "_write_window_closed", False)


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=30))


def _text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


def unannotated(tools) -> list[str]:
    """Names of tools without an explicit readOnlyHint, or a write tool not marked destructive."""
    bad = []
    for t in tools:
        hints = t.annotations
        if hints is None or not isinstance(hints.readOnlyHint, bool):
            bad.append(t.name)
        elif hints.readOnlyHint is False and hints.destructiveHint is not True:
            bad.append(t.name)
    return bad


# ---------------------------------------------------------------------------
# Every tool declares read or write
# ---------------------------------------------------------------------------

def test_every_registered_tool_has_an_explicit_read_only_hint():
    tools = _run(server.mcp.list_tools())
    assert unannotated(tools) == [], (
        "Declare every tool with @read_tool or @write_tool in server.py, "
        "not with mcp.tool directly."
    )


def test_annotation_check_catches_a_plain_tool():
    scratch = FastMCP("scratch")

    @scratch.tool()
    def get_something(device_id: str) -> dict:
        return {}

    assert unannotated(_run(scratch.list_tools())) == ["get_something"]


def test_server_source_has_no_plain_tool_decorator():
    source = Path(server.__file__).read_text()
    assert "@mcp.tool" not in source


def test_hints_match_the_classification():
    tools = {t.name: t.annotations for t in _run(server.mcp.list_tools())}
    for name in EXPECTED_READ_TOOLS:
        assert tools[name].readOnlyHint is True, name
    for name in EXPECTED_WRITE_TOOLS:
        assert tools[name].readOnlyHint is False, name
        assert tools[name].destructiveHint is True, name


def test_classification_is_complete():
    assert server.WRITE_TOOLS == EXPECTED_WRITE_TOOLS
    assert server.READ_TOOLS == EXPECTED_READ_TOOLS
    assert not server.READ_TOOLS & server.WRITE_TOOLS


def test_default_tool_list_is_unchanged():
    names = [t.name for t in _run(server.mcp.list_tools())]
    assert len(names) == 37
    assert set(names) == EXPECTED_READ_TOOLS | EXPECTED_WRITE_TOOLS


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "env, allowed",
    [
        ({}, True),
        ({"MCP_READ_ONLY": "false"}, True),
        ({"MCP_READ_ONLY": "0"}, True),
        ({"MCP_READ_ONLY": "true"}, False),
        ({"MCP_READ_ONLY": "1"}, False),
        ({"MCP_READ_ONLY": "YES"}, False),
        ({"MCP_READ_ONLY": "sometimes"}, False),
        ({"MCP_WRITES_UNTIL": "2000"}, True),
        ({"MCP_WRITES_UNTIL": "1000"}, False),
        ({"MCP_WRITES_UNTIL": "500"}, False),
        ({"MCP_WRITES_UNTIL": "soon"}, False),
        ({"MCP_WRITES_UNTIL": "nan"}, False),
        ({"MCP_READ_ONLY": "true", "MCP_WRITES_UNTIL": "2000"}, False),
    ],
)
def test_writes_allowed(env, allowed):
    assert write_policy.writes_allowed(env, now=1000.0) is allowed


def test_writes_allowed_reads_the_injected_clock(monkeypatch):
    monkeypatch.setattr(write_policy, "clock", lambda: 1999.0)
    assert write_policy.writes_allowed({"MCP_WRITES_UNTIL": "2000"})
    monkeypatch.setattr(write_policy, "clock", lambda: 2000.0)
    assert not write_policy.writes_allowed({"MCP_WRITES_UNTIL": "2000"})


def test_describe_names_the_state(monkeypatch):
    monkeypatch.setattr(write_policy, "clock", lambda: 1000.0)
    assert write_policy.describe({}) == "write tools on"
    assert "MCP_READ_ONLY" in write_policy.describe({"MCP_READ_ONLY": "true"})
    assert "has passed" in write_policy.describe({"MCP_WRITES_UNTIL": "10"})
    assert "on until" in write_policy.describe({"MCP_WRITES_UNTIL": "2000"})


# ---------------------------------------------------------------------------
# CLI write flag
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("policy", [{"MCP_READ_ONLY": "true"}, {"MCP_WRITES_UNTIL": "1"}])
def test_cli_write_flag_forced_off(monkeypatch, policy):
    monkeypatch.setenv("SLC_CLI_WRITE_ENABLED", "true")
    monkeypatch.setenv("SLC_CLI_YOLO", "true")
    for name, value in policy.items():
        monkeypatch.setenv(name, value)
    assert cli_policy.cli_write_enabled() is False
    assert cli_policy.cli_yolo_enabled() is False
    with pytest.raises(CLIPolicyViolation, match="write access is disabled"):
        cli_policy.check_command("set hostname lab")
    cli_policy.check_command("show px status")


def test_cli_write_flag_unchanged_by_default(monkeypatch):
    monkeypatch.setenv("SLC_CLI_WRITE_ENABLED", "true")
    assert cli_policy.cli_write_enabled() is True
    cli_policy.check_command("set hostname lab")


# ---------------------------------------------------------------------------
# Read-only at start-up (fresh interpreter)
# ---------------------------------------------------------------------------

_PROBE = textwrap.dedent(
    """
    import asyncio, json
    from fastmcp import Client
    import slc_mcp.server as server
    from slc_mcp import cli_policy

    async def main():
        async with Client(server.mcp) as c:
            tools = await c.list_tools()
            refused = await c.call_tool(
                "factory_reset",
                {"device_id": "d1", "confirm": "FACTORY RESET"},
                raise_on_error=False,
            )
        print(json.dumps({
            "tools": sorted(t.name for t in tools),
            "refused_is_error": refused.is_error,
            "refused_text": " ".join(getattr(x, "text", "") for x in refused.content),
            "cli_write_enabled": cli_policy.cli_write_enabled(),
        }))

    asyncio.run(main())
    """
)


def _probe(tmp_path, **env_overrides) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in POLICY_ENV}
    env.update(env_overrides)
    # Other tests switch the provider in os.environ; the probe never needs credentials.
    env["SLC_CREDENTIAL_PROVIDER"] = "env"
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    "policy",
    [
        {"MCP_READ_ONLY": "true"},
        {"MCP_WRITES_UNTIL": str(int(time.time()) - 60)},
    ],
    ids=["read_only", "writes_until_passed"],
)
def test_read_only_start_registers_no_write_tool_and_refuses_by_name(tmp_path, policy):
    result = _probe(tmp_path, SLC_CLI_WRITE_ENABLED="true", **policy)
    assert set(result["tools"]) == EXPECTED_READ_TOOLS
    assert result["refused_is_error"] is True
    assert "read-only" in result["refused_text"]
    assert result["cli_write_enabled"] is False


def test_default_start_in_fresh_interpreter_lists_all_37(tmp_path):
    result = _probe(tmp_path)
    assert set(result["tools"]) == EXPECTED_READ_TOOLS | EXPECTED_WRITE_TOOLS


def test_write_function_refuses_a_direct_call_when_read_only(monkeypatch):
    monkeypatch.setenv("MCP_READ_ONLY", "true")
    with patch.object(server, "_call_post") as post:
        result = server.reboot_device("device-1", confirm=True)
    assert result["ok"] is False
    assert "read-only" in result["error"]
    post.assert_not_called()


# ---------------------------------------------------------------------------
# Write window
# ---------------------------------------------------------------------------

class _ListChanged(MessageHandler):
    def __init__(self):
        super().__init__()
        self.count = 0
        self.event = asyncio.Event()

    async def on_tool_list_changed(self, message):
        self.count += 1
        self.event.set()


async def _idle():
    return None


def test_write_window_closes_on_the_injected_clock(monkeypatch, fresh_visibility):
    now = [1000.0]
    monkeypatch.setattr(write_policy, "clock", lambda: now[0])
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1500")
    real_enforce = server.enforce_write_window
    monkeypatch.setattr(server, "enforce_write_window", _idle)  # keep the lifespan's timer out of it

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    async def scenario():
        handler = _ListChanged()
        async with Client(server.mcp, message_handler=handler) as c:
            assert EXPECTED_WRITE_TOOLS <= {t.name for t in await c.list_tools()}

            # Inside the window a write tool runs (and stops at its own confirm guard).
            early = await c.call_tool("save_config", {"device_id": "d1"}, raise_on_error=False)
            assert "confirm=True" in _text(early)

            await real_enforce(sleep=fake_sleep)

            after = {t.name for t in await c.list_tools()}
            assert not after & EXPECTED_WRITE_TOOLS
            assert after == EXPECTED_READ_TOOLS
            await asyncio.wait_for(handler.event.wait(), timeout=5)
            assert handler.count == 1

            # A client that still holds the old tool list is refused by name.
            late = await c.call_tool(
                "factory_reset", {"device_id": "d1", "confirm": "FACTORY RESET"}, raise_on_error=False
            )
            assert late.is_error
            assert "read-only" in _text(late)

    with patch.object(server, "_call_post") as post:
        _run(scenario())
    post.assert_not_called()
    assert sum(sleeps) == pytest.approx(500.0)
    assert max(sleeps) <= 60.0


def test_write_call_refused_after_expiry_before_tools_are_disabled(monkeypatch, fresh_visibility):
    now = [1000.0]
    monkeypatch.setattr(write_policy, "clock", lambda: now[0])
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1500")
    monkeypatch.setattr(server, "enforce_write_window", _idle)

    async def scenario():
        async with Client(server.mcp) as c:
            await c.list_tools()
            now[0] = 1500.0
            late = await c.call_tool(
                "reboot_device", {"device_id": "d1", "confirm": True}, raise_on_error=False
            )
            assert late.is_error
            assert "read-only" in _text(late)

    with patch.object(server, "_call_post") as post:
        _run(scenario())
    post.assert_not_called()


def test_lifespan_closes_the_write_window_in_real_time(monkeypatch, fresh_visibility):
    monkeypatch.setenv("MCP_WRITES_UNTIL", str(time.time() + 0.5))

    async def scenario():
        handler = _ListChanged()
        async with Client(server.mcp, message_handler=handler) as c:
            assert EXPECTED_WRITE_TOOLS <= {t.name for t in await c.list_tools()}
            await asyncio.wait_for(handler.event.wait(), timeout=10)
            assert {t.name for t in await c.list_tools()} == EXPECTED_READ_TOOLS

    _run(scenario())


def test_no_window_means_no_timer(monkeypatch, fresh_visibility):
    async def never(_seconds):
        raise AssertionError("should not sleep without MCP_WRITES_UNTIL")

    _run(server.enforce_write_window(sleep=never))
    assert server._write_window_closed is False
