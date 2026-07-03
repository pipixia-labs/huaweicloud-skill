"""Tests for final completion-gap tools."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load a script module for isolated unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_acceptance_probe_run = load_module("hcloud_acceptance_probe_run", SCRIPTS / "hcloud_acceptance_probe_run.py")
hcloud_acceptance_closure = load_module("hcloud_acceptance_closure", SCRIPTS / "hcloud_acceptance_closure.py")
hcloud_live_regression_plan = load_module("hcloud_live_regression_plan", SCRIPTS / "hcloud_live_regression_plan.py")
hcloud_terraform_operations_plan = load_module(
    "hcloud_terraform_operations_plan",
    SCRIPTS / "hcloud_terraform_operations_plan.py",
)


class CompletionGapToolsTest(unittest.TestCase):
    """Validate live probe, regression, and Terraform operations planners."""

    def probe_plan(self) -> dict:
        """Return a minimal acceptance probe plan."""
        return {
            "services": [
                {
                    "service": "EIP",
                    "probes": [
                        {
                            "id": "public_protocol_probe",
                            "status": "planned",
                            "probe_templates": ["curl -fsS --max-time 10 <probe_url-or-public-ip-url>"],
                        }
                    ],
                }
            ]
        }

    def lifecycle_plan(self) -> dict:
        """Return a minimal lifecycle plan with acceptance evidence."""
        return {
            "services": [
                {
                    "service": "EIP",
                    "stages": [
                        {
                            "id": "post_change_verification",
                            "acceptance_evidence_plan": {
                                "service": "EIP",
                                "completion_rule": "All required acceptance evidence must pass.",
                                "evidence_items": [
                                    {
                                        "id": "public_protocol_probe",
                                        "layer": "protocol_or_network",
                                        "status": "ready",
                                        "description": "Probe the public user path.",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ]
        }

    def terraform_args(self, **overrides):
        """Return default Terraform operations args."""
        values = {
            "operation": "full",
            "workdir": ".",
            "import_target": ["huaweicloud_compute_instance.app=server-1"],
            "readback": ["ECS:ShowServer:server_id=server-1"],
            "backend_type": "obs",
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "execute_drift": False,
            "execute_import": False,
            "allow_state_change": False,
            "confirm_token": None,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_probe_runner_reports_missing_placeholder_without_execution(self) -> None:
        result = hcloud_acceptance_probe_run.build_execution(self.probe_plan(), {}, execute=False, timeout=1)

        self.assertTrue(result["success"])
        evidence = result["evidence"]["public_protocol_probe"]
        self.assertEqual(evidence["status"], "missing")
        self.assertIn("placeholder", evidence["summary"])

    def test_probe_runner_executes_supported_http_probe_with_bound_value(self) -> None:
        values = hcloud_acceptance_probe_run.parse_values(["probe_url=http://example.test"])
        fake = hcloud_acceptance_probe_run.status_result(
            hcloud_acceptance_probe_run.PASSED,
            "HTTP probe returned 200.",
            source="http",
        )

        with mock.patch.object(hcloud_acceptance_probe_run, "http_probe", return_value=fake) as http_probe:
            result = hcloud_acceptance_probe_run.build_execution(self.probe_plan(), values, execute=True, timeout=1)

        http_probe.assert_called_once_with("http://example.test", method="GET", timeout=1)
        evidence = result["evidence"]["public_protocol_probe"]
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(result["services"][0]["status_counts"]["passed"], 1)

    def test_acceptance_closure_chain_prepares_and_evaluates_missing_without_execution(self) -> None:
        values = hcloud_acceptance_closure.probe_run.parse_values(["probe_url=http://example.test"])

        result = hcloud_acceptance_closure.build_chain(self.lifecycle_plan(), values, execute=False, timeout=1)

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "chain")
        self.assertEqual(result["overall_status"], "missing")
        self.assertEqual(result["probe_plan"]["services"][0]["planned_probe_count"], 1)
        self.assertEqual(result["evidence_result"]["services"][0]["summary"]["missing"], 1)

    def test_acceptance_closure_chain_can_execute_supported_probe_and_evaluate_passed(self) -> None:
        values = hcloud_acceptance_closure.probe_run.parse_values(["probe_url=http://example.test"])
        fake = hcloud_acceptance_closure.probe_run.status_result(
            hcloud_acceptance_closure.probe_run.PASSED,
            "HTTP probe returned 200.",
            source="http",
        )

        with mock.patch.object(hcloud_acceptance_closure.probe_run, "http_probe", return_value=fake) as http_probe:
            result = hcloud_acceptance_closure.build_chain(self.lifecycle_plan(), values, execute=True, timeout=1)

        http_probe.assert_called_once_with("http://example.test", method="GET", timeout=1)
        self.assertEqual(result["overall_status"], "passed")
        self.assertEqual(result["evidence_result"]["services"][0]["summary"]["passed"], 1)

    def test_live_regression_plan_lists_user_required_inputs(self) -> None:
        args = SimpleNamespace(scenario=["terraform-operations", "cce-assessment"], region="cn-north-4", profile="dev")

        result = hcloud_live_regression_plan.build_plan(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["scenario_count"], 2)
        self.assertEqual([item["id"] for item in result["scenarios"]], ["terraform-operations", "cce-assessment"])
        self.assertTrue(any("AK/SK" in item for item in result["user_assistance_required"]))
        payload = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("secret", payload.lower())

    def test_terraform_operations_plan_builds_gated_import_drift_and_readback(self) -> None:
        result = hcloud_terraform_operations_plan.build_plan(self.terraform_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation"], "full")
        self.assertEqual(result["import_commands"][0]["command"][:2], ["terraform", "import"])
        self.assertTrue(result["import_commands"][0]["state_changing"])
        self.assertIn("confirm_token", result["state_change_gate"])
        self.assertEqual(result["drift_commands"][0]["command"][:2], ["terraform", "plan"])
        self.assertEqual(result["hcloud_readback"][0]["operation"], "ShowServer")
        self.assertTrue(result["hcloud_readback"][0]["success"], result["hcloud_readback"])

    def test_terraform_import_plan_requires_targets(self) -> None:
        result = hcloud_terraform_operations_plan.build_plan(self.terraform_args(operation="import", import_target=[]))

        self.assertFalse(result["success"])
        self.assertIn("--import-target", result["error"])


if __name__ == "__main__":
    unittest.main()
