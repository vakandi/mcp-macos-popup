#!/usr/bin/env python3
"""
macos-popup MCP Server
Affiche des popups Electron élégants sur l'écran du Mac pour notifier
Wael d'informations (notifications rapides ou docs popups avec markdown).

Architecture:
  - Ce serveur MCP (stdio) reçoit les appels d'outils.
  - Il POST le payload vers un daemon Electron local (127.0.0.1:5789).
  - Le daemon est spawné automatiquement s'il n'est pas déjà lancé.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
ELECTRON_BIN = PROJECT_DIR / "node_modules" / ".bin" / "electron"
PORT = int(os.environ.get("POPUP_PORT", "5789"))
BASE = f"http://127.0.0.1:{PORT}"

LEVELS = ("info", "success", "warning", "error")

# ─── MCP Protocol Helpers ───────────────────────────────────────────────────


def mcp_send(data: dict) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def mcp_log(msg: str) -> None:
    print(f"[macos-popup] {msg}", file=sys.stderr, flush=True)


# ─── Daemon management ──────────────────────────────────────────────────────


def _http(method: str, path: str, payload: dict | None = None, timeout: float = 3.0) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _daemon_running() -> bool:
    try:
        return bool(_http("GET", "/health", timeout=1.0).get("ok"))
    except Exception:
        return False


def _spawn_daemon() -> None:
    if not ELECTRON_BIN.exists():
        raise RuntimeError(
            f"Electron binary not found at {ELECTRON_BIN}. "
            f"Run: cd {PROJECT_DIR} && npm install"
        )
    subprocess.Popen(
        [str(ELECTRON_BIN), str(PROJECT_DIR / "main.js")],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _ensure_daemon() -> None:
    if _daemon_running():
        return
    _spawn_daemon()
    # Electron cold start can take a few seconds.
    deadline = time.time() + 20
    while time.time() < deadline:
        if _daemon_running():
            return
        time.sleep(0.4)
    raise RuntimeError("Electron popup daemon did not come up within 20s")


def _deliver(path: str, payload: dict) -> dict:
    try:
        _ensure_daemon()
        return _http("POST", path, payload)
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── Tool handlers ──────────────────────────────────────────────────────────


def handle_show_popup(args: dict[str, Any]) -> dict:
    title = str(args.get("title", "")).strip()
    message = str(args.get("message", ""))
    level = args.get("level", "info")
    duration = args.get("duration", 8)
    source = str(args.get("source", "Elia"))
    screen = args.get("screen")

    if not title and not message:
        return {"content": [{"type": "text", "text": "Error: title or message required"}], "isError": True}
    if level not in LEVELS:
        level = "info"

    result = _deliver("/popup", {
        "mode": "notify",
        "title": title or "Notification",
        "message": message,
        "level": level,
        "duration": duration,
        "source": source,
        "screen": screen,
    })
    text = "Popup displayed on screen." if result.get("ok") else f"Failed: {result.get('error')}"
    return {"content": [{"type": "text", "text": text}], "isError": not result.get("ok", False)}


def handle_show_docs(args: dict[str, Any]) -> dict:
    title = str(args.get("title", "")).strip()
    markdown = str(args.get("markdown", ""))
    level = args.get("level", "info")
    duration = args.get("duration", 30)
    source = str(args.get("source", "Elia"))
    screen = args.get("screen")

    if not title and not markdown:
        return {"content": [{"type": "text", "text": "Error: title or markdown required"}], "isError": True}
    if level not in LEVELS:
        level = "info"

    result = _deliver("/popup", {
        "mode": "docs",
        "title": title or "Documentation",
        "markdown": markdown,
        "level": level,
        "duration": duration,
        "source": source,
        "screen": screen,
    })
    text = "Docs popup displayed on screen." if result.get("ok") else f"Failed: {result.get('error')}"
    return {"content": [{"type": "text", "text": text}], "isError": not result.get("ok", False)}


def handle_dismiss_all(args: dict[str, Any]) -> dict:
    result = _deliver("/dismiss_all", {})
    text = "All popups dismissed." if result.get("ok") else f"Failed: {result.get('error')}"
    return {"content": [{"type": "text", "text": text}], "isError": not result.get("ok", False)}


def handle_list_screens(args: dict[str, Any]) -> dict:
    try:
        _ensure_daemon()
        result = _http("GET", "/screens", timeout=3.0)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed: {e}"}], "isError": True}
    displays = result.get("displays", [])
    focused = result.get("focused")
    lines = []
    for d in displays:
        marks = []
        if d.get("primary"):
            marks.append("primary")
        if d.get("focused"):
            marks.append("focused")
        suffix = f" ({', '.join(marks)})" if marks else ""
        lines.append(f"- {d.get('id')}: {d.get('label')}{suffix} — {d.get('workArea', {}).get('width')}x{d.get('workArea', {}).get('height')}")
    text = "Screens:\n" + "\n".join(lines) + f"\nFocused screen id: {focused}"
    return {"content": [{"type": "text", "text": text}]}


def handle_get_focused_screen(args: dict[str, Any]) -> dict:
    try:
        _ensure_daemon()
        result = _http("GET", "/focused_screen", timeout=3.0)
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Failed: {e}"}], "isError": True}
    display = result.get("display") or {}
    text = (
        f"Focused screen: {display.get('id')} — {display.get('label')}\n"
        f"Work area: {display.get('workArea', {}).get('width')}x{display.get('workArea', {}).get('height')}\n"
        f"Primary: {display.get('primary')}"
    )
    return {"content": [{"type": "text", "text": text}]}


# ─── Tool definitions ───────────────────────────────────────────────────────

TOOLS: dict[str, dict] = {
    "show_popup": {
        "name": "show_popup",
        "description": (
            "Show a quick notification popup on Wael's macOS screen via a native "
            "Electron window (dark glassy card, top-right, auto-dismiss). Use it to "
            "alert Wael of important information: task done, deploy finished, error "
            "found, etc."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short bold title of the popup"},
                "message": {"type": "string", "description": "Notification body text (plain text)"},
                "level": {
                    "type": "string",
                    "enum": list(LEVELS),
                    "description": "Visual severity: info (blue), success (green), warning (orange), error (red)",
                },
                "duration": {"type": "number", "description": "Seconds before auto-dismiss (default 8, max 300)"},
                "source": {"type": "string", "description": "Origin chip label, e.g. 'Gilfoyle', 'Deploy'"},
                "screen": {"type": ["string", "number", "null"], "description": "Display id, index, label, 'primary', or 'focused'. Omit for primary."},
            },
            "required": ["title"],
        },
        "handler": handle_show_popup,
    },
    "show_docs": {
        "name": "show_docs",
        "description": (
            "Show a larger documentation-style popup on Wael's macOS screen that renders "
            "MARKDOWN (headings, lists, code blocks, links, quotes). Use it to surface rich "
            "information: a summary report, API results, a changelog, key findings. Stays "
            "longer on screen than show_popup."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Title of the docs card"},
                "markdown": {"type": "string", "description": "Markdown content to render"},
                "level": {
                    "type": "string",
                    "enum": list(LEVELS),
                    "description": "Accent color: info/success/warning/error",
                },
                "duration": {"type": "number", "description": "Seconds before auto-dismiss (default 30, max 300)"},
                "source": {"type": "string", "description": "Origin chip label"},
                "screen": {"type": ["string", "number", "null"], "description": "Display id, index, label, 'primary', or 'focused'. Omit for primary."},
            },
            "required": ["title", "markdown"],
        },
        "handler": handle_show_docs,
    },
    "list_screens": {
        "name": "list_screens",
        "description": "List every connected macOS display, including ids, labels, sizes and which one is focused.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": handle_list_screens,
    },
    "get_focused_screen": {
        "name": "get_focused_screen",
        "description": "Return the display that currently has focus, so a popup can be shown on the right screen.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": handle_get_focused_screen,
    },
    "dismiss_all_popups": {
        "name": "dismiss_all_popups",
        "description": "Immediately close every popup currently shown on screen.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": handle_dismiss_all,
    },
}


# ─── MCP Server Loop ────────────────────────────────────────────────────────


def main() -> None:
    mcp_log("macos-popup MCP Server starting...")
    mcp_log(f"daemon endpoint: {BASE} | electron: {ELECTRON_BIN.exists()}")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "initialize":
            mcp_send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "macos-popup", "version": "1.0.0"},
                    "capabilities": {"tools": {}},
                },
            })

        elif method == "notifications/initialized":
            pass

        elif method == "tools/list":
            tools_list = [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"],
                }
                for t in TOOLS.values()
            ]
            mcp_send({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools_list}})

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            tool = TOOLS.get(tool_name)
            if tool:
                try:
                    result = tool["handler"](tool_args)
                    mcp_send({"jsonrpc": "2.0", "id": msg_id, "result": result})
                except Exception as e:
                    mcp_log(f"Error handling {tool_name}: {e}")
                    mcp_send({
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "error": {"code": -32603, "message": f"Internal error: {e}"},
                    })
            else:
                mcp_send({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
                })

        elif method in ("shutdown", "exit"):
            break

        elif method == "ping":
            mcp_send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

        else:
            mcp_send({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            })


if __name__ == "__main__":
    main()
