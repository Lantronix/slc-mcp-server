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

class FakeTime:
    """Wall and monotonic clocks the test moves by hand. Start-up is wall 1000, monotonic 0."""

    def __init__(self):
        self.wall = 1000.0
        self.mono = 0.0

    def advance(self, seconds):
        self.wall += seconds
        self.mono += seconds


@pytest.fixture()
def fake_time(monkeypatch):
    t = FakeTime()
    monkeypatch.setattr(write_policy, "clock", lambda: t.wall)
    monkeypatch.setattr(write_policy, "monotonic", lambda: t.mono)
    monkeypatch.setattr(write_policy, "_start_wall", write_policy._start_wall)
    monkeypatch.setattr(write_policy, "_start_mono", write_policy._start_mono)
    write_policy.mark_start()
    return t


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
        ({"MCP_WRITES_UNTIL": " 2000 "}, True),
        ({"MCP_WRITES_UNTIL": "1000"}, False),
        ({"MCP_WRITES_UNTIL": "500"}, False),
        ({"MCP_WRITES_UNTIL": "-5"}, False),
        ({"MCP_WRITES_UNTIL": "soon"}, False),
        ({"MCP_WRITES_UNTIL": "nan"}, False),
        ({"MCP_WRITES_UNTIL": "inf"}, False),
        ({"MCP_WRITES_UNTIL": "2000.5"}, False),
        ({"MCP_WRITES_UNTIL": "1e20"}, False),
        ({"MCP_WRITES_UNTIL": "9" * 400}, False),
        ({"MCP_READ_ONLY": "true", "MCP_WRITES_UNTIL": "2000"}, False),
    ],
)
def test_writes_allowed(fake_time, env, allowed):
    assert write_policy.writes_allowed(env) is allowed


def test_window_of_exactly_seven_days_is_accepted(fake_time):
    limit = 1000 + write_policy.MAX_WINDOW_SECONDS
    assert write_policy.writes_allowed({"MCP_WRITES_UNTIL": str(limit)})
    assert not write_policy.writes_allowed({"MCP_WRITES_UNTIL": str(limit + 1)})


def test_milliseconds_are_refused_and_logged(fake_time, caplog):
    env = {"MCP_WRITES_UNTIL": "1798761600000"}
    with caplog.at_level("ERROR", logger="slc_mcp.write_policy"):
        assert write_policy.writes_until(env) == 0
        assert not write_policy.writes_allowed(env)
    assert "milliseconds" in caplog.text
    assert caplog.text.count("milliseconds") == 1  # logged once, not per call


@pytest.mark.parametrize("value", ["1e20", "1798761600000", "nan", "-1", "9" * 400, "2000.5"])
def test_describe_never_raises(fake_time, value):
    line = write_policy.describe({"MCP_WRITES_UNTIL": value})
    assert line.startswith("write tools off")


def test_window_ends_on_the_wall_clock(fake_time):
    env = {"MCP_WRITES_UNTIL": "2000"}
    fake_time.wall = 1999.0
    assert write_policy.writes_allowed(env)
    fake_time.wall = 2000.0  # wall clock jumps ahead; monotonic hasn't moved
    assert not write_policy.writes_allowed(env)


def test_window_ends_on_the_monotonic_clock(fake_time):
    env = {"MCP_WRITES_UNTIL": "2000"}
    fake_time.mono = 999.0
    assert write_policy.writes_allowed(env)
    fake_time.mono = 1000.0  # wall clock set back, but 1000 s have really passed
    assert fake_time.wall == 1000.0
    assert not write_policy.writes_allowed(env)
    assert write_policy.seconds_left(env) == 0


def test_describe_names_the_state(fake_time):
    assert write_policy.describe({}) == "write tools on"
    assert "MCP_READ_ONLY" in write_policy.describe({"MCP_READ_ONLY": "true"})
    assert "write tools off" in write_policy.describe({"MCP_WRITES_UNTIL": "10"})
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


def test_write_window_closes_on_the_injected_clock(monkeypatch, fresh_visibility, fake_time):
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1500")
    real_enforce = server.enforce_write_window
    monkeypatch.setattr(server, "enforce_write_window", _idle)  # keep the automatic timer out of it

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        fake_time.advance(seconds)

    async def scenario():
        handler = _ListChanged()
        async with Client(server.mcp, message_handler=handler) as c:
            assert EXPECTED_WRITE_TOOLS <= {t.name for t in await c.list_tools()}

            # Inside the window a write tool runs (and stops at its own confirm guard).
            early = await c.call_tool("save_config", {"device_id": "d1"}, raise_on_error=False)
            assert "confirm=True" in _text(early)

            await real_enforce(sleep=fake_sleep)

            after = {t.name for t in await c.list_tools()}
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


def test_write_call_refused_after_expiry_before_tools_are_disabled(monkeypatch, fresh_visibility, fake_time):
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1500")
    monkeypatch.setattr(server, "enforce_write_window", _idle)

    async def scenario():
        async with Client(server.mcp) as c:
            await c.list_tools()
            fake_time.advance(500)
            late = await c.call_tool(
                "reboot_device", {"device_id": "d1", "confirm": True}, raise_on_error=False
            )
            assert late.is_error
            assert "read-only" in _text(late)

    with patch.object(server, "_call_post") as post:
        _run(scenario())
    post.assert_not_called()


def test_list_tools_closes_an_expired_window_without_the_timer(monkeypatch, fresh_visibility, fake_time):
    # The timer is asleep (host suspended); the next tools/list must not show write tools.
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1500")
    monkeypatch.setattr(server, "enforce_write_window", _idle)

    async def scenario():
        handler = _ListChanged()
        async with Client(server.mcp, message_handler=handler) as c:
            assert EXPECTED_WRITE_TOOLS <= {t.name for t in await c.list_tools()}
            fake_time.mono += 600  # suspend: monotonic moves, wall clock is stale
            assert {t.name for t in await c.list_tools()} == EXPECTED_READ_TOOLS
            await asyncio.wait_for(handler.event.wait(), timeout=5)

    _run(scenario())
    assert server._write_window_closed is True


def test_restart_px_client_rechecks_before_enabling(monkeypatch, fake_time):
    monkeypatch.setenv("MCP_WRITES_UNTIL", "1060")
    monkeypatch.setenv("SLC_CLI_WRITE_ENABLED", "true")
    sent: list[str] = []

    def fake_sleep(seconds):
        fake_time.advance(seconds)

    # The client reports stopped after 70 s, 10 s after the window closed.
    status = iter(["running"] * 13 + ["not running"])

    def post(device_id, path, body=None):
        sent.append(body["commands"])
        if body["commands"] == "show px status":
            return {"ok": True, "data": {"message": [f"Status of Client: {next(status)}"]}}
        return {"ok": True, "data": {}}

    with patch.object(server, "_call_post", side_effect=post), patch.object(server.time, "sleep", side_effect=fake_sleep):
        result = server.restart_px_client("d1", confirm=True, timeout_seconds=120)

    assert result["ok"] is False
    assert "read-only" in result["error"]
    assert "stopped but not started again" in result["error"]
    assert sent[0] == "set px client disable"
    assert "set px client enable" not in sent


def test_restart_px_client_enables_inside_the_window(monkeypatch, fake_time):
    monkeypatch.setenv("SLC_CLI_WRITE_ENABLED", "true")
    sent: list[str] = []

    def post(device_id, path, body=None):
        sent.append(body["commands"])
        if body["commands"] == "show px status":
            return {"ok": True, "data": {"message": ["Status of Client: not running"]}}
        return {"ok": True, "data": {}}

    with patch.object(server, "_call_post", side_effect=post), patch.object(server.time, "sleep"):
        result = server.restart_px_client("d1", confirm=True)
    assert result["ok"] is True
    assert sent == ["set px client disable", "show px status", "set px client enable"]


def test_timer_closes_the_write_window_in_real_time(monkeypatch, fresh_visibility):
    monkeypatch.setenv("MCP_WRITES_UNTIL", str(int(time.time()) + 2))

    async def scenario():
        handler = _ListChanged()
        async with Client(server.mcp, message_handler=handler) as c:
            assert EXPECTED_WRITE_TOOLS <= {t.name for t in await c.list_tools()}
            await asyncio.wait_for(handler.event.wait(), timeout=10)
            assert {t.name for t in await c.list_tools()} == EXPECTED_READ_TOOLS

    _run(scenario())


def test_server_needs_no_custom_lifespan():
    # Applications that mount mcp.http_app() without its lifespan must not hit a
    # missing-lifespan error because of the write window.
    from fastmcp.server.server import default_lifespan

    assert server.mcp._lifespan is default_lifespan


def test_no_window_means_no_timer(monkeypatch, fresh_visibility):
    async def never(_seconds):
        raise AssertionError("should not sleep without MCP_WRITES_UNTIL")

    _run(server.enforce_write_window(sleep=never))
    assert server._write_window_closed is False
