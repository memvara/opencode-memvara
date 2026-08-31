#!/usr/bin/env node
/**
 * Merge Memvara into an OpenCode config file: the hosted MCP entry, and the JavaScript
 * plugin that makes memory automatic.
 *
 *   node bin/install.mjs --config /tmp/opencode.json
 *   node bin/install.mjs --mcp-only      # the endpoint alone, no local process
 *   node bin/install.mjs                 # ~/.config/opencode/opencode.json
 *
 * Until 0.2.5 this file REFUSED to register a plugin -- it threw on finding one, and said
 * "Memvara is remote MCP, not a session hook." That was true of every version that
 * shipped before this one. It is not true now: `hooks/` runs `python3` on this machine on
 * every message and when a session goes idle, and the README says so in the same commit
 * that made it true. `--mcp-only` is how you get the old behaviour deliberately rather
 * than by the installer deciding for you.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HOSTED = "https://app.memvara.dev/mcp";
const ENTRY = { type: "remote", url: HOSTED, enabled: true };

/**
 * The plugin entry point, as an absolute path.
 *
 * Absolute rather than relative, and measured rather than assumed: OpenCode resolves a
 * relative entry against the directory it was started in, so a repo-relative path works
 * only while the user's shell happens to sit in this checkout. An absolute path in the
 * `plugin` array was verified to load against opencode 1.18.20 from an unrelated working
 * directory, with the module deliberately placed outside `.opencode/plugin/` so the
 * directory convention could not be what loaded it.
 */
const PLUGIN = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "..", "hooks", "js", "opencode.mjs");

function parseArgs(argv) {
  let config;
  let mcpOnly = false;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--config") { config = argv[i + 1]; i++; }
    else if (argv[i] === "--mcp-only") { mcpOnly = true; }
  }
  return {
    config: config || path.join(os.homedir(), ".config", "opencode", "opencode.json"),
    mcpOnly,
  };
}

function main() {
  const { config, mcpOnly } = parseArgs(process.argv.slice(2));
  let body = {};
  if (fs.existsSync(config)) {
    body = JSON.parse(fs.readFileSync(config, "utf8"));
  }

  body.mcp = body.mcp || {};
  body.mcp.memvara = { ...ENTRY };

  if (!mcpOnly) {
    if (!fs.existsSync(PLUGIN)) {
      // Refuse rather than write a path to nothing. OpenCode does not report a plugin
      // entry that fails to resolve, so a config naming a missing file is a plugin that
      // is installed, listed, and silently never runs.
      throw new Error(`refusing to write: no plugin at ${PLUGIN}`);
    }
    const plugins = Array.isArray(body.plugin) ? body.plugin : [];
    // Replace any earlier entry for this checkout rather than appending a second one:
    // re-running the installer must not register the same module twice.
    body.plugin = plugins.filter((p) => !String(p).endsWith("/hooks/js/opencode.mjs"));
    body.plugin.push(PLUGIN);
  }

  fs.mkdirSync(path.dirname(config), { recursive: true });
  fs.writeFileSync(config, JSON.stringify(body, null, 2) + "\n");
  process.stdout.write(
    mcpOnly
      ? `wrote mcp.memvara -> ${config}\n`
      : `wrote mcp.memvara and plugin -> ${config}\n`);
}

main();
