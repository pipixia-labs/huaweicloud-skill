"""Tests for the unified closure planner wrapper."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load a script module for local unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_closure_plan = load_module("hcloud_closure_plan", SCRIPTS / "hcloud_closure_plan.py")


class HcloudClosurePlanTest(unittest.TestCase):
    """Validate lifecycle, governance, and scenario closure tiers share one entry point."""

    def args(self, **overrides):
        """Return default wrapper args."""
        values = {
            "tier": "lifecycle",
            "service": ["VPC"],
            "group": None,
            "task": None,
            "operation": None,
            "param": [],
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "json_input_file": None,
            "arg": [],
            "no_dryrun": False,
            "allow_unregistered": False,
            "limit": 5,
            "timeout": 1,
            "min_live_ops": 2,
            "catalog_max_operations": 2,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_normalizes_tier_aliases(self) -> None:
        self.assertEqual(hcloud_closure_plan.normalize_tier("p0"), "lifecycle")
        self.assertEqual(hcloud_closure_plan.normalize_tier("p1"), "governance")
        self.assertEqual(hcloud_closure_plan.normalize_tier("p2"), "scenario")

    def test_builds_lifecycle_plan_through_unified_entry(self) -> None:
        result = hcloud_closure_plan.build_plan(self.args(tier="p0", service=["VPC"]))

        self.assertTrue(result["success"], result)
        self.assertEqual(result["selected_tier"], "lifecycle")
        self.assertEqual(result["entrypoint"], "scripts/hcloud_closure_plan.py")
        self.assertEqual(result["services"][0]["service"], "VPC")

    def test_builds_governance_plan_through_unified_entry(self) -> None:
        result = hcloud_closure_plan.build_plan(self.args(tier="governance", service=["TMS"]))

        self.assertTrue(result["success"], result)
        self.assertEqual(result["selected_tier"], "governance")
        self.assertIn("scripts/hcloud_governance_closure_plan.py", result["compatibility_modules"].values())

    def test_builds_scenario_plan_through_unified_entry(self) -> None:
        result = hcloud_closure_plan.build_plan(self.args(tier="scenario", group=["CCE"]))

        self.assertTrue(result["success"], result)
        self.assertEqual(result["selected_tier"], "scenario")
        self.assertEqual(result["selected_groups"], ["CCE"])
        self.assertEqual(result["groups"][0]["group"], "CCE")


if __name__ == "__main__":
    unittest.main()
