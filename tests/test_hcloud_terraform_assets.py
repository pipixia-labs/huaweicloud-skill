"""Tests for Terraform asset catalogs, routing, and local readiness checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_terraform_catalog  # noqa: E402
import hcloud_terraform_context_inspect  # noqa: E402
import hcloud_terraform_router  # noqa: E402


class HcloudTerraformAssetsTest(unittest.TestCase):
    """Validate Terraform assets are complete, routable, and clean."""

    def load_example_catalog(self) -> dict:
        """Load the generated Terraform example catalog."""
        return json.loads(hcloud_terraform_catalog.EXAMPLE_CATALOG_PATH.read_text(encoding="utf-8"))

    def load_reference_catalog(self) -> dict:
        """Load the generated Terraform reference catalog."""
        return json.loads(hcloud_terraform_catalog.REFERENCE_CATALOG_PATH.read_text(encoding="utf-8"))

    def example_by_id(self, example_id: str) -> dict:
        """Return one example catalog entry by id."""
        catalog = self.load_example_catalog()
        for example in catalog["examples"]:
            if example["id"] == example_id:
                return example
        self.fail(f"missing Terraform example {example_id}")

    def test_example_catalog_covers_all_migrated_stacks(self) -> None:
        catalog = self.load_example_catalog()
        actual_dirs = [path for path in (ROOT / "examples" / "terraform").iterdir() if path.is_dir()]

        self.assertEqual(catalog["example_count"], 55)
        self.assertEqual(catalog["example_count"], len(actual_dirs))
        self.assertEqual(catalog["default_route_count"], 12)
        self.assertTrue(all(Path(ROOT / item["path"]).exists() for item in catalog["examples"]))

    def test_reference_catalog_has_core_and_inventory_routes(self) -> None:
        catalog = self.load_reference_catalog()
        ids = {item["id"]: item for item in catalog["references"]}

        self.assertGreaterEqual(catalog["reference_count"], 17)
        for reference_id in {
            "README",
            "provider-auth",
            "discovery-workflow",
            "interop-with-hcloud",
            "service-variant-guide",
            "data-source-selection-guide",
            "troubleshooting",
        }:
            self.assertIn(reference_id, ids)
            self.assertEqual(ids[reference_id]["category"], "core")
            self.assertTrue(ids[reference_id]["default_route"])

        self.assertEqual(ids["provider-resource-inventory"]["category"], "inventory")
        self.assertEqual(ids["source-skill"]["category"], "source-archive")

    def test_short_aliases_do_not_pollute_longer_service_ids(self) -> None:
        cce = self.example_by_id("cce_stack")
        dcs = self.example_by_id("dcs_stack")

        self.assertIn("CCE", cce["services"])
        self.assertNotIn("CC", cce["services"])
        self.assertEqual(cce["category"], "container")
        self.assertIn("DCS", dcs["services"])
        self.assertNotIn("DC", dcs["services"])
        self.assertEqual(dcs["category"], "database")

    def test_router_prefers_terraform_for_iac_goal(self) -> None:
        result = hcloud_terraform_router.route("用 Terraform 创建 ECS 测试环境", limit=3)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["recommended_runtime"], "terraform")
        self.assertEqual(result["service_hints"], ["ECS"])
        self.assertEqual(result["matches"][0]["id"], "ecs_stack")
        self.assertIn("references/terraform/provider-auth.md", {item["path"] for item in result["references"]})

    def test_router_keeps_readback_and_debug_on_hcloud(self) -> None:
        result = hcloud_terraform_router.route("帮我查询 ECS 当前状态", limit=3)

        self.assertFalse(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["recommended_runtime"], "hcloud")
        self.assertEqual(result["matches"], [])

    def test_context_inspect_reports_catalogs_and_redacted_env_shape(self) -> None:
        with mock.patch.dict(os.environ, {"HW_ACCESS_KEY": "ak", "HW_SECRET_KEY": "sk", "HW_REGION_NAME": "cn-north-4"}, clear=False):
            args = argparse.Namespace(workdir=ROOT)
            context = hcloud_terraform_context_inspect.build_context(args)

        self.assertTrue(context["success"])
        self.assertTrue(context["asset_catalog"]["example_catalog_exists"])
        self.assertTrue(context["asset_catalog"]["reference_catalog_exists"])
        self.assertTrue(context["environment"]["HW_ACCESS_KEY"]["set"])
        self.assertNotIn("ak", json.dumps(context, ensure_ascii=False))
        self.assertTrue(context["readiness"]["can_generate"])

    def test_forbidden_artifacts_are_excluded_from_migrated_assets(self) -> None:
        scanned_roots = [ROOT / "references" / "terraform", ROOT / "examples" / "terraform"]
        findings: list[str] = []
        for scanned_root in scanned_roots:
            findings.extend(hcloud_terraform_context_inspect.forbidden_artifacts(scanned_root))

        self.assertEqual(findings, [])

    def test_forbidden_artifact_scan_allows_tfvars_examples_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workdir = Path(tmp_dir)
            (workdir / "terraform.tfvars.example").write_text("region = \"cn-north-4\"\n", encoding="utf-8")
            (workdir / "terraform.tfvars").write_text("secret = \"value\"\n", encoding="utf-8")
            (workdir / ".terraform").mkdir()

            findings = hcloud_terraform_context_inspect.forbidden_artifacts(workdir)

        self.assertEqual(len(findings), 2)
        self.assertTrue(any(path.endswith("terraform.tfvars") for path in findings))
        self.assertTrue(any(path.endswith(".terraform") for path in findings))
        self.assertFalse(any(path.endswith("terraform.tfvars.example") for path in findings))


if __name__ == "__main__":
    unittest.main()
