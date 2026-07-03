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
                "scripts/hcloud_acceptance_probe_run.py",
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
        result = hcloud_scenario_router.route("小企业想低成本做官网，需要简单后端，考虑轻量服务器", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "entry-level-web-hosting")
        self.assertIn("OBS", match["services"])
        self.assertIn("references/playbooks/entry-level-web-hosting.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/flexus-l-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/obs-static-website-hosting.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/static-site-generated-assets-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_environment_doctor.py", match["planners"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_production_web_app_to_multi_service_closure(self) -> None:
        result = hcloud_scenario_router.route(
            "生产 Web 应用上线，ECS 接 RDS，ELB 域名 HTTPS 和 WAF 怎么闭环",
            limit=1,
        )

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "web-application-production-readiness")
        self.assertIn("ELB", match["services"])
        self.assertIn("RDS", match["services"])
        self.assertIn("SCM", match["services"])
        self.assertIn("references/playbooks/web-application-production-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/elb-http-backend-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/rds-instance-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/waf-policy-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_account_inventory.py", match["planners"])
        self.assertIn("scripts/hcloud_acceptance_probe_plan.py", match["planners"])
        self.assertIn("ELB:ShowLoadBalancer", match["sdk_supplements"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_obs_static_site_to_obs_hosting_playbook(self) -> None:
        result = hcloud_scenario_router.route("OBS 静态网站自定义域名 CNAME 访问 403 怎么排查", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "obs-static-website-hosting")
        self.assertIn("OBS", match["services"])
        self.assertIn("DNS", match["services"])
        self.assertIn("references/playbooks/obs-static-website-hosting.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/obs-boundary.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_obs_readonly.py", match["planners"])
        followup_tools = [item["tool"] for item in match["recommended_followups"]]
        self.assertIn("scripts/hcloud_lifecycle_closure_plan.py", followup_tools)

    def test_routes_ecs_metric_gap_to_monitoring_troubleshooting(self) -> None:
        result = hcloud_scenario_router.route("ECS 内存指标 mem_used_percent 查不到指标 怎么处理", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "observability-readiness")
        self.assertIn("CES", match["services"])
        self.assertIn("references/playbooks/ecs-monitoring-troubleshooting.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/ces-metric-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_resource_discovery.py", match["planners"])
        self.assertIn("scripts/hcloud_ces_alarm_plan.py", match["planners"])

    def test_routes_idle_eip_cost_to_governance_playbook(self) -> None:
        result = hcloud_scenario_router.route("未绑定 EIP 公网 IP 一直扣费，怎么做成本回收", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "audit-and-cost-governance")
        self.assertIn("EIP", match["services"])
        self.assertIn("references/playbooks/eip-cost-optimization.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/billing-cost-governance.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_idle_audit.py", match["planners"])
        self.assertIn("scripts/hcloud_billing_result_summarize.py", match["planners"])

    def test_routes_permission_error_to_permission_diagnostics(self) -> None:
        result = hcloud_scenario_router.route("OBS 403 AccessDenied 需要什么权限", service="OBS", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "permission-diagnostics")
        self.assertIn("IAM", match["services"])
        self.assertIn("OBS", match["services"])
        self.assertIn("references/playbooks/iam-permission-diagnostics.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_safe_exec.py", match["planners"])
        self.assertEqual(match["recommended_followups"], [])

    def test_routes_container_image_deployment_to_swr_cci_playbooks(self) -> None:
        result = hcloud_scenario_router.route("用 CCI 部署 SWR Docker 镜像，Service 怎么暴露", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "container-image-deployment")
        self.assertIn("SWR", match["services"])
        self.assertIn("CCI", match["services"])
        self.assertIn("references/playbooks/swr-image-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/cci-workload-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_resource_discovery.py", match["planners"])
        self.assertIn("scripts/hcloud_service_change_plan.py", match["planners"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_cce_assessment_to_cloud_native_playbook(self) -> None:
        result = hcloud_scenario_router.route("CCE 云原生环境评估，检查节点池 插件 RBAC 和 pod readiness", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "container-readiness")
        self.assertIn("CCE", match["services"])
        self.assertIn("references/playbooks/cce-cloud-native-assessment.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/cce-cluster-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_cce_assessment_plan.py", match["planners"])
        self.assertIn("scripts/hcloud_p2_scenario_closure_plan.py", match["planners"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_functiongraph_goal_to_serverless_playbook(self) -> None:
        result = hcloud_scenario_router.route("FunctionGraph 函数计算 OBS 触发器 LTS 日志怎么配置", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "functiongraph-serverless-readiness")
        self.assertIn("FunctionGraph", match["services"])
        self.assertIn("LTS", match["services"])
        self.assertIn("references/playbooks/functiongraph-readiness.md", match["primary_playbooks"])
        self.assertIn("references/playbooks/lts-log-readiness.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_resource_query.py", match["planners"])
        self.assertIn("scripts/hcloud_service_change_plan.py", match["planners"])
        self.assertTrue(match["terraform_candidate"])

    def test_routes_terraform_import_drift_to_operations_guidance(self) -> None:
        result = hcloud_scenario_router.route("Terraform import 现网 ECS 纳管 drift remote state 怎么做", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "terraform-operations")
        self.assertIn("TERRAFORM", match["services"])
        self.assertIn("references/terraform/operations.md", match["primary_playbooks"])
        self.assertIn("scripts/hcloud_terraform_context_inspect.py", match["planners"])
        self.assertIn("scripts/hcloud_terraform_operations_plan.py", match["planners"])
        self.assertIn("scripts/hcloud_terraform_provider_inventory.py", match["planners"])
        self.assertFalse(match["terraform_candidate"])
        self.assertEqual(match["recommended_followups"], [])

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
