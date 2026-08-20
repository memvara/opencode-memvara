# opencode-memvara

Give OpenCode a memory it can prove — a **remote MCP** entry, not a
JavaScript session plugin.

Paste this into `opencode.json` (project) or `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "memvara": {
      "type": "remote",
      "url": "https://app.memvara.dev/mcp",
      "enabled": true
    }
  }
}
```

The first time OpenCode talks to the server it opens a browser so you can
click Allow. You can also run `opencode mcp auth memvara`. That grant lasts
90 days. There is no local Python process and we do not use an API key.

Do **not** add this repo to OpenCode's `"plugin": [...]` array. That path
loads JavaScript hooks on `session.*`; Memvara does not ship those.

## Skill

The judgment that spans tools is in `skills/memvara/SKILL.md`. OpenCode
does not load Claude skill folders automatically. Paste the file into
[AGENTS.md](https://opencode.ai/docs/rules/) or keep it next to the project
and point the agent at it.

## Installer

If you would rather merge the MCP block than edit JSON:

```
node bin/install.mjs
node bin/install.mjs --config ./opencode.json
```

It only writes `mcp.memvara`. It will refuse a config that already lists
`opencode-memvara` as a JS plugin.

## Other clients

Claude Code: [memvara/claude-memvara](https://github.com/memvara/claude-memvara).
A loop you wrote is `pip install memvara`.

## License

Apache-2.0. Skill vendored from [memvara/memvara](https://github.com/memvara/memvara).
