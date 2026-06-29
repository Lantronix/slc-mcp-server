# Adding New Tools

This server maps the SLC 9000 REST API v2 into MCP tools via FastMCP. A tool is a Python function decorated with `@mcp.tool()`.

The authoritative API spec is `SLC-API-v2-9_7_0_0R21-bundled.yaml`.

## Design conventions

- Tool signatures are small: `device_id: str` plus a few typed params.
- All tools return `client._ok(data)` or `client._err(message)`, never raw dicts or exceptions.
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
@mcp.tool()
def get_ntp_config(device_id: str) -> dict:
    """Get NTP server configuration."""
    return _call_get(device_id, "/network/ntp")
```

Write example with confirm guard:

```python
@mcp.tool()
def set_ntp_server(device_id: str, server: str, confirm: bool = False) -> dict:
    """Set the primary NTP server. Requires confirm=True."""
    if not confirm:
        return {"ok": False, "error": "Set confirm=True to update NTP config."}
    return _call_put(device_id, "/network/ntp", {"server": server})
```

Irreversible operation example (string confirm):

```python
@mcp.tool()
def wipe_logs(device_id: str, confirm: str = "") -> dict:
    """Clear all device logs. Pass confirm='WIPE LOGS' to execute."""
    if confirm != "WIPE LOGS":
        return {"ok": False, "error": "Pass confirm='WIPE LOGS' (exact string) to execute."}
    return _call_delete(device_id, "/logs")
```

## Step 4: Update docs

Add a row to the appropriate table in `docs/tools.md`.

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
