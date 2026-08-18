"""Contract tests for the portable Skill script entrypoints."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POSIX_ENTRYPOINT = ROOT / "bin" / "hcloud-skill"
WINDOWS_ENTRYPOINT = ROOT / "bin" / "hcloud-skill.cmd"


class PortableEntrypointTest(unittest.TestCase):
    """Keep bundled scripts callable from arbitrary host working directories."""

    def make_fixture(self, root: Path) -> tuple[Path, Path]:
        """Create a minimal installed-Skill layout under a path that may contain spaces."""
        bin_dir = root / "bin"
        scripts_dir = root / "scripts"
        bin_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)
        entrypoint = bin_dir / "hcloud-skill"
        shutil.copy2(POSIX_ENTRYPOINT, entrypoint)
        entrypoint.chmod(0o755)
        probe = scripts_dir / "probe.py"
        probe.write_text(
            """#!/usr/bin/env python3
import json
import os
import sys

print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}))
raise SystemExit(7 if "--fail" in sys.argv else 0)
""",
            encoding="utf-8",
        )
        return entrypoint, probe

    def test_entrypoints_are_packaged_and_posix_file_is_executable(self) -> None:
        self.assertTrue(POSIX_ENTRYPOINT.is_file())
        self.assertTrue(os.access(POSIX_ENTRYPOINT, os.X_OK))
        self.assertTrue(WINDOWS_ENTRYPOINT.is_file())

    def test_posix_entrypoint_resolves_skill_root_and_preserves_arguments(self) -> None:
        with tempfile.TemporaryDirectory(prefix="huaweicloud skill ") as temp_dir:
            root = Path(temp_dir) / "installed skill"
            entrypoint, _ = self.make_fixture(root)
            outside_cwd = Path(temp_dir) / "unrelated cwd"
            outside_cwd.mkdir()

            completed = subprocess.run(
                [str(entrypoint), "probe", "--region", "cn-north-4", "value with spaces"],
                cwd=outside_cwd,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["argv"], ["--region", "cn-north-4", "value with spaces"])
            self.assertEqual(Path(payload["cwd"]).resolve(), outside_cwd.resolve())

    def test_py_suffix_and_child_exit_code_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entrypoint, _ = self.make_fixture(Path(temp_dir) / "skill")

            completed = subprocess.run(
                [str(entrypoint), "probe.py", "--fail"],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 7)
            self.assertEqual(json.loads(completed.stdout)["argv"], ["--fail"])

    def test_invalid_or_missing_script_names_fail_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            entrypoint, _ = self.make_fixture(Path(temp_dir) / "skill")

            for script_name in ("../probe", "nested/probe", "/tmp/probe", "missing"):
                with self.subTest(script_name=script_name):
                    completed = subprocess.run(
                        [str(entrypoint), script_name],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertIn("hcloud-skill:", completed.stderr)

    def test_windows_shim_forwards_all_arguments_to_the_shared_launcher(self) -> None:
        source = WINDOWS_ENTRYPOINT.read_text(encoding="utf-8")

        self.assertIn("%~dp0hcloud-skill", source)
        self.assertIn("%*", source)
        self.assertIn("!ERRORLEVEL!", source)
        self.assertIn("py -3", source)
        self.assertIn("python", source)
        for business_marker in ("ECS", "BSS", "inventory", "billing"):
            self.assertNotIn(business_marker, source)


if __name__ == "__main__":
    unittest.main()
