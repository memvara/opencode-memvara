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
90 days. Nothing runs in the background and no API key ships in this repo.

Do **not** add this repo to OpenCode's `"plugin": [...]` array. That path
loads JavaScript hooks on `session.*`; Memvara does not ship those.

## Skill

The judgment that spans tools is in `skills/memvara/SKILL.md`. Copy the
`skills/memvara` directory to `~/.config/opencode/skills/memvara` (global)
or `.opencode/skills/memvara` (per project) and OpenCode picks it up.

It also scans `.claude/skills/` and `~/.claude/skills/`, so a machine that
already has the Claude Code plugin installed has the skill available in
OpenCode with nothing further to do. Measured against opencode 1.18.20 on
2026-08-31: with the skill present only at `~/.claude/skills/memvara`,
`opencode run` listed `memvara` among its available skills.

An earlier version of this file told you to paste the skill into AGENTS.md,
because at the time this host did not pick those directories up. That has
stopped being so; if you followed it, the copy in AGENTS.md no longer needs
to be there.

## When the browser sign-in will not finish

The skill carries `scripts/memvara_auth.py` — inside the skill directory,
so wherever you copied `skills/memvara` to above, it is `scripts/memvara_auth.py`
under that. In this repository that is `skills/memvara/scripts/memvara_auth.py`;
after a global copy it is `~/.config/opencode/skills/memvara/scripts/memvara_auth.py`.

It is the device-code flow, standard library only, no `pip install`, and
nothing left running when it returns. Ask OpenCode to authenticate memvara
and it runs the script, which prints a short code and a URL for you to
approve and then writes `~/.memvara/credentials.json`. It also does
`logout` and `stats`.

OpenCode reads slash commands from `~/.config/opencode/commands/` and
`.opencode/commands/`, which are yours rather than this repo's, so there
is no `/memvara authenticate` shipped here. Asking in words is the
interface on this host.

## Installer

If you would rather merge the MCP block than edit JSON:

```
node bin/install.mjs
node bin/install.mjs --config ./opencode.json
```

It only writes `mcp.memvara`. It will refuse a config that already lists
`opencode-memvara` as a JS plugin.

## Teach it your vocabulary

The built-in predicates are a personal-assistant vocabulary. A store of engineering facts
matches none of them, and an unknown predicate takes the safe default twice over:
multi-valued, so nothing supersedes it, and slow-decaying, so this morning's deploy still
ranks as fresh in two years. The first half shows up on the write receipt. The second is
silent.

Server-side configuration, so it is set where the server is launched:

```bash
MEMVARA_PREDICATES=engineering        # or: engineering,./ours.toml
```

A declaration outranks a guess, so a pack corrects a store that already classified
something wrongly rather than only shaping a fresh one.

## Coming from another memory product

```python
from memvara.compat import import_mem0, import_supermemory
```

mem0 records what changed and when, so that import rebuilds supersession. Supermemory
records current state, so its documents arrive as episodes on their original timestamps
and nothing invents a history it was never told — which means plain recall answers from
claims and looks empty until you ask for `include_episodes`. The skill says this at the
point of use.

## Other clients

Claude Code: [memvara/claude-memvara](https://github.com/memvara/claude-memvara).
A loop you wrote is `pip install memvara`.

## License

Apache-2.0. Skill vendored from [memvara/memvara](https://github.com/memvara/memvara).
