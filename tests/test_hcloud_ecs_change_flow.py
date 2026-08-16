"""Tests for resumable ECS create, job wait, and ACTIVE verification."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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


hcloud_ecs_change_flow = load_module(
    "hcloud_ecs_change_flow",
    SCRIPTS / "hcloud_ecs_change_flow.py",
)


def payload() -> dict:
    """Return one valid ECS create payload."""
    return {
        "path": {"project_id": "project-1"},
        "body": {
            "server": {
                "name": "web-server",
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


def security_group_evidence() -> dict:
    """Return bounded security-group readback evidence."""
    return {
        "security_group": {
            "id": "sg-1",
            "security_group_rules": [
                {
                    "id": "rule-1",
                    "security_group_id": "sg-1",
                    "direction": "ingress",
                    "protocol": "tcp",
                    "remote_ip_prefix": "203.0.113.10/32",
                    "port_range_min": 22,
                    "port_range_max": 22,
                }
            ],
        }
    }


def flow_args(directory: Path, **overrides) -> SimpleNamespace:
    """Create a complete ECS flow namespace and its JSON inputs."""
    input_path = directory / "ecs-create.json"
    evidence_path = directory / "security-group.json"
    input_path.write_text(json.dumps(payload()), encoding="utf-8")
    evidence_path.write_text(json.dumps(security_group_evidence()), encoding="utf-8")
    values = {
        "json_input_file": str(input_path),
        "security_group_evidence_file": str(evidence_path),
        "operation": "CreateServers",
        "region": "cn-north-4",
        "project_id": "project-1",
        "profile": None,
        "state_file": str(directory / "change-state.json"),
        "ledger_file": str(directory / "resource-ledger.json"),
        "workflow_id": "workflow-1",
        "step_id": "create-web-server",
        "resource_role": "web-server",
        "depends_on": ["subnet"],
        "execute_dryrun": False,
        "execute_submit": False,
        "execute_wait": False,
        "execute_verify": False,
        "confirm_submit": False,
        "submit_token": None,
        "allow_placeholders": False,
        "max_count": 10,
        "allow_large_count": False,
        "allow_public_web": False,
        "interval": 0.01,
        "timeout": 60.0,
        "command_timeout": 10,
        "max_command_failures": 2,
        "journal": None,
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class EcsChangeFlowTest(unittest.TestCase):
    """Validate the end-to-end ECS change lifecycle without cloud calls."""

    def test_plan_returns_bound_token_and_registers_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            result = hcloud_ecs_change_flow.build_flow(flow_args(directory))
            ledger = json.loads((directory / "resource-ledger.json").read_text(encoding="utf-8"))

        self.assertTrue(result["success"])
        self.assertTrue(result["planning_only"])
        self.assertEqual(len(result["submit_guard"]["submit_token"]), 16)
        self.assertEqual(ledger["resources"]["web-server"]["state"], "planned")

    def test_submit_wait_and_active_verification_converge_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan_args = flow_args(directory)
            plan = hcloud_ecs_change_flow.build_flow(plan_args)
            execute_args = flow_args(
                directory,
                execute_submit=True,
                execute_wait=True,
                execute_verify=True,
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with (
                mock.patch.object(
                    hcloud_ecs_change_flow,
                    "execute_command",
                    return_value={
                        "success": True,
                        "return_code": 0,
                        "parsed_json": {"job_id": "job-1"},
                    },
                ) as execute_command,
                mock.patch.object(
                    hcloud_ecs_change_flow.hcloud_ecs_wait_job,
                    "wait_for_job",
                    return_value={
                        "success": True,
                        "classification": "success",
                        "final_status": "SUCCESS",
                        "final_identifiers": {"entities.server_id": ["server-1"]},
                    },
                ),
                mock.patch.object(
                    hcloud_ecs_change_flow.hcloud_ecs_verify_active,
                    "wait_for_active",
                    return_value={
                        "success": True,
                        "final": {
                            "matched": [{"id": "server-1", "name": "web-server", "status": "ACTIVE"}],
                            "missing": [],
                            "inactive": [],
                        },
                    },
                ),
            ):
                result = hcloud_ecs_change_flow.build_flow(execute_args)
            ledger = json.loads((directory / "resource-ledger.json").read_text(encoding="utf-8"))

        execute_command.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertEqual(result["lifecycle_status"], "verified")
        resource = ledger["resources"]["web-server"]
        self.assertEqual(resource["identifiers"], ["server-1"])
        self.assertEqual(resource["job_ids"], ["job-1"])
        self.assertEqual(resource["state"], "verified")

    def test_ambiguous_submit_is_not_replayed_on_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_ecs_change_flow.build_flow(flow_args(directory))
            execute_args = flow_args(
                directory,
                execute_submit=True,
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with mock.patch.object(
                hcloud_ecs_change_flow,
                "execute_command",
                return_value={
                    "success": False,
                    "return_code": 1,
                    "parsed_json": None,
                },
            ):
                first = hcloud_ecs_change_flow.build_flow(execute_args)
            with mock.patch.object(
                hcloud_ecs_change_flow,
                "execute_command",
            ) as execute_command:
                resumed = hcloud_ecs_change_flow.build_flow(execute_args)

        execute_command.assert_not_called()
        self.assertEqual(first["lifecycle_status"], "submit_unknown")
        self.assertEqual(resumed["resume_action"], "verify_existing")
        self.assertEqual(resumed["outcome_status"], "partially_succeeded")
        self.assertEqual(resumed["error_code"], "SUBMIT_OUTCOME_REQUIRES_READBACK")

    def test_local_runtime_failure_is_failed_and_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_ecs_change_flow.build_flow(flow_args(directory))
            execute_args = flow_args(
                directory,
                execute_submit=True,
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with mock.patch.object(
                hcloud_ecs_change_flow,
                "execute_command",
                return_value={
                    "success": False,
                    "request_dispatched": False,
                    "parsed_json": None,
                },
            ):
                result = hcloud_ecs_change_flow.build_flow(execute_args)

        self.assertEqual(result["outcome_status"], "failed")
        self.assertEqual(result["error_code"], "ECS_SUBMIT_NOT_DISPATCHED")
        self.assertEqual(result["lifecycle_status"], "submit_failed")


if __name__ == "__main__":
    unittest.main()
