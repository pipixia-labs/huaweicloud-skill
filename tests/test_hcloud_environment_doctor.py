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
        args = SimpleNamespace(need=["terraform"], sdk_service=[], workdir=ROOT)
        with (
            mock.patch.object(hcloud_environment_doctor, "inspect_python", return_value=item("python", "ok", True)),
            mock.patch.object(hcloud_environment_doctor, "inspect_hcloud", return_value=item("hcloud", "ok", True)),
            mock.patch.object(hcloud_environment_doctor, "inspect_auth", return_value=item("cloud_credentials", "warning")),
            mock.patch.object(hcloud_environment_doctor, "inspect_sdk", return_value=item("sdk", "skipped")),
            mock.patch.object(hcloud_environment_doctor, "inspect_terraform", return_value=item("terraform", "blocker", True)),
            mock.patch.object(hcloud_environment_doctor, "inspect_obsutil", return_value=item("obsutil", "skipped")),
            mock.patch.object(hcloud_environment_doctor, "inspect_maas", return_value=item("maas", "skipped")),
            mock.patch.object(hcloud_environment_doctor, "inspect_proxy", return_value=item("proxy", "skipped")),
            mock.patch.object(hcloud_environment_doctor, "inspect_network", return_value=item("network", "skipped")),
            mock.patch.object(hcloud_environment_doctor, "inspect_artifacts", return_value=item("artifacts", "ok")),
        ):
            result = hcloud_environment_doctor.build_report(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "check_only")
        self.assertTrue(result["no_changes_made"])
        self.assertEqual(result["scan_scope"], "task_scoped")
        self.assertFalse(result["summary"]["ready"])
        self.assertEqual(result["summary"]["required_blockers"], ["terraform"])
        self.assertEqual(result["summary"]["required_unready"], ["terraform"])
        self.assertEqual(result["dependency_contract"], "huaweicloud_skill_runtime_dependencies_v1")
        self.assertEqual(result["recovery_plan"]["contract"], "huaweicloud_skill_recovery_plan_v1")
        self.assertFalse(result["recovery_plan"]["ready"])
        self.assertEqual(result["recovery_plan"]["step_count"], 1)
        self.assertEqual(result["recovery_plan"]["steps"][0]["dependency"], "terraform")
        self.assertFalse(result["recovery_plan"]["execution_performed"])
        self.assertIn("does not install packages", result["execution_boundary"])
        self.assertTrue(all(not Path(reference).is_absolute() and (ROOT / reference).exists() for reference in result["source_references"]))

    def test_task_scoped_report_does_not_probe_unselected_dependencies(self) -> None:
        args = SimpleNamespace(need=["sdk"], sdk_service=["ECS"], workdir=ROOT)
        sdk_result = item("huaweicloud_python_sdk", "ok", True)
        with (
            mock.patch.object(hcloud_environment_doctor, "inspect_python", return_value=item("python", "ok", True)),
            mock.patch.object(hcloud_environment_doctor, "inspect_hcloud") as inspect_hcloud,
            mock.patch.object(hcloud_environment_doctor, "inspect_auth") as inspect_auth,
            mock.patch.object(hcloud_environment_doctor, "inspect_sdk", return_value=sdk_result) as inspect_sdk,
            mock.patch.object(hcloud_environment_doctor, "inspect_terraform") as inspect_terraform,
            mock.patch.object(hcloud_environment_doctor, "inspect_obsutil") as inspect_obsutil,
            mock.patch.object(hcloud_environment_doctor, "inspect_maas") as inspect_maas,
            mock.patch.object(hcloud_environment_doctor, "inspect_proxy") as inspect_proxy,
        ):
            result = hcloud_environment_doctor.build_report(args)

        inspect_sdk.assert_called_once_with({"sdk"}, ["ECS"])
        for probe in (
            inspect_hcloud,
            inspect_auth,
            inspect_terraform,
            inspect_obsutil,
            inspect_maas,
            inspect_proxy,
        ):
            probe.assert_not_called()
        self.assertTrue(result["summary"]["ready"])
        self.assertEqual(result["scan_scope"], "task_scoped")

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

    def test_auth_inspection_accepts_every_supported_paired_alias(self) -> None:
        import credential_aliases

        for family in credential_aliases.CLOUD_CREDENTIAL_FAMILIES:
            with (
                self.subTest(family=family.name),
                mock.patch.dict(
                    os.environ,
                    {
                        family.access_key: "access-secret-value",
                        family.secret_key: "secret-secret-value",
                        "HUAWEICLOUD_REGION": "cn-north-4",
                    },
                    clear=True,
                ),
            ):
                result = hcloud_environment_doctor.inspect_auth({"live"})

            payload = json.dumps(result, ensure_ascii=False)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                result["details"]["credential_observation"]["selected_family"],
                family.name,
            )
            self.assertEqual(
                result["details"]["credential_observation"]["visibility"],
                "current_process_only",
            )
            self.assertNotIn("access-secret-value", payload)
            self.assertNotIn("secret-secret-value", payload)

    def test_missing_current_process_credentials_do_not_claim_user_configuration_missing(
        self,
    ) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_environment_doctor.inspect_auth(set())

        self.assertEqual(result["status"], "warning")
        self.assertEqual(
            result["details"]["credential_observation"]["configuration_status"],
            "unknown",
        )
        self.assertIn("current process", result["summary"].lower())
        self.assertNotIn("not configured", result["summary"].lower())

    def test_live_need_makes_missing_credentials_a_blocker(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_environment_doctor.inspect_auth({"live"})

        self.assertEqual(result["status"], "blocker")
        self.assertTrue(result["required"])
        self.assertIn("HW_ACCESS_KEY", result["details"]["environment"])

    def test_hcloud_is_required_only_when_selected(self) -> None:
        summary = {
            "hcloud": {"found": False},
            "config": {"exists": False},
            "meta_repo": {"exists": False},
        }
        with mock.patch.object(hcloud_environment_doctor.hcloud_context_inspect, "build_summary", return_value=summary) as build:
            optional = hcloud_environment_doctor.inspect_hcloud(set())
            required = hcloud_environment_doctor.inspect_hcloud({"hcloud"})

        self.assertEqual(optional["status"], "skipped")
        self.assertFalse(optional["required"])
        self.assertEqual(required["status"], "blocker")
        self.assertTrue(required["required"])
        self.assertTrue(all(call.kwargs["include_sdk_runtime"] is False for call in build.call_args_list))

    def test_hcloud_recovery_reports_privacy_profile_region_and_metadata_actions(self) -> None:
        summary = {
            "hcloud": {"found": True, "version": "7.2.12"},
            "config": {
                "exists": True,
                "agree_privacy": False,
                "current_profile_name": None,
                "current_profile": None,
            },
            "meta_repo": {
                "exists": True,
                "services_file_exists": False,
                "cached_service_count": 0,
                "template_services": [],
                "template_file_count": 0,
            },
        }
        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect,
            "build_summary",
            return_value=summary,
        ):
            result = hcloud_environment_doctor.inspect_hcloud({"hcloud"})

        self.assertEqual(result["status"], "warning")
        self.assertFalse(result["details"]["live_call_context_ready"])
        self.assertFalse(result["details"]["privacy_statement_accepted"])
        self.assertFalse(result["details"]["region_ready"])
        self.assertFalse(result["details"]["metadata_cache_ready"])
        self.assertIn(
            "hcloud configure set --cli-agree-privacy-statement=true",
            result["recovery_commands"],
        )
        self.assertIn(
            "python3 scripts/hcloud_project_resolve.py --region <region> --pretty",
            result["recovery_commands"],
        )
        self.assertTrue(any("meta" in command.lower() for command in result["recovery_commands"]))

    def test_hcloud_metadata_and_project_recovery_can_remain_advisory(self) -> None:
        summary = {
            "hcloud": {"found": True, "version": "7.2.12"},
            "config": {
                "exists": True,
                "agree_privacy": True,
                "current_profile_name": "test",
                "current_profile": {
                    "name": "test",
                    "mode": "AKSK",
                    "region": "cn-north-4",
                    "project_id": "",
                    "has_access_key": True,
                },
            },
            "meta_repo": {
                "exists": True,
                "services_file_exists": False,
                "cached_service_count": 0,
                "template_services": [],
                "template_file_count": 0,
            },
        }
        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect,
            "build_summary",
            return_value=summary,
        ):
            check = hcloud_environment_doctor.inspect_hcloud({"hcloud"})
        recovery = hcloud_environment_doctor.build_recovery_plan([check])

        self.assertEqual(check["status"], "ok")
        self.assertTrue(check["details"]["live_call_context_ready"])
        self.assertFalse(check["details"]["project_id_configured"])
        self.assertTrue(recovery["ready"])
        self.assertEqual(recovery["step_count"], 1)
        self.assertFalse(recovery["steps"][0]["blocking"])
        self.assertIn(
            "python3 scripts/hcloud_project_resolve.py --region <region> --pretty",
            recovery["steps"][0]["commands"],
        )

    def test_recovery_plan_is_derived_from_checks_without_executing_actions(self) -> None:
        checks = [
            item("python", "ok", True),
            {
                **item("hcloud", "warning", True),
                "next_actions": ["Configure hcloud."],
                "install_commands": [],
                "recovery_commands": ["hcloud configure list"],
            },
            item("network", "unknown", True),
        ]

        result = hcloud_environment_doctor.build_recovery_plan(checks)

        self.assertFalse(result["ready"])
        self.assertEqual(result["step_count"], 2)
        self.assertEqual(
            [step["dependency"] for step in result["steps"]],
            ["hcloud", "network"],
        )
        self.assertEqual(result["steps"][0]["commands"], ["hcloud configure list"])
        self.assertFalse(result["execution_performed"])
        self.assertTrue(result["host_neutral"])

    def test_sdk_service_requirements_are_scoped_to_requested_packages(self) -> None:
        def package_path(package_name):
            return Path("/sdk/ecs") if package_name == "huaweicloudsdkecs" else None

        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect.hcloud_sdk_catalog,
            "installed_package_path",
            side_effect=package_path,
        ):
            result = hcloud_environment_doctor.inspect_sdk({"sdk"}, ["ECS", "VPC"])

        self.assertEqual(result["status"], "blocker")
        self.assertEqual(result["details"]["installed_services"], ["ECS"])
        self.assertEqual(result["details"]["missing_services"], ["VPC"])
        self.assertIn("huaweicloudsdkvpc", result["install_commands"][0])
        self.assertNotIn("huaweicloudsdkecs", result["install_commands"][0])

    def test_required_sdk_without_service_scope_stays_unknown(self) -> None:
        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect,
            "inspect_sdk_runtime",
        ) as inspect_runtime:
            result = hcloud_environment_doctor.inspect_sdk({"sdk"})

        inspect_runtime.assert_not_called()
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["required"])
        self.assertEqual(result["details"]["requested_services"], [])
        self.assertEqual(result["details"]["package_scan"], "skipped_without_task_service_scope")
        self.assertEqual(result["install_commands"], [])
        self.assertIn("--sdk-service", result["next_actions"][0])

    def test_optional_sdk_without_service_scope_skips_package_scan(self) -> None:
        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect,
            "inspect_sdk_runtime",
        ) as inspect_runtime:
            result = hcloud_environment_doctor.inspect_sdk(set())

        inspect_runtime.assert_not_called()
        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["required"])

    def test_full_overview_preserves_broad_sdk_inventory(self) -> None:
        runtime = {"installed_package_count": 2, "installed_services_sample": ["ECS", "VPC"]}
        with mock.patch.object(
            hcloud_environment_doctor.hcloud_context_inspect,
            "inspect_sdk_runtime",
            return_value=runtime,
        ) as inspect_runtime:
            result = hcloud_environment_doctor.inspect_sdk(set(), broad_overview=True)

        inspect_runtime.assert_called_once()
        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["required"])
        self.assertEqual(result["details"]["package_scan"], "full_overview")
        self.assertEqual(result["details"]["installed_services"], ["ECS", "VPC"])

    def test_invalid_sdk_service_does_not_generate_a_broad_package_name(self) -> None:
        result = hcloud_environment_doctor.inspect_sdk({"sdk"}, ["!!!"])

        self.assertEqual(result["status"], "blocker")
        self.assertEqual(result["details"]["invalid_services"], ["!!!"])
        self.assertEqual(result["install_commands"], [])

    def test_required_unknown_dependency_prevents_ready_summary(self) -> None:
        summary = hcloud_environment_doctor.summarize(
            [
                item("python", "ok", True),
                item("network", "unknown", True),
            ]
        )

        self.assertFalse(summary["ready"])
        self.assertEqual(summary["required_unready"], ["network"])
        self.assertEqual(summary["required_blockers"], [])

    def test_artifact_directory_requirement_is_task_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            ready = hcloud_environment_doctor.inspect_artifacts({"artifacts"}, Path(tmp_dir))

        self.assertEqual(ready["status"], "ok")
        self.assertTrue(ready["required"])

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

    def test_obs_need_accepts_hcloud_but_preserves_obsutil_result_name(self) -> None:
        def which(command):
            return "/usr/bin/hcloud" if command == "hcloud" else None

        empty_config = {"exists": False, "has_ak": False, "has_sk": False}
        with (
            mock.patch.object(hcloud_environment_doctor.shutil, "which", side_effect=which),
            mock.patch.object(
                hcloud_environment_doctor,
                "obsutil_config_status",
                return_value=empty_config,
            ),
        ):
            general_obs = hcloud_environment_doctor.inspect_obsutil({"obs"})
            standalone = hcloud_environment_doctor.inspect_obsutil({"obsutil"})
            overview = hcloud_environment_doctor.inspect_obsutil(set())

        self.assertEqual(general_obs["name"], "obsutil")
        self.assertEqual(general_obs["status"], "ok")
        self.assertEqual(general_obs["details"]["requirement"], "obs_tooling_any")
        self.assertEqual(standalone["status"], "blocker")
        self.assertEqual(overview["status"], "skipped")

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
        self.assertEqual(
            hcloud_environment_doctor.sdk_install_commands(["RDS"], "Linux"),
            ["python3 -m pip install huaweicloudsdkrds"],
        )


if __name__ == "__main__":
    unittest.main()
