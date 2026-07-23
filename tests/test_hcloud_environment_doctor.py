"""Tests for check-only Huawei Cloud environment doctor."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SCRIPT = SCRIPTS / "hcloud_environment_doctor.py"
SPEC = importlib.util.spec_from_file_location("hcloud_environment_doctor", SCRIPT)
assert SPEC and SPEC.loader
hcloud_environment_doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_environment_doctor)


def item(name: str, status: str, required: bool = False) -> dict:
    """Build a minimal check item for report aggregation tests."""
    return {
        "name": name,
        "status": status,
        "required": required,
        "summary": status,
        "details": {},
        "next_actions": [],
        "install_commands": [],
    }


class HcloudEnvironmentDoctorTest(unittest.TestCase):
    """Validate local environment doctor contracts without touching the machine."""

    def test_build_report_is_check_only_and_tracks_required_blockers(self) -> None:
        args = SimpleNamespace(need=["terraform"], workdir=ROOT)
        with mock.patch.object(hcloud_environment_doctor, "inspect_python", return_value=item("python", "ok", True)), \
            mock.patch.object(hcloud_environment_doctor, "inspect_hcloud", return_value=item("hcloud", "ok", True)), \
            mock.patch.object(hcloud_environment_doctor, "inspect_auth", return_value=item("cloud_credentials", "warning")), \
            mock.patch.object(hcloud_environment_doctor, "inspect_sdk", return_value=item("sdk", "skipped")), \
            mock.patch.object(hcloud_environment_doctor, "inspect_terraform", return_value=item("terraform", "blocker", True)), \
            mock.patch.object(hcloud_environment_doctor, "inspect_obsutil", return_value=item("obsutil", "skipped")), \
            mock.patch.object(hcloud_environment_doctor, "inspect_maas", return_value=item("maas", "skipped")), \
            mock.patch.object(hcloud_environment_doctor, "inspect_proxy", return_value=item("proxy", "skipped")):
            result = hcloud_environment_doctor.build_report(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "check_only")
        self.assertTrue(result["no_changes_made"])
        self.assertFalse(result["summary"]["ready"])
        self.assertEqual(result["summary"]["required_blockers"], ["terraform"])
        self.assertIn("does not install packages", result["execution_boundary"])

    def test_auth_inspection_reports_presence_without_secret_values(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HW_ACCESS_KEY": "ak-value-secret",
                "HW_SECRET_KEY": "sk-value-secret",
                "HW_REGION_NAME": "cn-north-4",
            },
            clear=True,
        ):
            result = hcloud_environment_doctor.inspect_auth(set())

        payload = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["details"]["auth_modes"]["hw_env_complete"])
        self.assertNotIn("ak-value-secret", payload)
        self.assertNotIn("sk-value-secret", payload)

    def test_auth_inspection_accepts_huawei_env_aliases(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HUAWEI_ACCESS_KEY": "ak-value-secret",
                "HUAWEI_SECRET_KEY": "sk-value-secret",
                "HUAWEI_REGION": "cn-north-4",
                "HUAWEI_PROJECT_ID": "project-value",
                "HUAWEI_DOMAIN_ID": "domain-value",
            },
            clear=True,
        ):
            result = hcloud_environment_doctor.inspect_auth({"live"})

        payload = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["details"]["auth_modes"]["huawei_env_complete"])
        self.assertTrue(result["details"]["environment"]["HUAWEI_PROJECT_ID"]["set"])
        self.assertNotIn("ak-value-secret", payload)
        self.assertNotIn("sk-value-secret", payload)
        self.assertNotIn("project-value", payload)

    def test_live_need_makes_missing_credentials_a_blocker(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_environment_doctor.inspect_auth({"live"})

        self.assertEqual(result["status"], "blocker")
        self.assertTrue(result["required"])
        self.assertIn("HW_ACCESS_KEY", result["details"]["environment"])

    def test_obsutil_config_status_does_not_expose_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / ".obsutilconfig"
            path.write_text(
                "ak=ak-value-secret\nsk=sk-value-secret\nsecuritytoken=token-value-secret\n",
                encoding="utf-8",
            )
            result = hcloud_environment_doctor.obsutil_config_status(path)

        payload = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["has_ak"])
        self.assertTrue(result["has_sk"])
        self.assertTrue(result["has_security_token"])
        self.assertNotIn("ak-value-secret", payload)
        self.assertNotIn("sk-value-secret", payload)
        self.assertNotIn("token-value-secret", payload)

    def test_maas_need_controls_missing_api_key_severity(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            optional = hcloud_environment_doctor.inspect_maas(set())
            required = hcloud_environment_doctor.inspect_maas({"maas"})

        self.assertEqual(optional["status"], "skipped")
        self.assertEqual(required["status"], "blocker")

    def test_windows_guidance_uses_powershell_and_windows_executables(self) -> None:
        commands, notes = hcloud_environment_doctor.hcloud_install_guidance("Windows")

        self.assertTrue(any(command.startswith("Invoke-WebRequest") for command in commands))
        self.assertTrue(any("Expand-Archive" in command for command in commands))
        self.assertTrue(any("hcloud version" in command for command in commands))
        self.assertTrue(any("hcloud.exe" in note for note in notes))
        self.assertEqual(hcloud_environment_doctor.command_python("Windows"), "python")
        self.assertEqual(hcloud_environment_doctor.obsutil_check_commands("Windows"), ["obsutil.exe version"])
        self.assertIn(
            "python scripts/hcloud_terraform_context_inspect.py --pretty",
            hcloud_environment_doctor.terraform_check_commands("Windows"),
        )

    def test_posix_guidance_preserves_python3_and_shell_install_path(self) -> None:
        commands, notes = hcloud_environment_doctor.hcloud_install_guidance("Linux")

        self.assertEqual(notes, [])
        self.assertTrue(any(command.startswith("curl ") for command in commands))
        self.assertEqual(hcloud_environment_doctor.command_python("Linux"), "python3")
        self.assertEqual(hcloud_environment_doctor.obsutil_check_commands("Linux"), ["obsutil version"])


if __name__ == "__main__":
    unittest.main()
