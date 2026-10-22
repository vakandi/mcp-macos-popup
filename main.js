#!/usr/bin/env node
/**
 * mcp-macos-popup — daemon
 *
 * Persistent Electron process that listens on a local HTTP port and turns
 * JSON payloads into beautiful macOS popup notifications.
 *
 * Endpoints (127.0.0.1 only):
 *   GET  /health          -> {"ok":true}
 *   GET  /screens         -> list every display + the focused one
 *   GET  /focused_screen  -> the display that currently has focus
 *   POST /popup           -> create a popup {mode,title,message,markdown,level,duration,source,screen}
 *   POST /dismiss_all     -> close every open popup
 */

const { app, BrowserWindow, screen, nativeTheme } = require("electron");
const http = require("http");
const path = require("path");

const PORT = parseInt(process.env.POPUP_PORT || "5789", 10);
const MARGIN = 16;
const GAP = 12;
const WIDTHS = { notify: 380, docs: 480 };
const LEVELS = new Set(["info", "success", "warning", "error"]);

/** @type {Map<number, {win: BrowserWindow, height: number, id: number}[]>} */
const stacks = new Map();
let nextId = 1;

// ─── Screen helpers ─────────────────────────────────────────────────────────

function displayInfo(d, focusedId) {
  const b = d.bounds || {};
  const w = d.workArea || b;
  return {
    id: d.id,
    label: d.label || `Display ${d.id}`,
    primary: d.id === screen.getPrimaryDisplay().id,
    focused: d.id === focusedId,
    bounds: { x: b.x, y: b.y, width: b.width, height: b.height },
    workArea: { x: w.x, y: w.y, width: w.width, height: w.height },
    scaleFactor: d.scaleFactor,
    internal: !!d.internal,
  };
}

function focusedDisplay() {
  const focusedWindow = BrowserWindow.getFocusedWindow();
  if (focusedWindow && !focusedWindow.isDestroyed()) {
    return screen.getDisplayNearestPoint(focusedWindow.getBounds());
  }
  return screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
}

function allDisplays() {
  const focused = focusedDisplay();
  return screen.getAllDisplays().map((d) => displayInfo(d, focused ? focused.id : null));
}

function resolveDisplay(spec) {
  const displays = screen.getAllDisplays();
  const primary = screen.getPrimaryDisplay();
  if (spec == null || spec === "" || spec === "primary") return primary;
  if (spec === "focused" || spec === "focus") return focusedDisplay() || primary;
  const wanted = String(spec).trim().toLowerCase();
  if (wanted === "primary") return primary;
  const byId = displays.find((d) => String(d.id) === wanted);
  if (byId) return byId;
  const byLabel = displays.find((d) => (d.label || "").toLowerCase() === wanted);
  if (byLabel) return byLabel;
  const index = Number(spec);
  if (!Number.isNaN(index) && displays[index]) return displays[index];
  return primary;
}

function getStack(displayId) {
  if (!stacks.has(displayId)) stacks.set(displayId, []);
  return stacks.get(displayId);
}

function removeFromStack(item) {
  for (const stack of stacks.values()) {
    const idx = stack.findIndex((i) => i === item);
    if (idx !== -1) {
      stack.splice(idx, 1);
      repositionStack(item.displayId);
      return;
    }
  }
}

function repositionStack(displayId) {
  const stack = stacks.get(displayId);
  if (!stack) return;
  const display = screen.getAllDisplays().find((d) => d.id === displayId) || screen.getPrimaryDisplay();
  const area = display.workArea;
  let y = area.y + MARGIN;
  for (const item of stack) {
    if (!item.win.isDestroyed()) {
      const [w] = item.win.getSize();
      item.win.setPosition(area.x + area.width - w - MARGIN, y);
    }
    y += item.height + GAP;
  }
}

function closePopup(item) {
  if (item.win.isDestroyed()) return;
  item.win.webContents.send("fade-out");
  setTimeout(() => {
    if (!item.win.isDestroyed()) item.win.close();
  }, 260);
}

function createPopup(data) {
  const id = nextId++;
  const mode = data.mode === "docs" ? "docs" : "notify";
  const level = LEVELS.has(data.level) ? data.level : "info";
  const duration = Math.min(Math.max(Number(data.duration) || (mode === "docs" ? 30 : 8), 3), 300);
  const width = WIDTHS[mode];
  const display = resolveDisplay(data.screen);
  const displayId = display.id;

  const win = new BrowserWindow({
    width,
    height: 160,
    show: false,
    frame: false,
    transparent: true,
    vibrancy: "under-window",
    visualEffectState: "active",
    backgroundColor: "#00000000",
    resizable: false,
    movable: true,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    focusable: true,
    alwaysOnTop: true,
    hasShadow: true,
    roundedCorners: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.setAlwaysOnTop(true, "floating");

  const item = { win, height: 160, id, displayId };
  const stack = getStack(displayId);
  stack.push(item);

  win.on("closed", () => removeFromStack(item));

  win.webContents.on("did-finish-load", () => {
    win.webContents.send("popup-data", { id, mode, level, duration, title: data.title || "", message: data.message || "", markdown: data.markdown || "", source: data.source || "", screen: displayId });
  });

  const onHeight = (_e, h) => {
    if (win.isDestroyed()) return;
    const area = display.workArea;
    const maxH = Math.floor(area.height * 0.72);
    const height = Math.min(Math.max(Math.round(h), 90), maxH);
    item.height = height;
    win.setContentSize(width, height);
    const y = area.y + MARGIN + stack.slice(0, stack.indexOf(item)).reduce((s, i) => s + i.height + GAP, 0);
    win.setPosition(area.x + area.width - width - MARGIN, y);
    win.showInactive();
    repositionStack(displayId);
    setTimeout(() => {
      if (!win.isDestroyed()) closePopup(item);
    }, duration * 1000);
  };
  win.webContents.on("ipc-message", (e, ch, ...args) => {
    if (ch === "content-height") {
      const h = args[0];
      if (h === -1) return closePopup(item);
      onHeight(e, h);
    }
  });

  win.loadFile(path.join(__dirname, "popup.html"));
  return { id, displayId, label: display.label };
}

function dismissAll() {
  for (const stack of stacks.values()) {
    for (const item of [...stack]) closePopup(item);
  }
}

// ─── HTTP server ────────────────────────────────────────────────────────────

function readBody(req) {
  return new Promise((resolve, reject) => {
    let buf = "";
    req.on("data", (c) => {
      buf += c;
      if (buf.length > 512 * 1024) reject(new Error("payload too large"));
    });
    req.on("end", () => resolve(buf));
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const send = (code, obj) => {
    res.writeHead(code, { "Content-Type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  try {
    if (req.method === "GET" && req.url === "/health") {
      return send(200, { ok: true, popups: [...stacks.values()].reduce((n, s) => n + s.length, 0), displays: allDisplays().length });
    }
    if (req.method === "GET" && req.url === "/screens") {
      return send(200, { ok: true, displays: allDisplays(), focused: focusedDisplay() ? focusedDisplay().id : null });
    }
    if (req.method === "GET" && req.url === "/focused_screen") {
      const d = focusedDisplay();
      return send(200, { ok: true, display: d ? displayInfo(d, d.id) : null });
    }
    if (req.method === "POST" && req.url === "/popup") {
      const data = JSON.parse((await readBody(req)) || "{}");
      if (!data.title && !data.message && !data.markdown) return send(400, { ok: false, error: "empty popup" });
      return send(200, { ok: true, ...createPopup(data) });
    }
    if (req.method === "POST" && req.url === "/dismiss_all") {
      dismissAll();
      return send(200, { ok: true });
    }
    return send(404, { ok: false, error: "not found" });
  } catch (err) {
    return send(400, { ok: false, error: String(err && err.message ? err.message : err) });
  }
});

// ─── App lifecycle ──────────────────────────────────────────────────────────

app.whenReady().then(() => {
  if (process.platform === "darwin" && app.dock) app.dock.hide();
  nativeTheme.themeSource = "dark";

  server.on("error", (err) => {
    console.error("[daemon] server error:", err.message);
    app.exit(err.code === "EADDRINUSE" ? 0 : 1);
  });

  server.listen(PORT, "127.0.0.1", () => {
    console.log(`[daemon] listening on 127.0.0.1:${PORT}`);
  });
});

app.on("window-all-closed", () => {
  // Stay alive: this is a daemon, not a regular app.
});
