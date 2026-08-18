"""Detect drift between maintained Markdown examples and bundled script CLIs."""

from __future__ import annotations

import ast
import functools
import re
import shlex
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SCRIPT_REFERENCE = re.compile(r"(?:\./)?scripts/([A-Za-z0-9_.-]+\.py)")
FENCED_BLOCK = re.compile(r"```(?:bash|sh|shell|console|zsh|powershell)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
PYTHON_COMMAND = re.compile(r"(?:^|\s)(?:python(?:3)?|py\s+-3)\s+(?:\./)?scripts/[A-Za-z0-9_.-]+\.py(?:\s|$)")


def maintained_markdown_paths() -> list[Path]:
    """Return current user- and Agent-facing documentation, excluding historical logs."""
    paths = [ROOT / "SKILL.md", ROOT / "README.md"]
    for directory in (ROOT / "docs", ROOT / "references", ROOT / "examples"):
        paths.extend(directory.rglob("*.md"))
    return sorted(set(paths))


def argument_flags(path: Path) -> set[str]:
    """Collect long argparse option names declared in one Python source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    flags: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "add_argument":
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                if argument.value.startswith("--"):
                    flags.add(argument.value)
    return flags


@functools.cache
def help_flags(script_name: str) -> set[str]:
    """Collect long options exposed by the script's real top-level help output."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / script_name), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"{script_name} --help exited {completed.returncode}: {completed.stderr}"
        )
    return set(re.findall(r"(?<![A-Za-z0-9_])--[A-Za-z0-9][A-Za-z0-9_-]*", completed.stdout))


def shell_commands(text: str) -> list[str]:
    """Extract logical Python script commands from shell-like fenced blocks."""
    commands: list[str] = []
    for block in FENCED_BLOCK.findall(text):
        current: list[str] = []
        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not current and not PYTHON_COMMAND.search(line):
                continue
            if line.endswith("\\"):
                current.append(line[:-1].rstrip())
                continue
            current.append(line)
            command = " ".join(part for part in current if part)
            if PYTHON_COMMAND.search(command):
                commands.append(command)
            current = []
        if current:
            command = " ".join(part for part in current if part)
            if PYTHON_COMMAND.search(command):
                commands.append(command)
    return commands


def documented_invocations(path: Path) -> list[tuple[str, set[str]]]:
    """Return script names and wrapper-owned long flags from documented commands."""
    invocations: list[tuple[str, set[str]]] = []
    for command in shell_commands(path.read_text(encoding="utf-8")):
        tokens = shlex.split(command, comments=True, posix=True)
        script_index = next(
            index for index, token in enumerate(tokens) if SCRIPT_REFERENCE.fullmatch(token)
        )
        script_name = SCRIPT_REFERENCE.fullmatch(tokens[script_index]).group(1)  # type: ignore[union-attr]
        flags = {
            token.split("=", 1)[0]
            for token in tokens[script_index + 1 :]
            if token.startswith("--") and token != "--"
        }
        invocations.append((script_name, flags))
    return invocations


class DocumentedCliContractsTest(unittest.TestCase):
    """Ensure maintained examples reference real scripts and real CLI flags."""

    def test_all_documented_script_paths_exist(self) -> None:
        for path in maintained_markdown_paths():
            text = path.read_text(encoding="utf-8")
            for script_name in SCRIPT_REFERENCE.findall(text):
                with self.subTest(document=path.relative_to(ROOT), script=script_name):
                    self.assertTrue((SCRIPTS / script_name).is_file())

    def test_documented_long_flags_are_declared_by_the_target_cli(self) -> None:
        shared_flags = argument_flags(SCRIPTS / "hcloud_common.py")
        for path in maintained_markdown_paths():
            for script_name, documented_flags in documented_invocations(path):
                declared_flags = (
                    argument_flags(SCRIPTS / script_name)
                    | help_flags(script_name)
                    | shared_flags
                    | {"--help"}
                )
                for flag in documented_flags:
                    with self.subTest(document=path.relative_to(ROOT), script=script_name, flag=flag):
                        self.assertIn(flag, declared_flags)


if __name__ == "__main__":
    unittest.main()
