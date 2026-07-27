"""Tests for ECS ACTIVE resource verification helpers."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hcloud_ecs_verify_active.py"
SPEC = importlib.util.spec_from_file_location("hcloud_ecs_verify_active", SCRIPT)
assert SPEC and SPEC.loader
hcloud_ecs_verify_active = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_ecs_verify_active)


class EcsVerifyActiveTest(unittest.TestCase):
    """Validate ECS ACTIVE verification without calling hcloud."""

    def test_extract_servers_from_common_response_shape(self) -> None:
        payload = {"servers": [{"id": "server-1", "status": "ACTIVE"}]}

        servers = hcloud_ecs_verify_active.extract_servers(payload)

        self.assertEqual(servers, [{"id": "server-1", "status": "ACTIVE"}])

    def test_classify_targets_reports_all_active(self) -> None:
        servers = [
            {"id": "server-1", "name": "web", "status": "ACTIVE"},
            {"id": "server-2", "name": "worker", "status": "BUILD"},
        ]

        result = hcloud_ecs_verify_active.classify_targets(servers, ["server-1"], [])

        self.assertTrue(result["all_active"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["inactive"], [])

    def test_classify_targets_reports_missing_and_inactive(self) -> None:
        servers = [{"id": "server-1", "name": "web", "status": "BUILD"}]

        result = hcloud_ecs_verify_active.classify_targets(servers, ["server-1", "server-2"], [])

        self.assertFalse(result["all_active"])
        self.assertEqual(result["missing"], [{"type": "id", "value": "server-2"}])
        self.assertEqual(result["inactive"], [{"id": "server-1", "name": "web", "status": "BUILD"}])

    def test_wait_for_active_succeeds_when_target_becomes_active(self) -> None:
        args = SimpleNamespace(
            server_id=["server-1"],
            server_name=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=100,
            interval=0.01,
            timeout=1.0,
            command_timeout=1,
            max_command_failures=2,
            print_command_only=False,
        )

        with mock.patch.object(
            hcloud_ecs_verify_active,
            "run_list_servers",
            return_value={"success": True, "return_code": 0, "parsed_json": {"servers": [{"id": "server-1", "status": "ACTIVE"}]}},
        ):
            result = hcloud_ecs_verify_active.wait_for_active(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["verification_scope"], "resource_active")
        self.assertTrue(result["final"]["all_active"])


if __name__ == "__main__":
    unittest.main()
