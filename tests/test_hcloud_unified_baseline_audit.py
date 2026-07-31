"""Tests for the phase-0 unified-operation baseline audit."""

from __future__ import annotations

import copy
import contextlib
import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_unified_baseline_audit  # noqa: E402
import hcloud_invariant_coverage_audit  # noqa: E402
import hcloud_m2_5_closure_audit  # noqa: E402


class UnifiedBaselineAuditTests(unittest.TestCase):
    """Verify baseline registers are factual, complete, and intentionally conservative."""

    def test_default_baseline_reports_plan_only_closure_without_claiming_submit(self) -> None:
        report = hcloud_unified_baseline_audit.build_baseline()

        self.assertTrue(report["success"])
        self.assertEqual(report["baseline_status"], "mutation_paths_closed_plan_only_controlled_submit_not_ready")
        self.assertTrue(report["asset_register"]["all_paths_present"])
        self.assertTrue(report["execution_paths"]["all_reviewed_sources_present"])
        self.assertEqual(report["execution_paths"]["uncontrolled_submit_capable_groups"], [])
        self.assertEqual(report["invariants"]["by_enforcement_level"].get("code_enforced", 0), 1)
        self.assertEqual(report["service_maturity_matrix"]["registered_services"], 19)
        self.assertEqual(report["service_maturity_matrix"]["services_with_live_validation_profile"], 6)
        self.assertEqual(report["migration_map"]["rule_conflicts"], 5)

    def test_service_maturity_matrix_is_available_without_copying_api_facts(self) -> None:
        report = hcloud_unified_baseline_audit.build_baseline(include_service_matrix=True)
        matrix = report["service_maturity_matrix"]

        self.assertEqual(matrix["action_spec_status"], "trial_action_specs_present_not_execution_authorization")
        self.assertEqual(matrix["trial_action_spec_count"], 5)
        ecs = next(row for row in matrix["services_detail"] if row["service"] == "ECS")
        self.assertTrue(ecs["in_service_registry"])
        self.assertTrue(ecs["has_live_validation_profile"])
        self.assertGreater(ecs["registered_operation_count"], 0)
        self.assertEqual(ecs["trial_action_spec_ids"], ["huaweicloud.ecs.create_server.v1"])

    def test_every_reviewed_execution_source_is_unique_and_present(self) -> None:
        inventory = hcloud_unified_baseline_audit.load_object(
            hcloud_unified_baseline_audit.DEFAULT_EXECUTION_PATHS,
            "execution-path inventory",
        )
        groups = hcloud_unified_baseline_audit.validate_execution_paths(inventory, ROOT)
        sources = [source for group in groups for source in group["source_paths"]]

        self.assertEqual(len(sources), len(set(sources)))
        self.assertIn("scripts/maas_image_generation.py", sources)
        self.assertIn("scripts/hcloud_safe_exec.py", sources)
        self.assertIn("scripts/hcloud_action_plan.py", sources)
        self.assertIn("scripts/hcloud_metadata_read_plan.py", sources)
        self.assertIn("scripts/hcloud_entrypoint_shadow_audit.py", sources)
        self.assertIn("scripts/hcloud_invariant_coverage_audit.py", sources)
        self.assertIn("scripts/hcloud_m2_5_closure_audit.py", sources)

    def test_duplicate_asset_id_is_rejected(self) -> None:
        register = hcloud_unified_baseline_audit.load_object(
            hcloud_unified_baseline_audit.DEFAULT_ASSET_REGISTER,
            "asset register",
        )
        broken = copy.deepcopy(register)
        broken["assets"].append(copy.deepcopy(broken["assets"][0]))

        with self.assertRaisesRegex(hcloud_unified_baseline_audit.BaselineAuditError, "Duplicate asset id"):
            hcloud_unified_baseline_audit.validate_asset_register(broken, ROOT)

    def test_invalid_invariant_level_is_rejected(self) -> None:
        register = hcloud_unified_baseline_audit.load_object(
            hcloud_unified_baseline_audit.DEFAULT_INVARIANTS,
            "invariant register",
        )
        broken = copy.deepcopy(register)
        broken["invariants"][0]["level"] = "marketing_only"

        with self.assertRaisesRegex(hcloud_unified_baseline_audit.BaselineAuditError, "invalid level"):
            hcloud_unified_baseline_audit.validate_invariants(broken, ROOT)

    def test_invariant_requires_explicit_entrypoint_applicability(self) -> None:
        register = hcloud_unified_baseline_audit.load_object(
            hcloud_unified_baseline_audit.DEFAULT_INVARIANTS,
            "invariant register",
        )
        broken = copy.deepcopy(register)
        broken["invariants"][0].pop("applicable_path_groups")

        with self.assertRaisesRegex(hcloud_unified_baseline_audit.BaselineAuditError, "missing fields"):
            hcloud_unified_baseline_audit.validate_invariants(broken, ROOT)

    def test_invariant_coverage_reports_declared_scope_without_claiming_global_enforcement(self) -> None:
        report = hcloud_invariant_coverage_audit.build_coverage_report()

        self.assertTrue(report["success"])
        self.assertEqual(report["summary"]["reviewed_path_groups"], 10)
        self.assertEqual(report["summary"]["invariants"], 7)
        self.assertEqual(report["summary"]["declared_invariant_path_pairs"], 13)
        self.assertEqual(report["summary"]["code_enforced_invariant_count"], 1)
        self.assertEqual(report["summary"]["code_enforced_invariant_ids"], ["unknown_mutations_are_plan_only"])
        self.assertIn("planner_only_change_paths", report["summary"]["path_groups_without_declared_invariant"])

    def test_cli_fail_on_gaps_passes_after_runtime_plan_only_closure(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hcloud_unified_baseline_audit.main([]), 0)
            self.assertEqual(hcloud_unified_baseline_audit.main(["--fail-on-gaps"]), 0)

    def test_m2_5_closure_audit_records_runtime_plan_only_closure(self) -> None:
        report = hcloud_m2_5_closure_audit.build_closure_report()

        self.assertTrue(report["success"])
        self.assertEqual(report["closure_status"], "ready")
        self.assertEqual(report["summary"]["reviewed_mutation_path_groups"], 4)
        self.assertEqual(report["summary"]["status_counts"], {"closed_via_plan_only": 4})
        self.assertEqual(report["summary"]["open_path_group_ids"], [])
        self.assertIn("not permission", report["limitations"][0])

    def test_m2_5_closure_ledger_must_cover_every_reviewed_mutation_group(self) -> None:
        ledger = hcloud_m2_5_closure_audit.load_ledger(hcloud_m2_5_closure_audit.DEFAULT_CLOSURE_LEDGER)
        broken = copy.deepcopy(ledger)
        broken["entries"].pop()
        groups = hcloud_m2_5_closure_audit.load_reviewed_mutation_groups(
            hcloud_m2_5_closure_audit.DEFAULT_EXECUTION_PATHS
        )

        with self.assertRaisesRegex(hcloud_m2_5_closure_audit.ClosureAuditError, "misses reviewed mutation groups"):
            hcloud_m2_5_closure_audit.validate_ledger_entries(broken, groups)

    def test_closed_m2_5_path_requires_runtime_and_negative_test_evidence(self) -> None:
        ledger = hcloud_m2_5_closure_audit.load_ledger(hcloud_m2_5_closure_audit.DEFAULT_CLOSURE_LEDGER)
        broken = copy.deepcopy(ledger)
        broken["entries"][0].pop("runtime_evidence")
        groups = hcloud_m2_5_closure_audit.load_reviewed_mutation_groups(
            hcloud_m2_5_closure_audit.DEFAULT_EXECUTION_PATHS
        )

        with self.assertRaisesRegex(hcloud_m2_5_closure_audit.ClosureAuditError, "requires non-empty runtime_evidence"):
            hcloud_m2_5_closure_audit.validate_ledger_entries(broken, groups)


if __name__ == "__main__":
    unittest.main()
