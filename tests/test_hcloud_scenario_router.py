"""Tests for natural-language scenario routing."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_common  # noqa: E402
import hcloud_scenario_router  # noqa: E402


class HcloudScenarioRouterTest(unittest.TestCase):
    """Validate router entries remain local and actionable."""

    def test_routes_ecs_goal_to_compute_guides_and_sdk_supplements(self) -> None:
        result = hcloud_scenario_router.route("帮我创建 ECS 并选择规格镜像", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "ecs-compute-readiness")
        self.assertIn("references/guides/ecs.md", match["guides"])
        self.assertIn("references/playbooks/ecs-create-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_ecs_create_plan.py", match["planners"])
        self.assertIn("ECS:ListFlavors", match["sdk_supplements"])
        self.assertTrue(match["terraform_candidate"])
        self.assertEqual(match["terraform_route"]["router"], "scripts/hcloud_terraform_router.py")

    def test_category_and_service_hint_prefers_network_route(self) -> None:
        result = hcloud_scenario_router.route(
            "公网入口和安全组检查",
            category="network",
            service="VPC",
            limit=1,
        )

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "network-readiness")
        self.assertIn("references/guides/vpc.md", match["guides"])
        self.assertIn("VPC:ShowVpc", match["sdk_supplements"])
        followup_tools = [item["tool"] for item in match["recommended_followups"]]
        self.assertEqual(
            followup_tools,
            [
                "scripts/hcloud_lifecycle_closure_plan.py",
                "scripts/hcloud_acceptance_probe_plan.py",
                "scripts/hcloud_acceptance_evidence_result.py",
            ],
        )

    def test_routes_environment_setup_to_doctor(self) -> None:
        result = hcloud_scenario_router.route("帮我检查 hcloud terraform obsutil 环境和认证配置", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "environment-doctor")
        self.assertIn("scripts/hcloud_environment_doctor.py", match["planners"])
        self.assertFalse(match["terraform_candidate"])

    def test_routes_low_cost_static_site_to_entry_level_hosting(self) -> None:
        result = hcloud_scenario_router.route("小企业想低成本做静态网站，考虑 OBS 或轻量服务器", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "entry-level-web-hosting")
        self.assertIn("OBS", match["services"])
        self.assertIn("references/playbooks/entry-level-web-hosting.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/static-site-generated-assets-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_environment_doctor.py", match["planners"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_official_cn_alias_to_entry_level_hosting(self) -> None:
        result = hcloud_scenario_router.route("云耀云部署应用", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "entry-level-web-hosting")
        self.assertIn("FLEXUS-L", match["services"])
        self.assertTrue(any("alias:云耀云->FLEXUS-L" in reason for reason in match["reasons"]))

    def test_unknown_goal_has_no_match(self) -> None:
        result = hcloud_scenario_router.route("烹饪晚饭和整理书架", limit=3)

        self.assertFalse(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["matches"], [])

    def test_router_references_existing_local_assets(self) -> None:
        router = hcloud_scenario_router.load_router()
        registry = hcloud_common.load_json(hcloud_common.REFERENCES_DIR / "sdk-supplement-registry.json")
        sdk_entries = {
            f"{str(item.get('service', '')).upper()}:{item.get('hcloud_operation')}"
            for item in registry.get("operations", [])
            if isinstance(item, dict)
        }

        self.assertTrue((ROOT / "references" / "terraform-workflow.md").exists())
        self.assertTrue((ROOT / "references" / "terraform" / "README.md").exists())
        self.assertTrue((ROOT / "references" / "service-aliases.json").exists())
        self.assertTrue((ROOT / "scripts" / "hcloud_terraform_router.py").exists())
        for scenario in router.get("scenarios", []):
            for key in ("primary_playbooks", "guides", "planners"):
                for relative_path in scenario.get(key, []):
                    with self.subTest(scenario=scenario.get("id"), path=relative_path):
                        self.assertTrue((ROOT / relative_path).exists(), relative_path)
            for supplement in scenario.get("sdk_supplements", []):
                with self.subTest(scenario=scenario.get("id"), sdk_supplement=supplement):
                    self.assertIn(supplement, sdk_entries)

        route_result = hcloud_scenario_router.route("公网入口和安全组检查", category="network", service="VPC", limit=1)
        for followup in route_result["matches"][0]["recommended_followups"]:
            with self.subTest(followup=followup["tool"]):
                self.assertTrue((ROOT / followup["tool"]).exists(), followup["tool"])


if __name__ == "__main__":
    unittest.main()
