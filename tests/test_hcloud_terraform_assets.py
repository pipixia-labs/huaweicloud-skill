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
import hcloud_terraform_provider_inventory  # noqa: E402
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

        self.assertEqual(catalog["example_count"], 73)
        self.assertEqual(catalog["example_count"], len(actual_dirs))
        self.assertEqual(catalog["default_route_count"], 12)
        self.assertTrue(all(Path(ROOT / item["path"]).exists() for item in catalog["examples"]))

    def test_absorbed_upstream_examples_are_cataloged_and_sanitized(self) -> None:
        absorbed_ids = {
            "vpc_security_group_stack",
            "vpc_peering_stack",
            "nat_vpc_peering_stack",
            "cce_addon_stack",
            "elb_as_stack",
            "elb_reuse_stack",
            "nat_reuse_stack",
            "cce_node_pool_reuse_stack",
            "ecs_elb_rds_stack",
            "obs_cdn_dns_stack",
            "cce_coredns_addon_stack",
            "cce_turbo_cluster_stack",
            "cce_node_partition_stack",
            "rds_mysql_stack",
            "rds_postgresql_ha_stack",
            "rds_read_replica_stack",
            "rds_mysql_eip_stack",
            "rds_sqlserver_stack",
        }

        for example_id in absorbed_ids:
            with self.subTest(example_id=example_id):
                example = self.example_by_id(example_id)
                example_path = ROOT / example["path"]

                self.assertIn("terraform.tfvars.example", example["files"])
                self.assertNotIn("terraform.tfvars", example["files"])
                self.assertIn("versions.tf", example["entry_files"])
                self.assertIn("provider.tf", example["entry_files"])
                self.assertTrue((example_path / "README.md").exists())

        self.assertIn("VPC", self.example_by_id("vpc_security_group_stack")["services"])
        self.assertIn("VPC", self.example_by_id("vpc_peering_stack")["services"])
        self.assertIn("VPC", self.example_by_id("nat_vpc_peering_stack")["services"])

    def test_reference_catalog_has_core_and_inventory_routes(self) -> None:
        catalog = self.load_reference_catalog()
        ids = {item["id"]: item for item in catalog["references"]}

        self.assertGreaterEqual(catalog["reference_count"], 17)
        for reference_id in {
            "README",
            "provider-auth",
            "provider-validation",
            "generation-guardrails",
            "operations",
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
        reference_paths = {item["path"] for item in result["references"]}
        self.assertIn("references/terraform/provider-auth.md", reference_paths)
        self.assertIn("references/terraform/provider-validation.md", reference_paths)
        self.assertIn("references/terraform/generation-guardrails.md", reference_paths)
        self.assertIn("references/terraform/operations.md", reference_paths)

    def test_router_can_find_absorbed_vpc_examples(self) -> None:
        security_group = hcloud_terraform_router.route("用 Terraform 创建安全组并限制入口来源", limit=3)
        peering = hcloud_terraform_router.route("用 Terraform 创建两个 VPC 的对等连接和路由", limit=3)

        self.assertTrue(security_group["success"], json.dumps(security_group, ensure_ascii=False))
        self.assertEqual(security_group["service_hints"], ["VPC"])
        self.assertEqual(security_group["matches"][0]["id"], "vpc_security_group_stack")
        self.assertTrue(peering["success"], json.dumps(peering, ensure_ascii=False))
        self.assertEqual(peering["service_hints"], ["VPC"])
        self.assertEqual(peering["matches"][0]["id"], "vpc_peering_stack")

    def test_router_can_find_p0_p1_absorbed_examples(self) -> None:
        cases = [
            ("复用现网 ELB 增加 backend member", "elb_reuse_stack"),
            ("复用现网 NAT 增加 SNAT 规则", "nat_reuse_stack"),
            ("复用现网 CCE 集群新增节点池", "cce_node_pool_reuse_stack"),
            ("Terraform 部署 ECS ELB RDS Web 服务", "ecs_elb_rds_stack"),
            ("Terraform 创建 OBS CDN DNS 静态网站", "obs_cdn_dns_stack"),
            ("给 CCE 集群管理 CoreDNS addon", "cce_coredns_addon_stack"),
            ("创建 CCE Turbo 集群", "cce_turbo_cluster_stack"),
            ("创建 CCE 分区 node partition 节点池", "cce_node_partition_stack"),
            ("创建 RDS MySQL 单机实例", "rds_mysql_stack"),
            ("创建 RDS PostgreSQL 高可用实例", "rds_postgresql_ha_stack"),
            ("创建 RDS MySQL 只读副本", "rds_read_replica_stack"),
            ("创建 RDS MySQL 并绑定 EIP", "rds_mysql_eip_stack"),
            ("创建 RDS SQL Server 单机实例", "rds_sqlserver_stack"),
        ]

        for query, expected_id in cases:
            with self.subTest(query=query):
                result = hcloud_terraform_router.route(query, limit=5)
                self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
                self.assertEqual(result["matches"][0]["id"], expected_id)

    def test_router_keeps_readback_and_debug_on_hcloud(self) -> None:
        result = hcloud_terraform_router.route("帮我查询 ECS 当前状态", limit=3)

        self.assertFalse(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["recommended_runtime"], "hcloud")
        self.assertEqual(result["matches"], [])

    def test_router_returns_operations_reference_for_import_and_drift(self) -> None:
        result = hcloud_terraform_router.route("Terraform import 现网 ECS 并做 drift review remote state", limit=3)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["recommended_runtime"], "terraform")
        self.assertEqual(result["service_hints"], ["ECS"])
        self.assertTrue(result["hcloud_first_required"])
        reference_paths = {item["path"] for item in result["references"]}
        self.assertIn("references/terraform/operations.md", reference_paths)
        self.assertIn("references/terraform/interop-with-hcloud.md", reference_paths)

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
        self.assertIn("shared_config", context)
        self.assertIn("terraform_cli_config", context)
        self.assertIn("inspect_only", context["terraform_cli_config"]["notes"])
        self.assertIn("global_provider_cache_candidates", context["provider_cache"])

    def test_context_inspect_reports_terraform_cli_mirror_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "terraformrc"
            config_path.write_text(
                '\n'.join(
                    [
                        "provider_installation {",
                        "  network_mirror {",
                        '    url = "https://mirrors.huaweicloud.com/terraform/"',
                        '    include = ["registry.terraform.io/huaweicloud/*"]',
                        "  }",
                        "  direct {}",
                        "}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"TF_CLI_CONFIG_FILE": str(config_path)}, clear=False):
                result = hcloud_terraform_context_inspect.terraform_cli_config_hints()

        self.assertEqual(result["path_source"], "TF_CLI_CONFIG_FILE")
        self.assertTrue(result["exists"])
        self.assertTrue(result["readable"])
        self.assertTrue(result["has_provider_installation"])
        self.assertTrue(result["uses_network_mirror"])
        self.assertTrue(result["allows_direct"])
        self.assertTrue(result["huaweicloud_mirror_configured"])

    def test_context_inspect_warns_on_encrypted_shared_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text('{"authEncrypt": "true", "profiles": []}\n', encoding="utf-8")
            with mock.patch.dict(os.environ, {"HW_SHARED_CONFIG_FILE": str(config_path)}, clear=False):
                context = hcloud_terraform_context_inspect.build_context(argparse.Namespace(workdir=Path(tmp_dir)))

        self.assertEqual(context["shared_config"]["auth_encrypt"], "true")
        self.assertFalse(context["shared_config"]["usable_for_provider_shared_config"])
        self.assertIn("hcloud_shared_config_encrypted", context["readiness"]["warnings"])

    def test_readiness_accepts_os_provider_env_aliases(self) -> None:
        env = {key: {"set": False, "empty": False} for key in hcloud_terraform_context_inspect.TERRAFORM_ENV_KEYS}
        env["OS_ACCESS_KEY"]["set"] = True
        env["OS_SECRET_KEY"]["set"] = True
        env["OS_REGION_NAME"]["set"] = True

        result = hcloud_terraform_context_inspect.readiness(
            {"found": True},
            env,
            forbidden=[],
            shared_config={"usable_for_provider_shared_config": False, "warning": None},
        )

        self.assertTrue(result["auth"]["os_env_complete"])
        self.assertTrue(result["auth"]["cloud_credentials_complete"])
        self.assertTrue(result["can_plan"])

    def test_readiness_accepts_huawei_provider_env_aliases(self) -> None:
        env = {key: {"set": False, "empty": False} for key in hcloud_terraform_context_inspect.TERRAFORM_ENV_KEYS}
        env["HUAWEI_ACCESS_KEY"]["set"] = True
        env["HUAWEI_SECRET_KEY"]["set"] = True
        env["HUAWEI_REGION"]["set"] = True
        env["HUAWEI_PROJECT_ID"]["set"] = True
        env["HUAWEI_DOMAIN_ID"]["set"] = True

        result = hcloud_terraform_context_inspect.readiness(
            {"found": True},
            env,
            forbidden=[],
            shared_config={"usable_for_provider_shared_config": False, "warning": None},
        )

        self.assertTrue(result["auth"]["huawei_env_complete"])
        self.assertTrue(result["auth"]["cloud_credentials_complete"])
        self.assertTrue(result["can_plan"])
        self.assertIn("huawei_env_set_but_hw_env_unset", result["warnings"])

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

    def test_provider_inventory_builder_reads_provider_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider_root = Path(tmp_dir)
            (provider_root / "docs" / "resources").mkdir(parents=True)
            (provider_root / "docs" / "data-sources").mkdir(parents=True)
            (provider_root / "docs" / "resources" / "ecs_instance.md").write_text("# x\n", encoding="utf-8")
            (provider_root / "docs" / "resources" / "cce_cluster_pod_identity_association.md").write_text("# x\n", encoding="utf-8")
            (provider_root / "docs" / "data-sources" / "dcs_instances.md").write_text("# x\n", encoding="utf-8")
            (provider_root / "CHANGELOG.md").write_text("# CHANGELOG\n\n## 1.99.0 (June 30, 2026)\n", encoding="utf-8")

            resources = hcloud_terraform_provider_inventory.build_inventory(provider_root, "resources")
            data_sources = hcloud_terraform_provider_inventory.build_inventory(provider_root, "data-sources")
            rendered = hcloud_terraform_provider_inventory.render_inventory("Test", "测试。", resources)

        self.assertEqual(resources["count"], 2)
        self.assertEqual(data_sources["count"], 1)
        self.assertEqual(resources["snapshot"]["version"], "1.99.0")
        self.assertIn("cce_cluster_pod_identity_association", rendered)

    def test_provider_doc_signal_builder_reads_markdown_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            provider_root = Path(tmp_dir)
            docs_dir = provider_root / "docs" / "resources"
            docs_dir.mkdir(parents=True)
            (docs_dir / "rds_instance.md").write_text(
                "\n".join(
                    [
                        "# huaweicloud_rds_instance",
                        "",
                        "## Argument Reference",
                        "",
                        "* `vpc_id` - (Required, String, ForceNew) Changing this parameter will create a new resource.",
                        "* `password` - (Optional, String, Sensitive) Specifies the database password.",
                        "",
                        "## Import",
                        "",
                        "RDS instance can be imported using the `id`, e.g.",
                        "",
                        "```shell",
                        "terraform import huaweicloud_rds_instance.test <id>",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            signal = hcloud_terraform_provider_inventory.build_doc_signal(provider_root, "resources", "huaweicloud_rds_instance")

        self.assertTrue(signal["found"])
        self.assertEqual(signal["name"], "rds_instance")
        self.assertEqual(signal["doc_path"], "docs/resources/rds_instance.md")
        self.assertTrue(signal["force_new"]["present"])
        self.assertIn("vpc_id", signal["force_new"]["attributes"])
        self.assertTrue(signal["import"]["present"])
        self.assertIn("id", signal["import"]["hints"])
        self.assertTrue(signal["sensitive"]["present"])
        self.assertIn("password", signal["sensitive"]["attribute_hints"])

    def test_provider_inventories_include_current_reference_snapshot(self) -> None:
        resources = hcloud_terraform_provider_inventory.parse_inventory_items(
            ROOT / "references" / "terraform" / "inventories" / "provider-resource-inventory.md"
        )
        data_sources = hcloud_terraform_provider_inventory.parse_inventory_items(
            ROOT / "references" / "terraform" / "inventories" / "provider-data-source-inventory.md"
        )

        self.assertEqual(len(resources), 1689)
        self.assertEqual(len(data_sources), 2251)
        self.assertIn("apig_application_ai_api_key", resources)
        self.assertIn("cce_cluster_pod_identity_association", resources)
        self.assertIn("taurusdb_htap_sessions", data_sources)
        self.assertIn("vpn_metrics", data_sources)


if __name__ == "__main__":
    unittest.main()
