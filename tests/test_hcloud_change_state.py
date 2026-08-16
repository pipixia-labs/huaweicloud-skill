"""Tests for durable, service-agnostic Huawei change lifecycle state."""

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


hcloud_change_state = load_module(
    "hcloud_change_state",
    SCRIPTS / "hcloud_change_state.py",
)


class ChangeStateTest(unittest.TestCase):
    """Validate generic request identity, receipts, and resume decisions."""

    def test_request_fingerprint_is_stable_for_equivalent_payloads(self) -> None:
        first = hcloud_change_state.request_fingerprint(
            {
                "service": "RDS",
                "operation": "CreateInstance",
                "submit": ["hcloud", "RDS", "CreateInstance/v3"],
            }
        )
        second = hcloud_change_state.request_fingerprint(
            {
                "submit": ["hcloud", "RDS", "CreateInstance/v3"],
                "operation": "CreateInstance",
                "service": "RDS",
            }
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def test_extract_identifiers_supports_ecs_rds_and_eip_responses(self) -> None:
        cases = [
            (
                {"job_id": "job-ecs", "server_ids": ["server-1", "server-2"]},
                {"job_id": ["job-ecs"], "server_ids": ["server-1", "server-2"]},
            ),
            (
                {"job_id": "job-rds", "instance": {"id": "rds-1"}},
                {"job_id": ["job-rds"], "instance.id": ["rds-1"]},
            ),
            (
                {"publicip": {"id": "eip-1", "public_ip_address": "192.0.2.10"}},
                {"publicip.id": ["eip-1"]},
            ),
            (
                {"jobId": "job-1", "serverIds": ["server-1"]},
                {"jobId": ["job-1"], "serverIds": ["server-1"]},
            ),
        ]

        for response, expected in cases:
            with self.subTest(response=response):
                self.assertEqual(
                    hcloud_change_state.extract_identifiers(response),
                    expected,
                )

    def test_submitted_step_resumes_with_verification_without_resubmit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "change-state.json"
            fingerprint = hcloud_change_state.request_fingerprint({"service": "EIP", "operation": "CreatePublicip"})
            prepared = hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-eip",
                fingerprint=fingerprint,
                request_summary={"service": "EIP", "operation": "CreatePublicip"},
            )
            hcloud_change_state.record_submit(
                path,
                workflow_id="workflow-1",
                step_id="create-eip",
                fingerprint=fingerprint,
                success=True,
                identifiers={"publicip.id": ["eip-1"]},
                verification_params={"publicip_id": "eip-1"},
            )
            resumed = hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-eip",
                fingerprint=fingerprint,
                request_summary={"service": "EIP", "operation": "CreatePublicip"},
            )

        self.assertEqual(prepared["resume_action"], "execute_submit")
        self.assertEqual(resumed["resume_action"], "verify_existing")
        self.assertEqual(resumed["step"]["verification_params"], {"publicip_id": "eip-1"})

    def test_changed_request_cannot_reuse_existing_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "change-state.json"
            first_fingerprint = hcloud_change_state.request_fingerprint(
                {"service": "ECS", "operation": "CreatePostPaidServers", "count": 1}
            )
            hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-server",
                fingerprint=first_fingerprint,
                request_summary={"service": "ECS", "operation": "CreatePostPaidServers"},
            )
            changed = hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-server",
                fingerprint=hcloud_change_state.request_fingerprint({"service": "ECS", "operation": "CreatePostPaidServers", "count": 2}),
                request_summary={"service": "ECS", "operation": "CreatePostPaidServers"},
            )

        self.assertEqual(changed["resume_action"], "fingerprint_mismatch")
        self.assertFalse(changed["can_submit"])

    def test_ambiguous_submit_result_requires_readback_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "change-state.json"
            fingerprint = hcloud_change_state.request_fingerprint({"service": "ECS", "operation": "CreatePostPaidServers"})
            hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-server",
                fingerprint=fingerprint,
                request_summary={"service": "ECS", "operation": "CreatePostPaidServers"},
            )
            hcloud_change_state.record_submit(
                path,
                workflow_id="workflow-1",
                step_id="create-server",
                fingerprint=fingerprint,
                success=False,
            )
            resumed = hcloud_change_state.prepare_step(
                path,
                workflow_id="workflow-1",
                step_id="create-server",
                fingerprint=fingerprint,
                request_summary={"service": "ECS", "operation": "CreatePostPaidServers"},
            )

        self.assertEqual(resumed["step"]["status"], "submit_unknown")
        self.assertEqual(resumed["resume_action"], "verify_existing")
        self.assertFalse(resumed["can_submit"])


if __name__ == "__main__":
    unittest.main()
