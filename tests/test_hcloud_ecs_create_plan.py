"""Tests for local ECS create planning helpers."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hcloud_ecs_create_plan.py"
SPEC = importlib.util.spec_from_file_location("hcloud_ecs_create_plan", SCRIPT)
assert SPEC and SPEC.loader
hcloud_ecs_create_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_ecs_create_plan)


def minimal_payload() -> dict:
    """Return a complete minimal ECS create payload for local validation."""
    return {
        "path": {"project_id": "project-1"},
        "body": {
            "server": {
                "name": "ecs-test",
                "availability_zone": "cn-north-4a",
                "flavorRef": "s6.large.2",
                "imageRef": "image-1",
                "vpcid": "vpc-1",
                "nics": [{"subnet_id": "subnet-1"}],
                "security_groups": [{"id": "sg-1"}],
                "root_volume": {"volumetype": "SSD"},
                "key_name": "keypair-1",
                "count": 1,
            }
        },
    }


def security_group_evidence(remote_ip_prefix: str = "203.0.113.10/32", port: int = 22) -> dict:
    """Return readback evidence for the security group referenced by minimal_payload."""
    return {
        "security_group": {
            "id": "sg-1",
            "security_group_rules": [
                {
                    "id": "rule-1",
                    "security_group_id": "sg-1",
                    "direction": "ingress",
                    "protocol": "tcp",
                    "remote_ip_prefix": remote_ip_prefix,
                    "port_range_min": port,
                    "port_range_max": port,
                }
            ],
        }
    }


def write_security_group_evidence(directory: Path, evidence: dict | None = None) -> str:
    """Write security group readback evidence and return its path."""
    path = directory / "security-group-evidence.json"
    path.write_text(json.dumps(evidence or security_group_evidence()), encoding="utf-8")
    return str(path)


def validate_payload(payload: dict, **kwargs) -> dict:
    """Validate a payload with default security group evidence for unit tests."""
    kwargs.setdefault("security_group_evidence", security_group_evidence())
    return hcloud_ecs_create_plan.validate_payload(payload, **kwargs)


class EcsCreatePlanTest(unittest.TestCase):
    """Validate ECS create planner behavior without calling hcloud."""

    def test_validate_payload_rejects_placeholders(self) -> None:
        payload = minimal_payload()
        payload["path"]["project_id"] = "<project_id>"

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertIn(
            "Unresolved placeholder at path.project_id: <project_id>",
            validation["errors"],
        )

    def test_validate_payload_accepts_complete_minimal_payload(self) -> None:
        validation = validate_payload(minimal_payload())

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["errors"], [])
        self.assertEqual(validation["security_group_rule_evidence"]["rule_count"], 1)

    def test_validate_payload_rejects_referenced_security_group_without_rule_evidence(self) -> None:
        validation = hcloud_ecs_create_plan.validate_payload(minimal_payload())

        self.assertFalse(validation["valid"])
        self.assertIn(hcloud_ecs_create_plan.SECURITY_GROUP_EVIDENCE_ERROR, validation["errors"])
        self.assertTrue(validation["security_group_rule_evidence"]["required"])
        self.assertFalse(validation["security_group_rule_evidence"]["provided"])

    def test_build_result_generates_dryrun_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "ecs.json"
            path.write_text(json.dumps(minimal_payload()), encoding="utf-8")
            tmp_path = Path(tmp_dir)
            args = SimpleNamespace(
                json_input_file=str(path),
                operation="CreateServers",
                region="cn-north-4",
                profile=None,
                mode="dryrun",
                confirm_submit=False,
                allow_placeholders=False,
                max_count=10,
                allow_large_count=False,
                security_group_evidence_file=write_security_group_evidence(tmp_path),
            )

            result = hcloud_ecs_create_plan.build_result(args)

        self.assertTrue(result["success"])
        self.assertIn("--arg=--dryrun", result["commands"]["safe_exec"])
        self.assertIn("--arg=--cli-output=json", result["commands"]["safe_exec"])
        self.assertIn("--expect-json", result["commands"]["safe_exec"])
        self.assertIn("safe_exec_shell", result["commands"])
        self.assertIn("--cli-region=cn-north-4", result["commands"]["hcloud"])

    def test_build_result_writes_redacted_journal_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = minimal_payload()
            payload["body"]["server"].pop("key_name")
            payload["body"]["server"]["adminPass"] = "password-value"
            path = Path(tmp_dir) / "ecs.json"
            journal = Path(tmp_dir) / "journal.jsonl"
            path.write_text(json.dumps(payload), encoding="utf-8")
            tmp_path = Path(tmp_dir)
            args = SimpleNamespace(
                json_input_file=str(path),
                operation="CreateServers",
                region="cn-north-4",
                profile=None,
                mode="dryrun",
                confirm_submit=False,
                allow_placeholders=False,
                max_count=10,
                allow_large_count=False,
                journal=str(journal),
                security_group_evidence_file=write_security_group_evidence(tmp_path),
            )

            result = hcloud_ecs_create_plan.build_result(args)
            raw_journal = journal.read_text(encoding="utf-8")
            event = json.loads(raw_journal)

        self.assertTrue(result["success"])
        self.assertEqual(event["type"], "plan")
        self.assertEqual(event["stage"], "ecs_create_plan")
        self.assertNotIn("password-value", raw_journal)

    def test_submit_mode_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "ecs.json"
            path.write_text(json.dumps(minimal_payload()), encoding="utf-8")
            tmp_path = Path(tmp_dir)
            args = SimpleNamespace(
                json_input_file=str(path),
                operation="CreateServers",
                region="cn-north-4",
                profile=None,
                mode="submit",
                confirm_submit=False,
                allow_placeholders=False,
                max_count=10,
                allow_large_count=False,
                security_group_evidence_file=write_security_group_evidence(tmp_path),
            )

            result = hcloud_ecs_create_plan.build_result(args)

        self.assertFalse(result["success"])
        self.assertIn("Non-dryrun submit mode requires --confirm-submit.", result["validation"]["errors"])

    def test_allow_placeholders_does_not_generate_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            payload = minimal_payload()
            payload["path"]["project_id"] = "<project_id>"
            path = Path(tmp_dir) / "ecs.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            tmp_path = Path(tmp_dir)
            args = SimpleNamespace(
                json_input_file=str(path),
                operation="CreateServers",
                region="cn-north-4",
                profile=None,
                mode="dryrun",
                confirm_submit=False,
                allow_placeholders=True,
                max_count=10,
                allow_large_count=False,
                security_group_evidence_file=write_security_group_evidence(tmp_path),
            )

            result = hcloud_ecs_create_plan.build_result(args)

        self.assertTrue(result["success"])
        self.assertFalse(result["ready_to_run"])
        self.assertEqual(result["commands"], {})

    def test_validate_payload_rejects_embedded_placeholders(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["name"] = "ecs-<env>"

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertIn("Unresolved placeholder at body.server.name: ecs-<env>", validation["errors"])

    def test_validate_payload_rejects_large_count_without_override(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["count"] = 11

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertIn(
            "body.server.count exceeds conservative max 10. "
            "Use --allow-large-count only after confirming cost and quota impact.",
            validation["errors"],
        )

    def test_validate_payload_allows_large_count_with_override(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["count"] = 11

        validation = validate_payload(payload, allow_large_count=True)

        self.assertTrue(validation["valid"])

    def test_validate_payload_allows_admin_password_without_keypair(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"].pop("key_name")
        payload["body"]["server"]["adminPass"] = "password-value"

        validation = validate_payload(payload)

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["credential_mode"], "password")
        self.assertIn(
            "SSH credential mode is password; body.server.adminPass must be generated and saved to a restricted credential artifact before submit.",
            validation["warnings"],
        )

    def test_validate_payload_rejects_missing_login_credential(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"].pop("key_name")

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["credential_mode"], "missing")
        self.assertIn(
            "No SSH login credential configured: set exactly one of body.server.key_name or body.server.adminPass.",
            validation["errors"],
        )

    def test_validate_payload_rejects_conflicting_login_credentials(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["adminPass"] = "password-value"

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["credential_mode"], "conflict")
        self.assertIn(
            "Conflicting SSH login credentials: body.server.key_name and body.server.adminPass must not both be set.",
            validation["errors"],
        )

    def test_build_result_adds_keypair_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "ecs.json"
            path.write_text(json.dumps(minimal_payload()), encoding="utf-8")
            tmp_path = Path(tmp_dir)
            args = SimpleNamespace(
                json_input_file=str(path),
                operation="CreateServers",
                region="cn-north-4",
                profile=None,
                mode="dryrun",
                confirm_submit=False,
                allow_placeholders=False,
                max_count=10,
                allow_large_count=False,
                security_group_evidence_file=write_security_group_evidence(tmp_path),
            )

            result = hcloud_ecs_create_plan.build_result(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["validation"]["credential_mode"], "keypair")
        self.assertIn(
            "Before submit, verify the local private key that matches body.server.key_name and keep it chmod 600.",
            result["next_steps"],
        )

    def test_validate_payload_warns_when_security_group_is_missing(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"].pop("security_groups")

        validation = validate_payload(payload)

        self.assertTrue(validation["valid"])
        self.assertIn(
            "No body.server.security_groups[0].id found. Huawei Cloud may bind the default security group, "
            "but network exposure rules should be reviewed before submit.",
            validation["warnings"],
        )

    def test_validate_payload_rejects_embedded_unrestricted_sensitive_ingress_rule(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["security_group_rules"] = [
            {
                "direction": "ingress",
                "protocol": "tcp",
                "remote_ip_prefix": "0.0.0.0/0",
                "port_range_min": 80,
                "port_range_max": 80,
            }
        ]

        validation = validate_payload(payload)

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["policy_violations"][0]["code"], "unrestricted_sensitive_ingress_port")
        self.assertEqual(validation["policy_violations"][0]["ports"], [80])
        self.assertTrue(
            any(error.startswith("Security group policy violation") for error in validation["errors"]),
            validation["errors"],
        )

    def test_validate_payload_allows_embedded_restricted_sensitive_ingress_rule(self) -> None:
        payload = minimal_payload()
        payload["body"]["server"]["security_group_rules"] = [
            {
                "direction": "ingress",
                "protocol": "tcp",
                "remote_ip_prefix": "203.0.113.10/32",
                "port_range_min": 22,
                "port_range_max": 22,
            }
        ]

        validation = validate_payload(payload)

        self.assertTrue(validation["valid"], validation)
        self.assertEqual(validation["policy_violations"], [])

    def test_validate_payload_rejects_unrestricted_rule_in_external_security_group_evidence(self) -> None:
        validation = hcloud_ecs_create_plan.validate_payload(
            minimal_payload(),
            security_group_evidence=security_group_evidence(remote_ip_prefix="0.0.0.0/0", port=80),
        )

        self.assertFalse(validation["valid"])
        self.assertEqual(validation["policy_violations"][0]["code"], "unrestricted_sensitive_ingress_port")


if __name__ == "__main__":
    unittest.main()
