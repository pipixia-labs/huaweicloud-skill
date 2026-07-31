"""Tests for host handoff preparation and adapter readiness boundaries."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TRIAL_SPECS = ROOT / "references" / "action-semantics" / "trial"
FIXTURES = ROOT / "tests" / "fixtures" / "unified-action-plan"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_action_plan  # noqa: E402
import hcloud_controlled_adapter_registry  # noqa: E402
import hcloud_controlled_submit_handoff  # noqa: E402
import hcloud_unified_contracts  # noqa: E402


class ControlledSubmitHandoffTests(unittest.TestCase):
    """Ensure host handoff never turns an incomplete mapping into execution authority."""

    def load(self, path: Path) -> dict:
        """Load one local JSON test input."""
        return hcloud_unified_contracts.load_document(path)

    def build_ecs_intent(self, spec: dict) -> dict:
        """Build a valid secret-free ECS intent for local admission preparation."""
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
            "idempotency": {"client_token": "local-handoff-test-001"},
        }

    def build_confirmation(self, plan: dict, intent: dict) -> dict:
        """Bind test confirmation to the exact local plan and intent."""
        return {
            "status": "confirmed",
            "approval_id": "local-handoff-approval-001",
            "reviewed_action_plan_fingerprint": plan["plan_fingerprint"],
            "reviewed_execution_intent_fingerprint": hcloud_unified_contracts.fingerprint(intent),
            "preflight_evidence": [{"id": item["id"], "status": "passed"} for item in plan["preflight"]],
        }

    def build_dns_intent(self, spec: dict) -> dict:
        """Build a valid narrow DNS A-record intent for local handoff preparation."""
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
                "zone_id": "0123456789abcdef0123456789abcdef",
                "record_name": "www.example.com.",
                "record_type": "A",
                "record_values": ["192.0.2.10"],
                "ttl": 300,
            },
            "idempotency": {"client_token": "local-dns-handoff-test-001"},
        }

    def test_current_registry_exposes_evidence_gaps_instead_of_ready_adapters(self) -> None:
        registry = hcloud_controlled_adapter_registry.load_registry()

        report = hcloud_controlled_adapter_registry.audit_registry(registry)

        self.assertTrue(report["success"], report["root_errors"])
        self.assertEqual(report["controlled_submit_status"], "ready_for_selected_handoffs")
        self.assertEqual(
            report["ready_for_handoff"],
            ["ecs-create-server-controlled-hcloud-v1", "dns-create-record-set-controlled-hcloud-v1"],
        )
        adapters = {item["id"]: item for item in report["adapters"]}
        self.assertEqual(adapters["ecs-create-server-controlled-hcloud-v1"]["mapping_gaps"], [])
        self.assertEqual(adapters["dns-create-record-set-controlled-hcloud-v1"]["mapping_gaps"], [])

    def test_ecs_keypair_create_can_prepare_a_host_handoff_without_cloud_execution(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        intent = self.build_ecs_intent(spec)
        plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(plan, intent)

        result = hcloud_controlled_submit_handoff.build_controlled_submit_handoff(
            spec,
            context,
            intent,
            confirmation,
            hcloud_controlled_adapter_registry.load_registry(),
        )

        self.assertTrue(result["success"], result.get("errors"))
        handoff = result["controlled_submit_handoff"]
        self.assertEqual(handoff["adapter_ref"]["id"], "ecs-create-server-controlled-hcloud-v1")
        self.assertEqual(handoff["request_preparation"]["mapping_id"], "ecs_create_keypair_v1")
        self.assertEqual(handoff["execution_authority"]["mode"], "plan_only")
        self.assertEqual(handoff["execution_authority"]["submission_authority"], "host_adapter_required")
        self.assertIn("no hcloud", result["execution_boundary"].lower())

    def test_ecs_request_mapping_rejects_public_ssh_rule_before_handoff(self) -> None:
        spec = self.load(TRIAL_SPECS / "ecs-create-server.json")
        context = self.load(FIXTURES / "ecs-context.json")
        intent = self.build_ecs_intent(spec)
        rule = intent["parameters"]["security_group_rule_evidence"]["security_group"]["security_group_rules"][0]
        rule["remote_ip_prefix"] = "0.0.0.0/0"
        plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(plan, intent)

        result = hcloud_controlled_submit_handoff.build_controlled_submit_handoff(
            spec,
            context,
            intent,
            confirmation,
            hcloud_controlled_adapter_registry.load_registry(),
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "CONTROLLED_REQUEST_MAPPING_REJECTED")
        self.assertTrue(any("Security group policy violation" in item for item in result["errors"]))

    def test_dns_a_record_can_prepare_a_host_handoff_without_cloud_execution(self) -> None:
        spec = self.load(TRIAL_SPECS / "dns-create-record-set.json")
        context = self.load(FIXTURES / "dns-context.json")
        context["missing_inputs"] = []
        intent = self.build_dns_intent(spec)
        plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(plan, intent)

        result = hcloud_controlled_submit_handoff.build_controlled_submit_handoff(
            spec,
            context,
            intent,
            confirmation,
            hcloud_controlled_adapter_registry.load_registry(),
        )

        self.assertTrue(result["success"], result.get("errors"))
        handoff = result["controlled_submit_handoff"]
        self.assertEqual(handoff["adapter_ref"]["id"], "dns-create-record-set-controlled-hcloud-v1")
        self.assertEqual(handoff["request_preparation"]["mapping_id"], "dns_record_set_a_v1")
        self.assertEqual(handoff["execution_authority"]["mode"], "plan_only")
        self.assertEqual(handoff["execution_authority"]["submission_authority"], "host_adapter_required")
        self.assertNotIn("parameters", handoff["request_preparation"])
        self.assertIn("no hcloud", result["execution_boundary"].lower())

    def test_dns_request_mapping_rejects_invalid_ttl_before_handoff(self) -> None:
        spec = self.load(TRIAL_SPECS / "dns-create-record-set.json")
        context = self.load(FIXTURES / "dns-context.json")
        context["missing_inputs"] = []
        intent = self.build_dns_intent(spec)
        intent["parameters"]["ttl"] = 0
        plan = hcloud_action_plan.build_action_plan(spec, context)
        confirmation = self.build_confirmation(plan, intent)

        result = hcloud_controlled_submit_handoff.build_controlled_submit_handoff(
            spec,
            context,
            intent,
            confirmation,
            hcloud_controlled_adapter_registry.load_registry(),
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "CONTROLLED_REQUEST_MAPPING_REJECTED")
        self.assertIn("ttl must be an integer from 1 to 2147483647", result["errors"])

    def test_ready_declaration_cannot_hide_unresolved_mapping_gaps(self) -> None:
        registry = hcloud_controlled_adapter_registry.load_registry()
        adapter = registry["adapters"][0]
        adapter["status"] = "ready_for_handoff"
        adapter["request_mapping"]["status"] = "ready_for_handoff"
        adapter["request_mapping"]["blocking_reasons"] = []
        adapter["request_mapping"]["candidate_bindings"] = []

        report = hcloud_controlled_adapter_registry.audit_registry(registry)
        entry = report["adapters"][0]

        self.assertFalse(report["success"])
        self.assertEqual(entry["status"], "blocked")
        self.assertIn("ready adapter has unresolved request mapping gaps", entry["errors"])

    def test_handoff_contract_is_fixed_to_host_required_plan_only(self) -> None:
        handoff = {
            "schema_version": "controlled-submit-handoff/v1",
            "adapter_ref": {"id": "example-adapter", "registry_fingerprint": "sha256:" + "1" * 64},
            "action_spec_ref": {
                "id": "huaweicloud.example.create.v1",
                "lifecycle": "curated",
                "fingerprint": "sha256:" + "2" * 64,
            },
            "catalog_ref": {
                "catalog_fingerprint": "sha256:" + "3" * 64,
                "service": "EXAMPLE",
                "operation": "CreateExample",
                "version": "v1",
            },
            "submission_authorization_fingerprint": "sha256:" + "4" * 64,
            "execution_intent_fingerprint": "sha256:" + "5" * 64,
            "request_preparation": {
                "mapping_id": "example-mapping",
                "request_fingerprint": "sha256:" + "6" * 64,
                "payload_delivery": "host_rederives_from_fingerprint_bound_execution_intent",
            },
            "host_authority_requirements": {
                "verification_location": "host_adapter",
                "requirements": ["identity", "one_time", "expiry", "audit"],
            },
            "execution_authority": {"mode": "plan_only", "submission_authority": "host_adapter_required"},
        }
        handoff["handoff_fingerprint"] = hcloud_unified_contracts.fingerprint(
            handoff,
            excluded_fields={"handoff_fingerprint"},
        )

        valid = hcloud_unified_contracts.validate_contract("controlled-submit-handoff", handoff)
        self.assertTrue(valid["success"], valid["errors"])
        handoff["execution_authority"]["mode"] = "submit"
        invalid = hcloud_unified_contracts.validate_contract("controlled-submit-handoff", handoff)
        self.assertFalse(invalid["success"])
        self.assertIn("controlled submit handoff must retain execution_authority.mode=plan_only", invalid["errors"])
        self.assertIn("handoff_fingerprint does not match the handoff content", invalid["errors"])


if __name__ == "__main__":
    unittest.main()
