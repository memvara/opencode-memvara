#!/usr/bin/env node
/**
 * Merge hosted Memvara MCP into an OpenCode config file.
 * Does not register a JavaScript plugin and does not capture sessions.
 *
 *   node bin/install.mjs --config /tmp/opencode.json
 *   node bin/install.mjs            # ~/.config/opencode/opencode.json
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HOSTED = "https://app.memvara.dev/mcp";
const ENTRY = {
  type: "remote",
  url: HOSTED,
  enabled: true,
};

function parseArgs(argv) {
  let config;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--config") {
      config = argv[i + 1];
      i++;
    }
  }
  return {
    config:
      config ||
      path.join(os.homedir(), ".config", "opencode", "opencode.json"),
  };
}

function main() {
  const { config } = parseArgs(process.argv.slice(2));
  let body = {};
  if (fs.existsSync(config)) {
    const raw = fs.readFileSync(config, "utf8");
    body = JSON.parse(raw);
  }
  if (Array.isArray(body.plugin) && body.plugin.includes("opencode-memvara")) {
    throw new Error(
      "refusing to write: this file lists opencode-memvara as a JS plugin. Memvara is remote MCP, not a session hook.",
    );
  }
  body.mcp = body.mcp || {};
  body.mcp.memvara = { ...ENTRY };
  fs.mkdirSync(path.dirname(config), { recursive: true });
  fs.writeFileSync(config, JSON.stringify(body, null, 2) + "\n");
  process.stdout.write(`wrote mcp.memvara -> ${config}\n`);
}

main();
