"""Tests for the code-enforced runtime plan-only boundary."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_runtime_admission  # noqa: E402
import hcloud_safe_exec  # noqa: E402
import maas_common  # noqa: E402


class RuntimeAdmissionTests(unittest.TestCase):
    """Prove that frozen paths reject before a subprocess or HTTP request."""

    def test_block_result_is_uniform_and_carries_plan_only_authority(self) -> None:
        result = hcloud_runtime_admission.block_result(
            "guarded_hcloud_change_submit",
            "guarded submit",
            reason="test boundary",
            next_action="stay in plan mode",
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")
        self.assertEqual(result["execution_authority"]["mode"], "plan_only")
        self.assertEqual(result["execution_authority"]["submission_authority"], "not_implemented")

    def test_generic_non_read_and_unresolved_operations_are_not_admitted(self) -> None:
        args = SimpleNamespace(command_part=[], service="ECS", operation="CreateServers")

        self.assertEqual(
            hcloud_safe_exec.generic_dispatch_block_reason(args, {"success": True, "read_only": False}),
            "The operation is mutating or its effect cannot be proven read-only.",
        )
        self.assertEqual(
            hcloud_safe_exec.generic_dispatch_block_reason(args, {"success": False}),
            "The operation has no successful catalog-backed read-only resolution.",
        )
        self.assertIsNone(hcloud_safe_exec.generic_dispatch_block_reason(args, {"success": True, "read_only": True}))

    def test_generic_command_part_mutation_never_starts_hcloud(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            marker = root / "hcloud-called"
            fake_hcloud = root / "hcloud"
            fake_hcloud.write_text("#!/bin/sh\ntouch \"$HCLOUD_MARKER\"\n", encoding="utf-8")
            fake_hcloud.chmod(fake_hcloud.stat().st_mode | stat.S_IXUSR)
            environment = dict(os.environ)
            environment["PATH"] = f"{root}{os.pathsep}{environment.get('PATH', '')}"
            environment["HCLOUD_MARKER"] = str(marker)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "hcloud_safe_exec.py"),
                    "--command-part=configure",
                    "--command-part=set",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertFalse(marker.exists())
        result = json.loads(completed.stdout)
        self.assertEqual(result["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")
        self.assertEqual(result["execution_authority"]["mode"], "plan_only")

    def test_maas_shared_transport_rejects_post_before_opening_network(self) -> None:
        with self.assertRaisesRegex(maas_common.MaasAPIError, "plan-only"):
            maas_common.request_json("POST", "/v1/images/generations", api_key="not-used", body={})


if __name__ == "__main__":
    unittest.main()
