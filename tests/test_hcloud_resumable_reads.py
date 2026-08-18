"""Contract tests for resumable account inventory and billing reads."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load one bundled script module for isolated tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_account_inventory = load_module(
    "resumable_hcloud_account_inventory",
    SCRIPTS / "hcloud_account_inventory.py",
)
hcloud_billing_live_read = load_module(
    "resumable_hcloud_billing_live_read",
    SCRIPTS / "hcloud_billing_live_read.py",
)


def inventory_args(checkpoint: Path, **overrides) -> SimpleNamespace:
    """Return a bounded executable inventory argument set."""
    values = {
        "service": ["ECS", "VPC"],
        "region": ["cn-north-4"],
        "region_file": None,
        "project_id": "project-1",
        "enterprise_project_id": None,
        "profile": None,
        "limit": 10,
        "obs_endpoint": None,
        "obs_config": None,
        "obs_payer": None,
        "execute": True,
        "strict": True,
        "timeout": 30,
        "max_workers": 1,
        "checkpoint_file": str(checkpoint),
        "resume": False,
        "time_budget": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def billing_args(checkpoint: Path, **overrides) -> SimpleNamespace:
    """Return a bounded executable cost-data argument set."""
    values = {
        "operation": "cost-data",
        "entry_point": None,
        "endpoint_base": "https://bss.myhuaweicloud.com",
        "language": "zh_CN",
        "bill_cycle": None,
        "shared_month": None,
        "begin_time": "2026-08-01",
        "end_time": "2026-08-14",
        "time_measure_id": 1,
        "group_by": ["CLOUD_SERVICE_TYPE"],
        "filter": [],
        "cost_type": "ORIGINAL_COST",
        "amount_type": "PAYMENT_AMOUNT",
        "project_id": None,
        "service_type_code": None,
        "resource_type": None,
        "resource_spec": None,
        "usage_type": None,
        "region_code": "cn-north-4",
        "pricing_region": None,
        "available_zone": None,
        "pricing_preset": None,
        "resource_size": None,
        "size_measure_id": None,
        "usage_value": None,
        "subscription_num": None,
        "inquiry_precision": 1,
        "period_type": None,
        "period_num": None,
        "fee_installment_mode": None,
        "resource_id": None,
        "enterprise_project_id": None,
        "charge_mode": None,
        "bill_type": None,
        "method": None,
        "sub_customer_id": None,
        "customer_id": None,
        "order_id": None,
        "balance_type": None,
        "status": None,
        "free_resource_id": None,
        "quota_id": None,
        "include_zero_record": None,
        "statistic_type": None,
        "offset": 0,
        "limit": 10,
        "query": [],
        "body_json_file": None,
        "body_json_text": None,
        "execute": True,
        "confirm_live_billing_read": hcloud_billing_live_read.CONFIRM_TOKEN,
        "include_redacted_records": False,
        "timeout": 30,
        "time_budget": 1,
        "max_output_chars": 2000,
        "checkpoint_file": str(checkpoint),
        "resume": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def billing_completed(command: list[str], payload: dict) -> subprocess.CompletedProcess[str]:
    """Return a mocked safe-exec result backed by its private payload artifact."""
    artifact_arg = next(item for item in command if str(item).startswith("--parsed-json-file="))
    artifact_path = Path(str(artifact_arg).split("=", 1)[1])
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")
    artifact_path.chmod(0o600)
    result = {
        "success": True,
        "return_code": 0,
        "duration_seconds": 0.1,
        "service": "BSS",
        "operation": "ListCosts/v2",
        "command": ["hcloud", "BSS", "ListCosts/v2"],
        "parsed_json": None,
    }
    return subprocess.CompletedProcess(command, 0, json.dumps(result), "")


class ResumableInventoryTest(unittest.TestCase):
    """Ensure inventory resumes only unfinished stable check identities."""

    def test_time_budget_checkpoint_resumes_remaining_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "inventory-checkpoint.json"
            clock = [0.0]
            first_run_calls: list[str] = []

            def first_run_check(args, target, region):  # noqa: ANN001, ANN202
                first_run_calls.append(target["operation"])
                clock[0] += 2.0
                return {
                    **target,
                    "scope": hcloud_account_inventory.scope_for(args, region),
                    "success": True,
                    "plan": {"success": True},
                }

            with (
                patch.object(hcloud_account_inventory.time, "monotonic", side_effect=lambda: clock[0]),
                patch.object(
                    hcloud_account_inventory,
                    "build_target_plan_for_region",
                    side_effect=first_run_check,
                ),
            ):
                partial = hcloud_account_inventory.build_plan(inventory_args(checkpoint))

            self.assertEqual(partial["outcome_status"], "partially_succeeded")
            self.assertEqual(partial["execution_progress"]["completed_check_count"], 1)
            self.assertEqual(partial["execution_progress"]["pending_check_count"], 3)
            self.assertEqual(partial["execution_progress"]["stop_reason"], "time_budget_reached")
            self.assertTrue(checkpoint.is_file())
            self.assertEqual(checkpoint.stat().st_mode & 0o777, 0o600)

            resumed_calls: list[str] = []

            def resumed_check(args, target, region):  # noqa: ANN001, ANN202
                resumed_calls.append(target["operation"])
                return {
                    **target,
                    "scope": hcloud_account_inventory.scope_for(args, region),
                    "success": True,
                    "plan": {"success": True},
                }

            with (
                patch.object(hcloud_account_inventory.time, "monotonic", return_value=0.0),
                patch.object(
                    hcloud_account_inventory,
                    "build_target_plan_for_region",
                    side_effect=resumed_check,
                ),
            ):
                complete = hcloud_account_inventory.build_plan(
                    inventory_args(
                        checkpoint,
                        resume=True,
                        time_budget=30,
                    )
                )

            self.assertEqual(len(first_run_calls), 1)
            self.assertEqual(len(resumed_calls), 3)
            self.assertNotIn(first_run_calls[0], resumed_calls)
            self.assertTrue(complete["success"], complete)
            self.assertEqual(complete["outcome_status"], "succeeded")
            self.assertTrue(complete["execution_progress"]["complete"])
            self.assertEqual(complete["execution_progress"]["reused_check_count"], 1)

    def test_resume_rejects_scope_drift_without_executing_checks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "inventory-checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "contract": "huaweicloud_account_inventory_checkpoint_v1",
                        "scope_sha256": "wrong",
                        "scope": {},
                        "state": {},
                    }
                ),
                encoding="utf-8",
            )
            checkpoint.chmod(0o600)

            with patch.object(hcloud_account_inventory, "build_target_plan_for_region") as execute:
                result = hcloud_account_inventory.build_plan(
                    inventory_args(checkpoint, resume=True)
                )

            execute.assert_not_called()
            self.assertFalse(result["success"])
            self.assertEqual(result["error_code"], "CHECKPOINT_SCOPE_MISMATCH")

    def test_compact_receipt_exposes_progress_and_checkpoint_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "inventory-result.json"
            result = {
                "success": True,
                "mode": "execute",
                "outcome_status": "partially_succeeded",
                "summary": {"check_count": 1},
                "execution_progress": {"pending_check_count": 3},
                "checkpoint": {"path": "/workspace/inventory.checkpoint.json"},
            }
            with patch.object(hcloud_account_inventory.hcloud_common, "emit_json") as emit:
                hcloud_account_inventory.emit_cli_result(
                    result,
                    output_file=str(output_file),
                    pretty=False,
                )

            receipt = emit.call_args.args[0]
            self.assertEqual(receipt["execution_progress"]["pending_check_count"], 3)
            self.assertEqual(
                receipt["checkpoint"]["path"],
                "/workspace/inventory.checkpoint.json",
            )

    def test_manifest_declares_private_scope_bound_resume_contracts(self) -> None:
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            "scripts/hcloud_account_inventory.py": hcloud_account_inventory.CHECKPOINT_CONTRACT,
            "scripts/hcloud_billing_live_read.py": hcloud_billing_live_read.CHECKPOINT_CONTRACT,
        }
        for script, contract_id in expected.items():
            with self.subTest(script=script):
                contract = manifest["public_script_contracts"][script]["resume_contract"]
                self.assertEqual(contract["id"], contract_id)
                self.assertTrue(contract["private_checkpoint"])
                self.assertTrue(contract["scope_bound"])
                self.assertTrue(contract["time_budget_supported"])


class ResumableBillingTest(unittest.TestCase):
    """Ensure billing checkpoints privately preserve accepted pages for exact resume."""

    def test_time_budget_checkpoint_resumes_at_next_offset(self) -> None:
        first_page = {
            "total_count": 11,
            "currency": "CNY",
            "cost_data": [
                {"dimensions": [{"key": "SERVICE", "value": f"service-{index}"}], "amount_by_costs": "1.00"}
                for index in range(10)
            ],
        }
        second_page = {
            "total_count": 11,
            "currency": "CNY",
            "cost_data": [
                {"dimensions": [{"key": "SERVICE", "value": "service-last"}], "amount_by_costs": "2.00"}
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "billing-checkpoint.json"
            clock = [0.0]

            def first_run(command, **_kwargs):  # noqa: ANN001, ANN202
                clock[0] += 2.0
                return billing_completed(command, first_page)

            with (
                patch.object(hcloud_billing_live_read.time, "monotonic", side_effect=lambda: clock[0]),
                patch.object(hcloud_billing_live_read.subprocess, "run", side_effect=first_run),
            ):
                partial = hcloud_billing_live_read.build_live_read(
                    billing_args(checkpoint)
                )

            self.assertEqual(partial["outcome_status"], "partially_succeeded")
            pagination = partial["execution"]["result"]["summary"]["pagination"]
            self.assertEqual(pagination["next_offset"], 10)
            self.assertEqual(pagination["stop_reason"], "time_budget_reached")
            self.assertTrue(checkpoint.is_file())
            self.assertEqual(checkpoint.stat().st_mode & 0o777, 0o600)

            observed_offsets: list[int] = []

            def resumed_run(command, **_kwargs):  # noqa: ANN001, ANN202
                offset_arg = next(item for item in command if "--offset=" in str(item))
                observed_offsets.append(int(str(offset_arg).rsplit("=", 1)[1]))
                return billing_completed(command, second_page)

            with (
                patch.object(hcloud_billing_live_read.time, "monotonic", return_value=0.0),
                patch.object(hcloud_billing_live_read.subprocess, "run", side_effect=resumed_run),
            ):
                complete = hcloud_billing_live_read.build_live_read(
                    billing_args(checkpoint, resume=True, time_budget=30)
                )

            self.assertEqual(observed_offsets, [10])
            self.assertTrue(complete["success"], complete)
            self.assertEqual(complete["outcome_status"], "succeeded")
            summary = complete["execution"]["result"]["summary"]
            self.assertEqual(summary["pagination"]["record_count"], 11)
            self.assertTrue(summary["pagination"]["resumed"])

    def test_resume_rejects_billing_scope_drift_before_cloud_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint = Path(temp_dir) / "billing-checkpoint.json"
            checkpoint.write_text(
                json.dumps(
                    {
                        "contract": "huaweicloud_billing_live_read_checkpoint_v1",
                        "scope_sha256": "wrong",
                        "scope": {},
                        "state": {},
                    }
                ),
                encoding="utf-8",
            )
            checkpoint.chmod(0o600)

            with patch.object(hcloud_billing_live_read.subprocess, "run") as execute:
                result = hcloud_billing_live_read.build_live_read(
                    billing_args(checkpoint, resume=True, region_code="cn-east-3")
                )

            execute.assert_not_called()
            self.assertFalse(result["success"])
            self.assertEqual(result["error_code"], "CHECKPOINT_SCOPE_MISMATCH")

    def test_compact_receipt_exposes_billing_resume_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / "billing-result.json"
            result = {
                "success": False,
                "mode": "execute",
                "outcome_status": "partially_succeeded",
                "execution": {
                    "result": {
                        "summary": {
                            "pagination": {"next_offset": 10},
                            "summary": {},
                        },
                        "checkpoint": {
                            "path": "/workspace/billing.checkpoint.json",
                        },
                    }
                },
            }
            with patch.object(hcloud_billing_live_read.hcloud_common, "emit_json") as emit:
                hcloud_billing_live_read.emit_cli_result(
                    result,
                    output_file=str(output_file),
                    pretty=False,
                )

            receipt = emit.call_args.args[0]
            self.assertEqual(receipt["summary"]["pagination"]["next_offset"], 10)
            self.assertEqual(
                receipt["checkpoint"]["path"],
                "/workspace/billing.checkpoint.json",
            )


if __name__ == "__main__":
    unittest.main()
