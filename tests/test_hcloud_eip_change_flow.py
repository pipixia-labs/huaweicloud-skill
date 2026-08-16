"""Tests for resumable EIP changes and resource-ledger integration."""

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


hcloud_eip_change_flow = load_module(
    "hcloud_eip_change_flow",
    SCRIPTS / "hcloud_eip_change_flow.py",
)


def service_plan() -> dict:
    """Return a valid offline EIP create plan."""
    return {
        "success": True,
        "service": "EIP",
        "operation": "CreatePublicip",
        "commands": {
            "dryrun_or_plan": ["safe-exec", "dryrun"],
            "submit": ["safe-exec", "submit"],
        },
        "risk": {"dryrun_required": False},
    }


def flow_args(directory: Path, **overrides) -> SimpleNamespace:
    """Return a complete EIP flow namespace."""
    values = {
        "operation": "CreatePublicip",
        "publicip_id": None,
        "region": "cn-north-4",
        "project_id": "project-1",
        "profile": None,
        "json_input_file": None,
        "arg": [],
        "no_dryrun": False,
        "allow_unregistered": False,
        "execute_dryrun": False,
        "execute_submit": False,
        "confirm_submit": False,
        "submit_token": None,
        "skip_dryrun": False,
        "execute_verify": False,
        "journal": None,
        "timeout": 120,
        "state_file": str(directory / "change-state.json"),
        "ledger_file": str(directory / "resource-ledger.json"),
        "workflow_id": "workflow-1",
        "step_id": "create-eip",
        "resource_role": "public-eip",
        "depends_on": ["web-server"],
        "cleanup_operation": "DeletePublicip",
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class EipChangeFlowTest(unittest.TestCase):
    """Validate EIP state and exact resource ownership without cloud calls."""

    def test_plan_registers_task_owned_eip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            with mock.patch.object(
                hcloud_eip_change_flow.hcloud_service_change_plan,
                "build_service_plan",
                return_value=service_plan(),
            ):
                result = hcloud_eip_change_flow.build_flow(flow_args(directory))
            ledger = json.loads((directory / "resource-ledger.json").read_text(encoding="utf-8"))

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertEqual(ledger["resources"]["public-eip"]["state"], "planned")

    def test_create_requires_exact_task_owned_cleanup_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            args = flow_args(
                directory,
                ledger_file=None,
                resource_role=None,
                cleanup_operation=None,
            )
            with mock.patch.object(
                hcloud_eip_change_flow.hcloud_service_change_plan,
                "build_service_plan",
                return_value=service_plan(),
            ):
                result = hcloud_eip_change_flow.build_flow(args)

        self.assertFalse(result["success"])
        self.assertIn("task-owned resource ledger", result["lifecycle_state_error"])

    def test_update_does_not_claim_existing_eip_as_task_owned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            args = flow_args(
                directory,
                operation="UpdatePublicip",
                publicip_id="eip-existing",
                ledger_file=None,
                resource_role=None,
                cleanup_operation=None,
            )
            update_plan = {
                **service_plan(),
                "operation": "UpdatePublicip",
            }
            with mock.patch.object(
                hcloud_eip_change_flow.hcloud_service_change_plan,
                "build_service_plan",
                return_value=update_plan,
            ):
                result = hcloud_eip_change_flow.build_flow(args)

        self.assertTrue(result["success"], result)
        self.assertFalse((directory / "resource-ledger.json").exists())

    def test_submit_and_verify_record_exact_publicip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            with mock.patch.object(
                hcloud_eip_change_flow.hcloud_service_change_plan,
                "build_service_plan",
                return_value=service_plan(),
            ):
                plan = hcloud_eip_change_flow.build_flow(flow_args(directory))
                args = flow_args(
                    directory,
                    execute_submit=True,
                    execute_verify=True,
                    confirm_submit=True,
                    submit_token=plan["submit_guard"]["submit_token"],
                )
                with (
                    mock.patch.object(
                        hcloud_eip_change_flow,
                        "execute_command",
                        return_value={
                            "success": True,
                            "return_code": 0,
                            "parsed_json": {"publicip": {"id": "eip-1"}},
                        },
                    ),
                    mock.patch.object(
                        hcloud_eip_change_flow.hcloud_resource_query,
                        "build_plan",
                        return_value={"success": True, "operation": "ShowPublicip"},
                    ),
                ):
                    result = hcloud_eip_change_flow.build_flow(args)
            ledger = json.loads((directory / "resource-ledger.json").read_text(encoding="utf-8"))

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertEqual(result["lifecycle_state"]["step"]["status"], "verified")
        resource = ledger["resources"]["public-eip"]
        self.assertEqual(resource["identifiers"], ["eip-1"])
        self.assertEqual(resource["state"], "verified")

    def test_ambiguous_submit_is_persisted_and_not_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            with mock.patch.object(
                hcloud_eip_change_flow.hcloud_service_change_plan,
                "build_service_plan",
                return_value=service_plan(),
            ):
                plan = hcloud_eip_change_flow.build_flow(flow_args(directory))
                args = flow_args(
                    directory,
                    execute_submit=True,
                    confirm_submit=True,
                    submit_token=plan["submit_guard"]["submit_token"],
                )
                with mock.patch.object(
                    hcloud_eip_change_flow,
                    "execute_command",
                    return_value={"success": False, "return_code": 1, "parsed_json": None},
                ):
                    first = hcloud_eip_change_flow.build_flow(args)
                with mock.patch.object(
                    hcloud_eip_change_flow,
                    "execute_command",
                ) as execute_command:
                    resumed = hcloud_eip_change_flow.build_flow(args)

        execute_command.assert_not_called()
        self.assertEqual(first["outcome_status"], "partially_succeeded")
        self.assertEqual(resumed["submit_resume"]["prior_status"], "submit_unknown")

    def test_delete_verification_accepts_confirmed_absence(self) -> None:
        args = SimpleNamespace(
            **{
                **flow_args(Path("."), operation="DeletePublicip").__dict__,
                "execute_verify": True,
            }
        )
        with mock.patch.object(
            hcloud_eip_change_flow.hcloud_resource_query,
            "build_plan",
            return_value={
                "success": False,
                "result": {"error_details": {"category": "not_found"}},
            },
        ):
            result = hcloud_eip_change_flow.build_verify_plan(args, "eip-1")

        self.assertTrue(result["success"])
        self.assertTrue(result["absent_state_confirmed"])
        self.assertEqual(result["verification_intent"], "expect_absent")


if __name__ == "__main__":
    unittest.main()
