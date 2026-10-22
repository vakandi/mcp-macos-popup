#!/usr/bin/env node
const { spawn } = require("child_process");
const path = require("path");

const server = path.join(__dirname, "..", "server.py");
const child = spawn("python3", [server], { stdio: "inherit" });

child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
