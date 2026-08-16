"""Tests for generic registered-read async convergence."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

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


hcloud_async_job_wait = load_module(
    "hcloud_async_job_wait",
    SCRIPTS / "hcloud_async_job_wait.py",
)


def wait_args(**overrides) -> SimpleNamespace:
    """Return a complete generic async waiter namespace."""
    values = {
        "service": "EVS",
        "operation": "ShowJob",
        "param": ["job_id=job-1"],
        "arg": [],
        "region": "cn-north-4",
        "project_id": "project-1",
        "profile": None,
        "status_path": ["job.status", "status"],
        "success_status": ["SUCCESS", "COMPLETED"],
        "failure_status": ["FAILED", "ERROR"],
        "interval": 0.01,
        "timeout": 1.0,
        "command_timeout": 1,
        "max_command_failures": 2,
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AsyncJobWaitTest(unittest.TestCase):
    """Validate generic status extraction and bounded polling."""

    def test_extract_path_supports_nested_objects_and_list_indexes(self) -> None:
        payload = {"jobs": [{"state": "RUNNING"}, {"state": "SUCCESS"}]}

        self.assertEqual(
            hcloud_async_job_wait.extract_path(payload, "jobs.1.state"),
            "SUCCESS",
        )

    def test_wait_uses_registered_read_query_until_success(self) -> None:
        responses = [
            {
                "success": True,
                "result": {"parsed_json": {"job": {"status": "RUNNING"}}},
            },
            {
                "success": True,
                "result": {
                    "parsed_json": {
                        "job": {
                            "status": "SUCCESS",
                            "resource_id": "volume-1",
                        }
                    }
                },
            },
        ]
        with mock.patch.object(
            hcloud_async_job_wait.hcloud_resource_query,
            "build_plan",
            side_effect=responses,
        ) as build_plan:
            result = hcloud_async_job_wait.wait_for_job(wait_args())

        self.assertEqual(build_plan.call_count, 2)
        self.assertTrue(result["success"])
        self.assertEqual(result["final_status"], "SUCCESS")
        self.assertEqual(
            result["final_identifiers"],
            {"job.resource_id": ["volume-1"]},
        )

    def test_unregistered_or_mutating_query_never_falls_back_to_shell(self) -> None:
        with mock.patch.object(
            hcloud_async_job_wait.hcloud_resource_query,
            "build_plan",
            return_value={
                "success": False,
                "error": "Operation is mutating; use a guarded planner.",
            },
        ):
            result = hcloud_async_job_wait.wait_for_job(wait_args(max_command_failures=1))

        self.assertFalse(result["success"])
        self.assertEqual(result["classification"], "query_failure")
        self.assertNotIn("command", result)


if __name__ == "__main__":
    unittest.main()
