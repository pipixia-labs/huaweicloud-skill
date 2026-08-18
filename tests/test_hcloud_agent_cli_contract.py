"""Contracts for the stable Agent-facing CLI denominator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "references" / "script-audience-manifest.json"
LAUNCHER = ROOT / "bin" / ("hcloud-skill.cmd" if sys.platform == "win32" else "hcloud-skill")
AGENT_GROUPS = ("default_runtime", "guarded_change", "runtime_supplement")


def load_manifest() -> dict:
    """Return the machine-readable script audience manifest."""

    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def agent_entrypoints(manifest: dict) -> list[str]:
    """Return stable, de-duplicated Agent-facing scripts in declaration order."""

    scripts: list[str] = []
    groups = {group["id"]: group for group in manifest["script_groups"]}
    for group_id in AGENT_GROUPS:
        for script in groups[group_id]["scripts"]:
            if script not in scripts:
                scripts.append(script)
    return scripts


class AgentCliContractTest(unittest.TestCase):
    """Keep the actual Agent CLI surface aligned with its minimum contract."""

    def test_manifest_declares_the_real_agent_entrypoint_denominator(self) -> None:
        manifest = load_manifest()
        contract = manifest["agent_cli_contract"]
        scripts = agent_entrypoints(manifest)

        self.assertEqual(contract["id"], "huaweicloud_skill_agent_cli_v1")
        self.assertEqual(contract["covered_script_groups"], list(AGENT_GROUPS))
        self.assertEqual(contract["stable_launchers"], ["bin/hcloud-skill", "bin/hcloud-skill.cmd"])
        self.assertEqual(contract["successful_result"]["required_fields"], ["success"])
        self.assertEqual(contract["successful_result"]["default_stdout"], "final_json_object")
        self.assertEqual(len(scripts), 55)
        self.assertEqual(len(scripts), len(set(scripts)))
        for script in scripts:
            self.assertTrue((ROOT / script).is_file(), script)

        exceptions = {
            item["script"]: item["mode"]
            for item in contract["explicit_output_exceptions"]
        }
        self.assertEqual(
            exceptions,
            {
                "scripts/hcloud_dependency_evidence.py": "explicit_markdown",
                "scripts/hcloud_operation_behavior.py": "explicit_markdown",
                "scripts/hcloud_operation_resolver.py": "explicit_shell_command",
                "scripts/maas_text_to_image.py": "progress_then_final_json",
            },
        )

        public_contract = manifest["public_result_contract"]
        self.assertEqual(public_contract["extends"], contract["id"])
        self.assertEqual(
            public_contract["scope"],
            "large_or_selected_structured_results",
        )
        self.assertLessEqual(
            set(manifest["public_script_contracts"]),
            set(scripts),
        )
        contract_text = (ROOT / "references" / "public-script-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("55 个真实 Agent 入口", contract_text)
        self.assertIn("不是所有小 planner/inspector", contract_text)

    def test_every_agent_entrypoint_exposes_help_through_the_stable_launcher(self) -> None:
        manifest = load_manifest()
        with tempfile.TemporaryDirectory() as cwd:
            for script in agent_entrypoints(manifest):
                with self.subTest(script=script):
                    completed = subprocess.run(
                        [str(LAUNCHER), Path(script).stem, "--help"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=8,
                        cwd=cwd,
                    )
                    self.assertEqual(
                        completed.returncode,
                        0,
                        f"{script}: {completed.stderr or completed.stdout}",
                    )

    def test_legacy_bounded_inspectors_emit_the_success_denominator(self) -> None:
        commands = (
            [sys.executable, str(ROOT / "scripts" / "hcloud_context_inspect.py")],
            [
                sys.executable,
                str(ROOT / "scripts" / "hcloud_meta_lookup.py"),
                "--list-services",
                "--limit",
                "1",
            ],
        )
        for command in commands:
            with self.subTest(script=Path(command[1]).name):
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(completed.stdout)
                self.assertIs(result["success"], True)


if __name__ == "__main__":
    unittest.main()
