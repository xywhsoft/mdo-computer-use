"""Exercise the actual application APIs without a proxy or alternate MCP client."""
from __future__ import annotations

import time

from .driver import extension_package


def wait_operation(app, operation: dict, timeout: float = 35) -> dict:
    deadline = time.monotonic() + timeout
    current = operation
    while not current.get("terminal"):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Operation {operation['kind']} exceeded its validation deadline")
        time.sleep(.1)
        current = app.request("/api/v1/operations/" + current["id"])["data"]
    if current.get("state") != "succeeded":
        raise RuntimeError(f"Operation failed: {current.get('error_code')} {current.get('message')}")
    return current


def probe(app) -> dict:
    try:
        operation = app.request("/api/v1/mcp/cua-driver/refresh", "POST")["data"]
        finished = wait_operation(app, operation)
        catalog = app.request("/api/v1/mcp")["data"]
        server = next(item for item in catalog["items"] if item["id"] == "cua-driver")
        if not server["connected"] or not server["tools_discovered"] or not server["discovered_tool_count"]:
            raise RuntimeError("Cua tools were not published by the actual mdo runtime")
        return {"protocol_version": server["protocol_version"],
                "tools": server["discovered_tool_count"],
                "requests_completed": server["requests_completed"],
                "refresh_state": finished["state"], "connected": server["connected"]}
    finally:
        disconnected = app.request("/api/v1/mcp/cua-driver/disconnect", "POST")["data"]
        if disconnected["connected"]:
            raise RuntimeError("mdo did not disconnect its Cua transport")


def install_template(app) -> dict:
    package = extension_package()
    request = {"action": "plan_import", "single_kind": "mcp", "package": package}
    plan = app.request("/api/v1/ecosystem", "POST", request)["data"]
    app.request("/api/v1/ecosystem", "POST",
                dict(request, action="import", expected_plan=plan["sha256"]))
    catalog = app.request("/api/v1/mcp/templates")["data"]
    items = [item for item in catalog["items"] if item.get("template", {}).get("id") == "cua-driver"]
    if len(items) != 1:
        raise RuntimeError("Expected one installed Cua service template")
    # Return only public metadata, never the private device binding or credentials.
    return {"installed": True, "template_id": "cua-driver", "item": items[0]}


def verify_template(app) -> dict:
    from .__main__ import STATE
    from .driver import LOCK, verify
    installed = install_template(app)
    binary = verify(STATE / "cua" / LOCK["version"])
    body = {"id": "computer-use-template-check", "action": "preview",
            "receipt_key": installed["item"]["receipt"]["key"], "variant": "windows",
            "values": {"driver-path": str(binary)}, "confirm_launch": True}
    headers = {"If-Match": '"new"'}
    preview = app.request("/api/v1/mcp/connections", "POST", body, headers)["data"]
    if preview["config"]["enabled"] or preview["config"]["transport"]["program"] != str(binary):
        raise RuntimeError("Template did not produce the expected disabled local connection")
    saved = app.request("/api/v1/mcp/connections", "POST", dict(body, action="save"), headers)["data"]
    try:
        if saved["enabled"] or not saved["template_connection"]:
            raise RuntimeError("Native template binding was not preserved")
        return {"preview": True, "saved_disabled": True, "template_connection": True,
                "program_binding": True, "removed_after_check": True}
    finally:
        app.request("/api/v1/mcp/connections", "POST", {"id": body["id"], "action": "delete"},
                    {"If-Match": '"' + saved["revision"] + '"'})
