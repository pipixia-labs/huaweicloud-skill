"""Tests for the task-owned Huawei Cloud resource ledger."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

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


hcloud_resource_ledger = load_module(
    "hcloud_resource_ledger",
    SCRIPTS / "hcloud_resource_ledger.py",
)


class ResourceLedgerTest(unittest.TestCase):
    """Validate resource ownership, convergence, and exact cleanup ordering."""

    def test_registration_is_idempotent_but_rejects_changed_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "resource-ledger.json"
            arguments = {
                "workflow_id": "workflow-1",
                "role": "web-server",
                "service": "ECS",
                "region": "cn-north-4",
                "project_id": "project-1",
                "expected_count": 1,
                "request_fingerprint": "a" * 64,
                "cleanup_operation": "DeleteServers",
                "identifier_parameter": "server_id",
            }

            first = hcloud_resource_ledger.register_resource(path, **arguments)
            second = hcloud_resource_ledger.register_resource(path, **arguments)

            self.assertEqual(first, second)
            with self.assertRaisesRegex(ValueError, "different resource declaration"):
                hcloud_resource_ledger.register_resource(
                    path,
                    **{**arguments, "region": "cn-east-3"},
                )

    def test_submit_and_verification_preserve_exact_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "resource-ledger.json"
            hcloud_resource_ledger.register_resource(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                service="ECS",
                region="cn-north-4",
                expected_count=2,
                cleanup_operation="DeleteServers",
                identifier_parameter="server_id",
            )
            submitted = hcloud_resource_ledger.record_submission(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                accepted=True,
                identifiers=["server-1", "server-2", "server-1"],
                job_ids=["job-1"],
            )
            verified = hcloud_resource_ledger.record_verification(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                success=True,
            )

        self.assertEqual(submitted["state"], "submitted")
        self.assertEqual(submitted["identifiers"], ["server-1", "server-2"])
        self.assertEqual(submitted["job_ids"], ["job-1"])
        self.assertEqual(verified["state"], "verified")

    def test_verification_cannot_succeed_with_wrong_resource_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "resource-ledger.json"
            hcloud_resource_ledger.register_resource(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                service="ECS",
                region="cn-north-4",
                expected_count=2,
            )
            hcloud_resource_ledger.record_submission(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                accepted=True,
                identifiers=["server-1"],
            )

            result = hcloud_resource_ledger.record_verification(
                path,
                workflow_id="workflow-1",
                role="web-servers",
                success=True,
            )

        self.assertEqual(result["state"], "verification_failed")
        self.assertEqual(result["verification"]["error_code"], "RESOURCE_COUNT_MISMATCH")

    def test_cleanup_plan_uses_owned_ids_in_reverse_dependency_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "resource-ledger.json"
            resources = [
                ("vpc", "VPC", [], "vpc-1", "DeleteVpc", "vpc_id"),
                ("subnet", "VPC", ["vpc"], "subnet-1", "DeleteSubnet", "subnet_id"),
                ("server", "ECS", ["subnet"], "server-1", "DeleteServers", "server_id"),
                ("eip", "EIP", ["server"], "eip-1", "DeletePublicip", "publicip_id"),
            ]
            for role, service, dependencies, identifier, operation, parameter in resources:
                hcloud_resource_ledger.register_resource(
                    path,
                    workflow_id="workflow-1",
                    role=role,
                    service=service,
                    region="cn-north-4",
                    dependencies=dependencies,
                    cleanup_operation=operation,
                    identifier_parameter=parameter,
                )
                hcloud_resource_ledger.record_submission(
                    path,
                    workflow_id="workflow-1",
                    role=role,
                    accepted=True,
                    identifiers=[identifier],
                )
                hcloud_resource_ledger.record_verification(
                    path,
                    workflow_id="workflow-1",
                    role=role,
                    success=True,
                )

            plan = hcloud_resource_ledger.build_cleanup_plan(
                path,
                workflow_id="workflow-1",
            )

        self.assertTrue(plan["ready"])
        self.assertEqual(
            [item["role"] for item in plan["actions"]],
            ["eip", "server", "subnet", "vpc"],
        )
        self.assertEqual(plan["actions"][0]["identifiers"], ["eip-1"])
        self.assertNotIn("discovery", plan)

    def test_cleanup_plan_blocks_unidentified_resources_instead_of_rediscovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "resource-ledger.json"
            hcloud_resource_ledger.register_resource(
                path,
                workflow_id="workflow-1",
                role="database",
                service="RDS",
                region="cn-north-4",
                cleanup_operation="DeleteInstance",
                identifier_parameter="instance_id",
            )

            plan = hcloud_resource_ledger.build_cleanup_plan(
                path,
                workflow_id="workflow-1",
            )

        self.assertFalse(plan["ready"])
        self.assertEqual(plan["blocked"][0]["error_code"], "RESOURCE_IDENTIFIER_MISSING")
        self.assertEqual(plan["actions"], [])


if __name__ == "__main__":
    unittest.main()
