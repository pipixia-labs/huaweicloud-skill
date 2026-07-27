"""Tests for the non-executing CCI workload preflight planner."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_cci_workload_plan  # noqa: E402


def valid_args(**overrides: object) -> SimpleNamespace:
    """Return a complete internal-service CCI plan input for tests."""
    values: dict[str, object] = {
        "namespace": "production",
        "namespace_flavor": "general-computing",
        "vpc_id": "vpc-123",
        "subnet_id": "subnet-123",
        "neutron_network_id": "network-123",
        "subnet_cidr": "192.168.10.0/24",
        "security_group_id": "sg-123",
        "network_name": "production-network",
        "workload_type": "deployment",
        "workload_name": "web",
        "image": "swr.example.com/org/web:1.0.0",
        "cpu_request": "500m",
        "cpu_limit": "500m",
        "memory_request": "1Gi",
        "memory_limit": "1Gi",
        "service_name": "web",
        "exposure": "internal",
        "eip_pool_name": None,
        "public_access_justification": None,
        "allowed_source_cidr": None,
        "planned_action": ["create"],
        "region": "cn-north-4",
        "project_id": "project-123",
        "profile": None,
        "timeout": 120,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class HcloudCciWorkloadPlanTest(unittest.TestCase):
    """Validate CCI planning stays evidence-first and non-executing."""

    def test_complete_internal_plan_is_ready_for_review(self) -> None:
        result = hcloud_cci_workload_plan.build_plan(valid_args())

        self.assertTrue(result["success"])
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["summary"]["readiness"], "ready_to_review")
        self.assertEqual(result["risk_gates"], [])
        self.assertIn("network_inventory", {item["id"] for item in result["evidence_plan"]})
        self.assertIn("pod_inventory", {item["id"] for item in result["evidence_plan"]})
        commands = [
            item["plan"]["command_shell"]
            for item in result["evidence_plan"]
            if item.get("source") == "hcloud" and item["plan"].get("command_shell")
        ]
        self.assertTrue(commands)
        self.assertTrue(all(sys.executable in command for command in commands))
        self.assertNotIn("--execute", "\n".join(commands))

    def test_rejects_mismatched_resource_values_and_reserved_subnet(self) -> None:
        result = hcloud_cci_workload_plan.build_plan(
            valid_args(cpu_limit="1", subnet_cidr="10.247.1.0/24")
        )

        self.assertEqual(result["summary"]["readiness"], "blocked")
        self.assertIn("cpu_request_limit", result["summary"]["blockers"])
        self.assertIn("subnet_cidr", result["summary"]["blockers"])

    def test_delete_namespace_is_hard_gated_without_a_delete_command(self) -> None:
        result = hcloud_cci_workload_plan.build_plan(
            valid_args(planned_action=["delete_namespace"])
        )

        self.assertEqual(result["summary"]["readiness"], "blocked")
        self.assertEqual(result["hard_gated_actions"], ["delete_namespace"])
        self.assertIn("delete_namespace", result["summary"]["blockers"])
        output = str(result)
        self.assertNotIn("deleteCoreV1Namespace", output)
        self.assertNotIn("--execute", output)

    def test_public_exposure_requires_bounded_access_evidence(self) -> None:
        blocked = hcloud_cci_workload_plan.build_plan(valid_args(exposure="eip"))
        reviewed = hcloud_cci_workload_plan.build_plan(
            valid_args(
                exposure="eip",
                eip_pool_name="production-pool",
                public_access_justification="Public checkout endpoint is required.",
                allowed_source_cidr="203.0.113.0/24",
            )
        )

        self.assertEqual(blocked["summary"]["readiness"], "blocked")
        self.assertIn("public_exposure", blocked["summary"]["blockers"])
        self.assertEqual(reviewed["summary"]["readiness"], "review_required")
        self.assertEqual(reviewed["summary"]["review_required"], ["public_exposure"])

    def test_missing_inputs_stay_explicit(self) -> None:
        result = hcloud_cci_workload_plan.build_plan(valid_args(namespace=None, image=None))

        self.assertEqual(result["summary"]["readiness"], "inputs_needed")
        self.assertIn("namespace", result["summary"]["inputs_needed"])
        self.assertIn("image", result["summary"]["inputs_needed"])
        self.assertEqual(
            [item["id"] for item in result["evidence_plan"]],
            ["namespace_inventory"],
        )


if __name__ == "__main__":
    unittest.main()
