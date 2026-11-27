# Adding New Tools

This server maps the SLC 9000 REST API v2 into MCP tools via FastMCP. A tool is a Python function decorated with `@read_tool` or `@write_tool`. Never use `@mcp.tool()` directly: the two decorators set the MCP `readOnlyHint` annotation (and `destructiveHint` on writes), keep write tools out of read-only mode (`MCP_READ_ONLY`, `MCP_WRITES_UNTIL`), and `tests/test_write_policy.py` fails on a tool without one.

The authoritative API spec is `SLC-API-v2-9_7_0_0R21-bundled.yaml`.

## Design conventions

- Tool signatures are small: `device_id: str` plus a few typed params.
- All tools return `client._ok(data)` or `client._err(message)`, never raw dicts or exceptions.
- Pick the class by effect: anything that changes the device (config, firmware, accounts, sessions, the Percepxion client) or this server's state is `@write_tool`, whatever HTTP verb it uses. If you're unsure, it's a write tool.
- Destructive tools require `confirm=True` (or a literal confirm string for irreversible ops like factory reset).
- Tool names use verb-first: `get_`, `update_`, `set_`, `check_`, `export_`, `apply_`.

## Step 1: Find the endpoint

Check the R21 YAML spec and identify:
- HTTP method and path (relative to `/api/v2`)
- Required and optional body fields
- Response schema

## Step 2: Pick the right helper

All HTTP helpers live in `server.py` as module-level functions:

```python
_call_get(device_id, path)
_call_post(device_id, path, body=None)
_call_put(device_id, path, body=None)
_call_patch(device_id, path, body=None)
_call_delete(device_id, path)
```

These handle session creation, token caching, and 401 retry automatically.

## Step 3: Add the tool

Add the function to `server.py` under the appropriate category comment block.

Read-only example:

```python
@read_tool
def get_ntp_config(device_id: str) -> dict:
    """Get NTP server configuration."""
    return _call_get(device_id, "/network/ntp")
```

Write example with confirm guard:

```python
@write_tool
def set_ntp_server(device_id: str, server: str, confirm: bool = False) -> dict:
    """Set the primary NTP server. Requires confirm=True."""
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to update NTP config."}
    return _call_put(device_id, "/network/ntp", {"server": server})
```

Irreversible operation example (string confirm):

```python
@write_tool
def wipe_logs(device_id: str, confirm: str = "") -> dict:
    """Clear all device logs. Pass confirm='WIPE LOGS' to execute."""
    if confirm != "WIPE LOGS":
        return {"ok": False, "error": "Pass confirm='WIPE LOGS' (exact string) to execute."}
    return _call_delete(device_id, "/logs")
```

## Step 4: Update docs

Add a row to the appropriate table in `docs/tools.md`, to the Tool Reference in `README.md`, and to the read and write table under Read-Only Mode in `README.md`. Add the name to `EXPECTED_READ_TOOLS` or `EXPECTED_WRITE_TOOLS` in `tests/test_write_policy.py`. If the change affects usage patterns, parameters, or safety behavior, update `skills/slc-device-ops/SKILL.md` in the same PR. `tests/test_skill_doc.py` fails when tool names in the skill drift from `server.py`, but behavior text is on you.

## Step 5: Smoke test

```bash
python -m py_compile src/slc_mcp/server.py
python -m pytest tests/ -v
```

Then call the tool against a test device.

## Notes

- The 2FA / TOTP challenge-response is handled automatically by `session.py`, new tools don't need to worry about it.
- If the API returns a non-standard error shape, `client.py`'s `_ok`/`_err` helpers normalize it.
- 401 retry is automatic via `_call_*` helpers, don't add retry logic in individual tools.
