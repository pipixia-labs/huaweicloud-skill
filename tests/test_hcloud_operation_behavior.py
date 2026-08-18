"""Tests for portable Huawei operation behavior evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):  # noqa: ANN201
    """Load one repository script for isolated unit tests."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_operation_behavior = load_module(
    "hcloud_operation_behavior",
    SCRIPTS / "hcloud_operation_behavior.py",
)
hcloud_operation_resolver = load_module(
    "hcloud_operation_resolver_behavior_test",
    SCRIPTS / "hcloud_operation_resolver.py",
)
hcloud_service_change_plan = load_module(
    "hcloud_service_change_plan_behavior_test",
    SCRIPTS / "hcloud_service_change_plan.py",
)
hcloud_ecs_create_plan = load_module(
    "hcloud_ecs_create_plan_behavior_test",
    SCRIPTS / "hcloud_ecs_create_plan.py",
)


class HcloudOperationBehaviorTest(unittest.TestCase):
    """Validate batch, async, and coverage evidence without cloud access."""

    def test_profiles_cover_current_eip_and_ecs_batch_cases(self) -> None:
        profiles = hcloud_operation_behavior.load_profiles()

        self.assertEqual(profiles["schema_version"], 1)
        self.assertEqual(
            set(profiles["operations"]),
            {
                "ECS.CreateServers",
                "ECS.CreatePostPaidServers",
                "ECS.DeleteServers",
                "EIP.BatchDeletePublicIp",
            },
        )

    def test_profile_identity_support_level_and_catalog_evidence_do_not_drift(self) -> None:
        profiles = hcloud_operation_behavior.load_profiles()
        registry = json.loads(
            (ROOT / "references" / "service-registry.json").read_text(
                encoding="utf-8"
            )
        )
        catalog = hcloud_operation_behavior.hcloud_catalog.load_catalog()

        for key, behavior in profiles["operations"].items():
            with self.subTest(operation=key):
                service = behavior["service"]
                operation = behavior["operation"]
                self.assertEqual(key, f"{service}.{operation}")
                catalog_service = hcloud_operation_behavior.hcloud_catalog.resolve_service(
                    catalog,
                    service,
                )
                catalog_operation = hcloud_operation_behavior.hcloud_catalog.resolve_operation(
                    catalog_service,
                    operation,
                )
                self.assertIsNotNone(catalog_operation)
                self.assertTrue(
                    set(behavior["versions"])
                    <= set(
                        hcloud_operation_behavior.hcloud_catalog.operation_versions(
                            catalog_operation
                        )
                    )
                )
                if behavior["support_level"] == "curated":
                    self.assertIn(
                        operation,
                        registry["services"][service]["change_operations"],
                    )

    def test_ecs_create_requires_job_then_active_resource_readback(self) -> None:
        behavior = hcloud_operation_behavior.find_operation_behavior(
            "ecs",
            "CreateServers/v2",
        )

        self.assertEqual(behavior["support_level"], "curated")
        self.assertEqual(behavior["cardinality"], "multi_resource")
        self.assertFalse(behavior["submit_receipt"]["per_item_completion"])
        self.assertEqual(
            behavior["batch_result_contract"]["initial_item_outcome"],
            "outcome_unknown",
        )
        self.assertEqual(
            behavior["batch_result_contract"]["applies_after"],
            "submit_receipt",
        )
        convergence = behavior["async_convergence"]
        self.assertEqual(convergence["mode"], "job_then_resource")
        self.assertEqual(convergence["poll"]["operation"], "ShowJob")
        self.assertEqual(
            convergence["resource_readback"]["success_states"],
            ["ACTIVE"],
        )
        self.assertFalse(convergence["public_polling_framework_required"])

    def test_eip_batch_delete_uses_absence_readback_not_job_polling(self) -> None:
        behavior = hcloud_operation_behavior.find_operation_behavior(
            "EIP",
            "BatchDeletePublicIp",
        )

        self.assertEqual(
            behavior["request_targets"]["path"],
            "body.publicip_ids[]",
        )
        self.assertEqual(behavior["submit_receipt"]["fields"], ["job_ids[]"])
        self.assertFalse(behavior["submit_receipt"]["job_receipts_queryable"])
        self.assertEqual(
            behavior["async_convergence"]["mode"],
            "resource_readback_only",
        )
        self.assertIsNone(behavior["async_convergence"]["poll"])
        self.assertEqual(
            behavior["async_convergence"]["resource_readback"]["expected"],
            "not_found",
        )

    def test_pay_per_use_create_receipt_does_not_invent_order_id(self) -> None:
        behavior = hcloud_operation_behavior.find_operation_behavior(
            "ECS",
            "CreatePostPaidServers",
        )

        self.assertEqual(
            behavior["submit_receipt"]["fields"],
            ["job_id", "serverIds[]"],
        )
        self.assertNotIn("order", behavior["submit_receipt"]["meaning"])

    def test_ecs_delete_keeps_every_target_unknown_until_readback(self) -> None:
        behavior = hcloud_operation_behavior.find_operation_behavior(
            "ECS",
            "DeleteServers",
        )

        self.assertEqual(behavior["support_level"], "metadata_backed")
        self.assertEqual(behavior["request_targets"]["path"], "body.servers[].id")
        self.assertEqual(behavior["request_targets"]["max_items"], 1000)
        self.assertEqual(behavior["submit_receipt"]["fields"], ["job_id"])
        self.assertEqual(
            behavior["batch_result_contract"]["initial_item_outcome"],
            "outcome_unknown",
        )
        self.assertEqual(
            behavior["async_convergence"]["resource_readback"]["expected"],
            "not_found",
        )

    def test_coverage_matrix_distinguishes_curated_and_profile_evidence(self) -> None:
        result = hcloud_operation_behavior.build_coverage_matrix()

        by_service = {row["service"]: row for row in result["services"]}
        self.assertEqual(result["summary"]["profiled_operation_count"], 4)
        self.assertEqual(
            by_service["EIP"]["profiled_batch_operations"],
            ["BatchDeletePublicIp"],
        )
        self.assertEqual(
            by_service["ECS"]["profiled_batch_operations"],
            ["CreatePostPaidServers", "CreateServers", "DeleteServers"],
        )
        self.assertEqual(
            by_service["ECS"]["metadata_backed_profile_operations"],
            ["DeleteServers"],
        )
        self.assertEqual(by_service["VPC"]["profiled_batch_operations"], [])
        self.assertTrue(by_service["VPC"]["generic_metadata_backed_available"])
        self.assertGreater(by_service["VPC"]["metadata_catalog_operation_count"], 0)
        self.assertFalse(by_service["EVS"]["has_operation_async_profile"])

    def test_operation_resolver_attaches_matching_behavior(self) -> None:
        catalog = json.loads(
            (ROOT / "references" / "hcloud-service-catalog" / "ecs.json").read_text(
                encoding="utf-8"
            )
        )
        result = hcloud_operation_resolver.resolve_operation_version(
            "ECS",
            "DeleteServers",
            {"servers"},
            catalog={"schema_version": 2, "services": {"ecs": catalog}},
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(
            result["operation_behavior"]["batch_result_contract"]["initial_item_outcome"],
            "outcome_unknown",
        )

    def test_service_change_plan_exposes_eip_batch_behavior(self) -> None:
        result = hcloud_service_change_plan.build_service_plan(
            SimpleNamespace(
                service="EIP",
                operation="BatchDeletePublicIp",
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                json_input_file=None,
                arg=["--publicip_ids.1=eip-1", "--publicip_ids.2=eip-2"],
                no_dryrun=True,
                allow_public_web=False,
                allow_unregistered=False,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(
            result["operation_behavior"]["async_convergence"]["mode"],
            "resource_readback_only",
        )

    def test_unprofiled_change_plan_preserves_the_existing_output_shape(self) -> None:
        result = hcloud_service_change_plan.build_service_plan(
            SimpleNamespace(
                service="VPC",
                operation="CreateVpc",
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                json_input_file=None,
                arg=["--name=vpc-test", "--cidr=192.168.0.0/16"],
                no_dryrun=True,
                allow_public_web=False,
                allow_unregistered=False,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertNotIn("operation_behavior", result)

    def test_ecs_create_plan_exposes_multi_resource_completion_contract(self) -> None:
        behavior = hcloud_ecs_create_plan.operation_behavior("CreateServers")

        self.assertEqual(behavior["cardinality"], "multi_resource")
        self.assertEqual(
            behavior["async_convergence"]["resource_readback"]["success_states"],
            ["ACTIVE"],
        )

    def test_agent_docs_expose_behavior_evidence_without_mandating_a_waiter(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        scripts_text = (ROOT / "references" / "scripts.md").read_text(encoding="utf-8")
        coverage_text = (ROOT / "references" / "service-coverage.md").read_text(
            encoding="utf-8"
        )
        source_map = (ROOT / "references" / "source-map.md").read_text(
            encoding="utf-8"
        )
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        default_runtime = next(
            group for group in manifest["script_groups"] if group["id"] == "default_runtime"
        )

        self.assertIn("hcloud_operation_behavior.py", skill_text)
        self.assertIn("Agent 可以直接轮询", skill_text)
        self.assertIn("不要求公共轮询框架", skill_text)
        self.assertIn("operation_behavior", scripts_text)
        self.assertIn("批量/异步行为证据", coverage_text)
        self.assertIn("Curated change", coverage_text)
        self.assertIn("hcloud_operation_behavior.py", source_map)
        self.assertIn(
            "scripts/hcloud_operation_behavior.py",
            default_runtime["scripts"],
        )
        self.assertEqual(
            manifest["public_script_contracts"]["scripts/hcloud_operation_behavior.py"]["kind"],
            "inspector_router",
        )


if __name__ == "__main__":
    unittest.main()
