# mcp-macos-popup

MCP server for native macOS popup notifications, with multi-screen support.

It shows dark glassy popup cards on macOS and lets an AI agent target a specific display. On multi-monitor setups, it can list every screen and return the screen that currently has focus.

## Tools

- `show_popup` — quick notification popup
- `show_docs` — larger Markdown popup
- `dismiss_all_popups` — close all popups
- `list_screens` — list connected displays
- `get_focused_screen` — return the focused display

`show_popup` and `show_docs` accept an optional `screen` argument: display id, index, label, `primary`, or `focused`.

## Install

```bash
npm install -g mcp-macos-popup
```

Or run directly:

```bash
npx mcp-macos-popup
```

Electron is installed automatically as a dependency.

## MCP configuration

```json
{
  "mcpServers": {
    "macos-popup": {
      "command": "mcp-macos-popup"
    }
  }
}
```

## Usage

```bash
mcp-cli call macos-popup show_popup '{"title":"Elia","message":"the answer","level":"info","duration":10}'
mcp-cli call macos-popup list_screens '{}'
mcp-cli call macos-popup get_focused_screen '{}'
```

## Multi-screen

If four displays are connected, call `list_screens` or `get_focused_screen` first, then pass the chosen display id as `screen`:

```bash
mcp-cli call macos-popup show_popup '{"title":"Elia","message":"hello","screen":"focused"}'
```

## Development

```bash
npm install
npm run daemon
```
