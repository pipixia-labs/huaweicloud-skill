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
        self.assertIn("ECS:query:scripts/hcloud_resource_discovery.py", result["executable_validation_paths"])

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


if __name__ == "__main__":
    unittest.main()
