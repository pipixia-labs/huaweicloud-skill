"""Tests for the managed KPS key-pair change capability."""

from __future__ import annotations

import base64
import importlib.util
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
    """Load one Skill script module for isolated unit tests."""

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kps_change = load_module(
    "hcloud_kps_keypair_change",
    SCRIPTS / "hcloud_kps_keypair_change.py",
)


PUBLIC_KEY = "ssh-ed25519 " + base64.b64encode(b"managed-kps-test-key").decode("ascii")


def flow_args(directory: Path, **overrides) -> SimpleNamespace:
    """Return the small business-facing KPS argument set."""

    values = {
        "operation": "import",
        "region": "cn-north-4",
        "project_id": "project-1",
        "keypair_name": "task-keypair",
        "public_key_file": "task-keypair.pub",
        "timeout": 120,
    }
    values.update(overrides)
    (directory / "task-keypair.pub").write_text(PUBLIC_KEY + " test\n", encoding="utf-8")
    return SimpleNamespace(**values)


def detail_result(public_key: str = PUBLIC_KEY) -> dict:
    """Return one successful exact KPS detail response."""

    return {
        "success": True,
        "request_dispatched": True,
        "parsed_json": {
            "keypair": {
                "name": "task-keypair",
                "public_key": public_key,
                "fingerprint": "11:22:33",
            }
        },
    }


NOT_FOUND = {
    "success": False,
    "request_dispatched": True,
    "stdout": "keypair not found",
    "stderr": "",
}


class KpsKeypairChangeTest(unittest.TestCase):
    """Validate idempotency, exact verification, and bounded output."""

    def test_import_uses_kps_api_and_verifies_exact_public_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            args = flow_args(directory)
            with (
                mock.patch.dict(
                    "os.environ",
                    {"CLOUD_CLAW_ACTION_WORKSPACE_PATH": str(directory)},
                ),
                mock.patch.object(
                    kps_change,
                    "execute_command",
                    side_effect=[NOT_FOUND, {"success": True}, detail_result()],
                ) as execute,
            ):
                result = kps_change.import_keypair(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertTrue(result["changed"])
        self.assertEqual(result["resource"]["name"], "task-keypair")
        submit_command = execute.call_args_list[1].args[0]
        self.assertIn("--service=KPS", submit_command)
        self.assertIn("--operation=CreateKeypair", submit_command)
        self.assertIn("--arg=--keypair.name=task-keypair", submit_command)
        self.assertTrue(
            any(item.startswith("--arg=--keypair.public_key=ssh-ed25519 ") for item in submit_command)
        )
        self.assertNotIn("public_key", result["resource"])

    def test_import_reuses_matching_existing_key_without_submit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            args = flow_args(directory)
            with (
                mock.patch.dict(
                    "os.environ",
                    {"CLOUD_CLAW_ACTION_WORKSPACE_PATH": str(directory)},
                ),
                mock.patch.object(
                    kps_change,
                    "execute_command",
                    return_value=detail_result(),
                ) as execute,
            ):
                result = kps_change.import_keypair(args)

        self.assertTrue(result["success"])
        self.assertFalse(result["changed"])
        self.assertEqual(execute.call_count, 1)

    def test_import_rejects_same_name_with_different_key(self) -> None:
        other_key = "ssh-ed25519 " + base64.b64encode(b"other-key").decode("ascii")
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            args = flow_args(directory)
            with (
                mock.patch.dict(
                    "os.environ",
                    {"CLOUD_CLAW_ACTION_WORKSPACE_PATH": str(directory)},
                ),
                mock.patch.object(
                    kps_change,
                    "execute_command",
                    return_value=detail_result(other_key),
                ),
            ):
                result = kps_change.import_keypair(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["outcome_status"], "failed")
        self.assertEqual(result["error_code"], "KEYPAIR_NAME_CONFLICT")

    def test_delete_is_idempotent_when_keypair_is_already_absent(self) -> None:
        args = SimpleNamespace(
            operation="delete",
            region="cn-north-4",
            project_id="project-1",
            keypair_name="task-keypair",
            public_key_file=None,
            timeout=120,
        )
        with mock.patch.object(
            kps_change,
            "execute_command",
            return_value=NOT_FOUND,
        ) as execute:
            result = kps_change.delete_keypair(args)

        self.assertTrue(result["success"])
        self.assertFalse(result["changed"])
        self.assertEqual(execute.call_count, 1)

    def test_delete_verifies_absence_even_when_submit_result_is_ambiguous(self) -> None:
        args = SimpleNamespace(
            operation="delete",
            region="cn-north-4",
            project_id="project-1",
            keypair_name="task-keypair",
            public_key_file=None,
            timeout=120,
        )
        with mock.patch.object(
            kps_change,
            "execute_command",
            side_effect=[
                detail_result(),
                {"success": False, "request_dispatched": True},
                NOT_FOUND,
            ],
        ):
            result = kps_change.delete_keypair(args)

        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertTrue(result["changed"])


if __name__ == "__main__":
    unittest.main()
