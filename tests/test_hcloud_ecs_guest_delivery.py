"""Tests for generic ECS guest artifact delivery and acceptance."""

from __future__ import annotations

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
    """Load a script module for isolated unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_ecs_guest_delivery = load_module(
    "hcloud_ecs_guest_delivery",
    SCRIPTS / "hcloud_ecs_guest_delivery.py",
)


def delivery_args(directory: Path, **overrides) -> SimpleNamespace:
    """Return complete guest-delivery arguments and local fixtures."""
    source = directory / "site"
    source.mkdir(exist_ok=True)
    (source / "index.html").write_text("<h1>Hello</h1>", encoding="utf-8")
    password = directory / "ecs-password.txt"
    password.write_text("not-logged-password\n", encoding="utf-8")
    password.chmod(0o600)
    values = {
        "host": "203.0.113.10",
        "user": "debian",
        "port": 22,
        "source_dir": str(source),
        "destination_dir": "/srv/web",
        "identity_file": None,
        "password_file": str(password),
        "known_hosts_file": str(directory / "known_hosts"),
        "host_key_policy": "accept-new",
        "package": ["nginx"],
        "service_name": "nginx",
        "health_url": "http://203.0.113.10/",
        "allow_private_target": False,
        "execute": False,
        "confirm_delivery": False,
        "delivery_token": None,
        "state_file": str(directory / "delivery-state.json"),
        "workflow_id": "workflow-1",
        "step_id": "deploy-web",
        "connect_timeout": 10,
        "command_timeout": 120,
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class EcsGuestDeliveryTest(unittest.TestCase):
    """Validate secret-safe plans, execution evidence, and resume behavior."""

    def test_plan_is_bound_to_source_manifest_without_password_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            result = hcloud_ecs_guest_delivery.build_flow(delivery_args(Path(tmp_dir)))

        serialized = str(result)
        self.assertTrue(result["success"])
        self.assertTrue(result["planning_only"])
        self.assertEqual(len(result["delivery_guard"]["delivery_token"]), 16)
        self.assertIn("rsync", result["plan"]["phases"][2]["command"])
        self.assertIn(
            "install -d",
            str(result["plan"]["phases"][1]["command"]),
        )
        self.assertNotIn("not-logged-password", serialized)

    def test_execute_runs_idempotent_phases_and_http_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_ecs_guest_delivery.build_flow(delivery_args(directory))
            args = delivery_args(
                directory,
                execute=True,
                confirm_delivery=True,
                delivery_token=plan["delivery_guard"]["delivery_token"],
            )
            with (
                mock.patch.object(
                    hcloud_ecs_guest_delivery,
                    "execute_process",
                    return_value={"success": True, "return_code": 0},
                ) as execute_process,
                mock.patch.object(
                    hcloud_ecs_guest_delivery.hcloud_acceptance_probe_run,
                    "http_probe",
                    return_value={
                        "status": "passed",
                        "summary": "HTTP probe returned 200.",
                        "source": "http",
                        "detail": {"status_code": 200},
                    },
                ),
            ):
                result = hcloud_ecs_guest_delivery.build_flow(args)

        self.assertEqual(execute_process.call_count, 4)
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertEqual(result["lifecycle_status"], "verified")
        self.assertEqual(result["acceptance"]["status"], "passed")

    def test_ambiguous_delivery_is_not_replayed_and_can_be_verified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            plan = hcloud_ecs_guest_delivery.build_flow(delivery_args(directory))
            args = delivery_args(
                directory,
                execute=True,
                confirm_delivery=True,
                delivery_token=plan["delivery_guard"]["delivery_token"],
            )
            with mock.patch.object(
                hcloud_ecs_guest_delivery,
                "execute_process",
                side_effect=[
                    {"success": True, "return_code": 0},
                    {"success": False, "return_code": 255},
                ],
            ):
                first = hcloud_ecs_guest_delivery.build_flow(args)
            with (
                mock.patch.object(
                    hcloud_ecs_guest_delivery,
                    "execute_process",
                ) as execute_process,
                mock.patch.object(
                    hcloud_ecs_guest_delivery.hcloud_acceptance_probe_run,
                    "http_probe",
                    return_value={"status": "passed", "summary": "ok"},
                ),
            ):
                resumed = hcloud_ecs_guest_delivery.build_flow(args)

        execute_process.assert_not_called()
        self.assertEqual(first["outcome_status"], "partially_succeeded")
        self.assertTrue(resumed["resume"]["delivery_was_not_repeated"])
        self.assertEqual(resumed["outcome_status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
