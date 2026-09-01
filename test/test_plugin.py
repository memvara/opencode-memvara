"""Gates for the OpenCode remote-MCP package.

This is not a JavaScript session plugin. The files OpenCode will read are
an opencode.json snippet and, if someone asks, the skill markdown.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "memvara"
HOSTED = "https://app.memvara.dev/mcp"
REPO_NAME = "memvara/opencode-memvara"


def _json(path: pathlib.Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


class LibraryUnreachable(Exception):
    """Neither a local checkout nor GitHub could answer. Raised, never swallowed.

    A drift check that quietly passes when it cannot look is the same as no drift check.
    This repository has already been caught by exactly that shape: `skill-sync.yml` failed
    on every scheduled run for days while nothing here went red, because the vendored copy
    and `skill.lock` stayed consistent with each other and the only thing that would have
    noticed was a scheduled job nobody read.
    """


def _trust() -> "ssl.SSLContext":
    """A context that trusts the same roots `curl` does.

    python.org's macOS build ignores the system trust store, so an unqualified `urlopen`
    raises CERTIFICATE_VERIFY_FAILED against a certificate `curl` accepts. Without this the
    drift check below does not fail on a Mac -- it *skips*, reporting the library as
    unreachable when the library is fine, which is the quiet half of the failure it was
    written to catch.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "memvara-tests"})
    with urllib.request.urlopen(request, timeout=30, context=_trust()) as resp:
        return bytes(resp.read())


def _library_bytes(sha: str, path: str) -> bytes:
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        try:
            return subprocess.check_output(
                ["git", "-C", root, "show", f"{sha}:{path}"],
                stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # The checkout has the sha `skill.lock` names and nothing else: CI clones the
            # library AT that sha, shallow, so the library's current HEAD is simply not an
            # object here. Falling back to the network rather than failing is what lets the
            # drift check below run on CI at all -- and it only matters when the lock is
            # stale, which is precisely when the check has something to say.
            pass
    return _fetch(f"https://raw.githubusercontent.com/memvara/memvara/{sha}/{path}")


def _library_head() -> str:
    """The library default branch's current sha, or raise `LibraryUnreachable`."""
    root = os.environ.get("MEMVARA_LIBRARY")
    if root:
        for ref in ("origin/main", "main"):
            try:
                return subprocess.check_output(
                    ["git", "-C", root, "rev-parse", ref],
                    stderr=subprocess.DEVNULL).decode().strip()
            except subprocess.CalledProcessError:
                continue
    try:
        body = _fetch("https://api.github.com/repos/memvara/memvara/commits/main")
        return str(json.loads(body)["sha"])
    except Exception as exc:
        raise LibraryUnreachable(str(exc)) from exc


def _library_skill_files(sha: str) -> "set[str]":
    """Every path under the packaged skill at `sha`, relative to it."""
    root = os.environ.get("MEMVARA_LIBRARY")
    prefix = "memvara/skills/memvara/"
    if root:
        try:
            out = subprocess.check_output(
                ["git", "-C", root, "ls-tree", "-r", "--name-only", sha,
                 "memvara/skills/memvara"], stderr=subprocess.DEVNULL).decode()
        except subprocess.CalledProcessError:
            # Not an object in this checkout -- see `_library_bytes`. Ask GitHub instead
            # of reporting the library unreachable, which would SKIP the check on the one
            # run that needed it.
            out = None
        if out is not None:
            return {line[len(prefix):] for line in out.splitlines()
                    if line.startswith(prefix)}
    try:
        tree = json.loads(_fetch(
            f"https://api.github.com/repos/memvara/memvara/git/trees/{sha}?recursive=1"))
    except Exception as exc:
        raise LibraryUnreachable(str(exc)) from exc
    return {entry["path"][len(prefix):] for entry in tree.get("tree", [])
            if entry.get("type") == "blob" and entry["path"].startswith(prefix)}


def _library_files(sha: str, path: str) -> "set[str]":
    """Every path under `path` at `sha`, relative to `path`.

    The hook twin of `_library_skill_files`, and separate from it on purpose: that one
    hardcodes the packaged-skill prefix, and widening it to take a path would have made
    every existing caller pass an argument to say what it already meant.
    """
    root = os.environ.get("MEMVARA_LIBRARY")
    prefix = f"{path}/"
    if root:
        try:
            out = subprocess.check_output(
                ["git", "-C", root, "ls-tree", "-r", "--name-only", sha, path],
                stderr=subprocess.DEVNULL).decode()
        except subprocess.CalledProcessError:
            out = None
        if out is not None:
            return {line[len(prefix):] for line in out.splitlines()
                    if line.startswith(prefix)}
    try:
        tree = json.loads(_fetch(
            f"https://api.github.com/repos/memvara/memvara/git/trees/{sha}?recursive=1"))
    except Exception as exc:
        raise LibraryUnreachable(str(exc)) from exc
    return {entry["path"][len(prefix):] for entry in tree.get("tree", [])
            if entry.get("type") == "blob" and entry["path"].startswith(prefix)}


def _lock(name: str = "skill.lock") -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


#: The vendored hook tree, and the library path it is vendored from.
HOOKS = ROOT / "hooks"
LIBRARY_HOOKS_PATH = "plugin/hooks"

#: Hook scripts are executable content OpenCode loads into its own process and runs on
#: every message, so the allowlist names them one by one. A file appearing under `hooks/`
#: that nobody listed here is the failure this gate exists to catch.
ALLOWED_HOOK_FILES = {
    "run.py", "recall.py", "capture.py", "session_start.py", "approve.py", "daemon.py",
    "core/__init__.py", "core/host.py", "core/envelope.py",
    "hosts/__init__.py", "hosts/claude.py", "hosts/opencode.py",
    "js/shim.mjs", "js/opencode.mjs",
    "lib/__init__.py", "lib/extract.py", "lib/fast.py", "lib/hosted.py", "lib/ipc.py",
    "lib/open.py", "lib/standing.py", "lib/transcript.py", "lib/usage.py",
    "lib/write.py",
    "tools/__init__.py", "tools/generate.py",
}


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
    """It writes both halves now, and it used to refuse the second one.

    Until 0.2.5 `test_refuses_js_plugin_array` asserted the installer THREW on a config
    that named this repo as a JS plugin, because Memvara shipped no hooks and a config
    that said otherwise was a mistake. This repository ships them now, so that assertion
    is replaced rather than deleted: the refusal below is the one that still matters --
    a plugin path that does not resolve.
    """

    def test_writes_both_the_endpoint_and_the_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "opencode.json"
            subprocess.check_call(
                ["node", str(ROOT / "bin" / "install.mjs"), "--config", str(cfg)])
            body = _json(cfg)
            self.assertEqual(body["mcp"]["memvara"]["url"], HOSTED)
            self.assertEqual(body["mcp"]["memvara"]["type"], "remote")
            # The plugin path must BE the vendored module, not merely be present. A
            # config naming some other file is a plugin that installs and never recalls.
            self.assertEqual(
                [pathlib.Path(x).resolve() for x in body["plugin"]],
                [(HOOKS / "js" / "opencode.mjs").resolve()],
                "the installer wrote a plugin entry that is not this repo's module")

    def test_mcp_only_writes_no_plugin(self) -> None:
        """The old behaviour, still reachable, because it is a real choice.

        A user who wants the endpoint and nothing running locally has to be able to say
        so. Without this the only way to get it would be to hand-edit the file the
        installer just wrote, which is the shape that makes people skip the installer.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "opencode.json"
            subprocess.check_call(
                ["node", str(ROOT / "bin" / "install.mjs"),
                 "--config", str(cfg), "--mcp-only"])
            body = _json(cfg)
            self.assertEqual(body["mcp"]["memvara"]["url"], HOSTED)
            self.assertNotIn("plugin", body)

    def test_running_it_twice_registers_one_plugin(self) -> None:
        """Appending blindly would register the module twice, and OpenCode would load it
        twice -- two recalls injected per message, and two captures per idle."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = pathlib.Path(tmp) / "opencode.json"
            for _ in range(2):
                subprocess.check_call(
                    ["node", str(ROOT / "bin" / "install.mjs"), "--config", str(cfg)])
            self.assertEqual(len(_json(cfg)["plugin"]), 1)

    def test_it_refuses_to_write_a_plugin_path_that_does_not_resolve(self) -> None:
        """The refusal that replaced the old one.

        OpenCode does not report a plugin entry that fails to load, so a config naming a
        missing file is a plugin that is installed, listed, and silently never runs --
        indistinguishable, from the outside, from one that is working.
        """
        with tempfile.TemporaryDirectory() as tmp:
            # A copy of the installer with no hooks tree beside it: the state a partial
            # checkout or an interrupted vendor leaves behind.
            bin_dir = pathlib.Path(tmp) / "bin"
            bin_dir.mkdir()
            (bin_dir / "install.mjs").write_bytes(
                (ROOT / "bin" / "install.mjs").read_bytes())
            cfg = pathlib.Path(tmp) / "opencode.json"
            proc = subprocess.run(
                ["node", str(bin_dir / "install.mjs"), "--config", str(cfg)],
                capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("refusing to write", proc.stderr + proc.stdout)
            self.assertFalse(cfg.exists(),
                             "it refused and still wrote the config")


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

    def test_the_vendored_skill_is_not_behind_the_library(self) -> None:
        """The whole tree, against the library's CURRENT default branch.

        `test_matches_library_at_lock_sha` cannot catch a stale sync and is not supposed
        to: it compares the copy against the sha the copy itself names, so a lock and a
        tree frozen together agree with each other forever. That is exactly how this repo
        shipped a skill five commits behind -- `skill-sync.yml` dying every night on a
        permission the organization pins, nothing here going red, and the agreement
        between the two stale files being the thing that hid it.

        Two deliberate choices about noise. It compares BYTES rather than shas, so the
        library moving does not fail this repository -- only the library's *skill* moving
        does, which is rare. And it compares the file SET as well, because a new reference
        file upstream is drift that a per-file comparison of the files we already have
        would never see.

        When the library cannot be reached this SKIPS rather than passes. A skip is
        visible in the run output; a pass is not, and a check that silently succeeds when
        it could not look is the failure it exists to prevent, one level up.
        """
        try:
            head = _library_head()
            upstream = _library_skill_files(head)
        except LibraryUnreachable as exc:
            raise unittest.SkipTest(
                f"library unreachable, drift NOT checked: {exc}") from exc

        self.assertTrue(upstream, "the library reported an empty skill tree")
        ours = {str(path.relative_to(SKILL))
                for path in SKILL.rglob("*") if path.is_file()}
        self.assertEqual(
            ours, upstream,
            f"the vendored skill's file set differs from the library at {head[:7]} — "
            "run scripts/sync_plugin_repos.py from the library and update skill.lock")

        drifted = []
        for rel in sorted(upstream):
            expected = _library_bytes(head, f"memvara/skills/memvara/{rel}")
            if (SKILL / rel).read_bytes() != expected:
                drifted.append(rel)
        self.assertEqual(
            drifted, [],
            f"vendored skill is behind memvara/memvara@{head[:7]}: {drifted} — "
            "sync it")


class Readme(unittest.TestCase):
    def test_install_copy(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(HOSTED, text)
        self.assertIn('"type": "remote"', text)
        self.assertIn("plugin", text.lower())
        self.assertNotIn("npx ", text)
        # The page used to carry "Do **not** add this repo to OpenCode's `plugin` array".
        # It shipped no hooks then and the instruction was right; it ships them now and
        # the installer writes exactly that entry, so the sentence must be gone. Stated
        # as an absence AND as a presence, because an absence alone is satisfied by a
        # README that has stopped describing the install at all.
        self.assertNotIn("Do **not** add this repo to OpenCode's", text)
        self.assertIn("--mcp-only", text,
                      "the README does not tell the reader how to get the endpoint "
                      "without the local process")

    def test_license(self) -> None:
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("Apache License", text)

    def test_version(self) -> None:
        self.assertEqual(_json(ROOT / "plugin.json")["version"], Version.VERSION)

    def test_github_org(self) -> None:
        env = os.environ.get("GITHUB_REPOSITORY")
        if env:
            self.assertEqual(env, REPO_NAME)


class SharedInstructions(unittest.TestCase):
    """CLAUDE.md is shared across every plugin repo, and nothing used to carry it.

    It was hand-copied and it drifted: eleven of fourteen sections were byte-identical
    across all seven repositories while a section written in one of them reached none of
    the others. The canonical is `plugin-claude.md` in the library; `skill-sync.yml`
    composes this file from it and preserves the `local:` block, because two sections
    legitimately differ per repo — a repository's own runtime facts, and hook rules that
    only one plugin needs.

    Without this guard the sync would be a tidier way to drift rather than an end to it,
    which is the objection the section it carries makes about hand-maintained copies.
    """

    BEGIN = "<!-- local: begin"
    END = "<!-- local: end -->"

    def _text(self) -> str:
        return (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    def test_the_local_block_is_delimited_exactly_once(self) -> None:
        """Two of either marker and the splice takes the wrong span; none and the composer
        refuses rather than replacing this repository's sections with a placeholder.
        """
        text = self._text()
        self.assertEqual(text.count(self.BEGIN), 1)
        self.assertEqual(text.count(self.END), 1)
        self.assertLess(text.index(self.BEGIN), text.index(self.END))

    def test_the_shared_half_matches_the_library(self) -> None:
        """Compared against the LIBRARY, never against this file's own halves.

        A check that read both halves of one file would prove it internally consistent and
        nothing else — exactly how a vendored skill sat five commits behind while its own
        drift test passed.
        """
        lock = _lock()
        try:
            canonical = _library_bytes(lock["sha"], "plugin-claude.md").decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(
                f"library has no plugin-claude.md at {lock['sha'][:7]}: {exc}") from exc
        text = self._text()
        head, rest = text.split(self.BEGIN, 1)
        _, tail = rest.split(self.END, 1)
        want_head, want_tail = canonical.split("@@LOCAL@@\n", 1)
        self.assertEqual(head, want_head,
                         "text above the local block drifted — edit plugin-claude.md in "
                         "memvara/memvara, not the copy here")
        self.assertEqual(tail.lstrip("\n"), want_tail.lstrip("\n"),
                         "text below the local block drifted from plugin-claude.md")

    def test_the_local_block_holds_what_only_this_repo_knows(self) -> None:
        """Not decorative: it carries the two sections that differ per repo. A sync that
        flattened it would lose them silently — the file would still read as a complete
        CLAUDE.md, just one belonging to a different repository.
        """
        local = self._text().split(self.BEGIN, 1)[1].split(self.END, 1)[0]
        self.assertIn("Runtime facts that cost hours to find", local)
        self.assertIn("If this repo ships hooks", local)


class Hygiene(unittest.TestCase):
    def test_no_app_manifest(self) -> None:
        """`hooks/` used to be asserted absent here beside `.app.json`, and is not any
        more: this repository ships it. The half that replaced that assertion is the
        `Hooks` class below, which is strictly stronger than "the directory is absent" --
        it names every file in the tree one by one and compares all of them against the
        library. An emptied `hooks/` fails those and would have satisfied the assertion
        removed here."""
        self.assertFalse((ROOT / ".app.json").exists())


class Hooks(unittest.TestCase):
    """The tree OpenCode loads into its own process, and runs unasked on every message.

    Vendored byte for byte from `memvara/memvara` with ZERO transforms -- stricter than
    `skill.lock`, which sanctions exactly one line. Two comparisons, because they catch
    different failures: one against the sha the lock names, and one against the library's
    current default branch. The first alone is satisfied forever by a lock and a copy
    frozen together, which is how the vendored skill in this family once shipped five
    commits behind for four days while every test passed.
    """

    def _ours(self) -> "set[str]":
        """Every vendored file, relative to `hooks/`, POSIX-spelled.

        `__pycache__` is dropped: running a hook writes bytecode next to it, it is
        gitignored and never committed, and failing on it would fail on every machine
        that has used the plugin once.
        """
        return {path.relative_to(HOOKS).as_posix() for path in HOOKS.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts}

    def test_the_vendored_hook_bytes_match_the_library_at_the_pinned_sha(self) -> None:
        lock = _lock("hooks.lock")
        self.assertEqual(lock["repo"], "memvara/memvara")
        self.assertEqual(lock["path"], LIBRARY_HOOKS_PATH)
        self.assertEqual(lock["host"], "opencode")
        sha = lock["sha"]
        self.assertEqual(len(sha), 40, f"hooks.lock sha is not a full sha: {sha!r}")

        ours = self._ours()
        self.assertTrue(ours, "no vendored hook files found — this guard would pass on "
                              "an empty tree, which is the shape it exists to stop")
        try:
            upstream = _library_files(sha, LIBRARY_HOOKS_PATH)
        except LibraryUnreachable as exc:
            raise unittest.SkipTest(
                f"library unreachable, vendored bytes NOT checked: {exc}") from exc
        self.assertEqual(ours, upstream,
                         f"the vendored hook file set differs from the library@{sha[:7]}")
        drifted = [rel for rel in sorted(ours)
                   if (HOOKS / rel).read_bytes()
                   != _library_bytes(sha, f"{LIBRARY_HOOKS_PATH}/{rel}")]
        self.assertEqual(drifted, [], f"vendored hooks drifted from {sha[:7]}: {drifted}")

    def test_the_vendored_hooks_are_not_behind_the_library(self) -> None:
        """The whole tree, and the file SET, against the library's CURRENT branch.

        Skips loudly rather than passing when the library cannot be reached: a check that
        passes because it could not look is the failure one level up.
        """
        try:
            head = _library_head()
            upstream = _library_files(head, LIBRARY_HOOKS_PATH)
        except LibraryUnreachable as exc:
            raise unittest.SkipTest(
                f"library unreachable, hook drift NOT checked: {exc}") from exc
        self.assertTrue(upstream, "the library reported an empty hook tree")
        self.assertEqual(self._ours(), upstream,
                         f"the vendored hook file set differs from the library at "
                         f"{head[:7]} — re-vendor and update hooks.lock")

    def test_the_hook_file_set_is_named_here_one_by_one(self) -> None:
        """A file the client executes that nobody listed is the thing to catch."""
        extra = self._ours() - ALLOWED_HOOK_FILES
        self.assertFalse(extra, f"unlisted hook files: {sorted(extra)} — add them to "
                                "ALLOWED_HOOK_FILES deliberately, having read them")

    def test_the_allowlist_names_nothing_that_is_no_longer_in_the_tree(self) -> None:
        """The direction that is easy to leave out. A file deleted upstream leaves its
        entry behind, the entry covers nothing, and a list that has stopped covering a
        file looks exactly like a list that covers everything."""
        missing = ALLOWED_HOOK_FILES - self._ours()
        self.assertFalse(missing, f"allowlist names files that are gone: {sorted(missing)}")

    def test_this_repository_ships_the_record_its_lock_binds(self) -> None:
        """`hooks.lock` says `host=opencode`; that record has to be in the tree.

        Bound and shipped are different facts, and the pair is what makes the binding
        real: a lock naming a record nobody vendored produces `skipped=unknown host` on
        every event, in a log file, forever.
        """
        self.assertEqual(_lock("hooks.lock")["host"], "opencode")
        self.assertTrue((HOOKS / "hosts" / "opencode.py").is_file())

    def test_no_shell_registration_manifest_is_shipped(self) -> None:
        """`hooks.json` is a Claude-shaped manifest of shell commands. OpenCode registers
        a JavaScript module instead, and `tools/generate.py` refuses to build one for this
        host by name. A `hooks.json` sitting here would be a file that registers nothing
        on this client while reading, to anyone who opened it, as the registration."""
        self.assertFalse((HOOKS / "hooks.json").exists())

    def test_the_plugin_module_reaches_the_entry_point_it_names(self) -> None:
        """The module resolves `run.py` from its own location, and that file must be
        there. `is_file()` alone would not be enough anywhere a path could point at the
        wrong file, so this compares the RESOLVED path to the entry point itself."""
        module = HOOKS / "js" / "opencode.mjs"
        self.assertTrue(module.is_file())
        text = module.read_text(encoding="utf-8")
        self.assertIn('new URL("..", import.meta.url)', text,
                      "the module no longer derives the hooks directory from its own "
                      "location, so a vendored copy would run some other checkout's hooks")
        self.assertEqual((module.parent.parent / "run.py").resolve(),
                         (HOOKS / "run.py").resolve())

    def test_the_reply_this_host_reads_is_flat(self) -> None:
        """OpenCode's shim parses a flat object; Claude's nested `hookSpecificOutput`
        shape would parse as valid JSON and carry no context at all.

        This renders the record directly rather than running `recall` and reading its
        stdout. The first version did the latter and was WORTHLESS: recall dedups per
        session and answers nothing for a prompt it has already served, so the test hit
        its own "nothing to say" skip on a machine with a live store -- and reported
        `OK (skipped=1)` with the envelope deliberately switched to "nested". A guard
        that skips is not a guard, and one that skips on the developer's own machine is
        one nobody will ever see fail.
        """
        sys.path.insert(0, str(HOOKS))
        try:
            from core import envelope  # noqa: PLC0415
            from core.host import Reply  # noqa: PLC0415
            import hosts.opencode as record  # noqa: PLC0415
        finally:
            sys.path.remove(str(HOOKS))
        rendered = envelope.render(
            record.HOST, Reply(hook="recall", status="a status line", context="CTX"))
        body = json.loads(rendered)
        self.assertEqual(body.get("additionalContext"), "CTX",
                         "context is not at the top level, so the shim will not find it")
        self.assertNotIn("hookSpecificOutput", body,
                         "the record renders Claude's nested shape; the shim reads a "
                         "flat object and would deliver nothing")
        self.assertNotIn("systemMessage", body,
                         "a status line was rendered for a host that has no channel to "
                         "show one, so the renderer is inventing a key nobody reads")

    def test_the_reply_is_ascii_so_a_chunk_boundary_cannot_split_a_character(self) -> None:
        """The invariant that makes the shim's stream reading safe, pinned deliberately.

        A review of this port claimed the shim corrupted UTF-8 at chunk boundaries, on the
        grounds that accumulating stdout as `out += buffer` decodes each chunk alone and
        turns a split multi-byte character into U+FFFD -- silently, since the surrounding
        JSON still parses. The mechanism is real. The scenario was NOT: `json.dumps`
        escapes non-ASCII by default, so a reply carrying an em dash goes out as the seven
        ASCII bytes `\\u2014` and there is no multi-byte sequence for a boundary to split.
        Measured: 16,371 bytes of real recall output, zero bytes above 127.

        So the guard belongs on the property that makes it true rather than on the
        corruption that cannot currently happen. Set `ensure_ascii=False` in the renderer
        and this fails -- at which point the shim's decoding starts to matter and the
        comment there stops being belt-and-braces.
        """
        sys.path.insert(0, str(HOOKS))
        try:
            from core import envelope  # noqa: PLC0415
            from core.host import Reply  # noqa: PLC0415
            import hosts.opencode as record  # noqa: PLC0415
        finally:
            sys.path.remove(str(HOOKS))
        rendered = envelope.render(
            record.HOST,
            Reply(hook="recall", context="an em dash — and a star ⋈ and an accent é"))
        raw = rendered.encode("utf-8")
        high = [b for b in raw if b > 127]
        self.assertEqual(
            high, [],
            f"the rendered reply carries {len(high)} non-ASCII bytes, so a stdout chunk "
            "boundary can now split a character and the shim's decoding is load-bearing "
            "rather than defensive")

    def test_a_hook_never_fails_a_turn_whatever_the_environment(self) -> None:
        """No home directory, no store, no credentials: exit 0 and stay quiet.

        A non-zero exit from the read path is a blocked prompt on some hosts and a broken
        turn on this one, so this is the invariant the whole package is built around.
        """
        env = dict(os.environ, HOME="/nonexistent", MEMVARA_HOME="/nonexistent")
        for hook in ("session_start", "recall", "capture", "approve"):
            with self.subTest(hook=hook):
                proc = subprocess.run(
                    [sys.executable, str(HOOKS / "run.py"), hook, "--host", "opencode"],
                    input="{}", capture_output=True, text=True, env=env, timeout=120)
                self.assertEqual(proc.returncode, 0,
                                 f"{hook} exited {proc.returncode}: {proc.stderr[:300]}")
                if proc.stdout.strip():
                    json.loads(proc.stdout)


class Version(unittest.TestCase):
    """Every version this repository states must be the same one, and none may hide.

    Five skill syncs shipped under 0.1.0. The vendored skill is the whole of what a client
    receives here, it changed five times, and the string a client compares never moved.
    `claude-memvara` was caught by the identical shape at larger scale -- twenty-one
    commits on main behind an unchanged version, `/plugin update` answering "already at
    the latest version" for every one of them.

    Three deliberate choices, each of them paid for by a sabotage run.

    Files are found by walking the tree, not by reading a list, so a manifest nobody
    remembered cannot go unchecked. `DECLARED` is then the completeness half -- it names
    the manifests that MUST carry a version, and it is compared against the walk in both
    directions, which is what keeps a hand-written list from quietly narrowing coverage.

    The file set comes from `git ls-files`, not from the filesystem. Two sweeps of the
    tree were tried first and both were wrong in a way a passing run could not show: one
    ignored directories by absolute path, which excluded the entire repository whenever the
    checkout was a worktree (those live under `.claude/worktrees/`, so `.claude` was in the
    parts of every path); the next was caught by CI dragging in six manifests from the
    library checkout under `_library/`. Git already knows which files this repository owns.

    And the assertions demand presence rather than absence of the wrong value. The
    coverage check was first written as a bare set comparison and passed on that broken
    walk because both sides were empty; the value check alone still passes when one
    manifest of several drops its version entirely. A guard an absence satisfies has
    stopped guarding.
    """

    VERSION = "0.2.3"
    DECLARED = {
        'plugin.json',
    }

    @classmethod
    def _walk(cls, node: object, where: str = ""):
        """Every `version` string at any depth, with the pointer that reached it."""
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "version" and isinstance(value, str):
                    yield f"{where}.{key}", value
                else:
                    yield from cls._walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from cls._walk(value, f"{where}[{index}]")

    @classmethod
    def _candidates(cls) -> list:
        """Every JSON file this repository TRACKS -- asked of git, not of the filesystem.

        The filesystem is the wrong referent. CI checks the library out into `_library/`,
        which carries the sibling plugins' own manifests, and an `rglob` swept all six into
        the walk; a denylist would then have to grow a name for every scratch directory
        anyone ever creates, and the first one nobody thought of is a false failure. What
        the question actually means is "files this repository owns", and git is the thing
        that knows. Untracked checkouts and nested worktrees fall out for free.

        No fallback when git cannot answer. A fallback here would silently cover less than
        the caller believes, which is the failure this whole class exists to prevent.
        """
        listed = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-z", "*.json"],
            check=True, capture_output=True, text=True).stdout
        return [
            ROOT / name for name in listed.split("\0")
            if name and pathlib.PurePath(name).name != "package-lock.json"
        ]

    def _stated(self) -> list:
        found = []
        for path in self._candidates():
            try:
                body = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            found.extend((path, where, value) for where, value in self._walk(body))
        return found

    def test_every_version_this_repo_states_is_the_released_one(self) -> None:
        stated = self._stated()
        self.assertTrue(
            stated, "no file states a version at all -- this guard has stopped guarding")
        for path, where, value in stated:
            self.assertEqual(
                value, self.VERSION,
                f"{path.relative_to(ROOT)}{where} says {value!r}; a partial bump is how a "
                "client gets told it is current while the contents moved underneath it")

    def test_exactly_the_manifests_that_must_declare_a_version_do(self) -> None:
        """Both directions, because each catches a mistake the other cannot see.

        A file the walk misses is a version nobody checks. A file that has stopped
        declaring one is a manifest shipping unversioned -- invisible to the value check
        above, which goes green as soon as any other file still says the right thing.
        Confirmed by sabotage: deleting the key from one of three manifests left it green.
        """
        reached = {str(path.relative_to(ROOT)) for path, _where, _value in self._stated()}
        by_text = {
            str(path.relative_to(ROOT)) for path in self._candidates()
            if '"version"' in path.read_text(encoding="utf-8")
        }
        self.assertEqual(by_text, self.DECLARED, "a manifest gained or lost its version")
        self.assertEqual(reached, self.DECLARED, "the JSON walk missed a stated version")

    def test_the_release_number_is_written_down_exactly_once_in_this_suite(self) -> None:
        """`VERSION` above is the only place the tests name it.

        Ported from claude-memvara, which learned it the same way this repository just
        did: another test asserted the release literally, so a bump had to be applied in
        two places and one of them was missed. Every extra place is the mechanism a
        partial bump needs, and a partial bump is what tells a client it is current while
        the contents moved underneath it.

        The duplicates that prompted this now read `Version.VERSION` instead, which is
        why they no longer count.
        """
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        self.assertEqual(
            source.count(f'"{self.VERSION}"'), 1,
            f"{self.VERSION} appears more than once in this file; VERSION is meant to be "
            "the single place the suite states the release")


def _readme_prose(root: pathlib.Path) -> str:
    """The README with every run of whitespace collapsed to one space.

    Prose wraps, and where it wraps is not a fact about what it says. Matching raw text
    pins a line break: a reflow turns a guard red while the sentence it guards is present
    and correct, and the cheapest way out of that is to delete the guard. It matters for
    the negative assertions too -- a claim reintroduced with a different wrap slips past
    `assertNotIn` on the raw text.
    """
    return " ".join(root.joinpath("README.md").read_text(encoding="utf-8").split())


class ModuleShape(unittest.TestCase):
    """Nothing may be defined below `unittest.main()`.

    Measured in the two sibling repos before this one: a class appended to the end of the
    file, after the `__main__` block, is collected by `unittest discover` and NOT by
    `python3 test/test_plugin.py`. Both printed OK -- 26 tests one way and 21 the other,
    with nothing in the output saying so. A passing run must not be able to mean "the
    check never ran", so the shape gets a guard rather than a comment.
    """

    def test_nothing_is_defined_after_the_main_block(self) -> None:
        import ast

        body = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8")).body
        guards = [i for i, node in enumerate(body)
                  if isinstance(node, ast.If) and "__main__" in ast.dump(node.test)]
        self.assertEqual(len(guards), 1, "expected exactly one __main__ block")
        after = [type(node).__name__ for node in body[guards[0] + 1:]]
        self.assertEqual(
            after, [],
            f"{after} is defined after `unittest.main()`, so "
            "`python3 test/test_plugin.py` runs without it and still prints OK")


class AuthScript(unittest.TestCase):
    """The skill ships the device-code flow, because this host has nowhere else for it.

    OpenCode reads slash commands from `~/.config/opencode/commands/` and
    `.opencode/commands/` -- the user's directories, not this repository's -- so there is
    no `/memvara authenticate` to ship. What it does load is the skill, and skill-relative
    paths were measured on it: a probe skill whose SKILL.md held no nonce and pointed at a
    sibling file produced `Skill "mvprobe"` then `Read .../references/secret.md` and
    returned the nonce, and returned `NO PROBE` with the registration removed and every
    file still on disk.

    `SkillTree` already diffs the bytes against the library. These check what vendoring
    cannot: that the file is here, that it RUNS, and that a person is told it exists.
    """

    SCRIPT = SKILL / "scripts" / "memvara_auth.py"
    COMMANDS = ("authenticate", "login", "logout", "stats")

    def test_the_skill_ships_the_auth_script(self) -> None:
        """Positive, because the failure to catch is a deletion."""
        self.assertTrue(
            self.SCRIPT.is_file(),
            f"{self.SCRIPT.relative_to(ROOT)} is missing; the README tells the user it "
            "is there and the skill tells the model to run it")

    def test_the_script_runs_here_and_names_every_command(self) -> None:
        """Executed rather than read, on the interpreter running this suite.

        A byte diff against the library cannot see a broken script: a library that
        shipped one hands every repo two copies that are equally broken and agree.
        """
        done = subprocess.run(
            [sys.executable, str(self.SCRIPT), "not-a-command"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        for command in self.COMMANDS:
            self.assertIn(command, done.stdout,
                          f"the usage this prints omits {command}")

    def test_the_readme_says_the_script_is_here_and_where(self) -> None:
        """The path is asserted and then RESOLVED, so a README naming a plausible path
        into the wrong directory fails here rather than sending someone nowhere."""
        text = _readme_prose(ROOT)
        quoted = "skills/memvara/scripts/memvara_auth.py"
        self.assertIn(quoted, text, "the README never mentions the auth script")
        self.assertTrue((ROOT / quoted).is_file(),
                        f"the README says {quoted}, and nothing is there")
        # Resolving against ROOT is right for THIS checkout and wrong for the reader, who
        # was told two paragraphs earlier to copy the skill somewhere else. So the README
        # has to say where it lands there too, or the only path it gives is the one that
        # does not exist on the machine following its instructions.
        self.assertIn("~/.config/opencode/skills/memvara/scripts/memvara_auth.py", text,
                      "the README gives the in-repo path only, and a reader who copied "
                      "the skill has no path that resolves on their machine")
        self.assertIn("no `pip install`", text,
                      "the README does not say the script needs nothing installed, "
                      "which is the reason it can rescue a locked-out machine")

    def test_the_readme_says_this_host_ships_no_slash_command(self) -> None:
        """The reduced port, stated in the shipped artifact rather than in a plan.

        Positive -- the sentence must be PRESENT -- so deleting the explanation fails
        exactly as loudly as never writing it.
        """
        text = _readme_prose(ROOT)
        self.assertIn("no `/memvara authenticate` shipped here", text)

    def test_the_readme_no_longer_promises_no_python(self) -> None:
        """It said "there is no local Python process", and now one ships.

        Both directions, and against normalised prose so a rewrapped reintroduction is
        still caught.
        """
        text = _readme_prose(ROOT)
        self.assertNotIn("no local Python process", text,
                         "the README still claims no Python ships, and a Python script "
                         "is sitting in skills/memvara/scripts/")
        # This used to require "Nothing runs in the background", which was true while the
        # only Python here was a command the user typed. It is false now: the plugin runs
        # python3 on every message and again when a session goes idle, without being
        # asked. Requiring the positive claim instead means a README that quietly stops
        # disclosing the background work fails exactly as loudly as one that denies it.
        self.assertNotIn("Nothing runs in the background", text)
        self.assertIn("What runs on your machine", text,
                      "the README has no section saying what this plugin runs locally")
        self.assertIn("~/.memvara/.hooks/", text,
                      "the README does not name where the hooks account for themselves, "
                      "and on this host that log is the only account there is")


class SkillDiscovery(unittest.TestCase):
    """This host loads Claude skill folders, and the README used to say it does not.

    The old text told the reader to paste SKILL.md into AGENTS.md, on the grounds that
    this host ignored those directories. (The sentence itself is not reproduced here: the
    tripwire below cannot tell a quotation from an assertion, it reads only README.md
    today, and a sibling repo's equivalent already scans every markdown file it owns.)
    Measured against opencode 1.18.20 on 2026-08-31 the grounds were false: with the
    skill present only at `~/.claude/skills/memvara`,
    `opencode run` listed `memvara` among its available skills. The instruction was
    costing every reader manual work the host had stopped requiring.

    Guarded positively, and by naming the directories, because "the README does not say
    the wrong thing" passes on a README that has stopped saying anything.
    """

    def test_the_readme_names_where_this_host_looks_for_skills(self) -> None:
        text = _readme_prose(ROOT)
        for where in ("~/.config/opencode/skills/memvara",
                      ".opencode/skills/memvara",
                      "~/.claude/skills/"):
            self.assertIn(where, text,
                          f"the README does not tell the reader about {where}")

    def test_the_readme_does_not_restate_the_claim_that_was_wrong(self) -> None:
        """A tripwire on the exact sentence, paired with the positive test above -- which
        is what keeps this from being a guard a deletion satisfies.

        It caught the commit that added it. The first draft of the README explained the
        correction by QUOTING the old claim, and a tripwire cannot tell a quotation from
        an assertion. This repository has met that before and answered it the same way:
        `CLAUDE.md` states the tool-count rule without quoting a wrong count, deliberately,
        because an illustrative figure in prose is indistinguishable from a claim. So the
        historical note says what changed without reproducing the sentence.
        """
        text = _readme_prose(ROOT)
        self.assertNotIn("does not load Claude skill folders", text)


if __name__ == "__main__":
    unittest.main()
