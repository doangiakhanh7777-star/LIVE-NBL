#!/usr/bin/env python3
"""Tiny stdio MCP wrapper for the NBL LIVE Local API.

Designed for OpenClaw running inside WSL. No third-party Python packages.
Never writes logs to stdout; stdout is reserved for MCP JSON-RPC.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SERVER_NAME = "nbl-live"
SERVER_VERSION = "1.0.2"
DEFAULT_TOKEN_FILE = "/mnt/c/Users/ADMIN/AppData/Local/NBL_LIVE_2/local_api_token.txt"


def windows_host():
    override = os.environ.get("NBL_API_HOST", "").strip()
    if override:
        return override
    try:
        text = subprocess.check_output(
            ["ip", "route", "show", "default"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        parts = text.split()
        if "via" in parts:
            return parts[parts.index("via") + 1]
    except Exception:
        pass
    return "127.0.0.1"


def api_base():
    value = os.environ.get("NBL_API_URL", "").strip().rstrip("/")
    if value:
        return value
    return "http://%s:%s" % (windows_host(), os.environ.get("NBL_API_PORT", "8766"))


def token():
    direct = os.environ.get("NBL_API_TOKEN", "").strip()
    if direct:
        return direct
    path = Path(os.environ.get("NBL_API_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    return path.read_text(encoding="ascii").strip()


def http(method, path, body=None):
    data = None
    headers = {
        "Authorization": "Bearer " + token(),
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(api_base() + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except Exception:
            payload = {"ok": False, "error": str(error)}
        return error.code, payload


def tool_defs():
    read_only = {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    write_safe = {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
    destructive = {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    return [
        {
            "name": "nbl_accounts",
            "description": "List NBL accounts and Studio connection state.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": read_only,
        },
        {
            "name": "nbl_schedules",
            "description": "List NBL LIVE schedules and states.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": read_only,
        },
        {
            "name": "nbl_live_status",
            "description": "Return currently active NBL LIVE schedules.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": read_only,
        },
        {
            "name": "nbl_create_schedule",
            "description": "Create one future LIVE schedule. Prefer account_number. Times: Unix or ISO-8601.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "account_number": {"type": "integer", "minimum": 1},
                    "session_id": {"type": "string"},
                    "account": {"type": "string"},
                    "profile_id": {"type": "string"},
                    "start": {"oneOf": [{"type": "number"}, {"type": "string"}]},
                    "end": {"oneOf": [{"type": "number"}, {"type": "string"}]},
                    "bundle_index": {"type": "integer", "minimum": 0, "maximum": 200, "default": 1},
                    "no_sales": {"type": "boolean", "default": False},
                    "allow_overlap": {"type": "boolean", "default": False},
                },
                "required": ["start", "end"],
                "additionalProperties": False,
            },
            "annotations": write_safe,
        },
        {
            "name": "nbl_cancel_schedule",
            "description": "Cancel a schedule that has not started.",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            "annotations": destructive,
        },
        {
            "name": "nbl_stop_schedule",
            "description": "Safely stop an active schedule or cancel it before start.",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
            "annotations": destructive,
        },
    ]


def call_tool(name, args):
    args = args if isinstance(args, dict) else {}
    if name == "nbl_accounts":
        status, value = http("GET", "/api/accounts")
    elif name == "nbl_schedules":
        status, value = http("GET", "/api/schedules")
    elif name == "nbl_live_status":
        status, value = http("GET", "/api/live/status")
    elif name == "nbl_create_schedule":
        status, value = http("POST", "/api/schedules", args)
    elif name == "nbl_cancel_schedule":
        status, value = http("POST", "/api/schedules/%s/cancel" % args.get("id", ""), {})
    elif name == "nbl_stop_schedule":
        status, value = http("POST", "/api/schedules/%s/stop" % args.get("id", ""), {})
    else:
        raise ValueError("Unknown tool: " + str(name))
    is_error = status >= 400 or not bool(value.get("ok", False))
    # Keep one compact representation only. Returning both text and
    # structuredContent duplicated every API response in the agent context.
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


def send(message):
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def response(request_id, result=None, error=None):
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result if result is not None else {}
    send(message)


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except Exception:
            continue
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}
        if request_id is None:
            continue
        try:
            if method == "initialize":
                requested = str(params.get("protocolVersion") or "2025-06-18")
                response(request_id, {
                    "protocolVersion": requested,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                    "instructions": "Manage configured NBL LIVE accounts. Read state before schedule changes. Prefer account_number.",
                })
            elif method == "ping":
                response(request_id, {})
            elif method == "tools/list":
                response(request_id, {"tools": tool_defs()})
            elif method == "tools/call":
                response(request_id, call_tool(params.get("name"), params.get("arguments") or {}))
            else:
                response(request_id, error={"code": -32601, "message": "Method not found"})
        except Exception as exc:
            response(request_id, error={"code": -32000, "message": str(exc)[:1000]})


if __name__ == "__main__":
    main()
