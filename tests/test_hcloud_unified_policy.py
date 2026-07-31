"""Tests for the deterministic, non-executing unified policy layer."""

from __future__ import annotations

import copy
import contextlib
import io
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "unified-action-plan"
TRIAL_SPECS = ROOT / "references" / "action-semantics" / "trial"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_action_plan  # noqa: E402
import hcloud_controlled_admission  # noqa: E402
import hcloud_metadata_read_plan  # noqa: E402
import hcloud_entrypoint_shadow_audit  # noqa: E402
import hcloud_operation_result  # noqa: E402
import hcloud_unified_contracts  # noqa: E402
import hcloud_unified_policy  # noqa: E402


class UnifiedPolicyTests(unittest.TestCase):
    """Verify conservative policy decisions before any execution adapter exists."""

    def load(self, path: Path) -> dict:
        return hcloud_unified_contracts.load_document(path)

    def build_ecs_execution_intent(self, spec: dict) -> dict:
        """Create one local fixture bound to the exact current ECS trial spec."""
        return {
            "schema_version": "execution-intent/v1",
            "execution_family": "hcloud",
            "action_spec_ref": {
                "id": spec["id"],
                "lifecycle": spec["lifecycle"],
                "fingerprint": hcloud_unified_contracts.fingerprint(spec),
            },
            "catalog_ref": copy.deepcopy(spec["catalog_ref"]),
            "scope": {"region": "cn-north-4", "project_id": "example-project"},
            "parameters": {
                "server_count": 1,
                "flavor_id": "c6.large.2",
                "image_id": "image-example",
                "subnet_id": "subnet-example",
                "server_name": "ecs-example",
                "availability_zone": "cn-north-4a",
                "vpc_id": "vpc-example",
                "root_volume_type": "SSD",
                "key_name": "keypair-example",
                "security_group_id": "sg-example",
                "security_group_rule_evidence": {
                    "security_group": {
                        "id": "sg-example",
                        "security_group_rules": [
                            {
                                "id": "rule-example",
                                "security_group_id": "sg-example",
                                "direction": "ingress",
                                "protocol": "tcp",
                                "remote_ip_prefix": "203.0.113.10/32",
                                "port_range_min": 22,
                                "port_range_max": 22
                            }
                        ]
                    }
                }
            },
            "idempotency": {"client_token": "local-test-request-001"},
        }

    def build_confirmation(self, action_plan: dict, execution_intent: dict) -> dict:
        """Create explicit local confirmation evidence for every planned preflight."""
        return {
            "status": "confirmed",
            "approval_id": "local-test-approval-001",
            "reviewed_action_plan_fingerprint": action_plan["plan_fingerprint"],
            "reviewed_execution_intent_fingerprint": hcloud_unified_contracts.fingerprint(execution_intent),
            "preflight_evidence": [
                {"id": item["id"], "status": "passed"}
                for item in action_plan["preflight"]
            ],
        }

    def build_dns_execution_intent(self, spec: dict) -> dict:
        """Create a fully scoped DNS create-record intent for admission tests."""
        return {
            "schema_version": "execution-intent/v1",
            "execution_family": "hcloud",
            "action_spec_ref": {
                "id": spec["id"],
                "lifecycle": spec["lifecycle"],
                "fingerprint": hcloud_unified_contracts.fingerprint(spec),
            },
            "catalog_ref": copy.deepcopy(spec["catalog_ref"]),
            "scope": {"region": "cn-north-4", "project_id": "example-project"},
            "parameters": {
                "zone_id": "zone-example",
                "record_name": "www.example.com.",
                "record_type": "A",
                "record_values": ["192.0.2.10"],
                "ttl": 300,
            },
            "idempotency": {"client_token": "local-test-dns-request-001"},
        }

    def test_trial_specs_generate_only_non_executing_plans(self) -> None:
        cases = {
            "ecs-create-server.json": ("ecs-context.json", "dry_run"),
            "dns-create-record-set.json": ("dns-context.json", "plan"),
            "maas-image-generation.json": ("maas-context.json", "plan"),
            "lts-list-logs.json": ("lts-context.json", "discover"),
            "cts-list-traces.json": ("cts-context.json", "discover"),
        }
        for spec_name, (context_name, expected_stage) in cases.items():
            with self.subTest(spec=spec_name):
                result = hcloud_action_plan.generate_action_plan(TRIAL_SPECS / spec_name, FIXTURES / context_name)
                self.assertTrue(result["success"], result.get("errors"))
                plan = result["action_plan"]
                self.assertEqual(plan["allowed_stage"], expected_stage)
                self.assertEqual(plan["execution_authority"]["submission_authority"], "not_implemented")
                self.assertIn("no hcloud, SDK, Terraform, or MaaS request was sent", result["execution_boundary"])
                validation = hcloud_unified_contracts.validate_contract("action-plan", plan)
                self.assertTrue(validation["success"], validation["errors"])

    def test_unknown_risk_tag_cannot_raise_a_plan_beyond_plan_stage(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        spec["risk_tags"].append("new_unreviewed_risk")

        decision = hcloud_unified_policy.evaluate_action_spec(spec, context)

        self.assertEqual(decision["allowed_stage"], "plan")
        self.assertEqual(decision["decision"], "plan_only_unknown_risk")
        self.assertEqual(decision["unknown_risk_tags"], ["new_unreviewed_risk"])

    def test_identity_or_security_policy_is_a_manual_gate(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        spec["risk_tags"] = ["identity"]

        decision = hcloud_unified_policy.evaluate_action_spec(spec, context)

        self.assertEqual(decision["allowed_stage"], "plan")
        self.assertEqual(decision["decision"], "manual_gate")
        self.assertEqual(decision["confirmation"]["mode"], "human_runbook_required")

    def test_timeout_at_submit_requires_readback_before_any_retry(self) -> None:
        result = hcloud_unified_policy.classify_operation_error(error_type="TIMEOUT", stage="submit")

        self.assertEqual(result["category"], "timeout")
        self.assertEqual(result["retry"], "read_back_before_retry")
        self.assertFalse(result["automatic_retry_allowed"])

    def test_cloud_permission_signal_overrides_generic_api_category(self) -> None:
        result = hcloud_unified_policy.classify_operation_error(
            error_type="OPENAPI_ERROR",
            cloud_error_code="AccessDenied",
            stage="plan",
        )

        self.assertEqual(result["category"], "permission")
        self.assertEqual(result["source"], "cloud_code_pattern")
        self.assertFalse(result["automatic_retry_allowed"])

    def test_catalog_fingerprint_drift_blocks_plan_generation(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        spec["catalog_ref"]["catalog_fingerprint"] = "sha256:" + "0" * 64

        errors = hcloud_action_plan.validate_hcloud_catalog_reference(spec)

        self.assertEqual(len(errors), 1)
        self.assertIn("catalog fingerprint drift", errors[0])

    def test_plan_fingerprint_binds_spec_and_context(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        first = hcloud_action_plan.build_action_plan(spec, context)
        altered_context = copy.deepcopy(context)
        altered_context["intent"] = "另一项受控 ECS 规划。"
        second = hcloud_action_plan.build_action_plan(spec, altered_context)

        self.assertNotEqual(first["plan_fingerprint"], second["plan_fingerprint"])
        self.assertNotEqual(first["context_fingerprint"], second["context_fingerprint"])

    def test_timeout_result_is_normalized_without_replaying_submit(self) -> None:
        source = self.load(FIXTURES / "timeout-submit-result.json")

        result = hcloud_operation_result.build_operation_result(source, "submit")

        self.assertEqual(result["schema_version"], "operation-result/v1")
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["error_policy"]["retry"], "read_back_before_retry")
        self.assertFalse(result["error_policy"]["automatic_retry_allowed"])
        validation = hcloud_unified_contracts.validate_contract("operation-result", result)
        self.assertTrue(validation["success"], validation["errors"])

    def test_success_result_keeps_follow_up_verification_visible(self) -> None:
        source = self.load(FIXTURES / "success-plan-result.json")

        result = hcloud_operation_result.build_operation_result(source, "plan")

        self.assertEqual(result["outcome"], "succeeded")
        self.assertEqual(result["next_actions"], [{"action": "continue_lifecycle", "stage": "plan"}])

    def test_result_adapter_rejects_unredacted_secret_fields(self) -> None:
        source = {"success": False, "api_key": "not-allowed"}

        with self.assertRaisesRegex(ValueError, "secret-bearing fields"):
            hcloud_operation_result.build_operation_result(source, "submit")

    def test_lts_metadata_read_plan_is_blocked_until_bounded_inputs_exist(self) -> None:
        result = hcloud_metadata_read_plan.generate_metadata_read_plan(
            TRIAL_SPECS / "lts-list-logs.json",
            FIXTURES / "lts-context.json",
        )

        self.assertTrue(result["success"], result.get("errors"))
        plan = result["metadata_read_plan"]
        self.assertEqual(plan["admission"]["status"], "blocked")
        self.assertEqual(plan["output_policy"]["policy_id"], "LTS:ListLogs")
        self.assertEqual(plan["output_policy"]["effective_mode"], "summary")
        self.assertEqual(plan["execution_authority"]["metadata_read_authority"], "not_implemented")
        self.assertTrue(any(item["status"] == "missing" for item in plan["query_requirements"]))

    def test_cts_metadata_read_plan_can_only_be_eligible_for_a_future_adapter(self) -> None:
        result = hcloud_metadata_read_plan.generate_metadata_read_plan(
            TRIAL_SPECS / "cts-list-traces.json",
            FIXTURES / "cts-ready-context.json",
        )

        self.assertTrue(result["success"], result.get("errors"))
        plan = result["metadata_read_plan"]
        self.assertEqual(plan["admission"]["status"], "eligible_for_future_adapter")
        self.assertEqual(plan["output_policy"]["policy_id"], "CTS:ListTraces")
        self.assertIn("no hcloud command", result["execution_boundary"])
        validation = hcloud_unified_contracts.validate_contract("metadata-read-plan", plan)
        self.assertTrue(validation["success"], validation["errors"])

    def test_metadata_read_rejects_mutating_or_generated_semantics(self) -> None:
        context = self.load(FIXTURES / "ecs-context.json")
        mutating_spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        generated_read_spec = self.load(TRIAL_SPECS / "lts-list-logs.json")
        generated_read_spec["lifecycle"] = "generated"

        mutating_plan = hcloud_metadata_read_plan.build_metadata_read_plan(mutating_spec, context)
        generated_plan = hcloud_metadata_read_plan.build_metadata_read_plan(generated_read_spec, self.load(FIXTURES / "lts-context.json"))

        self.assertEqual(mutating_plan["admission"]["status"], "blocked")
        self.assertTrue(any("effect=read" in reason for reason in mutating_plan["admission"]["reasons"]))
        self.assertEqual(generated_plan["admission"]["status"], "blocked")
        self.assertTrue(any("reviewed or curated" in reason for reason in generated_plan["admission"]["reasons"]))

    def test_metadata_read_rejects_catalog_fingerprint_drift(self) -> None:
        spec = self.load(TRIAL_SPECS / "cts-list-traces.json")
        spec["catalog_ref"]["catalog_fingerprint"] = "sha256:" + "0" * 64

        plan = hcloud_metadata_read_plan.build_metadata_read_plan(
            spec,
            self.load(FIXTURES / "cts-ready-context.json"),
        )

        self.assertEqual(plan["admission"]["status"], "blocked")
        self.assertTrue(any("catalog fingerprint drift" in reason for reason in plan["admission"]["reasons"]))

    def test_shadow_audit_reports_generic_mutation_path_as_runtime_plan_only(self) -> None:
        report = hcloud_entrypoint_shadow_audit.build_shadow_report(
            "scripts/hcloud_safe_exec.py",
            TRIAL_SPECS / "ecs-create-server.json",
            FIXTURES / "ecs-context.json",
        )

        self.assertEqual(report["legacy_entrypoint"]["group_id"], "generic_hcloud_dispatch")
        self.assertEqual(report["comparison"]["migration_status"], "runtime_plan_only_closed_pending_skill_controlled_entry")
        finding_ids = {item["id"] for item in report["comparison"]["findings"]}
        self.assertIn("legacy_mutation_path_closed_plan_only", finding_ids)
        self.assertNotIn("legacy_admission_is_not_a_unified_contract", finding_ids)
        self.assertEqual(report["comparison"]["unified_authority"], "not_implemented")

    def test_shadow_audit_exposes_unbridged_read_path_without_executing_it(self) -> None:
        report = hcloud_entrypoint_shadow_audit.build_shadow_report(
            "scripts/hcloud_lts_readonly.py",
            TRIAL_SPECS / "cts-list-traces.json",
            FIXTURES / "cts-ready-context.json",
        )

        self.assertEqual(report["legacy_entrypoint"]["effect"], "cloud_read")
        finding_ids = {item["id"] for item in report["comparison"]["findings"]}
        self.assertIn("legacy_read_path_not_yet_bridged", finding_ids)
        self.assertIn("not executed", report["execution_boundary"])

    def test_shadow_audit_rejects_an_unreviewed_source_path(self) -> None:
        with self.assertRaisesRegex(hcloud_entrypoint_shadow_audit.ShadowAuditError, "not a reviewed entrypoint"):
            hcloud_entrypoint_shadow_audit.build_shadow_report(
                "scripts/not-a-real-entrypoint.py",
                TRIAL_SPECS / "ecs-create-server.json",
                FIXTURES / "ecs-context.json",
            )

    def test_controlled_admission_prepares_but_never_grants_ecs_submit(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        execution_intent = self.build_ecs_execution_intent(spec)
        action_plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(action_plan, execution_intent)

        result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            context,
            execution_intent,
            confirmation,
        )

        self.assertTrue(result["success"], result.get("errors"))
        authorization = result["submission_authorization"]
        self.assertEqual(authorization["admission"]["status"], "prepared_for_future_adapter")
        self.assertEqual(authorization["execution_authority"]["submission_authority"], "not_implemented")
        self.assertEqual(authorization["action_plan_fingerprint"], action_plan["plan_fingerprint"])
        self.assertEqual(
            authorization["confirmation"]["preflight_evidence_fingerprint"],
            hcloud_unified_contracts.fingerprint(confirmation["preflight_evidence"]),
        )
        validation = hcloud_unified_contracts.validate_contract("submission-authorization", authorization)
        self.assertTrue(validation["success"], validation["errors"])

    def test_controlled_admission_rejects_intent_changed_after_confirmation(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        execution_intent = self.build_ecs_execution_intent(spec)
        action_plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(action_plan, execution_intent)
        execution_intent["parameters"]["server_count"] = 2

        result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            context,
            execution_intent,
            confirmation,
        )

        self.assertFalse(result["success"])
        self.assertIn("confirmation does not bind the current Execution Intent fingerprint", result["errors"])

    def test_controlled_admission_rejects_missing_preflight_evidence(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        execution_intent = self.build_ecs_execution_intent(spec)
        action_plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(action_plan, execution_intent)
        confirmation["preflight_evidence"] = []

        result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            context,
            execution_intent,
            confirmation,
        )

        self.assertFalse(result["success"])
        self.assertTrue(any("not confirmed as passed" in item for item in result["errors"]))

    def test_controlled_admission_rejects_a_missing_semantic_input(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        execution_intent = self.build_ecs_execution_intent(spec)
        execution_intent["parameters"].pop("image_id")
        action_plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(action_plan, execution_intent)

        result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            context,
            execution_intent,
            confirmation,
        )

        self.assertFalse(result["success"])
        self.assertIn("execution intent misses required input image_id", result["errors"])

    def test_controlled_admission_requires_a_refreshed_dns_context(self) -> None:
        spec = self.load(TRIAL_SPECS / "dns-create-record-set.json")
        stale_context = self.load(FIXTURES / "dns-context.json")
        execution_intent = self.build_dns_execution_intent(spec)
        stale_plan = hcloud_action_plan.build_action_plan(spec, stale_context)
        stale_confirmation = self.build_confirmation(stale_plan, execution_intent)

        stale_result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            stale_context,
            execution_intent,
            stale_confirmation,
        )
        self.assertFalse(stale_result["success"])
        self.assertIn(
            "Action Plan still has unresolved missing inputs: record_values",
            stale_result["errors"],
        )

        ready_context = copy.deepcopy(stale_context)
        ready_context["missing_inputs"] = []
        ready_context["intent"] = "创建经过确认的 DNS A 记录集。"
        ready_plan = hcloud_action_plan.build_action_plan(spec, ready_context)
        ready_confirmation = self.build_confirmation(ready_plan, execution_intent)
        ready_result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            ready_context,
            execution_intent,
            ready_confirmation,
        )
        self.assertTrue(ready_result["success"], ready_result.get("errors"))
        self.assertEqual(
            ready_result["submission_authorization"]["execution_authority"]["submission_authority"],
            "not_implemented",
        )

    def test_controlled_admission_rejects_reviewed_or_read_semantics(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        execution_intent = self.build_ecs_execution_intent(spec)
        confirmation = self.build_confirmation(hcloud_action_plan.build_action_plan(spec, context), execution_intent)
        spec["lifecycle"] = "reviewed"

        result = hcloud_controlled_admission.build_submission_authorization(
            spec,
            context,
            execution_intent,
            confirmation,
        )
        self.assertFalse(result["success"])
        self.assertIn("controlled submission preparation requires a curated Action Spec", result["errors"])

        read_spec = self.load(TRIAL_SPECS / "cts-list-traces.json")
        read_spec["lifecycle"] = "curated"
        read_context = self.load(FIXTURES / "cts-ready-context.json")
        read_intent = {
            "schema_version": "execution-intent/v1",
            "execution_family": "hcloud",
            "action_spec_ref": {
                "id": read_spec["id"],
                "lifecycle": read_spec["lifecycle"],
                "fingerprint": hcloud_unified_contracts.fingerprint(read_spec),
            },
            "catalog_ref": copy.deepcopy(read_spec["catalog_ref"]),
            "scope": {"region": "cn-north-4", "project_id": "example-project"},
            "parameters": {"limit": 20},
        }
        read_confirmation = self.build_confirmation(hcloud_action_plan.build_action_plan(read_spec, read_context), read_intent)
        read_result = hcloud_controlled_admission.build_submission_authorization(
            read_spec,
            read_context,
            read_intent,
            read_confirmation,
        )
        self.assertFalse(read_result["success"])
        self.assertIn("controlled submission preparation is for non-read effects only", read_result["errors"])

    def test_controlled_admission_cli_has_no_execute_flag(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                hcloud_controlled_admission.parse_args(
                    [
                        "--action-spec", "spec.json",
                        "--cloud-context", "context.json",
                        "--execution-intent", "intent.json",
                        "--confirmation", "confirmation.json",
                        "--execute",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
