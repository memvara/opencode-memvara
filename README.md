# opencode-memvara

Give OpenCode a memory it can prove — a hosted **MCP** endpoint, the skill
that says how to use it, and a JavaScript plugin that makes memory automatic.

```
node bin/install.mjs
```

That writes both halves into `~/.config/opencode/opencode.json`. For the
endpoint alone, with nothing running on this machine, use `--mcp-only` and
skip to the block below.

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

Or paste this into `opencode.json` (project) or
`~/.config/opencode/opencode.json` for the endpoint on its own:

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
90 days, and no API key ships in this repo.

## What runs on your machine

Until 0.2.5 this page said nothing ran in the background and told you not to
add this repo to OpenCode's `"plugin": [...]` array. Both were true then and
neither is true now, so both are gone rather than softened.

The installer registers `hooks/js/opencode.mjs`, and OpenCode loads it into
its own process. On every message it runs `python3 hooks/run.py recall`, and
on the first message of a session `session_start` as well; when a session
goes idle it runs `capture`, which spends 12-14 seconds mining the turn that
just ended. Capture is deliberately not awaited — measured on opencode
1.18.20, an awaited hook holds the turn open for exactly as long as it runs,
while an un-awaited one returns in a millisecond and its work still finishes.

Nothing this plugin does is visible in the OpenCode interface, because
OpenCode gives a plugin no channel to the screen. Its account of itself is
`~/.memvara/.hooks/` — `hooks.log` for the read path and `capture.log` for
the write path, where every run writes a line including the runs that decide
to do nothing.

Capture mines the turn with **your own model** — it runs `opencode run`
with whatever you have configured and authenticated, so nothing else needs
installing and nothing overrides the model you chose. `claude -p` stays as a
fallback if you happen to have Claude Code; with neither, extraction logs that
it could not run and raises an alert on the next prompt rather than storing
nothing in silence.

That makes capture's speed and quality yours too. On a small or free model
expect it to fail more often — one measured run exceeded the 90-second timeout
before a retry succeeded — and `capture.log` is where that shows.

To have the endpoint and none of this, install with `--mcp-only`.

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

```
node bin/install.mjs
node bin/install.mjs --config ./opencode.json
node bin/install.mjs --mcp-only
```

It writes `mcp.memvara` and appends the plugin's absolute path to
`plugin`, replacing an earlier entry for the same checkout rather than
adding a second. `--mcp-only` writes the endpoint and no plugin. It refuses
to write a plugin path that does not resolve, because OpenCode does not
report a plugin entry that fails to load — a config naming a missing file is
a plugin that is installed, listed, and silently never runs.

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
