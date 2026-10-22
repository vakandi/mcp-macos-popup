// Bridge between the sandboxed renderer and the daemon main process.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("popup", {
  onData: (cb) => ipcRenderer.on("popup-data", (_e, data) => cb(data)),
  onFadeOut: (cb) => ipcRenderer.on("fade-out", () => cb()),
  sendHeight: (h) => ipcRenderer.send("content-height", Math.ceil(h)),
});
