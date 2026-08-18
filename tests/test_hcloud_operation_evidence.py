"""Tests for the internal operation evidence accessor."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_operation_evidence  # noqa: E402


class OperationEvidenceTest(unittest.TestCase):
    """Keep paired operation facts consistent without creating a new fact store."""

    def test_default_lookup_returns_behavior_and_dependencies_when_both_exist(self) -> None:
        fields = hcloud_operation_evidence.operation_evidence_fields(
            "ecs",
            "ECS-CreateServers/v2",
        )

        self.assertEqual(fields["operation_behavior"]["operation"], "CreateServers")
        self.assertEqual(fields["dependency_evidence"]["id"], "ECS.server.create")

    def test_lookup_returns_only_evidence_that_is_actually_profiled(self) -> None:
        behavior_profiles = {
            "schema_version": 1,
            "operations": {
                "TEST.DoThing": {
                    "service": "TEST",
                    "operation": "DoThing",
                    "evidence_sources": ["fixture"],
                }
            },
        }
        dependency_profiles = {"schema_version": 1, "profiles": {}}

        fields = hcloud_operation_evidence.operation_evidence_fields(
            "TEST",
            "DoThing/v1",
            behavior_profiles=behavior_profiles,
            dependency_profiles=dependency_profiles,
        )

        self.assertEqual(set(fields), {"operation_behavior"})
        self.assertEqual(fields["operation_behavior"]["evidence_sources"], ["fixture"])

    def test_unknown_operation_returns_an_empty_additive_view(self) -> None:
        fields = hcloud_operation_evidence.operation_evidence_fields(
            "UNKNOWN",
            "RunSomething",
            behavior_profiles={"schema_version": 1, "operations": {}},
            dependency_profiles={"schema_version": 1, "profiles": {}},
        )

        self.assertEqual(fields, {})

    def test_returned_profiles_do_not_mutate_the_source_documents(self) -> None:
        behavior_profiles = {
            "schema_version": 1,
            "operations": {
                "TEST.DoThing": {
                    "service": "TEST",
                    "operation": "DoThing",
                    "nested": {"state": "original"},
                }
            },
        }
        dependency_profiles = {"schema_version": 1, "profiles": {}}

        first = hcloud_operation_evidence.operation_evidence_fields(
            "TEST",
            "DoThing",
            behavior_profiles=behavior_profiles,
            dependency_profiles=dependency_profiles,
        )
        first["operation_behavior"]["nested"]["state"] = "changed"
        second = hcloud_operation_evidence.operation_evidence_fields(
            "TEST",
            "DoThing",
            behavior_profiles=behavior_profiles,
            dependency_profiles=dependency_profiles,
        )

        self.assertEqual(second["operation_behavior"]["nested"]["state"], "original")

    def test_shared_consumers_use_the_internal_accessor(self) -> None:
        for filename in (
            "hcloud_operation_resolver.py",
            "hcloud_service_change_plan.py",
            "hcloud_ecs_create_plan.py",
        ):
            with self.subTest(filename=filename):
                source = (SCRIPTS / filename).read_text(encoding="utf-8")
                self.assertIn("hcloud_operation_evidence", source)
                self.assertNotIn("import hcloud_dependency_evidence", source)
                self.assertNotIn("import hcloud_operation_behavior", source)

    def test_accessor_is_internal_and_not_a_second_public_fact_store(self) -> None:
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        groups = {group["id"]: group["scripts"] for group in manifest["script_groups"]}

        self.assertIn(
            "scripts/hcloud_operation_evidence.py",
            groups["internal_library"],
        )
        for group_id in ("default_runtime", "guarded_change", "runtime_supplement"):
            self.assertNotIn(
                "scripts/hcloud_operation_evidence.py",
                groups[group_id],
            )
        self.assertNotIn(
            "scripts/hcloud_operation_evidence.py",
            manifest["public_script_contracts"],
        )


if __name__ == "__main__":
    unittest.main()
