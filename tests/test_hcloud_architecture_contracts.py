"""Architecture contract tests for huaweicloud-skill."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load a script module from a path for local unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    """Write a minimal inline-string XLSX workbook for parser contract tests."""
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            ref = f"{chr(ord('A') + column_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            (
                f'<workbook xmlns="{check_question_coverage.XLSX_MAIN_NS}" '
                f'xmlns:r="{check_question_coverage.XLSX_REL_NS}">'
                '<sheets><sheet name="v1" sheetId="1" r:id="rId1"/></sheets>'
                "</workbook>"
            ),
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            (
                f'<Relationships xmlns="{check_question_coverage.PACKAGE_REL_NS}">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                "</Relationships>"
            ),
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            (
                f'<worksheet xmlns="{check_question_coverage.XLSX_MAIN_NS}">'
                f'<sheetData>{"".join(sheet_rows)}</sheetData>'
                "</worksheet>"
            ),
        )


hcloud_change_plan = load_module("hcloud_change_plan", SCRIPTS / "hcloud_change_plan.py")
hcloud_resource_discovery = load_module("hcloud_resource_discovery", SCRIPTS / "hcloud_resource_discovery.py")
check_materials_drift = load_module("check_materials_drift", SCRIPTS / "check_materials_drift.py")
check_question_coverage = load_module("check_question_coverage", SCRIPTS / "check_question_coverage.py")
hcloud_run_journal = load_module("hcloud_run_journal", SCRIPTS / "hcloud_run_journal.py")


class ArchitectureContractsTest(unittest.TestCase):
    """Validate docs, registry, and script contracts stay aligned."""

    def test_portable_capability_manifest_is_skill_owned_and_read_only(self) -> None:
        manifest = json.loads((ROOT / "capabilities.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            manifest["contract_namespace"],
            "huaweicloud-skill.capabilities",
        )
        capabilities = {item["id"]: item for item in manifest["capabilities"]}
        inventory = capabilities["huaweicloud.account_inventory.v1"]
        self.assertEqual(inventory["risk"], "read")
        self.assertEqual(inventory["credential_scope"], "huaweicloud")
        self.assertEqual(
            inventory["entrypoint"],
            "scripts/hcloud_account_inventory.py",
        )
        self.assertEqual(inventory["result_contract"], "json_outcome_v1")
        self.assertFalse(inventory["arguments"]["regions"].get("required", False))
        self.assertTrue((ROOT / inventory["entrypoint"]).is_file())
        billing = capabilities["huaweicloud.billing.read.v1"]
        self.assertEqual(billing["risk"], "read")
        self.assertEqual(billing["credential_scope"], "huaweicloud")
        self.assertEqual(billing["runtime"], "hcloud")
        self.assertEqual(
            billing["entrypoint"],
            "scripts/hcloud_billing_live_read.py",
        )
        self.assertIn("--execute", billing["fixed_args"])
        self.assertIn("READ_BILLING_DATA", billing["fixed_args"])
        self.assertEqual(billing["result_contract"], "json_outcome_v1")
        self.assertEqual(billing["arguments"]["limit"]["default"], 50)
        self.assertTrue((ROOT / billing["entrypoint"]).is_file())
        expected_changes = {
            "huaweicloud.ecs.create.v1": (
                "write",
                "scripts/hcloud_ecs_change_flow.py",
                "ecs-change-v1",
            ),
            "huaweicloud.ecs.create.v2": (
                "write",
                "scripts/hcloud_ecs_change_flow.py",
                "ecs-change-v2",
            ),
            "huaweicloud.eip.change.v1": (
                "write",
                "scripts/hcloud_eip_change_flow.py",
                "eip-change-v1",
            ),
            "huaweicloud.eip.destructive_change.v1": (
                "destructive",
                "scripts/hcloud_eip_change_flow.py",
                "eip-change-v1",
            ),
            "huaweicloud.resource.change.v1": (
                "write",
                "scripts/hcloud_guarded_change_flow.py",
                "resource-change-v1",
            ),
            "huaweicloud.ecs.guest_delivery.v1": (
                "write",
                "scripts/hcloud_ecs_guest_delivery.py",
                "ecs-guest-delivery-v1",
            ),
            "huaweicloud.kps.import_keypair.v1": (
                "write",
                "scripts/hcloud_kps_keypair_change.py",
                "kps-keypair-change-v1",
            ),
            "huaweicloud.kps.delete_keypair.v1": (
                "destructive",
                "scripts/hcloud_kps_keypair_change.py",
                "kps-keypair-change-v1",
            ),
        }
        runtime_bundles = manifest["runtime_bundles"]
        for capability_id, (risk, entrypoint, bundle_name) in expected_changes.items():
            capability = capabilities[capability_id]
            self.assertEqual(capability["risk"], risk)
            self.assertEqual(capability["entrypoint"], entrypoint)
            self.assertEqual(capability["runtime_bundle"], bundle_name)
            self.assertEqual(capability["result_contract"], "json_outcome_v1")
            self.assertTrue((ROOT / entrypoint).is_file())
            include_patterns = runtime_bundles[bundle_name]["include"]
            expanded = {
                path.relative_to(ROOT).as_posix()
                for pattern in include_patterns
                for path in ROOT.glob(pattern)
                if path.is_file()
            }
            self.assertIn(entrypoint, expanded)
            self.assertLess(len(expanded), 300)
            self.assertNotIn("SKILL.md", expanded)
            self.assertFalse(any(path.startswith("tests/") for path in expanded))

        for bundle_name in (
            "ecs-change-v1",
            "ecs-change-v2",
            "eip-change-v1",
            "kps-keypair-change-v1",
            "resource-change-v1",
        ):
            expanded = {
                path.relative_to(ROOT).as_posix()
                for pattern in runtime_bundles[bundle_name]["include"]
                for path in ROOT.glob(pattern)
                if path.is_file()
            }
            self.assertIn("scripts/hcloud_safe_exec.py", expanded)
            self.assertIn("scripts/hcloud_catalog.py", expanded)
            self.assertIn("scripts/hcloud_operation_resolver.py", expanded)
            self.assertIn("scripts/hcloud_output_policy.py", expanded)
            self.assertIn("references/hcloud-output-policies.json", expanded)
            self.assertIn("references/hcloud-service-catalog.index.json", expanded)
            self.assertIn("references/hcloud-service-confidence.json", expanded)

        eip_arguments = capabilities["huaweicloud.eip.change.v1"]["arguments"]
        self.assertNotIn("required", eip_arguments["ledger_file"])
        self.assertNotIn("required", eip_arguments["resource_role"])
        self.assertNotIn("default", eip_arguments["cleanup_operation"])
        self.assertEqual(
            eip_arguments["operation"]["choices"],
            ["CreatePublicip", "UpdatePublicip"],
        )
        self.assertEqual(
            capabilities["huaweicloud.eip.destructive_change.v1"]["arguments"][
                "operation"
            ]["choices"],
            ["DeletePublicip"],
        )

        kps_import = capabilities["huaweicloud.kps.import_keypair.v1"]
        self.assertEqual(
            set(kps_import["arguments"]),
            {"region", "project_id", "keypair_name", "public_key_file", "timeout"},
        )
        self.assertTrue(kps_import["arguments"]["public_key_file"]["required"])
        self.assertNotIn("private_key", kps_import["arguments"])
        self.assertEqual(
            set(capabilities["huaweicloud.kps.delete_keypair.v1"]["arguments"]),
            {"region", "project_id", "keypair_name", "timeout"},
        )

        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        contract_text = (
            ROOT / "references/capability-contracts.md"
        ).read_text(encoding="utf-8")
        self.assertIn("平台无关", contract_text)
        self.assertIn("`planning_status`", contract_text)
        self.assertIn("`outcome_status`", contract_text)
        self.assertIn("省略 `regions`", contract_text)
        self.assertIn("`skipped_checks`", contract_text)
        self.assertIn("`complete=true`", contract_text)
        self.assertIn("`affects_completeness=false`", contract_text)
        self.assertIn("endpoint 元数据缺失", contract_text)
        self.assertIn("`inventory_scope`", contract_text)
        self.assertIn("不表示已经枚举华为云账号可能使用的所有产品", contract_text)
        self.assertIn("不要先用裸 hcloud 获取区域列表", skill_text)
        self.assertIn("不要臆造某个平台的 Tool 名称", skill_text)
        self.assertIn("run_read_only_capability", skill_text)
        self.assertIn("Agent 自主决定查什么和传什么业务参数", skill_text)
        self.assertIn("账号级多服务资源盘点", skill_text)
        self.assertIn("账单、成本或费用记录查询", skill_text)
        self.assertIn("只有以下三种情况", skill_text)
        self.assertIn("`READ_ONLY_CAPABILITY_NOT_REGISTERED`", skill_text)
        self.assertIn("正例（北京4资源盘点）", skill_text)
        self.assertIn("正例（北京4区域成本）", skill_text)
        self.assertIn("反例", skill_text)
        self.assertIn("`cost-data`", skill_text)
        self.assertIn("`region_code=cn-north-4`", skill_text)
        self.assertIn("参数错误、凭据错误、超时、部分成功", skill_text)
        self.assertIn("专用场景脚本 ->", skill_text)
        self.assertIn("只适用于查询未登记", skill_text)
        self.assertIn("`run_guarded_change_capability`", skill_text)
        self.assertIn("`GUARDED_CHANGE_CAPABILITY_NOT_REGISTERED`", skill_text)
        self.assertIn("优先选择同一业务能力的最新版本", skill_text)
        self.assertIn("最新 capability 未声明时 Agent 不生成", skill_text)
        self.assertIn("`huaweicloud.ecs.create.v2` 固定使用 `CreateServers`", skill_text)
        self.assertIn("submit 结果不确定后禁止重复提交", skill_text)
        self.assertIn("`huaweicloud.kps.import_keypair.v1`", skill_text)
        self.assertIn("`huaweicloud.kps.delete_keypair.v1`", skill_text)
        self.assertIn("Agent 只编排业务步骤", skill_text)
        self.assertIn("不检查 bundle digest", skill_text)

    def test_ssh_guidance_is_runtime_neutral_and_secret_safe(self) -> None:
        playbook = (
            ROOT / "references/playbooks/ecs-ssh-access-readiness.md"
        ).read_text(encoding="utf-8")
        boundaries = (
            ROOT / "references/runtime-safety-boundaries.md"
        ).read_text(encoding="utf-8")

        self.assertIn("当前 Agent/runtime", playbook)
        self.assertIn("sshpass -f credentials/ecs-password.txt", playbook)
        self.assertIn("UserKnownHostsFile=credentials/known_hosts", playbook)
        self.assertIn("不得进入命令参数、环境变量", boundaries)
        for text in (playbook, boundaries):
            self.assertNotIn("CloudClaw", text)
            self.assertNotIn("cloud_claw.online", text)
            self.assertNotIn("result_contract=process_exit_v1", text)

    def test_core_instructions_do_not_name_host_agent_products(self) -> None:
        instruction_paths = [ROOT / "SKILL.md", *sorted((ROOT / "references").rglob("*.md"))]

        for path in instruction_paths:
            text = path.read_text(encoding="utf-8")
            for product_name in ("CloudClaw", "cloud_claw", "cloud-ppx", ".cloud-ppx"):
                with self.subTest(path=path.relative_to(ROOT), product=product_name):
                    self.assertNotIn(product_name, text)

    def test_scripts_do_not_auto_discover_sibling_source_repositories(self) -> None:
        forbidden_markers = (
            "ROOT.parent",
            "hcloud_common.ROOT.parent",
            "reference-projects",
            "agent_with_massive_apis",
            "huaweicloud-skills-by-huawei",
        )

        for path in sorted(SCRIPTS.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden_markers:
                with self.subTest(script=path.name, marker=marker):
                    self.assertNotIn(marker, text)

    def test_bundled_question_coverage_fixture_is_self_contained(self) -> None:
        result = check_question_coverage.analyze_questions(
            check_question_coverage.DEFAULT_QUESTIONS_DIR,
            xlsx_path=check_question_coverage.DEFAULT_XLSX_PATH,
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["files_checked"], 4)
        self.assertIsNone(result["xlsx_validation"])

    def test_service_registry_paths_and_high_coverage_contracts(self) -> None:
        registry = json.loads((ROOT / "references" / "service-registry.json").read_text(encoding="utf-8"))

        self.assertIn("ECS", registry["services"])
        for service, entry in registry["services"].items():
            for playbook in entry["playbooks"]:
                self.assertTrue((ROOT / playbook).exists(), f"{service} playbook missing: {playbook}")
            if entry["coverage"] == "high":
                self.assertTrue(entry["playbooks"], f"{service} high coverage requires playbooks")
                self.assertTrue(entry["planner"], f"{service} high coverage requires planner")
                self.assertTrue(entry["resource_verifier"], f"{service} high coverage requires resource verifier")
                self.assertTrue((ROOT / entry["planner"]).exists())
                self.assertTrue((ROOT / entry["resource_verifier"]).exists())
            if entry["change_operations"]:
                self.assertTrue(entry["planner"] or entry["known_limits"], f"{service} change operation needs planner or limits")
                flow = entry.get("change_flow")
                if flow:
                    self.assertTrue((ROOT / flow).exists(), f"{service} change_flow missing: {flow}")

        services = registry["services"]
        self.assertEqual(services["EIP"].get("change_flow"), "scripts/hcloud_eip_change_flow.py")
        self.assertEqual(services["IMS"]["change_operations"], [])
        self.assertEqual(
            services["KPS"]["change_operations"],
            ["CreateKeypair", "DeleteKeypair"],
        )
        self.assertEqual(
            services["KPS"].get("change_flow"),
            "scripts/hcloud_kps_keypair_change.py",
        )
        for service, entry in services.items():
            if entry.get("change_flow") == "scripts/hcloud_eip_change_flow.py":
                self.assertEqual(service, "EIP", f"{service} must not route to the EIP-specific flow")
            if (
                entry.get("planner") == "scripts/hcloud_service_change_plan.py"
                and service != "EIP"
                and entry.get("change_operations")
            ):
                self.assertEqual(
                    entry.get("change_flow"),
                    "scripts/hcloud_guarded_change_flow.py",
                    f"{service} service planner changes should use the generic guarded flow",
                )

    def test_resource_discovery_builds_json_friendly_commands(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="ListServersDetails",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
        )

        plan = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(plan["success"])
        command = plan["commands"][0]["command"]
        self.assertIn("--arg=--cli-output=json", command)
        self.assertIn("--expect-json", command)
        self.assertIn("--arg=--limit=20", command)

    def test_resource_discovery_resolves_lowercase_operation_names(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="listcloudservers",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
        )

        plan = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(plan["success"], plan)
        self.assertEqual(plan["commands"][0]["operation"], "ListCloudServers")
        self.assertEqual(plan["requested_operation"], "listcloudservers")

    def test_kps_discovery_uses_local_metadata_operation_name(self) -> None:
        args = SimpleNamespace(
            service="KPS",
            operation="ListKeypairs",
            region="cn-north-4",
            project_id=None,
            profile=None,
            limit=20,
            execute=False,
        )

        plan = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(plan["success"])
        self.assertEqual(plan["commands"][0]["operation"], "ListKeypairs")
        self.assertNotIn("--arg=--limit=20", plan["commands"][0]["command"])
        self.assertEqual(plan["commands"][0]["omitted_args"], ["--limit"])

    def test_resource_scoped_queries_are_not_generic_discovery_operations(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="ShowServer",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
        )

        plan = hcloud_resource_discovery.build_plan(args)

        self.assertFalse(plan["success"])
        self.assertIn("requires explicit parameters", plan["error"])
        self.assertEqual(plan["catalog_required_params"], ["server_id"])

    def test_eip_discovery_uses_catalog_known_limit(self) -> None:
        args = SimpleNamespace(
            service="EIP",
            operation="ListPublicips",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
        )

        plan = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(plan["success"])
        self.assertEqual(plan["commands"][0]["operation"], "ListPublicips")
        self.assertIn("--arg=--limit=20", plan["commands"][0]["command"])
        self.assertNotIn("omitted_args", plan["commands"][0])

    def test_change_plan_classifies_delete_as_high_risk(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="DeleteServers",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
        )

        plan = hcloud_change_plan.build_plan(args)

        self.assertEqual(plan["risk"]["level"], "high")
        self.assertTrue(plan["risk"]["requires_confirmation"])
        self.assertIn("--arg=--dryrun", plan["commands"]["dryrun_or_plan"])

    def test_change_plan_classifies_composite_mutation_names(self) -> None:
        cases = [
            ("BatchDeleteServerNics", "high"),
            ("ChangeServerOsWithCloudInit", "high"),
            ("NeutronDeleteNetwork", "high"),
            ("GlanceDeleteImage", "high"),
            ("ResizeServer", "medium"),
            ("AssociateServerVirtualIp", "medium"),
            ("BatchCreateServerTags", "medium"),
            ("ListServersDetails", "low"),
            ("ShowJob", "low"),
            ("listcloudservers", "low"),
            ("showserver", "low"),
            ("listl7rules", "low"),
            ("searchqueryscaleflavors", "low"),
            ("downloadslowlog", "low"),
            ("batchdeleteservernics", "high"),
            ("changeserveroswithcloudinit", "high"),
            ("ShowResetPasswordFlag", "low"),
            ("showresetpasswordflag", "low"),
        ]

        for operation, expected_level in cases:
            with self.subTest(operation=operation):
                risk = hcloud_change_plan.assess_risk(operation, dryrun_supported=True)

                self.assertEqual(risk.level, expected_level)
                self.assertEqual(risk.requires_confirmation, expected_level != "low")
                self.assertEqual(risk.verification_required, expected_level != "low")

    def test_change_plan_requires_confirmation_for_sensitive_reads(self) -> None:
        cases = [
            "ShowServerPassword",
            "showserverpassword",
            "ShowCertificatePrivateKeyEcho",
            "showcertificateprivatekeyecho",
        ]

        for operation in cases:
            with self.subTest(operation=operation):
                risk = hcloud_change_plan.assess_risk(operation, dryrun_supported=True)

                self.assertEqual(risk.level, "high")
                self.assertTrue(risk.requires_confirmation)
                self.assertFalse(risk.dryrun_required)
                self.assertFalse(risk.verification_required)

    def test_change_plan_uses_conservative_gate_for_unknown_non_read_operations(self) -> None:
        risk = hcloud_change_plan.assess_risk("RunMaintenanceTask", dryrun_supported=True)

        self.assertEqual(risk.level, "medium")
        self.assertTrue(risk.requires_confirmation)
        self.assertTrue(risk.verification_required)

    def test_change_plan_applies_metadata_category_risk_floor(self) -> None:
        security_risk = hcloud_change_plan.assess_risk(
            "UpdatePolicy",
            dryrun_supported=True,
            service="WAF",
            metadata_category="Security & Compliance",
        )
        identity_risk = hcloud_change_plan.assess_risk(
            "CreateAnalyzer",
            dryrun_supported=True,
            service="IAMAccessAnalyzer",
            metadata_category="Management & Governance",
        )
        iam_provider_risk = hcloud_change_plan.assess_risk(
            "CreateOIDCProviderV5",
            dryrun_supported=True,
            service="IAM",
            metadata_category="Management & Governance",
        )
        billing_mutation_risk = hcloud_change_plan.assess_risk(
            "UpdatePeriodToOnDemandInstantly",
            dryrun_supported=True,
            service="BSS",
            metadata_category="Management & Governance",
        )
        read_risk = hcloud_change_plan.assess_risk(
            "ListPolicies",
            dryrun_supported=True,
            service="WAF",
            metadata_category="Security & Compliance",
        )

        self.assertEqual(security_risk.level, "high")
        self.assertTrue(security_risk.hard_guard)
        self.assertEqual(identity_risk.level, "high")
        self.assertTrue(identity_risk.hard_guard)
        self.assertEqual(iam_provider_risk.level, "high")
        self.assertTrue(iam_provider_risk.hard_guard)
        self.assertEqual(billing_mutation_risk.level, "high")
        self.assertTrue(billing_mutation_risk.hard_guard)
        self.assertEqual(read_risk.level, "low")
        self.assertFalse(read_risk.hard_guard)

    def test_change_plan_blocks_unrestricted_sensitive_ingress_ports(self) -> None:
        for port in (22, 80, 443, 3000, 5000, 8000, 8080):
            with self.subTest(port=port):
                args = SimpleNamespace(
                    service="VPC",
                    operation="CreateSecurityGroupRule",
                    region="cn-north-4",
                    project_id="project-1",
                    profile=None,
                    json_input_file=None,
                    arg=[
                        "--direction=ingress",
                        "--protocol=tcp",
                        "--remote_ip_prefix=0.0.0.0/0",
                        f"--port_range_min={port}",
                        f"--port_range_max={port}",
                    ],
                    no_dryrun=False,
                )

                plan = hcloud_change_plan.build_plan(args)

                self.assertFalse(plan["success"], plan)
                self.assertEqual(plan["commands"], {})
                self.assertEqual(plan["policy_violations"][0]["code"], "unrestricted_sensitive_ingress_port")
                self.assertIn(port, plan["policy_violations"][0]["ports"])

    def test_change_plan_allows_restricted_or_non_sensitive_security_group_rules(self) -> None:
        cases = [
            [
                "--direction=ingress",
                "--protocol=tcp",
                "--remote_ip_prefix=203.0.113.10/32",
                "--port_range_min=22",
                "--port_range_max=22",
            ],
            [
                "--direction=egress",
                "--protocol=tcp",
                "--remote_ip_prefix=0.0.0.0/0",
                "--port_range_min=22",
                "--port_range_max=22",
            ],
            [
                "--direction=ingress",
                "--protocol=tcp",
                "--remote_ip_prefix=0.0.0.0/0",
                "--port_range_min=9000",
                "--port_range_max=9000",
            ],
        ]
        for arg in cases:
            with self.subTest(arg=arg):
                args = SimpleNamespace(
                    service="VPC",
                    operation="CreateSecurityGroupRule",
                    region="cn-north-4",
                    project_id="project-1",
                    profile=None,
                    json_input_file=None,
                    arg=arg,
                    no_dryrun=False,
                )

                plan = hcloud_change_plan.build_plan(args)

                self.assertTrue(plan["success"], plan)
                self.assertNotIn("policy_violations", plan)

    def test_change_plan_allows_explicit_public_web_ingress(self) -> None:
        for port in (80, 443):
            with self.subTest(port=port):
                args = SimpleNamespace(
                    service="VPC",
                    operation="CreateSecurityGroupRule",
                    region="cn-north-4",
                    project_id="project-1",
                    profile=None,
                    json_input_file=None,
                    arg=[
                        "--direction=ingress",
                        "--protocol=tcp",
                        "--remote_ip_prefix=0.0.0.0/0",
                        f"--port_range_min={port}",
                        f"--port_range_max={port}",
                    ],
                    no_dryrun=False,
                    allow_public_web=True,
                )

                plan = hcloud_change_plan.build_plan(args)

                self.assertTrue(plan["success"], plan)
                self.assertEqual(
                    plan["public_web_exposure"],
                    {
                        "enabled": True,
                        "allowed_protocol": "tcp",
                        "allowed_ports": [80, 443],
                        "allowed_ipv4_source": "0.0.0.0/0",
                    },
                )
                self.assertTrue(
                    any("public Web" in warning for warning in plan["plan"]["warnings"]),
                    plan["plan"]["warnings"],
                )

    def test_change_plan_public_web_allowance_keeps_unsafe_rules_blocked(self) -> None:
        cases = [
            ("ssh", "tcp", 22, 22),
            ("development_port", "tcp", 3000, 3000),
            ("wide_range", "tcp", 80, 443),
            ("ambiguous_protocol", "all", 80, 80),
        ]
        for name, protocol, min_port, max_port in cases:
            with self.subTest(case=name):
                args = SimpleNamespace(
                    service="VPC",
                    operation="CreateSecurityGroupRule",
                    region="cn-north-4",
                    project_id="project-1",
                    profile=None,
                    json_input_file=None,
                    arg=[
                        "--direction=ingress",
                        f"--protocol={protocol}",
                        "--remote_ip_prefix=0.0.0.0/0",
                        f"--port_range_min={min_port}",
                        f"--port_range_max={max_port}",
                    ],
                    no_dryrun=False,
                    allow_public_web=True,
                )

                plan = hcloud_change_plan.build_plan(args)

                self.assertFalse(plan["success"], plan)
                self.assertEqual(plan["commands"], {})
                self.assertEqual(
                    plan["policy_violations"][0]["code"],
                    "unrestricted_sensitive_ingress_port",
                )

    def test_materials_drift_mapping_is_well_formed(self) -> None:
        result = check_materials_drift.check_mapping()

        for item in result["findings"]:
            self.assertEqual(item["missing"], [], item)

    def test_question_coverage_accepts_safe_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            read_dir = root / "read_type"
            crud_dir = root / "crud"
            read_dir.mkdir()
            crud_dir.mkdir()
            (read_dir / "ecs.json").write_text(
                json.dumps(
                    [
                        {"question": "List ECS instances.", "relevant_apis": ["listcloudservers"]},
                        {"question": "Read initial password.", "relevant_apis": ["showserverpassword"]},
                    ]
                ),
                encoding="utf-8",
            )
            (crud_dir / "ecs_update.json").write_text(
                json.dumps(
                    [
                        {
                            "question": "Rename ECS.",
                            "relevant_apis": ["ecs-BatchUpdateServersName", "ecs-ListServersDetails"],
                            "type": "update",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (crud_dir / "ecs_delete.json").write_text(
                json.dumps(
                    [
                        {
                            "question": "Delete NICs.",
                            "relevant_apis": ["ecs-BatchDeleteServerNics", "ecs-ListCloudServers"],
                            "type": "delete",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            result = check_question_coverage.analyze_questions(root, xlsx_path=None)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["schema_errors"], [])
        self.assertEqual(result["risk_errors"], [])
        self.assertEqual(result["coverage_errors"], [])
        self.assertEqual(result["unique_risk_summary"]["high"], 2)

    def test_question_coverage_can_fail_registry_threshold(self) -> None:
        counters = {
            "ECS": check_question_coverage.collections.Counter({"total": 10, "registered": 1}),
        }

        result = check_question_coverage.coverage_errors_from_registry(counters, {"ECS": 0.5}, 0.1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["service"], "ECS")
        self.assertEqual(result[0]["registered_ratio"], 0.1)

    def test_validation_workbook_extracts_service_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workbook = Path(tmp_dir) / "data.xlsx"
            write_minimal_xlsx(
                workbook,
                [
                    ["问题", "验证方法"],
                    ["Check ECS.", "1. 调用 ECS 查询工具（ListServersDetails）确认实例存在"],
                    ["Check subnet.", "1. 调用子网查询工具（ListSubnets）确认子网存在"],
                ],
            )

            result = check_question_coverage.analyze_validation_workbook(workbook)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["schema_errors"], [])
        self.assertIn("ECS", result["operation_summary_by_service"])
        self.assertIn("VPC", result["operation_summary_by_service"])
        self.assertEqual(result["unregistered_operation_count"], 0)
        self.assertEqual(result["execution_path_error_count"], 0)
        self.assertEqual(result["status_summary"], {"passed": 2, "skipped": 0, "not_covered": 0})
        self.assertIn("ECS:query:scripts/hcloud_resource_discovery.py", result["executable_validation_paths"])

    def test_validation_workbook_reports_missing_workbook_as_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workbook = Path(tmp_dir) / "missing.xlsx"

            result = check_question_coverage.analyze_validation_workbook(workbook)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["skipped"])
        self.assertEqual(result["status_summary"], {"passed": 0, "skipped": 1, "not_covered": 0})

    def test_validation_workbook_tracks_resource_query_execution_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workbook = Path(tmp_dir) / "data.xlsx"
            write_minimal_xlsx(
                workbook,
                [
                    ["问题", "验证方法"],
                    ["Check cluster.", "1. 调用 CCE 查询工具（ShowCluster）确认集群存在"],
                    ["Check CDN.", "1. 调用 CDN 查询工具（ShowDomain）确认域名存在"],
                    ["Check RDS config.", "1. 调用 RDS 查询工具（ShowConfigurationDetail）确认参数模板存在"],
                    ["Check VPC.", "1. 调用 VPC 查询工具（ShowVpc）确认网络存在"],
                    ["Check EVS.", "1. 调用云硬盘查询工具（ShowVolume）确认磁盘存在"],
                    ["Check IMS.", "1. 调用镜像查询工具（GlanceShowImage）确认镜像存在"],
                    ["Check KPS.", "1. 调用密钥对查询工具（ListKeypairDetail）确认密钥对存在"],
                    ["Check NAT.", "1. 调用 NAT 查询工具（ShowNatGatewayDnatRule）确认 DNAT 规则存在"],
                    ["Check OBS buckets.", "1. 调用 OBS 查询工具（ListBuckets）确认桶列表可用"],
                    ["Check OBS lifecycle.", "1. 调用 OBS 查询工具（GetBucketLifecycle）确认生命周期配置"],
                ],
            )

            result = check_question_coverage.analyze_validation_workbook(workbook)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["execution_path_error_count"], 0)
        self.assertEqual(
            result["executable_validation_paths"]["CCE:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["CDN:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["RDS:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["VPC:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["EVS:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["IMS:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["KPS:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["NAT:resource_query:scripts/hcloud_resource_query.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["OBS:query:scripts/hcloud_obs_readonly.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["OBS:resource_query:scripts/hcloud_obs_readonly.py"],
            1,
        )
        self.assertEqual(
            result["operation_aliases_applied"]["RDS:ShowConfigurationDetail->ShowConfiguration"],
            1,
        )

    def test_validation_workbook_tracks_guarded_change_execution_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            workbook = Path(tmp_dir) / "data.xlsx"
            write_minimal_xlsx(
                workbook,
                [
                    ["问题", "验证方法"],
                    ["Change VPC.", "1. 调用 VPC 变更工具（CreateSecurityGroupRule）生成风险门禁计划"],
                    ["Change EIP.", "1. 调用 EIP 变更工具（UpdatePublicip）生成 EIP flow"],
                    ["Change OBS.", "1. 调用 OBS 变更工具（PutBucketLifecycle）生成 planner"],
                ],
            )

            result = check_question_coverage.analyze_validation_workbook(workbook)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["execution_path_error_count"], 0)
        self.assertEqual(
            result["executable_validation_paths"]["VPC:guarded_change:scripts/hcloud_guarded_change_flow.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["EIP:guarded_change:scripts/hcloud_eip_change_flow.py"],
            1,
        )
        self.assertEqual(
            result["executable_validation_paths"]["OBS:planner_only_change:scripts/hcloud_obs_change_plan.py"],
            1,
        )

    def test_run_journal_appends_and_summarizes_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            journal = Path(tmp_dir) / "run.jsonl"
            hcloud_run_journal.append_event(journal, {"type": "command", "success": True})
            hcloud_run_journal.append_event(journal, {"type": "verification", "success": True})

            summary = hcloud_run_journal.summarize_events(hcloud_run_journal.read_events(journal))

        self.assertEqual(summary["event_count"], 2)
        self.assertEqual(summary["command_count"], 1)
        self.assertEqual(summary["verification_count"], 1)

    def test_run_journal_redacts_sensitive_event_data_on_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            journal = Path(tmp_dir) / "run.jsonl"
            entry = hcloud_run_journal.append_event(
                journal,
                {
                    "type": "command",
                    "command": [
                        "hcloud",
                        "configure",
                        "set",
                        "--secret-key=secret-value",
                        "--password",
                        "password-value",
                        '--arg={"adminPass":"json-password-value"}',
                    ],
                    "adminPass": "password-value",
                    "accessToken": "token-value",
                    "stdout": "created with token-value",
                    "stderr": 'using --access-token=token-inline-value and {"private_key":"private-key-value"}',
                },
            )
            raw_text = journal.read_text(encoding="utf-8")

        self.assertEqual(entry["adminPass"], "***")
        self.assertEqual(entry["accessToken"], "***")
        self.assertEqual(entry["stdout"], "created with ***")
        self.assertEqual(entry["command"][3], "--secret-key=***")
        self.assertEqual(entry["command"][5], "***")
        self.assertNotIn("password-value", raw_text)
        self.assertNotIn("token-value", raw_text)
        self.assertNotIn("secret-value", raw_text)
        self.assertNotIn("json-password-value", raw_text)
        self.assertNotIn("token-inline-value", raw_text)
        self.assertNotIn("private-key-value", raw_text)

    def test_v06_acceptance_scenarios_cover_upgrade_goals(self) -> None:
        text = (ROOT / "tests" / "v0_6_acceptance_scenarios.md").read_text(encoding="utf-8")

        required_phrases = [
            "hcloud_environment_doctor.py",
            "entry-level-web-hosting",
            "Flexus L",
            "OBS",
            "hcloud_billing_readonly.py",
            "hcloud_billing_result_summarize.py",
            "semantic_route",
            "hcloud_ces_alarm_plan.py",
            "AGT.ECS",
            "mem_usedPercent",
            "hcloud_governance_closure_plan.py",
            "hcloud_terraform_context_inspect.py",
            "hcloud_terraform_provider_inventory.py",
            "ForceNew",
            "Import",
            "terraform import",
            "--security-group-evidence-file",
            "0.0.0.0/0",
        ]

        self.assertGreaterEqual(text.count("## Scenario"), 8)
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_script_audience_manifest_covers_current_scripts(self) -> None:
        manifest = json.loads(
            (ROOT / "references" / "script-audience-manifest.json").read_text(encoding="utf-8")
        )
        groups = manifest["script_groups"]
        listed_scripts: list[str] = []

        for group in groups:
            with self.subTest(group=group["id"]):
                self.assertIn("audience", group)
                self.assertIn("boundary", group)
                self.assertTrue(group["scripts"])
                for script in group["scripts"]:
                    self.assertFalse(Path(script).is_absolute(), script)
                    self.assertTrue((ROOT / script).exists(), script)
                    listed_scripts.append(script)

        actual_scripts = sorted(f"scripts/{path.name}" for path in SCRIPTS.glob("*.py"))
        self.assertEqual(sorted(listed_scripts), sorted(set(listed_scripts)))
        self.assertEqual(sorted(listed_scripts), actual_scripts)

        by_group = {group["id"]: set(group["scripts"]) for group in groups}
        self.assertIn("scripts/hcloud_environment_doctor.py", by_group["default_runtime"])
        self.assertIn("scripts/hcloud_billing_readonly.py", by_group["default_runtime"])
        self.assertIn("scripts/hcloud_change_plan.py", by_group["guarded_change"])
        self.assertIn(
            "scripts/hcloud_kps_keypair_change.py",
            by_group["guarded_change"],
        )
        self.assertIn("scripts/hcloud_sdk_readonly.py", by_group["runtime_supplement"])
        self.assertIn("scripts/check_question_coverage.py", by_group["maintenance_and_regression"])
        self.assertIn(
            "scripts/hcloud_terraform_provider_inventory.py",
            by_group["maintenance_and_regression"],
        )
        self.assertNotIn(
            "scripts/hcloud_terraform_provider_inventory.py",
            by_group["default_runtime"],
        )
        self.assertIn("scripts/hcloud_common.py", by_group["internal_library"])
        self.assertIn("scripts/hcloud_output_policy.py", by_group["internal_library"])
        self.assertIn("scripts/qwen_text_to_image.py", by_group["compatibility"])
        compatibility = next(group for group in groups if group["id"] == "compatibility")
        self.assertEqual(compatibility["status"], "deprecated")
        self.assertEqual(compatibility["deprecated_in"], "v0.8.0")
        self.assertIn("scripts/hcloud_closure_plan.py", compatibility["replacement_entry_points"])
        self.assertIn("scripts/hcloud_acceptance_closure.py", compatibility["replacement_entry_points"])
        self.assertIn("compatibility_retirement_policy", manifest["consolidation_policy"])
        self.assertEqual(
            manifest["consolidation_policy"]["compatibility_retirement_policy"]["source"],
            "references/versioning-policy.md",
        )

        execution_boundary = manifest["hcloud_execution_boundary"]
        self.assertEqual(
            execution_boundary["business_api_policy"],
            "safe_exec_by_default_with_evidenced_fallback",
        )
        direct_groups = execution_boundary["direct_invocation_categories"]
        classified_direct_scripts = {
            script
            for group in direct_groups
            for script in group["scripts"]
        }
        detected_direct_scripts = set()
        for path in SCRIPTS.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            resolves_hcloud = (
                'shutil.which("hcloud")' in source
                or "shutil.which('hcloud')" in source
                or "resolve_hcloud_binary" in source
            )
            if "subprocess.run" in source and resolves_hcloud:
                detected_direct_scripts.add(f"scripts/{path.name}")

        self.assertEqual(classified_direct_scripts, detected_direct_scripts)
        safe_executor = next(
            group for group in direct_groups if group["id"] == "safe_business_api_executor"
        )
        self.assertEqual(safe_executor["scripts"], ["scripts/hcloud_safe_exec.py"])
        metadata_only = next(
            group for group in direct_groups if group["id"] == "metadata_and_diagnostics"
        )
        self.assertIn("version", metadata_only["allowed_command_shapes"])
        self.assertIn("meta download", metadata_only["allowed_command_shapes"])

    def test_task_records_exclude_secrets_but_may_reference_restricted_credentials(self) -> None:
        guide = (ROOT / "references" / "task-workspace-guide.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("普通 task 记录、证据、manifest 和业务产物", guide)
        self.assertIn("受限 credential artifact", guide)
        self.assertIn("`0600`", guide)
        self.assertIn("只记录相对路径、用途和可用状态", guide)

    def test_large_output_policy_is_machine_readable_and_visible_at_entry(self) -> None:
        import hcloud_catalog

        policy = json.loads(
            (ROOT / "references" / "hcloud-output-policies.json").read_text(
                encoding="utf-8"
            )
        )
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        output_guide = (
            ROOT / "references" / "output-and-query.md"
        ).read_text(encoding="utf-8")

        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(policy["operations"]["IMS:ListImages"]["mode"], "summary")
        self.assertEqual(policy["operations"]["ECS:ListFlavors"]["mode"], "summary")
        self.assertEqual(
            policy["operations"]["ECS:ListFlavorSellPolicies"]["mode"],
            "summary",
        )
        self.assertEqual(
            policy["operations"]["CodeArtsRepo:ShowFileContent"]["mode"],
            "file-only",
        )
        self.assertTrue(policy["families"])
        self.assertIn("OUTPUT_POLICY_REQUIRED", skill_text)
        self.assertIn("references/hcloud-output-policies.json", skill_text)
        self.assertIn("禁止先执行裸 `hcloud` 试探响应大小", skill_text)
        self.assertIn("不得把完整列表、完整文件或完整 `parsed_json` 再输出到对话", skill_text)
        for operation_key in policy["operations"]:
            self.assertIn(f"`{operation_key}`", skill_text)
        self.assertIn("--output-mode=auto", output_guide)
        self.assertIn("--allow-large-output", output_guide)

        catalog = hcloud_catalog.load_catalog()
        for key, entry in policy["operations"].items():
            default_limit = entry.get("default_limit")
            if not default_limit:
                continue
            service_name, operation_name = key.split(":", 1)
            service = hcloud_catalog.resolve_service(catalog, service_name)
            operation = hcloud_catalog.resolve_operation(service, operation_name)
            self.assertIsNotNone(operation, key)
            for version in hcloud_catalog.operation_versions(operation):
                detail = hcloud_catalog.operation_version_detail(operation, version)
                params = {
                    hcloud_catalog.normalize_param_name(name)
                    for name in hcloud_catalog.operation_param_names(detail)
                }
                self.assertIn(
                    default_limit["param"],
                    params,
                    f"{key}/{version}",
                )

    def test_active_docs_and_examples_use_unified_entry_points(self) -> None:
        legacy_entry_points = {
            "hcloud_acceptance_evidence_result.py",
            "hcloud_acceptance_probe_plan.py",
            "hcloud_acceptance_probe_run.py",
            "hcloud_governance_closure_plan.py",
            "hcloud_lifecycle_closure_plan.py",
            "hcloud_p2_scenario_closure_plan.py",
            "qwen_text_to_image.py",
        }
        active_paths = [
            ROOT / "README.md",
            ROOT / "SKILL.md",
            ROOT / "references" / "runtime-safety-boundaries.md",
            ROOT / "references" / "maas-model-calls.md",
            ROOT / "references" / "maas-image-generation.md",
            ROOT / "references" / "scenario-router.json",
            *sorted((ROOT / "examples").rglob("*.md")),
        ]

        for path in active_paths:
            text = path.read_text(encoding="utf-8")
            for legacy_entry_point in legacy_entry_points:
                with self.subTest(path=path.relative_to(ROOT), entry=legacy_entry_point):
                    self.assertNotIn(legacy_entry_point, text)

    def test_skill_entry_stays_slim_and_points_to_truth_sources(self) -> None:
        skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        safety_text = (ROOT / "references" / "runtime-safety-boundaries.md").read_text(encoding="utf-8")
        version_text = (ROOT / "references" / "versioning-policy.md").read_text(encoding="utf-8")

        self.assertLessEqual(len(skill_text.splitlines()), 300)
        self.assertIn("references/runtime-safety-boundaries.md", skill_text)
        self.assertIn("references/scripts.md", skill_text)
        self.assertIn("references/versioning-policy.md", skill_text)
        self.assertIn("hcloud_closure_plan.py", skill_text)
        self.assertIn("hcloud_acceptance_closure.py", skill_text)
        self.assertIn("不要自行拼接或直接执行裸 `hcloud` 命令", skill_text)
        self.assertIn("专用场景脚本 ->", skill_text)
        self.assertIn(
            "只有帮助/诊断或脚本无法表达的窄范围操作才允许裸 `hcloud` 兜底",
            skill_text,
        )
        self.assertIn("CHANGELOG.md", version_text)
        self.assertIn("RELEASE_NOTES.md", version_text)
        self.assertNotIn("## 当前版本覆盖", skill_text)
        self.assertNotIn("tests/v0_6_acceptance_scenarios.md", skill_text)

        entry_section = skill_text.split("## 首选入口", 1)[1].split("## 资料入口", 1)[0]
        entry_rows = [
            line for line in entry_section.splitlines()
            if line.startswith("| ") and " | " in line and not line.startswith("| ---")
        ]
        self.assertLessEqual(len(entry_rows), 11)

        for phrase in (
            "异步任务必须跟到终态",
            "安全组入口端口必须收敛",
            "结果叙事必须真实",
            "机内执行和 SSH fallback",
            "不要为了让过程显得完整",
            "0.0.0.0/0",
            "COC",
            "169.254.169.254",
            "--allow-private-targets",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, safety_text)

        for phrase in ("兼容入口退役节奏", "v0.8", "v0.9", "v1.0"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, version_text)


if __name__ == "__main__":
    unittest.main()
