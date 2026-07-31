"""Tests for portable unified-operation schema and semantic validation."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "unified-contracts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_unified_contracts  # noqa: E402


class UnifiedContractsTests(unittest.TestCase):
    """Keep portable contracts strict without making them an execution mechanism."""

    def load_fixture(self, name: str) -> dict:
        return hcloud_unified_contracts.load_document(FIXTURES / name)

    def test_all_contract_fixtures_validate(self) -> None:
        fixtures = {
            "cloud-context": "cloud-context.json",
            "action-spec": "action-spec.json",
            "action-plan": "action-plan.json",
            "execution-intent": "execution-intent.json",
            "metadata-read-plan": "metadata-read-plan.json",
            "operation-result": "operation-result.json",
            "submission-authorization": "submission-authorization.json",
        }
        for contract, fixture_name in fixtures.items():
            with self.subTest(contract=contract):
                result = hcloud_unified_contracts.validate_contract(contract, self.load_fixture(fixture_name))
                self.assertTrue(result["success"], result["errors"])
                self.assertTrue(result["canonical_fingerprint"].startswith("sha256:"))
                self.assertIn("does not grant execution permission", result["validation_boundary"])

    def test_fingerprint_is_stable_across_key_order(self) -> None:
        document = self.load_fixture("cloud-context.json")
        reordered = {key: document[key] for key in reversed(list(document))}

        self.assertEqual(hcloud_unified_contracts.fingerprint(document), hcloud_unified_contracts.fingerprint(reordered))

    def test_hcloud_action_spec_requires_exact_catalog_reference(self) -> None:
        document = self.load_fixture("action-spec.json")
        document.pop("catalog_ref")

        result = hcloud_unified_contracts.validate_contract("action-spec", document)
        self.assertFalse(result["success"])
        self.assertIn("hcloud Action Spec requires catalog_ref", result["errors"])

    def test_action_spec_rejects_copied_http_facts(self) -> None:
        document = self.load_fixture("action-spec.json")
        document["path"] = "/v1/{project_id}/cloudservers"

        result = hcloud_unified_contracts.validate_contract("action-spec", document)
        self.assertFalse(result["success"])
        self.assertTrue(any("reference rather than copy API facts" in error for error in result["errors"]))

    def test_contracts_reject_secret_bearing_fields(self) -> None:
        document = self.load_fixture("cloud-context.json")
        document["api_key"] = "not-allowed-in-contracts"

        result = hcloud_unified_contracts.validate_contract("cloud-context", document)
        self.assertFalse(result["success"])
        self.assertIn("secret-bearing field is not allowed in contracts: api_key", result["errors"])

    def test_submit_plan_requires_curated_spec_and_confirmation_requirement(self) -> None:
        document = self.load_fixture("action-plan.json")
        document["allowed_stage"] = "submit"
        document["action_spec_ref"]["lifecycle"] = "reviewed"
        document.pop("confirmation")

        result = hcloud_unified_contracts.validate_contract("action-plan", document)
        self.assertFalse(result["success"])
        self.assertIn("submit stage requires a curated Action Spec reference", result["errors"])
        self.assertIn("submit stage requires a confirmation requirement object", result["errors"])

    def test_redaction_marker_is_allowed_but_does_not_create_an_authorization_token(self) -> None:
        document = copy.deepcopy(self.load_fixture("cloud-context.json"))
        document["credential"] = "***"

        result = hcloud_unified_contracts.validate_contract("cloud-context", document)
        self.assertTrue(result["success"], result["errors"])


if __name__ == "__main__":
    unittest.main()
