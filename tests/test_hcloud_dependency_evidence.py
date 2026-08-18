"""Tests for portable Huawei resource dependency evidence."""

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


hcloud_dependency_evidence = load_module(
    "hcloud_dependency_evidence",
    SCRIPTS / "hcloud_dependency_evidence.py",
)
hcloud_service_change_plan = load_module(
    "hcloud_service_change_plan_dependency_test",
    SCRIPTS / "hcloud_service_change_plan.py",
)
hcloud_operation_resolver = load_module(
    "hcloud_operation_resolver_dependency_test",
    SCRIPTS / "hcloud_operation_resolver.py",
)


class HcloudDependencyEvidenceTest(unittest.TestCase):
    """Validate dependency profiles without cloud access or orchestration."""

    def test_profiles_cover_high_value_resource_lifecycles(self) -> None:
        payload = hcloud_dependency_evidence.load_profiles()
        services = {profile["service"] for profile in payload["profiles"].values()}

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(
            services,
            {"ECS", "VPC", "EIP", "ELB", "EVS", "NAT", "RDS", "DNS", "OBS"},
        )
        self.assertGreaterEqual(len(payload["profiles"]), 15)

    def test_profile_operations_exist_in_registry_or_obs_contract(self) -> None:
        payload = hcloud_dependency_evidence.load_profiles()
        registry = json.loads((ROOT / "references" / "service-registry.json").read_text())
        catalog = hcloud_dependency_evidence.hcloud_catalog.load_catalog()

        for key, profile in payload["profiles"].items():
            with self.subTest(profile=key):
                self.assertEqual(key, profile["id"])
                service = profile["service"]
                self.assertIn(service, registry["services"])
                known = set(registry["services"][service]["change_operations"])
                catalog_service = hcloud_dependency_evidence.hcloud_catalog.resolve_service(
                    catalog,
                    service,
                )
                known.update((catalog_service or {}).get("operations", {}))
                self.assertTrue(set(profile["applies_to_operations"]) <= known)

    def test_elb_pool_delete_models_sibling_blockers(self) -> None:
        evidence = hcloud_dependency_evidence.find_dependency_evidence(
            "ELB",
            "DeletePool/v3",
        )

        blockers = {item["resource_kind"]: item for item in evidence["blockers"]}
        self.assertEqual(set(blockers), {"member", "health_monitor"})
        self.assertTrue(all(item["must_resolve_before_submit"] for item in blockers.values()))
        self.assertEqual(
            evidence["verification"]["target_readback"]["expected"],
            "not_found",
        )

    def test_ecs_delete_requires_related_eip_and_volume_reconciliation(self) -> None:
        evidence = hcloud_dependency_evidence.find_dependency_evidence(
            "ECS",
            "DeleteServers",
        )

        related = {item["resource_kind"]: item for item in evidence["related_resources"]}
        self.assertIn("public_ip", related)
        self.assertIn("volume", related)
        self.assertTrue(related["public_ip"]["post_change_readback_required"])
        self.assertTrue(related["volume"]["post_change_readback_required"])

    def test_vpc_and_nat_delete_expose_child_resource_blockers(self) -> None:
        vpc = hcloud_dependency_evidence.find_dependency_evidence("VPC", "DeleteVpc")
        nat = hcloud_dependency_evidence.find_dependency_evidence("NAT", "DeleteNatGateway")

        self.assertIn("subnet", {item["resource_kind"] for item in vpc["blockers"]})
        self.assertEqual(
            {item["resource_kind"] for item in nat["blockers"]},
            {"dnat_rule", "snat_rule"},
        )

    def test_inspector_builds_dependency_coverage_without_execution(self) -> None:
        result = hcloud_dependency_evidence.build_coverage_matrix()

        self.assertTrue(result["success"])
        self.assertFalse(result["summary"]["workflow_engine_present"])
        self.assertFalse(result["summary"]["cloud_access_performed"])
        self.assertGreaterEqual(result["summary"]["profiled_service_count"], 9)

    def test_change_plan_attaches_matching_dependency_evidence(self) -> None:
        result = hcloud_service_change_plan.build_service_plan(
            SimpleNamespace(
                service="ELB",
                operation="DeletePool",
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                json_input_file=None,
                arg=["--pool_id=pool-1"],
                no_dryrun=True,
                allow_public_web=False,
                allow_unregistered=False,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["dependency_evidence"]["resource_kind"], "pool")

    def test_operation_resolver_attaches_matching_dependency_evidence(self) -> None:
        catalog = json.loads(
            (ROOT / "references" / "hcloud-service-catalog" / "ecs.json").read_text()
        )
        result = hcloud_operation_resolver.resolve_operation_version(
            "ECS",
            "DeleteServers",
            {"servers"},
            catalog={"schema_version": 2, "services": {"ecs": catalog}},
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["dependency_evidence"]["resource_kind"], "server")
        self.assertEqual(result["dependency_evidence"]["lifecycle"], "delete")

    def test_unprofiled_operation_does_not_add_dependency_field(self) -> None:
        result = hcloud_service_change_plan.build_service_plan(
            SimpleNamespace(
                service="VPC",
                operation="UpdateSecurityGroup",
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                json_input_file=None,
                arg=["--security_group_id=sg-1"],
                no_dryrun=True,
                allow_public_web=False,
                allow_unregistered=False,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertNotIn("dependency_evidence", result)

    def test_docs_and_manifest_expose_dependency_inspector(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        scripts_text = (ROOT / "references" / "scripts.md").read_text(encoding="utf-8")
        source_map = (ROOT / "references" / "source-map.md").read_text(encoding="utf-8")
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text()
        )

        self.assertIn("hcloud_dependency_evidence.py", skill_text)
        self.assertIn("dependency_evidence", scripts_text)
        self.assertIn("resource-dependency-profiles.json", source_map)
        self.assertEqual(
            manifest["public_script_contracts"]["scripts/hcloud_dependency_evidence.py"]["kind"],
            "inspector_router",
        )


if __name__ == "__main__":
    unittest.main()
