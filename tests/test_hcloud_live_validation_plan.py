"""Tests for high-frequency service live validation planning."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load a script module from a path for local unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_live_validation_plan = load_module(
    "hcloud_live_validation_plan",
    SCRIPTS / "hcloud_live_validation_plan.py",
)
hcloud_live_regression_plan = load_module(
    "hcloud_live_regression_plan",
    SCRIPTS / "hcloud_live_regression_plan.py",
)


class LiveValidationPlanTest(unittest.TestCase):
    """Validate live validation profiles and planner output."""

    def test_profiles_cover_high_frequency_services(self) -> None:
        profiles = json.loads((ROOT / "references" / "live-validation-profiles.json").read_text(encoding="utf-8"))

        target_services = {"ECS", "VPC", "EIP", "OBS", "ELB", "RDS"}

        self.assertEqual(set(profiles["services"]), target_services)
        for service in target_services:
            with self.subTest(service=service):
                profile = profiles["services"][service]
                self.assertEqual(profile["current_status"], "curated")
                self.assertEqual(profile["target_tier"], "live_validated_curated")
                self.assertIn("required_inputs", profile)
                self.assertIn("hcloud_readback_operations", profile)
                self.assertIn("acceptance_evidence", profile)
                self.assertIn("probe_candidates", profile)
                self.assertIn("promotion_gates", profile)

    def test_default_plan_reports_missing_inputs_without_live_execution(self) -> None:
        args = hcloud_live_validation_plan.parse_args([])

        result = hcloud_live_validation_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["target_services"], ["ECS", "VPC", "EIP", "OBS", "ELB", "RDS"])
        self.assertEqual(result["execution_boundary"], "planner_only_no_live_hcloud_no_probe_no_mutation")
        ecs = result["services"][0]
        self.assertEqual(ecs["service"], "ECS")
        self.assertIn("region", ecs["missing_required_inputs"])
        self.assertIn("server_id", ecs["missing_required_inputs"])
        self.assertTrue(ecs["hcloud_readback_plan"]["checks"])

    def test_eip_plan_composes_readiness_and_acceptance_evidence(self) -> None:
        args = hcloud_live_validation_plan.parse_args(
            [
                "--service",
                "EIP",
                "--region",
                "cn-north-4",
                "--project-id",
                "project-1",
                "--param",
                "publicip_id=eip-1",
                "--param",
                "probe_url=https://example.com/health",
            ]
        )

        result = hcloud_live_validation_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "EIP")
        self.assertEqual(service["missing_required_inputs"], [])
        operations = {check["operation"] for check in service["hcloud_readback_plan"]["checks"]}
        self.assertIn("ListPublicips", operations)
        self.assertIn("ShowPublicip", operations)
        publicip = next(item for item in service["acceptance_evidence"] if item["id"] == "publicip_readback")
        protocol = next(item for item in service["acceptance_evidence"] if item["id"] == "public_protocol_probe")
        self.assertEqual(publicip["status"], "ready_to_collect")
        self.assertEqual(protocol["status"], "ready_to_collect")
        self.assertIn("public_entry_verified", service["blocked_gate_ids"])

    def test_param_region_flows_to_readback_commands(self) -> None:
        args = hcloud_live_validation_plan.parse_args(
            [
                "--service",
                "EIP",
                "--param",
                "region=cn-north-4",
                "--param",
                "publicip_id=eip-1",
            ]
        )

        result = hcloud_live_validation_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["region"], "cn-north-4")
        command_tokens = [
            token
            for check in result["services"][0]["hcloud_readback_plan"]["checks"]
            for token in (check["command"] or [])
        ]
        self.assertIn("--arg=--cli-region=cn-north-4", command_tokens)

    def test_obs_plan_uses_obs_adapter_and_does_not_leak_secret_values(self) -> None:
        secret_value = "SHOULD_NOT_APPEAR_IN_OUTPUT"
        args = hcloud_live_validation_plan.parse_args(
            [
                "--service",
                "OBS",
                "--region",
                "cn-north-4",
                "--param",
                "bucket=example-bucket",
                "--param",
                f"secret_access_key={secret_value}",
            ]
        )

        result = hcloud_live_validation_plan.build_plan(args)
        serialized = json.dumps(result, ensure_ascii=False)

        self.assertTrue(result["success"], result)
        self.assertNotIn(secret_value, serialized)
        self.assertNotIn("secret_access_key", serialized)
        self.assertEqual(result["ignored_sensitive_param_count"], 1)
        service = result["services"][0]
        runners = {check["runner"] for check in service["hcloud_readback_plan"]["checks"]}
        self.assertEqual(runners, {"scripts/hcloud_obs_readonly.py"})
        operations = {check["operation"] for check in service["hcloud_readback_plan"]["checks"]}
        self.assertIn("StatBucket", operations)
        self.assertIn("GetBucketPolicy", operations)

    def test_live_regression_matrix_includes_core_service_validation(self) -> None:
        args = hcloud_live_regression_plan.parse_args(["--scenario", "core-service-validation"])

        result = hcloud_live_regression_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["scenario_count"], 1)
        scenario = result["scenarios"][0]
        self.assertEqual(scenario["id"], "core-service-validation")
        self.assertTrue(
            any("hcloud_live_validation_plan.py" in tool for tool in scenario["tools"]),
            scenario,
        )


if __name__ == "__main__":
    unittest.main()
