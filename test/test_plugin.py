"""Gates for the OpenCode remote-MCP package.

This is not a JavaScript session plugin. The files OpenCode will read are
an opencode.json snippet and, if someone asks, the skill markdown.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "memvara"
HOSTED = "https://app.memvara.dev/mcp"
REPO_NAME = "memvara/opencode-memvara"


def _json(path: pathlib.Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _library_bytes(sha: str, path: str) -> bytes:
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        return subprocess.check_output(
            ["git", "-C", root, "show", f"{sha}:{path}"],
        )
    import urllib.request
    url = f"https://raw.githubusercontent.com/memvara/memvara/{sha}/{path}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _lock() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / "skill.lock").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


class ExampleConfig(unittest.TestCase):
    def test_remote_mcp_only(self) -> None:
        body = _json(ROOT / "examples" / "opencode.json")
        assert isinstance(body, dict)
        entry = body["mcp"]["memvara"]
        self.assertEqual(entry["type"], "remote")
        self.assertEqual(entry["url"], HOSTED)
        self.assertTrue(entry.get("enabled", True))
        self.assertNotIn("plugin", body)
        self.assertNotIn("command", entry)

    def test_no_npx_in_json(self) -> None:
        """No JSON *this repo ships* may reach for npx.

        `_library` is skipped because it is not ours: CI checks the library out there, at
        `skill.lock`'s sha, so the drift test can run offline. The moment that lock moves
        to a sha where the library has an npm package, an unfiltered scan reads
        `_library/npm/memvara/package.json` -- whose description legitimately begins "npx
        memvara" -- and fails a sync PR for a string in another repository. That is not
        hypothetical: it happened in claude-memvara on 2026-08-25, and this lock bump is
        the one that would have done it here.

        The scan stays repo-wide rather than narrowing to `plugin/`: the rule is about
        anything shipped from here, and an allowlist of directories stops covering the
        next one added.
        """
        for path in ROOT.rglob("*.json"):
            if {"node_modules", "_library"} & set(path.parts):
                continue
            self.assertNotIn("npx", path.read_text(encoding="utf-8"), path)


class Installer(unittest.TestCase):
    def test_writes_mcp_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "opencode.json"
            subprocess.check_call(
                ["node", str(ROOT / "bin" / "install.mjs"), "--config", str(cfg)],
            )
            body = _json(cfg)
            self.assertEqual(body["mcp"]["memvara"]["url"], HOSTED)
            self.assertEqual(body["mcp"]["memvara"]["type"], "remote")
            self.assertNotIn("plugin", body)

    def test_refuses_js_plugin_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "opencode.json"
            cfg.write_text(
                json.dumps({"plugin": ["opencode-memvara"]}),
                encoding="utf-8",
            )
            proc = subprocess.run(
                ["node", str(ROOT / "bin" / "install.mjs"), "--config", str(cfg)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("JS plugin", proc.stderr + proc.stdout)


class SkillTree(unittest.TestCase):
    def test_skill_has_front_matter_and_references(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.splitlines()[0] == "---")
        named = set(re.findall(r"references/([a-z0-9-]+\.md)", text))
        self.assertTrue(named)
        for name in named:
            self.assertTrue((SKILL / "references" / name).is_file(), name)

    def test_matches_library_at_lock_sha(self) -> None:
        lock = _lock()
        self.assertEqual(lock["repo"], "memvara/memvara")
        sha = lock["sha"]
        self.assertEqual(len(sha), 40)
        for rel in ("SKILL.md", "references/hosted-mcp.md"):
            expected = _library_bytes(sha, f"memvara/skills/memvara/{rel}")
            self.assertEqual((SKILL / rel).read_bytes(), expected, rel)


class Readme(unittest.TestCase):
    def test_install_copy(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(HOSTED, text)
        self.assertIn('"type": "remote"', text)
        self.assertIn("plugin", text.lower())
        self.assertNotIn("npx ", text)
        self.assertIn("Do **not** add this repo to OpenCode's", text)

    def test_license(self) -> None:
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", text)

    def test_version(self) -> None:
        self.assertEqual(_json(ROOT / "plugin.json")["version"], "0.1.0")

    def test_github_org(self) -> None:
        env = os.environ.get("GITHUB_REPOSITORY")
        if env:
            self.assertEqual(env, REPO_NAME)


class Hygiene(unittest.TestCase):
    def test_no_hooks(self) -> None:
        self.assertFalse((ROOT / "hooks").exists())
        self.assertFalse((ROOT / ".app.json").exists())


if __name__ == "__main__":
    unittest.main()
