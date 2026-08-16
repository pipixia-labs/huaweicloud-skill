"""Tests for local ECS job waiter helpers."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hcloud_ecs_wait_job.py"
SPEC = importlib.util.spec_from_file_location("hcloud_ecs_wait_job", SCRIPT)
assert SPEC and SPEC.loader
hcloud_ecs_wait_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_ecs_wait_job)


class EcsWaitJobTest(unittest.TestCase):
    """Validate status extraction and classification without calling hcloud."""

    def test_extract_status_from_top_level_response(self) -> None:
        status = hcloud_ecs_wait_job.extract_status({"status": "SUCCESS"})

        self.assertEqual(status, "SUCCESS")

    def test_extract_status_from_nested_job_response(self) -> None:
        status = hcloud_ecs_wait_job.extract_status({"job": {"status": "running"}})

        self.assertEqual(status, "RUNNING")

    def test_classify_terminal_statuses(self) -> None:
        self.assertEqual(hcloud_ecs_wait_job.classify_status("SUCCESS"), "success")
        self.assertEqual(hcloud_ecs_wait_job.classify_status("FAILED"), "failure")
        self.assertEqual(hcloud_ecs_wait_job.classify_status("RUNNING"), "running")
        self.assertEqual(hcloud_ecs_wait_job.classify_status("QUEUED"), "unknown")

    def test_print_command_result_marks_job_only_verification_scope(self) -> None:
        args = SimpleNamespace(
            job_id="job-1",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            server_id=["server-1"],
            server_name=[],
            print_command_only=True,
        )

        result = hcloud_ecs_wait_job.wait_for_job(args)

        self.assertEqual(result["verification_scope"], "job_terminal_only")
        self.assertFalse(result["resource_verification"]["performed"])
        self.assertTrue(result["resource_verification"]["required_for_create_completion"])
        self.assertTrue(result["resource_verification"]["has_targets"])
        self.assertIn("hcloud_ecs_verify_active.py", result["resource_verification"]["recommended_followup_command"][1])
        self.assertIn("--server-id=server-1", result["resource_verification"]["recommended_followup_command"])

    def test_successful_terminal_job_returns_identifier_receipt(self) -> None:
        args = SimpleNamespace(
            job_id="job-1",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            server_id=[],
            server_name=["web-server"],
            interval=0.01,
            timeout=1.0,
            command_timeout=1,
            max_command_failures=1,
            print_command_only=False,
        )
        with mock.patch.object(
            hcloud_ecs_wait_job,
            "run_show_job",
            return_value={
                "success": True,
                "return_code": 0,
                "parsed_json": {
                    "status": "SUCCESS",
                    "entities": {"serverId": "server-1"},
                },
            },
        ):
            result = hcloud_ecs_wait_job.wait_for_job(args)

        self.assertTrue(result["success"])
        self.assertEqual(
            result["final_identifiers"],
            {"entities.serverId": ["server-1"]},
        )


if __name__ == "__main__":
    unittest.main()
