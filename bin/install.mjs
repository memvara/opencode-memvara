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
    if (argv[i] === "--config") {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("--")) {
        // Without this, a trailing `--config` fell through to the DEFAULT path and wrote
        // the user's global config while reporting success. It happened during review of
        // this file: a forgotten path created ~/.config/opencode/opencode.json pointing
        // at a worktree. A flag that names a target must not silently target something
        // else.
        throw new Error("refusing to run: --config needs a path");
      }
      config = value;
      i++;
    }
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
    if (body.plugin !== undefined && !Array.isArray(body.plugin)) {
      // Refuse rather than replace. The previous version reset a non-array value to `[]`,
      // which silently DELETED whatever the user had written -- measured, `"plugin":
      // "some-other-plugin"` came back as our path alone, with output reading like
      // success. This installer is careful not to clobber anything else; a value it
      // cannot interpret is a reason to stop, not to discard.
      throw new Error(
        `refusing to write: "plugin" in ${config} is not an array; fix it by hand first`);
    }
    // Replace any earlier entry for this module rather than appending a second one:
    // re-running the installer must not register it twice.
    //
    // Entries may be a bare path OR a `[path, options]` tuple -- OpenCode's own type is
    // `Array<string | [string, PluginOptions]>`. Stringifying the whole entry missed the
    // tuple form entirely, because `String([path, {}])` is `"…opencode.mjs,[object
    // Object]"`, so a user who passed options got a SECOND registration on every run and
    // the module loaded twice: two recalls per message, two captures per idle.
    const entryPath = (p) => (Array.isArray(p) ? p[0] : p);
    body.plugin = (body.plugin ?? []).filter(
      (p) => String(entryPath(p)) !== PLUGIN);
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
