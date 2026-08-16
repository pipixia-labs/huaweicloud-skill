"""Tests for generic guarded-flow resource and async lifecycle integration."""

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


hcloud_guarded_change_flow = load_module(
    "hcloud_guarded_change_flow",
    SCRIPTS / "hcloud_guarded_change_flow.py",
)


def flow_args(directory: Path, **overrides) -> SimpleNamespace:
    """Return a fully specified generic security-group-rule flow."""
    values = {
        "service": "VPC",
        "operation": "CreateSecurityGroupRule",
        "region": "cn-north-4",
        "project_id": "project-1",
        "profile": None,
        "json_input_file": None,
        "arg": ["--security_group_id=sg-1"],
        "no_dryrun": False,
        "allow_unregistered": False,
        "allow_public_web": False,
        "execute_dryrun": False,
        "execute_submit": False,
        "confirm_submit": False,
        "submit_token": None,
        "skip_dryrun": True,
        "execute_readiness": False,
        "verify_operation": None,
        "verify_param": [],
        "execute_verify": False,
        "journal": None,
        "state_file": str(directory / "change-state.json"),
        "workflow_id": "workflow-1",
        "step_id": "create-rule",
        "ledger_file": str(directory / "resource-ledger.json"),
        "resource_role": "web-ingress-rule",
        "expected_count": 1,
        "depends_on": ["security-group"],
        "cleanup_operation": "DeleteSecurityGroupRule",
        "identifier_parameter": "security_group_rule_id",
        "execute_wait": False,
        "async_service": "VPC",
        "async_operation": None,
        "async_job_param": "job_id",
        "async_param": [],
        "async_status_path": ["status"],
        "async_success_status": ["SUCCESS"],
        "async_failure_status": ["FAILED"],
        "async_interval": 0.01,
        "async_timeout": 1.0,
        "max_command_failures": 1,
        "timeout": 1,
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class GuardedChangeLifecycleTest(unittest.TestCase):
    """Validate generic change convergence and exact task ownership."""

    def test_submit_async_wait_and_verify_share_one_resource_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_guarded_change_flow.build_flow(flow_args(directory))
            args = flow_args(
                directory,
                execute_submit=True,
                execute_wait=True,
                execute_verify=True,
                async_operation="ShowSecurityGroupRule",
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with (
                mock.patch.object(
                    hcloud_guarded_change_flow,
                    "execute_command",
                    return_value={
                        "success": True,
                        "parsed_json": {
                            "job_id": "job-1",
                            "security_group_rule": {"id": "rule-1"},
                        },
                    },
                ) as submit_command,
                mock.patch.object(
                    hcloud_guarded_change_flow.hcloud_async_job_wait,
                    "wait_for_job",
                    return_value={
                        "success": True,
                        "classification": "success",
                        "final_status": "SUCCESS",
                        "final_identifiers": {"security_group_rule_id": ["rule-1"]},
                    },
                ) as wait_for_job,
                mock.patch.object(
                    hcloud_guarded_change_flow.hcloud_resource_query,
                    "execute_command",
                    return_value={
                        "success": True,
                        "parsed_json": {"security_group_rule": {"id": "rule-1"}},
                    },
                ),
            ):
                result = hcloud_guarded_change_flow.build_flow(args)
            ledger = json.loads((directory / "resource-ledger.json").read_text(encoding="utf-8"))

        submit_command.assert_called_once()
        wait_for_job.assert_called_once()
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        resource = ledger["resources"]["web-ingress-rule"]
        self.assertEqual(resource["identifiers"], ["rule-1"])
        self.assertEqual(resource["job_ids"], ["job-1"])
        self.assertEqual(resource["state"], "verified")

    def test_async_failure_keeps_submit_partial_and_does_not_resubmit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_guarded_change_flow.build_flow(flow_args(directory))
            args = flow_args(
                directory,
                execute_submit=True,
                execute_wait=True,
                async_operation="ShowSecurityGroupRule",
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with (
                mock.patch.object(
                    hcloud_guarded_change_flow,
                    "execute_command",
                    return_value={
                        "success": True,
                        "parsed_json": {
                            "job_id": "job-1",
                            "security_group_rule": {"id": "rule-1"},
                        },
                    },
                ) as submit_command,
                mock.patch.object(
                    hcloud_guarded_change_flow.hcloud_async_job_wait,
                    "wait_for_job",
                    return_value={
                        "success": False,
                        "classification": "timeout",
                        "final_status": "RUNNING",
                    },
                ),
            ):
                first = hcloud_guarded_change_flow.build_flow(args)
                resumed = hcloud_guarded_change_flow.build_flow(args)

        self.assertEqual(submit_command.call_count, 1)
        self.assertEqual(first["outcome_status"], "partially_succeeded")
        self.assertEqual(resumed["outcome_status"], "partially_succeeded")
        self.assertTrue(resumed["submit_resume"]["submit_was_not_repeated"])

    def test_local_runtime_failure_is_not_reported_as_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_guarded_change_flow.build_flow(flow_args(directory))
            args = flow_args(
                directory,
                execute_submit=True,
                confirm_submit=True,
                submit_token=plan["submit_guard"]["submit_token"],
            )
            with mock.patch.object(
                hcloud_guarded_change_flow,
                "execute_command",
                return_value={
                    "success": False,
                    "request_dispatched": False,
                    "error_code": "RUNTIME_DEPENDENCY_UNAVAILABLE",
                },
            ):
                result = hcloud_guarded_change_flow.build_flow(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["outcome_status"], "failed")
        self.assertEqual(result["lifecycle_state"]["step"]["status"], "submit_failed")
        self.assertIn("did not reach hcloud", result["next_steps"][-1])


if __name__ == "__main__":
    unittest.main()
