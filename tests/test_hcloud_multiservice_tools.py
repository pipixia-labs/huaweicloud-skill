"""Tests for multi-service smoke, planner, and verifier helpers."""

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
    """Load a script module for isolated unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_readonly_smoke = load_module("hcloud_readonly_smoke", SCRIPTS / "hcloud_readonly_smoke.py")
hcloud_eip_change_flow = load_module("hcloud_eip_change_flow", SCRIPTS / "hcloud_eip_change_flow.py")
hcloud_guarded_change_flow = load_module("hcloud_guarded_change_flow", SCRIPTS / "hcloud_guarded_change_flow.py")
hcloud_obs_change_plan = load_module("hcloud_obs_change_plan", SCRIPTS / "hcloud_obs_change_plan.py")
hcloud_obs_readonly = load_module("hcloud_obs_readonly", SCRIPTS / "hcloud_obs_readonly.py")
hcloud_catalog_readonly_smoke = load_module("hcloud_catalog_readonly_smoke", SCRIPTS / "hcloud_catalog_readonly_smoke.py")
hcloud_resource_detail_probe = load_module("hcloud_resource_detail_probe", SCRIPTS / "hcloud_resource_detail_probe.py")
hcloud_resource_discovery = load_module("hcloud_resource_discovery", SCRIPTS / "hcloud_resource_discovery.py")
hcloud_resource_query = load_module("hcloud_resource_query", SCRIPTS / "hcloud_resource_query.py")
hcloud_resource_verify = load_module("hcloud_resource_verify", SCRIPTS / "hcloud_resource_verify.py")
hcloud_service_readiness = load_module("hcloud_service_readiness", SCRIPTS / "hcloud_service_readiness.py")
hcloud_service_change_plan = load_module("hcloud_service_change_plan", SCRIPTS / "hcloud_service_change_plan.py")
hcloud_account_inventory = load_module("hcloud_account_inventory", SCRIPTS / "hcloud_account_inventory.py")
hcloud_idle_audit = load_module("hcloud_idle_audit", SCRIPTS / "hcloud_idle_audit.py")
hcloud_observability_plan = load_module("hcloud_observability_plan", SCRIPTS / "hcloud_observability_plan.py")
hcloud_billing_cost_probe = load_module("hcloud_billing_cost_probe", SCRIPTS / "hcloud_billing_cost_probe.py")
hcloud_billing_readonly = load_module("hcloud_billing_readonly", SCRIPTS / "hcloud_billing_readonly.py")
hcloud_billing_operation_gap = load_module(
    "hcloud_billing_operation_gap",
    SCRIPTS / "hcloud_billing_operation_gap.py",
)
hcloud_billing_live_read = load_module("hcloud_billing_live_read", SCRIPTS / "hcloud_billing_live_read.py")
hcloud_billing_result_summarize = load_module(
    "hcloud_billing_result_summarize",
    SCRIPTS / "hcloud_billing_result_summarize.py",
)
hcloud_cce_assessment_plan = load_module("hcloud_cce_assessment_plan", SCRIPTS / "hcloud_cce_assessment_plan.py")
hcloud_teardown_plan = load_module("hcloud_teardown_plan", SCRIPTS / "hcloud_teardown_plan.py")
hcloud_ces_alarm_plan = load_module("hcloud_ces_alarm_plan", SCRIPTS / "hcloud_ces_alarm_plan.py")
hcloud_ces_datapoint_plan = load_module("hcloud_ces_datapoint_plan", SCRIPTS / "hcloud_ces_datapoint_plan.py")
hcloud_lts_readonly = load_module("hcloud_lts_readonly", SCRIPTS / "hcloud_lts_readonly.py")
hcloud_lifecycle_closure_plan = load_module("hcloud_lifecycle_closure_plan", SCRIPTS / "hcloud_lifecycle_closure_plan.py")
hcloud_governance_closure_plan = load_module("hcloud_governance_closure_plan", SCRIPTS / "hcloud_governance_closure_plan.py")
hcloud_p2_scenario_closure_plan = load_module("hcloud_p2_scenario_closure_plan", SCRIPTS / "hcloud_p2_scenario_closure_plan.py")
hcloud_closure_maturity_audit = load_module("hcloud_closure_maturity_audit", SCRIPTS / "hcloud_closure_maturity_audit.py")
hcloud_acceptance_evidence_result = load_module("hcloud_acceptance_evidence_result", SCRIPTS / "hcloud_acceptance_evidence_result.py")
hcloud_acceptance_probe_plan = load_module("hcloud_acceptance_probe_plan", SCRIPTS / "hcloud_acceptance_probe_plan.py")


class MultiServiceToolsTest(unittest.TestCase):
    """Validate multi-service tool contracts without calling hcloud."""

    def eip_flow_args(self, **overrides):
        """Return default EIP flow args for unit tests."""
        values = {
            "operation": "UpdatePublicip",
            "publicip_id": "eip-1",
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "json_input_file": None,
            "arg": ["--publicip_id=eip-1"],
            "no_dryrun": False,
            "allow_unregistered": False,
            "execute_dryrun": False,
            "execute_submit": False,
            "confirm_submit": False,
            "submit_token": None,
            "skip_dryrun": False,
            "execute_verify": False,
            "journal": None,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def guarded_flow_args(self, **overrides):
        """Return default generic guarded flow args for unit tests."""
        values = {
            "service": "VPC",
            "operation": "CreateSecurityGroupRule",
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "json_input_file": None,
            "arg": ["--security_group_id=sg-1"],
            "no_dryrun": False,
            "allow_unregistered": False,
            "allow_public_web": False,
            "execute_dryrun": False,
            "execute_submit": False,
            "confirm_submit": False,
            "submit_token": None,
            "skip_dryrun": False,
            "execute_readiness": False,
            "verify_operation": None,
            "verify_param": ["security_group_rule_id=rule-1"],
            "execute_verify": False,
            "journal": None,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def inventory_args(self, **overrides):
        """Return default account inventory args for unit tests."""
        values = {
            "service": [],
            "region": "cn-north-4",
            "region_file": None,
            "project_id": "project-1",
            "enterprise_project_id": None,
            "profile": None,
            "limit": 10,
            "obs_endpoint": None,
            "obs_config": None,
            "obs_payer": None,
            "execute": False,
            "strict": True,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def observability_args(self, **overrides):
        """Return default observability plan args for unit tests."""
        values = {
            "service": "ECS",
            "target_id": "server-1",
            "target_name": "app-1",
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "limit": 10,
            "execute": False,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def billing_probe_args(self, **overrides):
        """Return default billing cost probe args for unit tests."""
        values = {
            "service_token": list(hcloud_billing_cost_probe.DEFAULT_SERVICE_TOKENS),
            "operation_keyword": ["invoice"],
            "limit": 5,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def billing_readonly_args(self, **overrides):
        """Return default billing readonly planner args for unit tests."""
        values = {
            "operation": "monthly-sum",
            "entry_point": None,
            "endpoint_base": hcloud_billing_readonly.DEFAULT_ENDPOINT_BASE,
            "language": "zh_CN",
            "bill_cycle": "2026-05",
            "shared_month": None,
            "begin_time": None,
            "end_time": None,
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
            "region_code": None,
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
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def billing_live_read_args(self, **overrides):
        """Return default billing live-read args for unit tests."""
        values = {
            **self.billing_readonly_args().__dict__,
            "execute": False,
            "confirm_live_billing_read": None,
            "include_redacted_records": False,
            "timeout": 1,
            "max_output_chars": 2000,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def ces_alarm_args(self, **overrides):
        """Return default CES alarm planner args for unit tests."""
        values = {
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "limit": 10,
            "alarm_name": "cpu-high",
            "namespace": "SYS.ECS",
            "metric_name": "cpu_util",
            "dimension": ["instance_id=server-1"],
            "comparison_operator": ">",
            "threshold": 80.0,
            "period": 300,
            "evaluation_periods": 3,
            "statistic": "average",
            "notification_enabled": False,
            "execute": False,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def ces_datapoint_args(self, **overrides):
        """Return default CES datapoint planner args for unit tests."""
        values = {
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "namespace": "SYS.ECS",
            "metric_name": "cpu_util",
            "dimension": ["instance_id=server-1"],
            "filter": "average",
            "period": 300,
            "from_ms": 1700000000000,
            "to_ms": 1700001800000,
            "lookback_minutes": 30,
            "result_json_file": None,
            "execute": False,
            "timeout": 1,
            "max_output_chars": 2000,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def lts_args(self, **overrides):
        """Return default LTS readonly args for unit tests."""
        values = {
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "limit": 10,
            "log_group_id": None,
            "log_stream_id": None,
            "start_time": None,
            "end_time": None,
            "keyword": None,
            "execute": False,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def lifecycle_args(self, **overrides):
        """Return default lifecycle closure planner args for unit tests."""
        values = {
            "service": ["VPC"],
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
            "limit": 10,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def governance_args(self, **overrides):
        """Return default P1 governance closure planner args for unit tests."""
        values = {
            "service": [],
            "param": [],
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "min_live_ops": 2,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def p2_args(self, **overrides):
        """Return default P2 scenario closure planner args for unit tests."""
        values = {
            "group": [],
            "param": [],
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "limit": 10,
            "catalog_max_operations": 3,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def cce_assessment_args(self, **overrides):
        """Return default CCE assessment planner args for unit tests."""
        values = {
            "cluster_id": None,
            "cluster_name": None,
            "namespace": None,
            "workload": None,
            "dimension": None,
            "include_kubernetes": False,
            "region": "cn-north-4",
            "project_id": "project-1",
            "profile": None,
            "limit": 10,
            "catalog_max_operations": 3,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def current_eip_submit_token(self, args: SimpleNamespace) -> str:
        """Return the submit token for a test EIP flow argument set."""
        service_plan = hcloud_eip_change_flow.hcloud_service_change_plan.build_service_plan(hcloud_eip_change_flow.service_plan_args(args))
        return hcloud_eip_change_flow.expected_submit_token(args, service_plan)

    def current_guarded_submit_token(self, args: SimpleNamespace) -> str:
        """Return the submit token for a test generic guarded flow argument set."""
        service_plan = hcloud_guarded_change_flow.hcloud_service_change_plan.build_service_plan(
            hcloud_guarded_change_flow.service_plan_args(args)
        )
        return hcloud_guarded_change_flow.expected_submit_token(args, service_plan)

    def test_readonly_smoke_builds_registered_service_commands(self) -> None:
        args = SimpleNamespace(
            service=["EIP", "RDS"],
            operation=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
        )

        result = hcloud_readonly_smoke.build_smoke_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["service_count"], 2)
        services = {item["service"] for item in result["checks"]}
        self.assertEqual(services, {"EIP", "RDS"})
        operations = {item["service"]: item["operation"] for item in result["checks"]}
        self.assertEqual(operations["EIP"], "ListPublicips")
        self.assertEqual(operations["RDS"], "ListInstances")
        for item in result["checks"]:
            command = item["plan"]["commands"][0]["command"]
            self.assertIn("--expect-json", command)
            self.assertIn("--arg=--cli-output=json", command)

    def test_cce_assessment_plan_defaults_to_non_executing_evidence(self) -> None:
        result = hcloud_cce_assessment_plan.build_plan(self.cce_assessment_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["service"], "CCE")
        self.assertIn("CreateKubernetesClusterCert", result["hard_gated_actions"])
        self.assertIn("references/playbooks/cce-cloud-native-assessment.md", result["recommended_playbooks"])
        self.assertIn("kubectl", result["execution_boundary"])
        checks = {item["id"]: item for item in result["checks"]}
        self.assertEqual(checks["control_plane:ListClusters"]["status"], "planned")
        self.assertEqual(checks["control_plane:ShowCluster"]["status"], "needs_input")
        self.assertIn("cluster_id", checks["control_plane:ShowCluster"]["plan"]["missing_params"])

    def test_cce_assessment_plan_uses_cluster_id_and_kubernetes_templates(self) -> None:
        result = hcloud_cce_assessment_plan.build_plan(
            self.cce_assessment_args(
                cluster_id="cluster-1",
                namespace="prod",
                workload="app=api",
                dimension=["workloads", "addons"],
                include_kubernetes=True,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual([item["id"] for item in result["dimensions"]], ["addons", "workloads"])
        checks = {item["id"]: item for item in result["checks"]}
        self.assertEqual(checks["addons:ListAddonInstances"]["status"], "planned")
        pods = checks["workloads:pods"]
        self.assertEqual(pods["status"], "planned")
        self.assertEqual(pods["source"], "kubectl")
        self.assertIn("prod", pods["command"])
        self.assertIn("app=api", pods["command"])

    def test_account_inventory_builds_core_readonly_plan(self) -> None:
        result = hcloud_account_inventory.build_plan(self.inventory_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["planning_status"], "succeeded")
        self.assertNotIn("outcome_status", result)
        self.assertTrue(result["planning_only"])
        self.assertGreaterEqual(result["summary"]["check_count"], 10)
        operations = {(check["service"], check["operation"]) for check in result["checks"]}
        self.assertIn(("ECS", "ListCloudServers"), operations)
        self.assertIn(("EIP", "ListPublicips"), operations)
        self.assertIn(("OBS", "ListBuckets"), operations)
        eip_check = next(check for check in result["checks"] if check["service"] == "EIP")
        self.assertIn("--arg=--cli-output=json", eip_check["plan"]["commands"][0]["command"])
        obs_check = next(check for check in result["checks"] if check["service"] == "OBS")
        self.assertIn("--command-part=ls", obs_check["plan"]["command"])

    def test_account_inventory_supports_multi_region_and_eps_scope(self) -> None:
        result = hcloud_account_inventory.build_plan(
            self.inventory_args(
                service=["EIP"],
                region=["cn-north-4", "cn-east-3"],
                enterprise_project_id="eps-1",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["regions"], ["cn-north-4", "cn-east-3"])
        self.assertEqual(result["enterprise_project_id"], "eps-1")
        self.assertEqual(result["summary"]["check_count"], 2)
        self.assertEqual(result["summary"]["region_count"], 2)
        self.assertEqual(result["summary"]["regions"], {"cn-east-3": 1, "cn-north-4": 1})
        for check in result["checks"]:
            self.assertEqual(check["scope"]["enterprise_project_id"], "eps-1")
            self.assertEqual(check["enterprise_project_scope"]["requested"], True)
            self.assertIn(
                check["enterprise_project_scope"]["status"],
                {"passed_to_command", "not_supported_by_operation"},
            )
            if check["enterprise_project_scope"]["status"] == "passed_to_command":
                self.assertIn(
                    "--arg=--enterprise_project_id=eps-1",
                    check["plan"]["commands"][0]["command"],
                )

    def test_account_inventory_filters_services(self) -> None:
        result = hcloud_account_inventory.build_plan(self.inventory_args(service=["EIP"]))

        self.assertTrue(result["success"], result)
        self.assertEqual(result["summary"]["check_count"], 1)
        self.assertEqual(result["checks"][0]["service"], "EIP")
        self.assertEqual(result["checks"][0]["operation"], "ListPublicips")

    def test_account_inventory_outcome_covers_partial_and_total_failure(self) -> None:
        self.assertEqual(
            hcloud_account_inventory.inventory_outcome_status(
                check_count=4,
                failed_check_count=0,
            ),
            "succeeded",
        )
        self.assertEqual(
            hcloud_account_inventory.inventory_outcome_status(
                check_count=4,
                failed_check_count=1,
            ),
            "partially_succeeded",
        )
        self.assertEqual(
            hcloud_account_inventory.inventory_outcome_status(
                check_count=4,
                failed_check_count=4,
            ),
            "failed",
        )

    def test_account_inventory_execute_returns_business_outcome_only(self) -> None:
        successful_check = {
            "service": "EIP",
            "operation": "ListPublicips",
            "category": "network",
            "purpose": "Inventory public IPs.",
            "scope": {"region": "cn-north-4"},
            "success": True,
            "plan": {"success": True, "commands": []},
        }
        args = self.inventory_args(service=["EIP"], execute=True)

        with patch.object(
            hcloud_account_inventory,
            "build_target_plan_for_region",
            return_value=successful_check,
        ):
            result = hcloud_account_inventory.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertNotIn("planning_status", result)
        self.assertFalse(result["planning_only"])

    def test_observability_plan_builds_metric_and_state_checks(self) -> None:
        result = hcloud_observability_plan.build_plan(self.observability_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["metric_discovery_plan"]["service"], "CES")
        self.assertEqual(result["metric_discovery_plan"]["commands"][0]["operation"], "ListMetrics")
        self.assertEqual(result["resource_state_plan"]["operation"], "ShowServer")
        self.assertIn("--arg=--server_id=server-1", result["resource_state_plan"]["command"])
        self.assertTrue(result["hints"]["metric_discovery_first"])
        self.assertIn("CPU utilization", result["hints"]["signals"])

    def test_observability_plan_skips_state_check_without_target_id(self) -> None:
        result = hcloud_observability_plan.build_plan(self.observability_args(target_id=None))

        self.assertTrue(result["success"], result)
        self.assertTrue(result["resource_state_plan"]["skipped"])
        self.assertEqual(result["metric_discovery_plan"]["service"], "CES")

    def test_billing_cost_probe_reports_bss_candidate_without_live_default(self) -> None:
        result = hcloud_billing_cost_probe.build_probe(self.billing_probe_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["direct_service_count"], 1)
        self.assertEqual(result["direct_service_candidates"][0]["service"], "BSS")
        self.assertEqual(result["assessment"]["status"], "candidate_service_present")
        self.assertFalse(result["assessment"]["can_run_live_billing_query"])
        self.assertIn("metadata-backed", " ".join(result["assessment"]["blockers"]))

    def test_billing_cost_probe_reports_custom_catalog_candidate(self) -> None:
        result = hcloud_billing_cost_probe.build_probe(
            self.billing_probe_args(service_token=["DBSS"], operation_keyword=["audit"], limit=3)
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["direct_service_count"], 1)
        self.assertEqual(result["direct_service_candidates"][0]["service"], "DBSS")
        self.assertEqual(result["assessment"]["status"], "candidate_service_present")

    def test_billing_readonly_builds_monthly_sum_request_spec(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(self.billing_readonly_args(service_type_code="hws.service.type.ec2"))

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertTrue(result["execution_supported"])
        request = result["request_spec"]
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["path"], "/v2/bills/customer-bills/monthly-sum")
        self.assertEqual(request["query"]["bill_cycle"], "2026-05")
        self.assertIn("service_type_code=hws.service.type.ec2", request["url"])
        self.assertIsNone(request["body"])
        command_plan = result["hcloud_command_plan"]
        self.assertTrue(command_plan["supported"])
        self.assertEqual(command_plan["operation"], "ShowCustomerMonthlySum")
        self.assertIn("--arg=--cli-region=cn-north-1", command_plan["safe_exec_command"])
        self.assertNotIn("X-Language", request["headers"])
        self.assertNotIn("--arg=--X-Language=zh_CN", command_plan["safe_exec_command"])
        self.assertNotIn("--arg=--cli-lang=cn", command_plan["safe_exec_command"])
        self.assertFalse(command_plan["operation_capabilities"]["x_language_header"])
        self.assertIn("--arg=--bill_cycle=2026-05", command_plan["safe_exec_command"])
        self.assertFalse(result["pagination_scope"]["complete_result_claim_allowed"])
        discipline = result["billing_semantic_discipline"]
        self.assertEqual(discipline["required_tuple"], ["fact", "grain", "money_basis", "scope", "billing_period"])
        self.assertEqual(discipline["selected_fact"], "ShowCustomerMonthlySum")
        self.assertIn("bill_cycle", discipline["billing_period_fields"])
        self.assertIn("service_type_code", discipline["scope_fields"])

    def test_billing_x_language_capability_matches_reviewed_operations(self) -> None:
        expected = {
            "billing-statements",
            "cost-data",
            "monthly-breakdown",
            "resource-records",
            "resource-fee-records",
            "usage-summary",
            "usage-detail",
            "free-resource-infos",
            "free-resource-usages",
            "order-details",
            "subcustomer-bill-detail",
            "reference-service-types",
            "reference-resource-types",
            "reference-usage-types",
            "reference-measure-units",
            "reference-service-resources",
        }

        actual = {operation for operation, metadata in hcloud_billing_readonly.OPERATIONS.items() if metadata.get("supports_x_language")}

        self.assertEqual(actual, expected)

    def test_billing_readonly_adds_x_language_only_for_supported_operation(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="reference-service-types",
                language="en_US",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["request_spec"]["headers"]["X-Language"], "en_US")
        command_plan = result["hcloud_command_plan"]
        self.assertTrue(command_plan["operation_capabilities"]["x_language_header"])
        self.assertIn("--arg=--X-Language=en_US", command_plan["safe_exec_command"])
        self.assertNotIn("--arg=--cli-lang=cn", command_plan["safe_exec_command"])

        invalid = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="reference-service-types",
                language="cn",
            )
        )
        self.assertFalse(invalid["success"])
        self.assertIn(
            "Unsupported X-Language",
            invalid["validation"]["errors"][-1],
        )

    def test_billing_readonly_builds_generated_cost_data_body(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="cost-data",
                begin_time="2026-05-01",
                end_time="2026-05-31",
                group_by=["CLOUD_SERVICE_TYPE", "REGION"],
                filter=["CLOUD_SERVICE_TYPE=hws.service.type.ec2"],
            )
        )

        self.assertTrue(result["success"], result)
        request = result["request_spec"]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/v4/costs/cost-analysed-bills/query")
        self.assertEqual(request["body_source"], "generated")
        self.assertEqual(request["body"]["time_condition"]["begin_time"], "2026-05-01")
        self.assertEqual(request["body"]["groupby"][1]["key"], "REGION")
        self.assertEqual(request["body"]["filters"][0]["filter_factor"]["value"], ["hws.service.type.ec2"])
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--time_condition.begin_time=2026-05-01", command)
        self.assertIn("--arg=--groupby.1.key=CLOUD_SERVICE_TYPE", command)
        self.assertIn("--arg=--groupby.2.key=REGION", command)
        self.assertIn("--arg=--filters.1.filter_factor.value.1=hws.service.type.ec2", command)

    def test_billing_cost_data_maps_region_code_to_region_filter(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="cost-data",
                begin_time="2026-05-01",
                end_time="2026-05-31",
                region_code="cn-north-4",
            )
        )

        self.assertTrue(result["success"], result)
        filters = result["request_spec"]["body"]["filters"]
        self.assertEqual(filters[0]["filter_factor"]["key"], "REGION_CODE")
        self.assertEqual(filters[0]["filter_factor"]["value"], ["cn-north-4"])
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn(
            "--arg=--filters.1.filter_factor.value.1=cn-north-4",
            command,
        )

    def test_billing_readonly_attaches_semantic_route(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                entry_point="monthly_spend",
                operation="cost-data",
                begin_time="2026-05-01",
                end_time="2026-05-31",
            )
        )

        self.assertTrue(result["success"], result)
        route = result["semantic_route"]
        self.assertEqual(route["entry_point"], "monthly_spend")
        self.assertIn("CostAnalysis", route["ontology_entities"])
        self.assertIn("BSS/ListCosts", route["source_operations"])
        self.assertIn("BSS/ShowCustomerMonthlySum", route["source_operations"])
        self.assertIn("cost-data", route["supported_planner_operations"])
        self.assertEqual(result["bss_cli_defaults"], {"cli_region": "cn-north-1", "x_language": "zh_CN"})
        discipline = result["billing_semantic_discipline"]
        self.assertEqual(discipline["semantic_entry_point"], "monthly_spend")
        self.assertIn("billed", discipline["money_basis"])
        self.assertIn("amortized", discipline["money_basis"])
        self.assertTrue(discipline["grain_candidates"])
        self.assertIn("time_condition.begin_time", discipline["billing_period_fields"])
        self.assertIn("groupby:CLOUD_SERVICE_TYPE", discipline["scope_fields"])

    def test_billing_readonly_accepts_explicit_json_body(self) -> None:
        body = {
            "cycle": "2026-05",
            "cloud_service_type": "hws.service.type.ec2",
            "limit": 3,
        }
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(operation="resource-records", body_json_text=json.dumps(body))
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["request_spec"]["path"], "/v2/bills/customer-bills/res-records/query")
        self.assertEqual(result["request_spec"]["body_source"], "body-json-text")
        self.assertEqual(result["request_spec"]["body"]["limit"], 3)
        self.assertFalse(result["execution_supported"])
        self.assertFalse(result["hcloud_command_plan"]["supported"])
        self.assertIn("Explicit JSON bodies", result["hcloud_command_plan"]["blocked_reasons"][0])

    def test_billing_readonly_rejects_missing_cost_time_range(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(self.billing_readonly_args(operation="cost-data"))

        self.assertFalse(result["success"])
        self.assertFalse(result["execution_supported"])
        self.assertIn("Missing required cost-data field", result["validation"]["errors"][0])

    def test_billing_readonly_builds_account_balance_plan(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(operation="account-balances", entry_point="balance_and_debt")
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["execution_supported"])
        self.assertEqual(result["title"], "ShowCustomerAccountBalances")
        self.assertEqual(result["semantic_route"]["entry_point"], "balance_and_debt")
        self.assertIn("account-balances", result["semantic_route"]["supported_planner_operations"])
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--operation", command)
        self.assertIn("ShowCustomerAccountBalances", command)
        self.assertIn("--arg=--cli-region=cn-north-1", command)
        self.assertNotIn("--arg=--X-Language=zh_CN", command)
        self.assertNotIn("--arg=--cli-lang=cn", command)

        billing_plan = hcloud_billing_readonly.build_request_spec(self.billing_readonly_args())
        billing_plan["request_spec"]["headers"]["X-Language"] = "zh_CN"
        guard_errors = hcloud_billing_live_read.validate_live_read_plan(
            billing_plan,
            fallback_limit=10,
        )
        self.assertIn("does not accept X-Language", guard_errors[-1])

    def test_billing_readonly_builds_usage_summary_plan(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="usage-summary",
                entry_point="charge_attribution",
                service_type_code="hws.service.type.vpc",
                resource_type="hws.resource.type.bandwidth",
                usage_type="95Peak",
                limit=5,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["execution_supported"])
        self.assertEqual(result["title"], "ListResourceUsageSummary")
        request = result["request_spec"]
        self.assertEqual(request["path"], "/v2/bills/customer-bills/resources/usage/summary")
        self.assertEqual(request["query"]["resource_type_code"], "hws.resource.type.bandwidth")
        self.assertEqual(request["query"]["usage_type"], "95Peak")
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--usage_type=95Peak", command)
        self.assertIn("--arg=--resource_type_code=hws.resource.type.bandwidth", command)
        discipline = result["billing_semantic_discipline"]
        self.assertIn("usage_type", discipline["scope_fields"])
        self.assertIn("bill_cycle", discipline["billing_period_fields"])
        self.assertIn("usage-summary", result["semantic_route"]["supported_planner_operations"])

    def test_billing_readonly_usage_detail_requires_resource_id(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="usage-detail",
                service_type_code="hws.service.type.vpc",
                resource_type="hws.resource.type.bandwidth",
                usage_type="95Peak",
            )
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["execution_supported"])
        self.assertIn("resource_id", result["validation"]["errors"][-1])

    def test_billing_readonly_builds_on_demand_pricing_plan(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="on-demand-pricing",
                entry_point="pricing_inquiry",
                project_id="project-1",
                pricing_preset="ecs",
                resource_spec=["s6.small.1"],
                pricing_region="cn-north-4",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["execution_supported"])
        self.assertEqual(result["title"], "ListOnDemandResourceRatings")
        request = result["request_spec"]
        self.assertEqual(request["path"], "/v2/bills/ratings/on-demand-resources")
        self.assertEqual(request["body_source"], "generated")
        product = request["body"]["product_infos"][0]
        self.assertEqual(request["body"]["project_id"], "project-1")
        self.assertEqual(product["cloud_service_type"], "hws.service.type.ec2")
        self.assertEqual(product["resource_type"], "hws.resource.type.vm")
        self.assertEqual(product["resource_spec"], "s6.small.1.linux")
        self.assertEqual(product["usage_measure_id"], 4)
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--product_infos.1.resource_spec=s6.small.1.linux", command)
        self.assertIn("--arg=--product_infos.1.usage_factor=Duration", command)
        self.assertIn("on-demand-pricing", result["semantic_route"]["supported_planner_operations"])
        discipline = result["billing_semantic_discipline"]
        self.assertIn("quoted", discipline["money_basis"])
        self.assertIn("product_infos:resource_spec", discipline["scope_fields"])

    def test_billing_readonly_builds_period_pricing_plan(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="period-pricing",
                entry_point="pricing_inquiry",
                project_id="project-1",
                pricing_preset="evs",
                resource_spec=["GPSSD"],
                resource_size=[100],
                size_measure_id=[17],
                period_type=["year"],
                period_num=[1],
                subscription_num=[2],
            )
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["execution_supported"])
        self.assertEqual(result["title"], "ListRateOnPeriodDetail")
        request = result["request_spec"]
        self.assertEqual(request["path"], "/v2/bills/ratings/period-resources/subscribe-rate")
        product = request["body"]["product_infos"][0]
        self.assertEqual(product["cloud_service_type"], "hws.service.type.ebs")
        self.assertEqual(product["resource_size"], 100)
        self.assertEqual(product["size_measure_id"], 17)
        self.assertEqual(product["period_type"], 3)
        self.assertEqual(product["subscription_num"], 2)
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--product_infos.1.period_type=3", command)
        self.assertIn("--arg=--product_infos.1.period_num=1", command)
        self.assertIn("period-pricing", result["semantic_route"]["supported_planner_operations"])

    def test_billing_readonly_builds_reconciliation_statement_plan(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(operation="billing-statements", entry_point="reconciliation")
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["title"], "ListCustomerBillsFeeRecords")
        self.assertEqual(result["request_spec"]["query"]["bill_cycle"], "2026-05")
        self.assertIn("billing-statements", result["semantic_route"]["supported_planner_operations"])
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("ListCustomerBillsFeeRecords", command)
        self.assertIn("--arg=--bill_cycle=2026-05", command)

    def test_billing_readonly_supports_free_resource_usage_dot_notation(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="free-resource-usages",
                entry_point="entitlement_and_deduction",
                free_resource_id="free-1",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["title"], "ListFreeResourceUsages")
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--free_resource_ids.1=free-1", command)
        discipline = result["billing_semantic_discipline"]
        self.assertIn("free_resource_ids.1", discipline["scope_fields"])

    def test_billing_readonly_rejects_monthly_sum_enterprise_project_filter(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(operation="monthly-sum", enterprise_project_id="ep-1")
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["execution_supported"])
        self.assertIn("ShowCustomerMonthlySum cannot filter by enterprise_project_id", result["validation"]["errors"][0])

    def test_billing_readonly_rejects_wrong_enterprise_project_filter_key(self) -> None:
        result = hcloud_billing_readonly.build_request_spec(
            self.billing_readonly_args(
                operation="cost-data",
                begin_time="2026-05-01",
                end_time="2026-05-31",
                filter=["ENTERPRISE_PROJECT=ep-1"],
            )
        )

        self.assertFalse(result["success"])
        self.assertIn("ENTERPRISE_PROJECT_ID", result["validation"]["errors"][0])

    def test_billing_result_summary_redacts_protected_identifiers_by_default(self) -> None:
        safe_exec_result = {
            "service": "BSS",
            "operation": "ShowCustomerMonthlySum",
            "parsed_json": {
                "total_count": 2,
                "consume_amount": "123.45",
                "currency": "CNY",
                "bill_sums": [
                    {
                        "customer_id": "customer-123",
                        "account_name": "finance-main",
                        "resource_id": "server-1",
                        "consume_amount": "100.00",
                    }
                ],
            },
        }

        result = hcloud_billing_result_summarize.build_summary(safe_exec_result, offset=0, limit=1)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["source"], "safe_exec")
        self.assertEqual(result["operation"], "ShowCustomerMonthlySum")
        self.assertEqual(result["pagination"]["total_count"], 2)
        self.assertFalse(result["pagination"]["complete_result_claim_allowed"])
        self.assertNotIn("customer-123", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("server-1", json.dumps(result, ensure_ascii=False))
        self.assertNotIn("redacted_records", result)
        self.assertEqual(
            result["summary"]["monetary_totals"],
            {"consume_amount": "123.45"},
        )
        self.assertEqual(result["summary"]["currency"], "CNY")
        self.assertEqual(
            result["summary"]["billing_scope"]["scope_type"],
            "all_account_monthly_summary",
        )
        self.assertFalse(result["summary"]["billing_scope"]["region_filtered"])

    def test_billing_cost_summary_exposes_bounded_region_aggregates(self) -> None:
        safe_exec_result = {
            "service": "BSS",
            "operation": "ListCosts/v2",
            "parsed_json": {
                "total_count": 2,
                "currency": "CNY",
                "cost_data": [
                    {
                        "dimensions": [
                            {"key": "REGION_CODE", "value": "cn-north-4"},
                            {"key": "RESOURCE_ID", "value": "server-secret"},
                        ],
                        "amount_by_costs": "18.88",
                        "official_amount_by_costs": "20.00",
                    },
                    {
                        "dimensions": [
                            {"key": "REGION_CODE", "value": "cn-east-3"}
                        ],
                        "amount_by_costs": "2.00",
                        "official_amount_by_costs": "2.50",
                    },
                ],
            },
        }

        result = hcloud_billing_result_summarize.build_summary(
            safe_exec_result,
            offset=0,
            limit=10,
        )

        self.assertTrue(result["success"], result)
        aggregates = result["summary"]["dimension_aggregates"]
        self.assertEqual(len(aggregates), 2)
        self.assertEqual(aggregates[0]["dimensions"][0]["value"], "cn-north-4")
        self.assertEqual(aggregates[0]["amount_by_costs"], "18.88")
        self.assertTrue(aggregates[0]["dimensions"][1]["value"].startswith("***:"))
        self.assertNotIn("server-secret", json.dumps(result, ensure_ascii=False))
        self.assertTrue(result["summary"]["billing_scope"]["region_filtered"])
        self.assertTrue(result["pagination"]["complete_result_claim_allowed"])

    def test_billing_cost_summary_preserves_region_filter_scope(self) -> None:
        result = hcloud_billing_result_summarize.build_summary(
            {
                "service": "BSS",
                "operation": "ListCosts/v2",
                "parsed_json": {
                    "total_count": 1,
                    "currency": "CNY",
                    "cost_data": [
                        {
                            "dimensions": [
                                {
                                    "key": "CLOUD_SERVICE_TYPE",
                                    "value": "hws.service.type.ec2",
                                }
                            ],
                            "amount_by_costs": "18.88",
                        }
                    ],
                },
            },
            offset=0,
            limit=10,
            request_spec={
                "body": {
                    "filters": [
                        {
                            "operator": 0,
                            "filter_factor": {
                                "key": "REGION_CODE",
                                "value": ["cn-north-4"],
                            },
                        }
                    ]
                }
            },
        )

        scope = result["summary"]["billing_scope"]
        self.assertTrue(scope["region_filtered"])
        self.assertEqual(scope["region_values"], ["cn-north-4"])

    def test_billing_result_summary_can_include_redacted_records(self) -> None:
        payload = {
            "total_count": 1,
            "cost_data": [
                {
                    "resource_id": "resource-abc",
                    "order_id": "order-abc",
                    "amount": "8.88",
                }
            ],
        }

        result = hcloud_billing_result_summarize.build_summary(
            payload,
            offset=0,
            limit=10,
            include_redacted_records=True,
        )

        self.assertTrue(result["success"], result)
        text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("resource-abc", text)
        self.assertNotIn("order-abc", text)
        self.assertIn("***:", text)
        self.assertTrue(result["pagination"]["complete_result_claim_allowed"])
        self.assertEqual(result["summary"]["record_lists"][0]["field"], "cost_data")

    def test_billing_operation_gap_converts_bss_script_names(self) -> None:
        self.assertEqual(
            hcloud_billing_operation_gap.snake_to_operation_name("list_customerself_resource_record_details.py"),
            "ListCustomerselfResourceRecordDetails",
        )
        self.assertEqual(
            hcloud_billing_operation_gap.snake_to_operation_name("show_customer_monthly_sum.py"),
            "ShowCustomerMonthlySum",
        )
        self.assertIsNone(hcloud_billing_operation_gap.snake_to_operation_name("inquiry_elb.py"))

    def test_billing_operation_gap_reports_official_reference_gaps(self) -> None:
        result = hcloud_billing_operation_gap.build_gap_report()

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["execution_boundary"], "local_reference_diff_only_no_hcloud_no_credentials")
        self.assertEqual(result["reference_sources"]["mode"], "bundled_snapshot")
        self.assertEqual(
            result["reference_sources"]["baseline"],
            "references/billing/operation-gap-baseline.json",
        )
        self.assertFalse(result["coverage"]["complete"])
        self.assertIn("ListCosts", result["coverage"]["supported_operations"])
        self.assertIn("ListResourceUsageSummary", result["coverage"]["supported_operations"])
        self.assertIn("ListResourceUsage", result["coverage"]["supported_operations"])
        self.assertIn("ListOnDemandResourceRatings", result["coverage"]["supported_operations"])
        self.assertIn("ListRateOnPeriodDetail", result["coverage"]["supported_operations"])
        missing = {item["operation"]: item for item in result["coverage"]["missing_operations"]}
        self.assertNotIn("ListResourceUsageSummary", missing)
        self.assertNotIn("ListResourceUsage", missing)
        self.assertNotIn("ListOnDemandResourceRatings", missing)
        self.assertNotIn("ListRateOnPeriodDetail", missing)
        self.assertIn("ListRenewRateOnPeriod", missing)
        self.assertEqual(missing["ListRenewRateOnPeriod"]["category"], "business_support_query_gap")
        helpers = {item["script"] for item in result["official"]["pricing_helpers"]}
        self.assertIn("inquiry_elb.py", helpers)
        self.assertNotIn("/Users/", json.dumps(result, ensure_ascii=False))

    def test_billing_live_read_plan_does_not_execute_by_default(self) -> None:
        result = hcloud_billing_live_read.build_live_read(self.billing_live_read_args(service_type_code="hws.service.type.ec2"))

        self.assertTrue(result["success"], result)
        self.assertEqual(result["mode"], "plan")
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["execution"]["executed"])
        self.assertTrue(result["live_read_plan"]["supported"])
        command = result["live_read_plan"]["safe_exec_command"]
        self.assertIn("ShowCustomerMonthlySum", command)
        self.assertIn("--arg=--cli-region=cn-north-1", command)
        self.assertNotIn("--arg=--X-Language=zh_CN", command)
        self.assertNotIn("--arg=--cli-lang=cn", command)

    def test_billing_live_read_declares_json_outcome_in_execute_mode(self) -> None:
        safe_exec_result = {
            "success": True,
            "return_code": 0,
            "duration_seconds": 0.1,
            "service": "BSS",
            "operation": "ShowCustomerMonthlySum",
            "command": ["hcloud", "BSS", "ShowCustomerMonthlySum"],
            "parsed_json": {"total_count": 0, "bill_sums": []},
        }
        completed = subprocess.CompletedProcess(
            args=["python3", "hcloud_safe_exec.py"],
            returncode=0,
            stdout=json.dumps(safe_exec_result),
            stderr="",
        )

        with patch.object(
            hcloud_billing_live_read.subprocess,
            "run",
            return_value=completed,
        ):
            result = hcloud_billing_live_read.build_live_read(
                self.billing_live_read_args(
                    execute=True,
                    confirm_live_billing_read=hcloud_billing_live_read.CONFIRM_TOKEN,
                )
            )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["outcome_status"], "succeeded")
        self.assertNotIn("planning_status", result)

    def test_billing_live_read_keeps_supported_x_language_header(self) -> None:
        result = hcloud_billing_live_read.build_live_read(
            self.billing_live_read_args(
                operation="reference-service-types",
                language="en_US",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["live_read_plan"]["supported"])
        command = result["live_read_plan"]["safe_exec_command"]
        self.assertIn("ListServiceTypes", command)
        self.assertIn("--arg=--X-Language=en_US", command)

    def test_billing_live_read_requires_confirmation_token(self) -> None:
        result = hcloud_billing_live_read.build_live_read(self.billing_live_read_args(execute=True, confirm_live_billing_read=None))

        self.assertFalse(result["success"])
        self.assertFalse(result["execution"]["executed"])
        self.assertIn("READ_BILLING_DATA", result["live_read_plan"]["guard_errors"][-1])

    def test_billing_live_read_rejects_large_page_limit(self) -> None:
        result = hcloud_billing_live_read.build_live_read(self.billing_live_read_args(limit=51))

        self.assertFalse(result["success"])
        self.assertFalse(result["live_read_plan"]["supported"])
        self.assertIn("limit must be <= 50", result["live_read_plan"]["guard_errors"][-1])

    def test_billing_live_read_blocks_non_executable_planner_output(self) -> None:
        body = {
            "cycle": "2026-05",
            "cloud_service_type": "hws.service.type.ec2",
            "limit": 3,
        }
        result = hcloud_billing_live_read.build_live_read(
            self.billing_live_read_args(
                operation="resource-records",
                body_json_text=json.dumps(body),
                execute=True,
                confirm_live_billing_read=hcloud_billing_live_read.CONFIRM_TOKEN,
            )
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["execution"]["executed"])
        self.assertFalse(result["live_read_plan"]["supported"])
        self.assertIn("not executable", result["live_read_plan"]["guard_errors"][0])

    def test_billing_docs_do_not_use_cli_lang_as_bss_operation_argument(self) -> None:
        paths = [
            ROOT / "references" / "playbooks" / "billing-cost-governance.md",
            ROOT / "references" / "iam-actions-catalog.json",
            ROOT / "tests" / "v0_6_acceptance_scenarios.md",
        ]

        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn(
                    "--cli-lang=cn",
                    path.read_text(encoding="utf-8"),
                )

    def test_billing_live_read_executes_safe_exec_and_returns_redacted_summary(self) -> None:
        safe_exec_result = {
            "success": True,
            "return_code": 0,
            "duration_seconds": 0.1,
            "service": "BSS",
            "operation": "ShowCustomerMonthlySum",
            "command": ["hcloud", "BSS", "ShowCustomerMonthlySum"],
            "parsed_json": {
                "total_count": 1,
                "bill_sums": [
                    {
                        "customer_id": "customer-123",
                        "resource_id": "server-123",
                        "consume_amount": "9.99",
                    }
                ],
            },
        }
        completed = subprocess.CompletedProcess(
            args=["python3", "hcloud_safe_exec.py"],
            returncode=0,
            stdout=json.dumps(safe_exec_result),
            stderr="",
        )

        with patch.object(hcloud_billing_live_read.subprocess, "run", return_value=completed) as run:
            result = hcloud_billing_live_read.build_live_read(
                self.billing_live_read_args(
                    execute=True,
                    confirm_live_billing_read=hcloud_billing_live_read.CONFIRM_TOKEN,
                    include_redacted_records=True,
                )
            )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["execution"]["executed"])
        run.assert_called_once()
        summary = result["execution"]["result"]["summary"]
        text = json.dumps(summary, ensure_ascii=False)
        self.assertNotIn("customer-123", text)
        self.assertNotIn("server-123", text)
        self.assertIn("***:", text)
        self.assertNotIn("parsed_json", json.dumps(result["execution"]["result"]["safe_exec_status"], ensure_ascii=False))

    def test_billing_live_read_summarizes_large_payload_from_private_artifact(self) -> None:
        payload = {
            "total_count": 50,
            "consume_amount": "2374.05",
            "currency": "CNY",
            "bill_sums": [
                {
                    "customer_id": f"customer-{index}",
                    "consume_amount": "29.68",
                    "padding": "x" * 200,
                }
                for index in range(50)
            ],
        }
        observed_artifact: Path | None = None

        def fake_run(command, **_kwargs):  # noqa: ANN001, ANN202
            nonlocal observed_artifact
            artifact_arg = next(
                item for item in command if str(item).startswith("--parsed-json-file=")
            )
            observed_artifact = Path(str(artifact_arg).split("=", 1)[1])
            observed_artifact.write_text(json.dumps(payload), encoding="utf-8")
            observed_artifact.chmod(0o600)
            safe_exec_result = {
                "success": True,
                "return_code": 0,
                "service": "BSS",
                "operation": "ShowCustomerMonthlySum/v2",
                "parsed_json": None,
                "parsed_json_suppressed": True,
            }
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=json.dumps(safe_exec_result),
                stderr="",
            )

        with patch.object(
            hcloud_billing_live_read.subprocess,
            "run",
            side_effect=fake_run,
        ):
            result = hcloud_billing_live_read.build_live_read(
                self.billing_live_read_args(
                    execute=True,
                    confirm_live_billing_read=hcloud_billing_live_read.CONFIRM_TOKEN,
                    limit=50,
                )
            )

        self.assertTrue(result["success"], result)
        self.assertIsNotNone(observed_artifact)
        self.assertFalse(observed_artifact.exists())
        summary = result["execution"]["result"]["summary"]
        self.assertEqual(summary["pagination"]["record_count"], 50)
        self.assertEqual(
            summary["summary"]["monetary_totals"]["consume_amount"],
            "2374.05",
        )

    def test_ces_alarm_plan_is_planner_only(self) -> None:
        result = hcloud_ces_alarm_plan.build_plan(self.ces_alarm_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["metric_discovery_plan"]["commands"][0]["operation"], "ListMetrics")
        self.assertEqual(result["existing_alarm_rules_plan"]["commands"][0]["operation"], "ListAlarmRules")
        self.assertTrue(result["alarm_rule_planner"]["success"])
        self.assertFalse(result["alarm_rule_planner"]["executable"])
        self.assertIsNone(result["alarm_rule_planner"]["submit_command"])
        self.assertEqual(result["alarm_rule_planner"]["rule_spec"]["metric_name"], "cpu_util")
        guidance = result["alarm_rule_planner"]["metric_guidance"]
        self.assertTrue(guidance["found"])
        self.assertEqual(guidance["recommended_namespace"], "SYS.ECS")
        self.assertFalse(guidance["agent_required"])

    def test_ces_alarm_plan_warns_for_agent_memory_metric_alias(self) -> None:
        result = hcloud_ces_alarm_plan.build_plan(
            self.ces_alarm_args(
                namespace="SYS.ECS",
                metric_name="mem_used_percent",
                alarm_name="memory-high",
                threshold=85.0,
            )
        )

        self.assertTrue(result["success"], result)
        guidance = result["alarm_rule_planner"]["metric_guidance"]
        self.assertTrue(guidance["found"])
        self.assertEqual(guidance["recommended_namespace"], "AGT.ECS")
        self.assertEqual(guidance["recommended_metric_name"], "mem_usedPercent")
        self.assertTrue(guidance["canonical_name_used"])
        self.assertTrue(guidance["agent_required"])
        self.assertEqual(guidance["known_error"]["code"], "ces.0014")
        self.assertTrue(any("not available in SYS.ECS" in warning for warning in guidance["warnings"]))
        self.assertTrue(any("Agent" in action for action in guidance["next_actions"]))

    def test_ces_datapoint_plan_builds_batch_metric_command(self) -> None:
        result = hcloud_ces_datapoint_plan.build_plan(self.ces_datapoint_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["operation"], "BatchListMetricData")
        body = result["request_spec"]["body"]
        self.assertEqual(body["filter"], "average")
        self.assertEqual(body["metrics"][0]["namespace"], "SYS.ECS")
        self.assertEqual(body["metrics"][0]["metric_name"], "cpu_util")
        self.assertEqual(body["metrics"][0]["dimensions"][0], {"name": "instance_id", "value": "server-1"})
        self.assertTrue(result["query_bounds"]["within_batch_limit"])
        command = result["hcloud_command_plan"]["safe_exec_command"]
        self.assertIn("--arg=--metrics.1.namespace=SYS.ECS", command)
        self.assertIn("--arg=--metrics.1.dimensions.1.name=instance_id", command)
        self.assertIn("--arg=--metrics.1.dimensions.1.value=server-1", command)
        self.assertTrue(result["metric_guidance"]["found"])

    def test_ces_datapoint_plan_interprets_empty_agent_metric(self) -> None:
        payload = {
            "success": True,
            "service": "CES",
            "operation": "BatchListMetricData",
            "parsed_json": {
                "metrics": [
                    {
                        "namespace": "AGT.ECS",
                        "metric_name": "mem_usedPercent",
                        "datapoints": [],
                    }
                ]
            },
        }
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json") as handle:
            json.dump(payload, handle)
            handle.flush()
            result = hcloud_ces_datapoint_plan.build_plan(
                self.ces_datapoint_args(
                    namespace="SYS.ECS",
                    metric_name="mem_used_percent",
                    result_json_file=handle.name,
                )
            )

        self.assertTrue(result["success"], result)
        interpretation = result["result_interpretation"]
        self.assertEqual(interpretation["state"], "empty_datapoints")
        self.assertEqual(interpretation["datapoint_count"], 0)
        self.assertTrue(any("Agent" in cause for cause in interpretation["likely_causes"]))
        self.assertTrue(any("namespace mismatch" in cause for cause in interpretation["likely_causes"]))

    def test_ces_datapoint_plan_rejects_too_wide_window(self) -> None:
        result = hcloud_ces_datapoint_plan.build_plan(
            self.ces_datapoint_args(
                from_ms=1700000000000,
                to_ms=1700000000000 + 3001 * 300 * 1000,
            )
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["query_bounds"]["within_batch_limit"])
        self.assertTrue(any("too wide" in error for error in result["validation"]["errors"]))

    def test_lts_readonly_builds_discovery_and_skips_log_query_without_params(self) -> None:
        result = hcloud_lts_readonly.build_plan(self.lts_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["log_group_plan"]["commands"][0]["operation"], "ListLogGroups")
        self.assertEqual(result["log_stream_plan"]["commands"][0]["operation"], "ListLogStreams")
        self.assertTrue(result["log_query_plan"]["skipped"])

    def test_lts_readonly_builds_list_logs_query_with_required_params(self) -> None:
        result = hcloud_lts_readonly.build_plan(
            self.lts_args(
                log_group_id="group-1",
                log_stream_id="stream-1",
                start_time="1700000000000",
                end_time="1700000300000",
                keyword="ERROR",
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["log_stream_plan"]["operation"], "ListLogStream")
        self.assertEqual(result["log_query_plan"]["operation"], "ListLogs")
        self.assertIn("--arg=--log_group_id=group-1", result["log_query_plan"]["command"])
        self.assertIn("--arg=--keywords=ERROR", result["log_query_plan"]["command"])
        self.assertIn("--arg=--limit=10", result["log_query_plan"]["command"])

    def test_readonly_smoke_uses_supported_cdn_cli_region(self) -> None:
        args = SimpleNamespace(
            service=["CDN"],
            operation=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
        )

        result = hcloud_readonly_smoke.build_smoke_plan(args)

        self.assertTrue(result["success"], result)
        command_item = result["checks"][0]["plan"]["commands"][0]
        self.assertIn("--arg=--cli-region=cn-north-1", command_item["command"])
        self.assertNotIn("--arg=--cli-region=cn-north-4", command_item["command"])
        self.assertEqual(command_item["region_resolution"]["requested_region"], "cn-north-4")
        self.assertEqual(command_item["region_resolution"]["resolved_region"], "cn-north-1")

    def test_readonly_smoke_routes_obs_to_dedicated_runner(self) -> None:
        args = SimpleNamespace(
            service=["OBS"],
            operation=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=5,
            obs_endpoint="obs.cn-north-4.myhuaweicloud.com",
            obs_config=None,
            obs_payer=None,
            execute=False,
            timeout=1,
            strict=True,
        )

        result = hcloud_readonly_smoke.build_smoke_plan(args)

        self.assertTrue(result["success"], result)
        check = result["checks"][0]
        self.assertEqual(check["runner"], "scripts/hcloud_obs_readonly.py")
        self.assertEqual(check["plan"]["operation"], "ListBuckets")
        self.assertIn("--command-part=obs", check["plan"]["command"])

    def test_resource_query_builds_explicit_show_command(self) -> None:
        args = SimpleNamespace(
            service="EIP",
            operation="ShowPublicip",
            param=["publicip_id=eip-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation_scope"], "resource_query")
        self.assertIn("--arg=--publicip_id=eip-1", result["command"])
        self.assertIn("--arg=--cli-output=json", result["command"])
        self.assertIn("--expect-json", result["command"])

    def test_resource_query_resolves_lowercase_operation_name(self) -> None:
        args = SimpleNamespace(
            service="EIP",
            operation="showpublicip",
            param=["publicip_id=eip-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation"], "ShowPublicip")
        self.assertEqual(result["requested_operation"], "showpublicip")
        self.assertIn("--arg=--publicip_id=eip-1", result["command"])

    def test_catalog_backed_discovery_builds_safe_read_commands(self) -> None:
        args = SimpleNamespace(
            service="WAF",
            operation=None,
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=10,
            catalog_max_operations=3,
            execute=False,
        )

        result = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["metadata_backed"])
        self.assertEqual(result["coverage"], "metadata-backed")
        self.assertLessEqual(len(result["commands"]), 3)
        self.assertTrue(all(item["metadata_backed"] for item in result["commands"]))
        self.assertIn("List", result["commands"][0]["operation"])

    def test_catalog_backed_discovery_bounds_limit_from_metadata(self) -> None:
        args = SimpleNamespace(
            service="RFS",
            operation="ListPrivateHooks",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=5,
            catalog_max_operations=1,
            execute=False,
        )

        result = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(result["success"], result)
        command_item = result["commands"][0]
        self.assertIn("--arg=--limit=10", command_item["command"])
        self.assertNotIn("--arg=--limit=5", command_item["command"])
        self.assertIn("--arg=--Client-Request-Id=00000000-0000-0000-0000-000000000000", command_item["command"])
        self.assertEqual(command_item["parameter_adjustments"][0]["reason"], "metadata_minimum")
        self.assertEqual(command_item["generated_args"], [{"param": "Client-Request-Id", "reason": "safe_required_header"}])

    def test_large_catalog_discovery_applies_output_policy_default_limit(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="ListFlavors",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=None,
            catalog_max_operations=1,
            execute=False,
        )

        result = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(result["success"], result)
        command_item = result["commands"][0]
        self.assertIn("--arg=--limit=20", command_item["command"])
        self.assertIn(
            {
                "param": "limit",
                "requested": None,
                "used": 20,
                "reason": "output_policy_default",
            },
            command_item["parameter_adjustments"],
        )

    def test_resource_discovery_execute_plan_parses_safe_exec_json(self) -> None:
        plan = {
            "commands": [
                {
                    "service": "UCS",
                    "operation": "ListAddonTemplates",
                    "command": ["python3", "scripts/hcloud_safe_exec.py"],
                }
            ]
        }
        completed = SimpleNamespace(
            stdout=json.dumps({"success": True, "parsed_json": {"items": []}}),
            stderr="",
            returncode=0,
        )

        with patch.object(hcloud_resource_discovery.subprocess, "run", return_value=completed):
            result = hcloud_resource_discovery.execute_plan(plan, timeout=1)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["results"][0]["result"]["parsed_json"], {"items": []})

    def test_catalog_backed_resource_query_requires_explicit_params(self) -> None:
        args = SimpleNamespace(
            service="WAF",
            operation="ListCcRules",
            param=[],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["missing_params"], ["policy_id"])
        self.assertEqual(result["operation_scope"], "metadata_resource_query")

    def test_catalog_backed_resource_query_builds_command(self) -> None:
        args = SimpleNamespace(
            service="WAF",
            operation="ListCcRules",
            param=["policy_id=policy-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["metadata_backed"])
        self.assertEqual(result["operation_scope"], "metadata_resource_query")
        self.assertIn("--service", result["command"])
        self.assertIn("WAF", result["command"])
        self.assertIn("--arg=--policy_id=policy-1", result["command"])

    def test_catalog_readonly_smoke_builds_plan_matrix(self) -> None:
        args = SimpleNamespace(
            service=["WAF"],
            operation=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=5,
            catalog_max_operations=2,
            execute=False,
            strict=True,
            timeout=1,
        )

        result = hcloud_catalog_readonly_smoke.build_smoke(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["service_count"], 1)
        self.assertLessEqual(result["operation_count"], 2)
        self.assertEqual(result["bucket_counts"], {"planned": result["operation_count"]})
        self.assertTrue(all(row["metadata_backed"] for row in result["matrix"]))
        self.assertTrue(all(row["evidence_summary"] for row in result["matrix"]))

        record = hcloud_catalog_readonly_smoke.build_smoke_record(args, result)

        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["mode"], "plan")
        self.assertEqual(record["context"]["region"], "cn-north-4")
        self.assertEqual(record["confidence_suggestions"], {"schema_version": 1, "services": {}})
        first_command = record["matrix"][0]["command"]
        self.assertNotIn("--arg=--project_id=project-1", first_command)
        self.assertIn("--arg=--project_id=<project-id>", first_command)

    def test_catalog_readonly_smoke_filters_specific_operation(self) -> None:
        args = SimpleNamespace(
            service=["WAF"],
            operation=["ListHost"],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=5,
            catalog_max_operations=2,
            execute=False,
            strict=True,
            timeout=1,
        )

        result = hcloud_catalog_readonly_smoke.build_smoke(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation_count"], 1)
        self.assertEqual(result["matrix"][0]["operation"], "ListHost")
        self.assertEqual(result["checks"][0]["requested_operation"], "ListHost")

    def test_catalog_readonly_smoke_classifies_permission_failure(self) -> None:
        execution = {
            "success": False,
            "error_details": {
                "category": "permission",
                "source": "hcloud",
                "message": "policy denied",
            },
        }

        result = hcloud_catalog_readonly_smoke.classify_execution(execution)

        self.assertEqual(result["result_bucket"], "auth_or_permission")
        self.assertEqual(result["error_category"], "permission")

    def test_catalog_readonly_smoke_builds_confidence_suggestions(self) -> None:
        result = {
            "matrix": [
                {
                    "service": "UCS",
                    "operation": "ListClusters",
                    "mode": "execute",
                    "result_bucket": "command_shape_ok",
                    "evidence_summary": "Read-only command executed successfully through hcloud_safe_exec.",
                },
                {
                    "service": "WAF",
                    "operation": "ListHost",
                    "mode": "execute",
                    "result_bucket": "auth_or_permission",
                    "evidence_summary": "Permission blocked the request.",
                },
            ]
        }

        suggestions = hcloud_catalog_readonly_smoke.build_confidence_suggestions(result)

        self.assertEqual(suggestions["services"]["UCS"]["operations"]["ListClusters"]["confidence"], "live-read-smoked")
        self.assertNotIn("WAF", suggestions["services"])

    def test_catalog_readonly_smoke_propagates_reproducible_evidence_without_secrets(self) -> None:
        args = SimpleNamespace(
            service=["UCS"],
            operation=["ListClusters"],
            region="cn-north-4",
            project_id="project-secret-value",
            profile="profile-secret-value",
            limit=5,
            catalog_max_operations=1,
            execute=True,
            strict=True,
            timeout=1,
        )
        result = {
            "mode": "execute",
            "success": True,
            "service_count": 1,
            "operation_count": 1,
            "bucket_counts": {"command_shape_ok": 1},
            "matrix": [
                {
                    "service": "UCS",
                    "operation": "ListClusters",
                    "mode": "execute",
                    "result_bucket": "command_shape_ok",
                    "evidence_summary": "Read-only command executed successfully through hcloud_safe_exec.",
                    "command": [
                        "python3",
                        "scripts/hcloud_safe_exec.py",
                        "--arg=--project_id=project-secret-value",
                        "--arg=--cli-profile=profile-secret-value",
                    ],
                }
            ],
        }
        evidence = {
            "observed_at": "2026-08-04T08:00:00Z",
            "evidence_source": {
                "tool": "scripts/hcloud_catalog_readonly_smoke.py",
                "skill_commit": "a" * 40,
                "worktree_state": "clean",
            },
            "environment": {
                "region": "cn-north-4",
                "python_version": "3.14.0",
                "platform": "Darwin",
                "architecture": "arm64",
                "hcloud_cli_version": "7.2.12",
            },
        }

        record = hcloud_catalog_readonly_smoke.build_smoke_record(
            args,
            result,
            evidence=evidence,
        )
        last_smoke = record["confidence_suggestions"]["services"]["UCS"]["operations"]["ListClusters"]["last_smoke"]
        serialized = json.dumps(record, ensure_ascii=False)

        self.assertEqual(record["generated_at"], evidence["observed_at"])
        self.assertEqual(record["evidence"], evidence)
        self.assertEqual(last_smoke["observed_at"], evidence["observed_at"])
        self.assertEqual(last_smoke["evidence_source"], evidence["evidence_source"])
        self.assertEqual(last_smoke["environment"], evidence["environment"])
        self.assertNotIn("project-secret-value", serialized)
        self.assertNotIn("profile-secret-value", serialized)

    def test_catalog_readonly_smoke_collects_bounded_environment_only_for_execute(self) -> None:
        args = SimpleNamespace(region="cn-north-4")
        source = {
            "tool": "scripts/hcloud_catalog_readonly_smoke.py",
            "skill_commit": None,
            "worktree_state": "unknown_no_local_git",
        }
        inspector_result = {
            "found": True,
            "path": "/private/sensitive/path/hcloud",
            "version_command": {
                "return_code": 0,
                "stdout": "Current KooCLI version is 7.2.12\nshould-not-persist",
                "stderr": "private-diagnostic",
            },
        }

        with patch.object(
            hcloud_catalog_readonly_smoke,
            "local_source_provenance",
            return_value=source,
        ):
            with patch.object(
                hcloud_catalog_readonly_smoke.hcloud_context_inspect,
                "inspect_hcloud_binary",
                return_value=inspector_result,
            ) as inspect:
                plan_evidence = hcloud_catalog_readonly_smoke.build_evidence_metadata(
                    args,
                    {"mode": "plan"},
                    observed_at="2026-08-04T08:00:00Z",
                )
                inspect.assert_not_called()
                execute_evidence = hcloud_catalog_readonly_smoke.build_evidence_metadata(
                    args,
                    {"mode": "execute"},
                    observed_at="2026-08-04T08:00:01Z",
                )

        serialized = json.dumps(execute_evidence, ensure_ascii=False)
        self.assertNotIn("hcloud_cli_version", plan_evidence["environment"])
        self.assertEqual(execute_evidence["environment"]["hcloud_cli_version"], "7.2.12")
        self.assertTrue(execute_evidence["environment"]["hcloud_version_command_succeeded"])
        self.assertNotIn("/private/sensitive/path", serialized)
        self.assertNotIn("should-not-persist", serialized)
        self.assertNotIn("private-diagnostic", serialized)

    def test_catalog_readonly_smoke_does_not_borrow_parent_git_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "installed-skill"
            root.mkdir()
            with patch.object(hcloud_catalog_readonly_smoke.subprocess, "run") as run:
                source = hcloud_catalog_readonly_smoke.local_source_provenance(root)

        run.assert_not_called()
        self.assertEqual(source["skill_commit"], None)
        self.assertEqual(source["worktree_state"], "unknown_no_local_git")

    def test_catalog_readonly_smoke_summarizes_execution_without_raw_output(self) -> None:
        plan = {
            "commands": [
                {
                    "service": "UCS",
                    "operation": "ListClusters",
                    "metadata_backed": True,
                    "command": ["python3", "scripts/hcloud_safe_exec.py"],
                    "catalog_operation_summary": "List clusters.",
                }
            ],
            "results": [
                {
                    "service": "UCS",
                    "operation": "ListClusters",
                    "result": {
                        "success": True,
                        "return_code": 0,
                        "stdout": '{"sensitive":"omitted"}',
                        "stderr": "",
                        "parsed_json": {"clusters": [{"id": "cluster-1"}], "count": 1},
                    },
                }
            ],
        }

        rows = hcloud_catalog_readonly_smoke.summarize_execution(plan)

        self.assertEqual(rows[0]["result_bucket"], "command_shape_ok")
        self.assertEqual(rows[0]["parsed_json_shape"]["top_level_keys_sample"], ["clusters", "count"])
        self.assertNotIn("stdout", rows[0])
        self.assertNotIn("stderr", rows[0])

    def test_catalog_readonly_smoke_fixtures_are_sanitized(self) -> None:
        fixture_names = [
            "hcloud-catalog-readonly-smoke-plan.json",
            "hcloud-catalog-readonly-smoke-execute.json",
            "hcloud-catalog-readonly-smoke-rfs-fixed.json",
            "hcloud-catalog-readonly-smoke-expanded.json",
            "hcloud-catalog-readonly-smoke-second-live.json",
            "hcloud-catalog-readonly-smoke-retry-aos-modelarts-cbr-cfw.json",
        ]
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                data = json.loads((ROOT / "tests" / "fixtures" / fixture_name).read_text(encoding="utf-8"))
                payload = json.dumps(data, ensure_ascii=False)
                self.assertIn("matrix", data)
                self.assertNotIn('"stdout":', payload)
                self.assertNotIn('"stderr":', payload)
                self.assertNotIn('"parsed_json":', payload)
                self.assertNotIn("project-1", payload)

        rfs_fixed = json.loads((ROOT / "tests" / "fixtures" / "hcloud-catalog-readonly-smoke-rfs-fixed.json").read_text(encoding="utf-8"))
        rfs_row = rfs_fixed["matrix"][0]
        self.assertEqual(rfs_row["result_bucket"], "command_shape_ok")
        self.assertIn("--arg=--limit=10", rfs_row["command"])
        self.assertIn(
            "--arg=--Client-Request-Id=00000000-0000-0000-0000-000000000000",
            rfs_row["command"],
        )

    def test_eip_change_flow_builds_guarded_plan(self) -> None:
        result = hcloud_eip_change_flow.build_flow(self.eip_flow_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["service"], "EIP")
        self.assertEqual(result["service_plan"]["operation"], "UpdatePublicip")
        self.assertTrue(result["submit_guard"]["submit_token_required"])
        self.assertEqual(len(result["submit_guard"]["submit_token"]), 16)
        self.assertIn("--arg=--dryrun", result["service_plan"]["commands"]["dryrun_or_plan"])
        self.assertIn("--expect-json", result["service_plan"]["commands"]["submit"])
        self.assertNotIn("submit", result)

    def test_eip_change_flow_requires_submit_confirmation(self) -> None:
        result = hcloud_eip_change_flow.build_flow(self.eip_flow_args(execute_submit=True, execute_dryrun=True))

        self.assertFalse(result["success"])
        self.assertEqual(result["submit_guard_failure"]["error"], "Submit execution requires --confirm-submit.")

    def test_eip_change_flow_requires_current_submit_token(self) -> None:
        result = hcloud_eip_change_flow.build_flow(self.eip_flow_args(execute_submit=True, execute_dryrun=True, confirm_submit=True))

        self.assertFalse(result["success"])
        self.assertEqual(
            result["submit_guard_failure"]["error"],
            "Submit execution requires a valid --submit-token from the current plan.",
        )

    def test_eip_change_flow_executes_dryrun_and_verify_with_mocks(self) -> None:
        with (
            patch.object(
                hcloud_eip_change_flow,
                "execute_command",
                return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1"}}},
            ) as dryrun_mock,
            patch.object(
                hcloud_eip_change_flow.hcloud_resource_query,
                "execute_command",
                return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1", "status": "DOWN"}}},
            ) as verify_mock,
        ):
            result = hcloud_eip_change_flow.build_flow(self.eip_flow_args(execute_dryrun=True, execute_verify=True))

        self.assertTrue(result["success"], result)
        self.assertTrue(result["dryrun"]["success"])
        self.assertTrue(result["verification"]["success"])
        self.assertEqual(result["verification"]["operation"], "ShowPublicip")
        dryrun_mock.assert_called_once()
        verify_mock.assert_called_once()

    def test_eip_change_flow_writes_journal_for_executed_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            journal = Path(tmp_dir) / "flow.jsonl"
            with (
                patch.object(
                    hcloud_eip_change_flow,
                    "execute_command",
                    return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1"}}},
                ),
                patch.object(
                    hcloud_eip_change_flow.hcloud_resource_query,
                    "execute_command",
                    return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1"}}},
                ),
            ):
                result = hcloud_eip_change_flow.build_flow(
                    self.eip_flow_args(execute_dryrun=True, execute_verify=True, journal=str(journal))
                )
            events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result["success"], result)
        self.assertEqual([event["stage"] for event in events], ["dryrun", "verify"])
        self.assertEqual(events[0]["type"], "command")
        self.assertEqual(events[1]["type"], "verification")

    def test_guarded_change_flow_builds_generic_plan(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["service"], "VPC")
        command = result["service_plan"]["commands"]["dryrun_or_plan"]
        self.assertIn("--arg=--cli-output=json", command)
        self.assertIn("--expect-json", command)
        self.assertIn("--arg=--dryrun", command)
        self.assertTrue(result["submit_guard"]["submit_token_required"])
        self.assertEqual(len(result["submit_guard"]["submit_token"]), 16)
        self.assertIn("post_change_readiness_plan", result)
        self.assertTrue(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["operation"], "ShowSecurityGroupRule")
        self.assertIn("--arg=--security_group_rule_id=rule-1", result["post_change_verification"]["command"])

    def test_guarded_change_flow_requires_submit_confirmation(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(execute_submit=True, execute_dryrun=True))

        self.assertFalse(result["success"])
        self.assertEqual(result["submit_guard_failure"]["error"], "Submit execution requires --confirm-submit.")
        self.assertTrue(result["planning_only"])

    def test_guarded_change_flow_requires_current_submit_token(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(execute_submit=True, execute_dryrun=True, confirm_submit=True)
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["submit_guard_failure"]["error"],
            "Submit execution requires a valid --submit-token from the current plan.",
        )

    def test_guarded_change_flow_blocks_metadata_hard_guard_submit(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(
                service="WAF",
                operation="BatchUpdateCustomRules",
                execute_submit=True,
                confirm_submit=True,
                skip_dryrun=True,
                allow_unregistered=True,
            )
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["service_plan"]["risk"]["hard_guard"])
        self.assertEqual(
            result["submit_guard_failure"]["error"],
            "Submit execution is blocked by a hard manual gate.",
        )

    def test_guarded_change_flow_blocks_unrestricted_sensitive_ingress_rule(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(
                arg=[
                    "--direction=ingress",
                    "--protocol=tcp",
                    "--remote_ip_prefix=0.0.0.0/0",
                    "--port_range_min=22",
                    "--port_range_max=22",
                ],
            )
        )

        self.assertFalse(result["success"], result)
        self.assertFalse(result["service_plan"]["success"])
        self.assertEqual(
            result["service_plan"]["policy_violations"][0]["code"],
            "unrestricted_sensitive_ingress_port",
        )
        self.assertEqual(result["service_plan"]["commands"], {})

    def test_guarded_change_flow_allows_public_web_plan_but_still_requires_submit_confirmation(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(
                arg=[
                    "--direction=ingress",
                    "--protocol=tcp",
                    "--remote_ip_prefix=0.0.0.0/0",
                    "--port_range_min=443",
                    "--port_range_max=443",
                ],
                allow_public_web=True,
                execute_submit=True,
            )
        )

        self.assertFalse(result["success"], result)
        self.assertTrue(result["service_plan"]["success"], result)
        self.assertTrue(result["service_plan"]["public_web_exposure"]["enabled"])
        self.assertEqual(
            result["submit_guard_failure"]["error"],
            "Submit execution requires --confirm-submit.",
        )

    def test_guarded_change_flow_executes_dryrun_and_readiness_with_mocks(self) -> None:
        with (
            patch.object(
                hcloud_guarded_change_flow,
                "execute_command",
                return_value={"success": True, "parsed_json": {"ok": True}},
            ) as dryrun_mock,
            patch.object(
                hcloud_guarded_change_flow.hcloud_resource_discovery,
                "execute_plan",
                return_value={"success": True, "results": []},
            ) as readiness_mock,
        ):
            result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(execute_dryrun=True, execute_readiness=True))

        self.assertTrue(result["success"], result)
        self.assertTrue(result["dryrun"]["success"])
        self.assertTrue(result["post_change_verification"]["success"])
        self.assertTrue(result["post_change_readiness"]["success"])
        dryrun_mock.assert_called_once()
        readiness_mock.assert_called_once()

    def test_guarded_change_flow_writes_journal_for_dryrun_verify_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            journal = Path(tmp_dir) / "guarded.jsonl"
            with (
                patch.object(
                    hcloud_guarded_change_flow,
                    "execute_command",
                    return_value={"success": True, "parsed_json": {"ok": True}},
                ),
                patch.object(
                    hcloud_guarded_change_flow.hcloud_resource_query,
                    "execute_command",
                    return_value={"success": True, "parsed_json": {"security_group_rule": {"id": "rule-1"}}},
                ),
                patch.object(
                    hcloud_guarded_change_flow.hcloud_resource_discovery,
                    "execute_plan",
                    return_value={"success": True, "results": []},
                ),
            ):
                result = hcloud_guarded_change_flow.build_flow(
                    self.guarded_flow_args(
                        execute_dryrun=True,
                        execute_verify=True,
                        execute_readiness=True,
                        journal=str(journal),
                    )
                )
            events = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result["success"], result)
        self.assertEqual([event["stage"] for event in events], ["dryrun", "verify", "readiness"])
        self.assertEqual(events[0]["type"], "command")
        self.assertEqual(events[1]["type"], "verification")
        self.assertEqual(events[2]["type"], "verification")

    def test_guarded_change_flow_extracts_verify_id_from_submit_result(self) -> None:
        with (
            patch.object(
                hcloud_guarded_change_flow,
                "execute_command",
                side_effect=[
                    {"success": True, "parsed_json": {"dryrun": True}},
                    {"success": True, "parsed_json": {"security_group_rule": {"id": "rule-2"}}},
                ],
            ) as execute_mock,
            patch.object(
                hcloud_guarded_change_flow.hcloud_resource_query,
                "execute_command",
                return_value={"success": True, "parsed_json": {"security_group_rule": {"id": "rule-2"}}},
            ) as verify_mock,
        ):
            args = self.guarded_flow_args(
                verify_param=[],
                execute_dryrun=True,
                execute_submit=True,
                confirm_submit=True,
                execute_verify=True,
            )
            args.submit_token = self.current_guarded_submit_token(args)
            result = hcloud_guarded_change_flow.build_flow(args)

        self.assertTrue(result["success"], result)
        self.assertFalse(result["planning_only"])
        self.assertEqual(result["post_change_verification"]["operation"], "ShowSecurityGroupRule")
        self.assertIn("--arg=--security_group_rule_id=rule-2", result["post_change_verification"]["command"])
        self.assertEqual(execute_mock.call_count, 2)
        verify_mock.assert_called_once()

    def test_guarded_change_flow_reports_missing_verify_target(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(verify_param=[]))

        self.assertTrue(result["success"], result)
        self.assertFalse(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["missing_params"], ["security_group_rule_id"])

    def test_guarded_change_flow_does_not_verify_wrong_vpc_resource(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(operation="CreateVpcPeering", arg=[], verify_param=[]))

        self.assertTrue(result["success"], result)
        self.assertFalse(result["post_change_verification"]["success"])
        self.assertEqual(
            result["post_change_verification"]["error"],
            "No service-specific verification profile is registered for this change operation.",
        )

    def test_guarded_change_flow_requires_rds_instance_verify_target(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(
                service="RDS",
                operation="CreateInstance",
                arg=[],
                verify_param=[],
            )
        )

        self.assertTrue(result["success"], result)
        self.assertFalse(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["operation"], "ShowInstanceConfiguration")
        self.assertEqual(result["post_change_verification"]["missing_params"], ["instance_id"])

    def test_guarded_change_flow_can_use_explicit_verify_operation(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(
                service="CDN",
                operation="CreateDomain",
                verify_operation="ShowDomain",
                verify_param=["domain_id=domain-1"],
            )
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["requested_operation"], "ShowDomain")
        self.assertEqual(result["post_change_verification"]["operation"], "ShowDomainDetail")
        self.assertIn("--arg=--cli-region=cn-north-1", result["post_change_verification"]["command"])

    def test_guarded_change_flow_accepts_not_found_for_delete_verify(self) -> None:
        with patch.object(
            hcloud_guarded_change_flow.hcloud_resource_query,
            "execute_command",
            return_value={"success": False, "error_details": {"category": "not_found"}},
        ):
            result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(operation="DeleteSecurityGroupRule", execute_verify=True))

        self.assertTrue(result["success"], result)
        verification = result["post_change_verification"]
        self.assertTrue(verification["success"])
        self.assertTrue(verification["absent_state_confirmed"])
        self.assertTrue(verification["verification_profile"]["expect_absent"])

    def test_guarded_change_flow_rejects_delegated_planner(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args(service="OBS", operation="CreateBucket"))

        self.assertFalse(result["success"])
        self.assertEqual(result["service_plan"]["delegated_planner"], "scripts/hcloud_obs_change_plan.py")

    def test_resource_query_builds_vpc_show_command(self) -> None:
        args = SimpleNamespace(
            service="VPC",
            operation="showvpc",
            param=["vpc_id=vpc-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation_scope"], "resource_query")
        self.assertEqual(result["operation"], "ShowVpc")
        self.assertIn("--arg=--vpc_id=vpc-1", result["command"])

    def test_resource_query_selects_v2_for_vpc_id_filter(self) -> None:
        args = SimpleNamespace(
            service="VPC",
            operation="ListSecurityGroups",
            param=["vpc_id=vpc-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation"], "ListSecurityGroups")
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v2")
        self.assertEqual(
            result["version_resolution"]["confidence"],
            "exact_parameter_match",
        )
        self.assertIn("ListSecurityGroups/v2", result["command"])
        self.assertIn("--arg=--vpc_id=vpc-1", result["command"])

    def test_resource_query_corrects_explicit_incompatible_version(self) -> None:
        args = SimpleNamespace(
            service="VPC",
            operation="ListSecurityGroups/v3",
            param=["vpc_id=vpc-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["corrected_operation"], "ListSecurityGroups/v2")
        self.assertIn("ListSecurityGroups/v2", result["corrected_command"])
        self.assertEqual(
            result["version_resolution"]["reason"],
            "provided_parameters_are_not_supported_by_explicit_version",
        )

    def test_generic_resource_query_rejects_obs_dedicated_runner(self) -> None:
        args = SimpleNamespace(
            service="OBS",
            operation="GetBucketLifecycle",
            param=["bucket=bucket-1"],
            arg=[],
            region="cn-north-4",
            project_id=None,
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["resource_query_runner"], "scripts/hcloud_obs_readonly.py")

    def test_obs_readonly_builds_list_buckets_command(self) -> None:
        args = SimpleNamespace(
            operation="listbuckets",
            bucket=None,
            endpoint="obs.cn-north-4.myhuaweicloud.com",
            config=None,
            payer=None,
            limit=5,
            arg=["-s"],
            execute=False,
            timeout=1,
        )

        result = hcloud_obs_readonly.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["operation"], "ListBuckets")
        self.assertEqual(result["requested_operation"], "listbuckets")
        self.assertIn("--command-part=ls", result["command"])
        self.assertIn("--command-part=-limit=5", result["command"])
        self.assertIn("--command-part=-e=obs.cn-north-4.myhuaweicloud.com", result["command"])

    def test_obs_readonly_requires_bucket_for_lifecycle(self) -> None:
        args = SimpleNamespace(
            operation="GetBucketLifecycle",
            bucket=None,
            endpoint=None,
            config=None,
            payer=None,
            limit=None,
            arg=[],
            execute=False,
            timeout=1,
        )

        result = hcloud_obs_readonly.build_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("requires --bucket", result["error"])

    def test_obs_readonly_summarizes_obsutil_auth_errors(self) -> None:
        execution = {
            "stdout": "List buckets failed, status [403], error code [InvalidAccessKeyId], error message [The Access Key Id you provided does not exist.]",
            "parsed_json_error": None,
        }

        summary = hcloud_obs_readonly.summarize_execution("ListBuckets", execution)

        self.assertEqual(summary["obs_status"], 403)
        self.assertEqual(summary["obs_error_code"], "InvalidAccessKeyId")
        self.assertIn("obsutil credentials", summary["advice"])

    def test_obs_change_plan_builds_lifecycle_put(self) -> None:
        args = SimpleNamespace(
            operation="putbucketlifecycle",
            bucket="bucket-1",
            local_file="lifecycle.json",
            json_input_file=None,
            endpoint=None,
            config=None,
            payer=None,
            arg=[],
            timeout=1,
        )

        result = hcloud_obs_change_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["operation"], "PutBucketLifecycle")
        self.assertEqual(result["risk"]["level"], "medium")
        self.assertIn("--command-part=lifecycle", result["commands"]["submit"])
        self.assertIn("--command-part=-method=put", result["commands"]["submit"])
        self.assertIn("--command-part=-localfile=lifecycle.json", result["commands"]["submit"])

    def test_obs_change_plan_flags_public_bucket_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.json"
            policy_path.write_text(
                json.dumps(
                    {
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Principal": "*",
                                "Action": ["obs:GetObject"],
                                "Resource": "*",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                operation="PutBucketPolicy",
                bucket="bucket-1",
                local_file=str(policy_path),
                json_input_file=None,
                endpoint=None,
                config=None,
                payer=None,
                arg=["-acl=public-read"],
                timeout=1,
            )

            result = hcloud_obs_change_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["risk"]["level"], "high")
        codes = {item["code"] for item in result["risk"]["policy_risk_findings"]}
        self.assertIn("public_principal", codes)
        self.assertIn("wildcard_resource", codes)
        self.assertIn("public_acl", codes)
        self.assertTrue(any("Review OBS policy_risk_findings" in warning for warning in result["plan"]["warnings"]))

    def test_resource_query_rejects_missing_required_param(self) -> None:
        args = SimpleNamespace(
            service="CCE",
            operation="ShowCluster",
            param=[],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["missing_params"], ["cluster_id"])

    def test_resource_query_blocks_sensitive_read_by_default(self) -> None:
        args = SimpleNamespace(
            service="ECS",
            operation="ShowServerPassword",
            param=["server_id=server-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("Sensitive read", result["error"])

    def test_resource_query_maps_rds_configuration_alias(self) -> None:
        args = SimpleNamespace(
            service="RDS",
            operation="ShowConfigurationDetail",
            param=["config_id=config-1"],
            arg=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            execute=False,
            timeout=1,
            allow_sensitive_read=False,
        )

        result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["requested_operation"], "ShowConfigurationDetail")
        self.assertEqual(result["operation"], "ShowConfiguration")
        self.assertIn("ShowConfiguration/v3", result["command"])
        self.assertIn("--arg=--config_id=config-1", result["command"])

    def test_service_readiness_builds_vpc_profile(self) -> None:
        args = SimpleNamespace(
            service=["VPC"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=False,
        )

        result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        checks = result["services"][0]["checks"]
        self.assertEqual(
            {item["operation"] for item in checks},
            {
                "ListVpcs",
                "ListSubnets",
                "ListSecurityGroups",
                "ListSecurityGroupRules",
                "ListVpcPeerings",
                "ShowVpc",
                "ShowSubnet",
                "ShowSecurityGroup",
                "ShowSecurityGroupRule",
            },
        )
        skipped = [item for item in checks if item.get("skipped")]
        self.assertEqual(
            {item["operation"] for item in skipped},
            {"ShowVpc", "ShowSubnet", "ShowSecurityGroup", "ShowSecurityGroupRule"},
        )
        planned = [item for item in checks if not item.get("skipped")]
        self.assertTrue(all(item["runner"] == "scripts/hcloud_resource_discovery.py" for item in planned))

    def test_service_readiness_default_includes_high_frequency_profiles(self) -> None:
        args = SimpleNamespace(
            service=None,
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=False,
        )

        result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        services = [item["service"] for item in result["services"]]
        self.assertEqual(services[:10], ["ECS", "VPC", "RDS", "IMS", "EVS", "EIP", "ELB", "NAT", "KPS", "IAM"])
        self.assertIn("OBS", services)

    def test_service_readiness_routes_obs_profile(self) -> None:
        args = SimpleNamespace(
            service=["OBS"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            obs_endpoint=None,
            obs_config=None,
            obs_payer=None,
            execute=False,
            timeout=1,
            strict=True,
            require_all=False,
        )

        result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        checks = result["services"][0]["checks"]
        list_check = next(item for item in checks if item["operation"] == "ListBuckets")
        self.assertEqual(list_check["runner"], "scripts/hcloud_obs_readonly.py")
        skipped = next(item for item in checks if item["operation"] == "GetBucketLifecycle")
        self.assertTrue(skipped["skipped"])
        self.assertEqual(skipped["missing_targets"], ["bucket"])

    def test_service_readiness_rds_backups_requires_instance_target(self) -> None:
        missing_args = SimpleNamespace(
            service=["RDS"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=False,
        )

        missing = hcloud_service_readiness.build_readiness(missing_args)

        self.assertTrue(missing["success"], missing)
        skipped = next(item for item in missing["services"][0]["checks"] if item["operation"] == "ListBackups")
        self.assertTrue(skipped["skipped"])
        self.assertEqual(skipped["missing_targets"], ["instance_id"])

        target_args = SimpleNamespace(
            service=["RDS"],
            target=["instance_id=db-1", "config_id=config-1"],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=True,
        )

        targeted = hcloud_service_readiness.build_readiness(target_args)

        self.assertTrue(targeted["success"], targeted)
        backup_check = next(item for item in targeted["services"][0]["checks"] if item["operation"] == "ListBackups")
        self.assertFalse(backup_check["skipped"])
        self.assertEqual(backup_check["runner"], "scripts/hcloud_resource_query.py")
        self.assertIn("--arg=--instance_id=db-1", backup_check["plan"]["command"])

    def test_service_readiness_skips_target_dependent_checks(self) -> None:
        args = SimpleNamespace(
            service=["ELB"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=False,
        )

        result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        skipped = [item for item in result["services"][0]["checks"] if item.get("skipped")]
        self.assertEqual(
            {item["operation"] for item in skipped},
            {"ShowLoadBalancer", "ShowListener", "ShowPool", "ListMembers", "ShowMember"},
        )
        member_check = next(item for item in skipped if item["operation"] == "ShowMember")
        self.assertEqual(member_check["missing_targets"], ["pool_id", "member_id"])

    def test_service_readiness_uses_targets_for_member_checks(self) -> None:
        args = SimpleNamespace(
            service=["ELB"],
            target=["pool_id=pool-1", "member_id=member-1", "loadbalancer_id=lb-1", "listener_id=listener-1"],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=False,
            timeout=1,
            strict=True,
            require_all=True,
        )

        result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        member_check = next(item for item in result["services"][0]["checks"] if item["operation"] == "ListMembers")
        self.assertFalse(member_check["skipped"])
        self.assertEqual(member_check["runner"], "scripts/hcloud_resource_query.py")
        self.assertIn("--arg=--pool_id=pool-1", member_check["plan"]["command"])
        show_member_check = next(item for item in result["services"][0]["checks"] if item["operation"] == "ShowMember")
        self.assertFalse(show_member_check["skipped"])
        self.assertIn("--arg=--member_id=member-1", show_member_check["plan"]["command"])

    def test_service_readiness_non_strict_execute_allows_execution_failures(self) -> None:
        args = SimpleNamespace(
            service=["VPC"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=True,
            timeout=1,
            strict=False,
            require_all=False,
        )

        def fake_check(_args, service, _entry, check_spec, _targets):
            return {
                "service": service,
                "operation": check_spec["operation"],
                "stage": "execute",
                "success": False,
                "execution_success": False,
                "skipped": False,
            }

        with patch.object(hcloud_service_readiness, "build_check", side_effect=fake_check):
            result = hcloud_service_readiness.build_readiness(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["services"][0]["success"])

    def test_service_readiness_non_strict_execute_keeps_plan_failures_blocking(self) -> None:
        args = SimpleNamespace(
            service=["VPC"],
            target=[],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=20,
            execute=True,
            timeout=1,
            strict=False,
            require_all=False,
        )

        def fake_check(_args, service, _entry, check_spec, _targets):
            operation = check_spec["operation"]
            if operation == "ListSubnets":
                return {"service": service, "operation": operation, "stage": "plan", "success": False, "skipped": False}
            return {"service": service, "operation": operation, "stage": "execute", "success": False, "skipped": False}

        with patch.object(hcloud_service_readiness, "build_check", side_effect=fake_check):
            result = hcloud_service_readiness.build_readiness(args)

        self.assertFalse(result["success"])
        self.assertFalse(result["services"][0]["success"])

    def test_resource_verify_accepts_eip_binding(self) -> None:
        payload = {
            "parsed_json": {
                "publicips": [
                    {
                        "id": "eip-1",
                        "alias": "eip-app-01",
                        "status": "BIND_ACTIVE",
                        "port_id": "port-1",
                        "associate_instance_id": "server-1",
                    }
                ]
            }
        }
        args = SimpleNamespace(
            service="EIP",
            target_id=["eip-1"],
            target_name=[],
            expect_status=["BIND_ACTIVE"],
            expect_field=[],
            expect_cidr=None,
            expect_bound_to="port-1",
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["matched_count"], 1)
        self.assertEqual(result["failures"], [])

    def test_resource_verify_accepts_eip_associate_instance_binding(self) -> None:
        payload = {
            "publicips": [
                {
                    "id": "eip-1",
                    "status": "ACTIVE",
                    "associate_instance_id": "elb-1",
                }
            ]
        }
        args = SimpleNamespace(
            service="EIP",
            target_id=["eip-1"],
            target_name=[],
            expect_status=["ACTIVE"],
            expect_field=[],
            expect_cidr=None,
            expect_bound_to="elb-1",
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertTrue(result["success"], result)

    def test_idle_audit_flags_review_candidates_without_destructive_actions(self) -> None:
        result = hcloud_idle_audit.audit_payloads(
            [
                (
                    "EIP",
                    {"publicips": [{"id": "eip-1", "alias": "unused-eip", "status": "DOWN", "port_id": ""}]},
                ),
                (
                    "EVS",
                    {"volumes": [{"id": "vol-1", "name": "old-data", "status": "available", "attachments": []}]},
                ),
                (
                    "ECS",
                    {"servers": [{"id": "server-1", "name": "stopped-app", "status": "SHUTOFF"}]},
                ),
            ]
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["candidate_count"], 3)
        candidate_types = {candidate["candidate_type"] for candidate in result["candidates"]}
        self.assertEqual(
            candidate_types,
            {"unbound_public_ip", "unattached_volume", "stopped_or_abnormal_instance"},
        )
        self.assertTrue(all(candidate["destructive_action_allowed"] is False for candidate in result["candidates"]))
        self.assertIn("EIP", result["summary"]["by_service"])
        self.assertIn("EVS", result["summary"]["by_service"])

    def test_idle_audit_preserves_scope_and_tag_dimensions(self) -> None:
        result = hcloud_idle_audit.audit_payloads(
            [
                (
                    "EIP",
                    {
                        "publicips": [
                            {
                                "id": "eip-1",
                                "status": "DOWN",
                                "port_id": "",
                                "region": "cn-north-4",
                                "project_id": "project-1",
                                "enterprise_project_id": "eps-1",
                                "tags": [{"key": "owner", "value": "team-a"}],
                            }
                        ]
                    },
                )
            ]
        )

        candidate = result["candidates"][0]
        self.assertEqual(candidate["scope"]["region"], "cn-north-4")
        self.assertEqual(candidate["scope"]["project_id"], "project-1")
        self.assertEqual(candidate["scope"]["enterprise_project_id"], "eps-1")
        self.assertEqual(candidate["tags"], {"owner": "team-a"})
        self.assertEqual(result["summary"]["by_region"], {"cn-north-4": 1})
        self.assertEqual(result["summary"]["by_enterprise_project"], {"eps-1": 1})

    def test_idle_audit_extracts_payloads_from_inventory_result(self) -> None:
        inventory = {
            "checks": [
                {
                    "service": "EIP",
                    "scope": {
                        "region": "cn-north-4",
                        "project_id": "project-1",
                        "enterprise_project_id": "eps-1",
                    },
                    "plan": {
                        "results": [
                            {
                                "result": {
                                    "success": True,
                                    "parsed_json": {"publicips": [{"id": "eip-1", "status": "DOWN", "port_id": None}]},
                                }
                            }
                        ]
                    },
                }
            ]
        }

        payloads = hcloud_idle_audit.payloads_from_inventory(inventory)
        result = hcloud_idle_audit.audit_payloads(payloads)

        self.assertEqual(len(payloads), 1)
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["service"], "EIP")
        self.assertEqual(result["candidates"][0]["scope"]["region"], "cn-north-4")
        self.assertEqual(result["candidates"][0]["scope"]["enterprise_project_id"], "eps-1")

    def test_idle_audit_flags_security_group_elb_and_rds_risks(self) -> None:
        result = hcloud_idle_audit.audit_payloads(
            [
                (
                    "VPC",
                    {
                        "security_group_rules": [
                            {
                                "id": "rule-1",
                                "direction": "ingress",
                                "protocol": "tcp",
                                "port_range_min": 22,
                                "port_range_max": 22,
                                "remote_ip_prefix": "0.0.0.0/0",
                            }
                        ]
                    },
                ),
                ("ELB", {"loadbalancers": [{"id": "lb-1", "listeners": [], "status": "ACTIVE"}]}),
                (
                    "RDS",
                    {
                        "instances": [
                            {
                                "id": "db-1",
                                "name": "db",
                                "status": "ACTIVE",
                                "backup_policy": {"enabled": False, "keep_days": 0},
                            }
                        ]
                    },
                ),
            ]
        )

        candidate_types = {candidate["candidate_type"] for candidate in result["candidates"]}
        self.assertIn("public_sensitive_ingress_rule", candidate_types)
        self.assertIn("load_balancer_without_listeners", candidate_types)
        self.assertIn("database_backup_policy_review", candidate_types)

    def test_teardown_plan_orders_candidates_and_never_generates_submit(self) -> None:
        result = hcloud_teardown_plan.build_plan(
            [
                {"service": "ECS", "candidate_type": "stopped_or_abnormal_instance", "id": "server-1"},
                {"service": "ELB", "candidate_type": "load_balancer_without_listeners", "id": "lb-1"},
                {"service": "EIP", "candidate_type": "unbound_public_ip", "id": "eip-1"},
            ]
        )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertFalse(result["destructive_action_allowed"])
        self.assertEqual([step["service"] for step in result["steps"]], ["ELB", "EIP", "ECS"])
        self.assertTrue(all(step["executable"] is False for step in result["steps"]))
        self.assertTrue(all(step["submit_command"] is None for step in result["steps"]))

    def test_resource_verify_reports_status_mismatch(self) -> None:
        payload = {"instances": [{"id": "rds-1", "name": "db", "status": "BUILD"}]}
        args = SimpleNamespace(
            service="RDS",
            target_id=[],
            target_name=["db"],
            expect_status=["AVAILABLE"],
            expect_field=[],
            expect_cidr=None,
            expect_bound_to=None,
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertFalse(result["success"])
        self.assertIn("status_mismatch", result["failures"])

    def test_resource_verify_accepts_expected_fields(self) -> None:
        payload = {"loadbalancers": [{"id": "lb-1", "provisioning_status": "ACTIVE", "operating_status": "ONLINE"}]}
        args = SimpleNamespace(
            service="ELB",
            target_id=["lb-1"],
            target_name=[],
            expect_status=["ACTIVE"],
            expect_field=["operating_status=ONLINE"],
            expect_cidr=None,
            expect_bound_to=None,
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertTrue(result["success"], result)

    def test_resource_verify_accepts_cdn_domain_status(self) -> None:
        payload = {"domains": [{"id": "domain-1", "domain_name": "static.example.com", "domain_status": "online"}]}
        args = SimpleNamespace(
            service="CDN",
            target_id=[],
            target_name=["static.example.com"],
            expect_status=["ONLINE"],
            expect_field=[],
            expect_cidr=None,
            expect_bound_to=None,
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertTrue(result["success"], result)

    def test_resource_verify_accepts_dns_recordset_name(self) -> None:
        payload = {"recordsets": [{"id": "recordset-1", "name": "www.example.com.", "status": "ACTIVE"}]}
        args = SimpleNamespace(
            service="DNS",
            target_id=[],
            target_name=["www.example.com."],
            expect_status=["ACTIVE"],
            expect_field=[],
            expect_cidr=None,
            expect_bound_to=None,
            require_match=True,
        )

        result = hcloud_resource_verify.verify_payload(args, payload)

        self.assertTrue(result["success"], result)

    def test_resource_verify_collects_singular_high_frequency_shapes(self) -> None:
        cases = [
            ("ECS", {"servers": [{"id": "server-1", "status": "ACTIVE"}]}),
            ("VPC", {"vpc": {"id": "vpc-1", "status": "OK"}}),
            ("ELB", {"loadbalancer": {"id": "lb-1", "provisioning_status": "ACTIVE"}}),
            ("EVS", {"volume": {"id": "vol-1", "status": "available"}}),
            ("NAT", {"dnat_rule": {"id": "dnat-1", "status": "ACTIVE"}}),
            ("IMS", {"image": {"id": "img-1", "status": "active"}}),
            ("KPS", {"keypair": {"keypair_name": "key-1"}}),
        ]

        for service, payload in cases:
            with self.subTest(service=service):
                resources = hcloud_resource_verify.collect_dicts(payload, service)

                self.assertEqual(len(resources), 1)

    def test_resource_verify_collects_top_level_rds_configuration(self) -> None:
        payload = {
            "id": "config-1",
            "name": "Default-PostgreSQL-11",
            "configuration_parameters": [
                {"name": "statement_timeout", "value": "0"},
            ],
        }

        resources = hcloud_resource_verify.collect_dicts(payload, "RDS")

        self.assertEqual(len(resources), 1)
        self.assertEqual(resources[0]["id"], "config-1")

    def test_resource_verify_does_not_treat_control_plane_receipt_as_resource(self) -> None:
        payload = {"request_id": "req-1", "resource_id": "server-1", "status": "SUCCESS"}

        resources = hcloud_resource_verify.collect_dicts(payload, "EIP")

        self.assertEqual(resources, [])

    def test_service_change_plan_adds_service_hints(self) -> None:
        args = SimpleNamespace(
            service="EIP",
            operation="CreatePublicip",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertTrue(result["registered_change_operation"])
        self.assertEqual(result["resource_verifier"], "scripts/hcloud_resource_verify.py")
        self.assertTrue(result["service_verification_hints"])
        self.assertIn("--arg=--dryrun", result["commands"]["dryrun_or_plan"])

    def test_service_change_plan_delegates_obs_to_specific_planner(self) -> None:
        args = SimpleNamespace(
            service="OBS",
            operation="putbucketlifecycle",
            region="cn-north-4",
            project_id=None,
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["operation"], "PutBucketLifecycle")
        self.assertEqual(result["delegated_planner"], "scripts/hcloud_obs_change_plan.py")

    def test_resource_detail_probe_builds_evs_nat_plan(self) -> None:
        args = SimpleNamespace(
            service=["EVS", "NAT"],
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            limit=5,
            execute=False,
            timeout=1,
        )

        result = hcloud_resource_detail_probe.build_probe(args)

        self.assertTrue(result["success"], result)
        self.assertEqual([item["service"] for item in result["checks"]], ["EVS", "NAT"])
        self.assertEqual(result["checks"][0]["detail_operation"], "ShowVolume")
        self.assertEqual(result["checks"][1]["detail_operation"], "ShowNatGateway")

    def test_service_change_plan_uses_supported_cdn_cli_region(self) -> None:
        args = SimpleNamespace(
            service="CDN",
            operation="CreateDomain",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertIn("--arg=--cli-region=cn-north-1", result["commands"]["dryrun_or_plan"])
        self.assertNotIn("--arg=--cli-region=cn-north-4", result["commands"]["dryrun_or_plan"])
        self.assertEqual(result["region_resolution"]["requested_region"], "cn-north-4")
        self.assertEqual(result["region_resolution"]["resolved_region"], "cn-north-1")

    def test_service_change_plan_maps_old_change_operation_alias(self) -> None:
        args = SimpleNamespace(
            service="RDS",
            operation="ResizeInstance",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=["--instance_id=rds-1"],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["requested_operation"], "ResizeInstance")
        self.assertEqual(result["operation"], "StartResizeFlavorAction")
        self.assertTrue(result["registered_change_operation"])

    def test_service_change_plan_builds_catalog_backed_mutation_plan(self) -> None:
        args = SimpleNamespace(
            service="UCS",
            operation="CreateClusterKubeconfig",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=["--clusterid=cluster-1"],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertTrue(result["metadata_backed"])
        self.assertFalse(result["registered_change_operation"])
        self.assertEqual(result["coverage"], "metadata-backed")
        self.assertIn("--service", result["commands"]["dryrun_or_plan"])
        self.assertIn("UCS", result["commands"]["dryrun_or_plan"])
        self.assertEqual(result["catalog_dryrun"], "unknown")
        self.assertNotIn("--arg=--dryrun", result["commands"]["dryrun_or_plan"])
        self.assertTrue(result["submit_requires_confirmation"])

    def test_service_change_plan_hard_guards_security_category_mutation(self) -> None:
        args = SimpleNamespace(
            service="WAF",
            operation="BatchUpdateCustomRules",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=["--policy_id=policy-1"],
            no_dryrun=False,
            allow_unregistered=True,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["metadata_backed"])
        self.assertEqual(result["catalog_category"], "Security & Compliance")
        self.assertEqual(result["risk"]["level"], "high")
        self.assertTrue(result["risk"]["hard_guard"])
        self.assertNotIn("--arg=--dryrun", result["commands"]["dryrun_or_plan"])

    def test_service_change_plan_rejects_catalog_backed_read_operation(self) -> None:
        args = SimpleNamespace(
            service="UCS",
            operation="ListManagedClusters",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertFalse(result["success"])
        self.assertTrue(result["metadata_backed"])
        self.assertIn("read-only", result["error"])

    def test_catalog_discovery_omits_confidence_unsupported_limit(self) -> None:
        args = SimpleNamespace(
            service="UCS",
            operation="ListManagedClusters",
            region="cn-north-4",
            project_id=None,
            profile=None,
            limit=5,
            execute=False,
        )

        result = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(result["success"], result)
        command = result["commands"][0]["command"]
        self.assertNotIn("--arg=--limit=5", command)
        self.assertEqual(result["commands"][0]["omitted_args"], ["--limit"])
        self.assertIn("confidence sidecar", result["commands"][0]["omitted_reason"])

    def test_service_change_plan_rejects_unregistered_operation(self) -> None:
        args = SimpleNamespace(
            service="EIP",
            operation="RunUnknownMutation",
            region="cn-north-4",
            project_id="project-1",
            profile=None,
            json_input_file=None,
            arg=[],
            no_dryrun=False,
            allow_unregistered=False,
        )

        result = hcloud_service_change_plan.build_service_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("not registered", result["error"])

    def test_lifecycle_closure_blocks_unrestricted_security_group_ingress(self) -> None:
        args = self.lifecycle_args(
            service=["VPC"],
            param=[
                "security_group_id=sg-1",
                "direction=ingress",
                "protocol=tcp",
                "remote_ip_prefix=0.0.0.0/0",
                "port_range_min=22",
                "port_range_max=22",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertFalse(result["success"])
        service = result["services"][0]
        self.assertTrue(service["hard_blocked"])
        self.assertEqual(len(service["hard_blockers"]), 1)
        self.assertEqual(service["hard_blockers"][0]["code"], "unrestricted_sensitive_ingress_port")
        readiness_checks = service["stages"][0]["readiness_plan"]["services"][0]["checks"]
        operations = [item["operation"] for item in readiness_checks]
        self.assertIn("ShowSecurityGroupRule", operations)

    def test_lifecycle_closure_eip_has_structured_acceptance_evidence(self) -> None:
        args = self.lifecycle_args(
            service=["EIP"],
            param=[
                "publicip_id=eip-1",
                "target_resource_id=server-1",
                "probe_url=https://example.com/health",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        evidence_plan = verification["acceptance_evidence_plan"]
        self.assertEqual(evidence_plan["service"], "EIP")
        self.assertEqual(evidence_plan["acceptance_level"], "task_level_acceptance_evidence_plan")
        self.assertEqual(evidence_plan["summary"]["ready_item_count"], 3)
        self.assertEqual(evidence_plan["summary"]["missing_input_item_count"], 0)
        self.assertEqual(
            {item["id"] for item in evidence_plan["evidence_items"]},
            {"publicip_readback", "binding_target_readback", "public_protocol_probe"},
        )
        self.assertTrue(any("ShowPublicip" in boundary for boundary in evidence_plan["claim_boundaries"]))

    def test_lifecycle_closure_evs_distinguishes_cloud_and_guest_readiness(self) -> None:
        args = self.lifecycle_args(
            service=["EVS"],
            param=[
                "volume_id=vol-1",
                "server_id=server-1",
                "mountpoint=/data",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "EVS")
        self.assertIn("filesystem", service["missing_recommended_inputs"])
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("fstab" in check for check in verification["checks"]))
        self.assertTrue(any("write test" in check for check in verification["checks"]))
        evidence_plan = verification["acceptance_evidence_plan"]
        guest_item = next(item for item in evidence_plan["evidence_items"] if item["id"] == "guest_device_filesystem")
        self.assertEqual(guest_item["status"], "missing_inputs")
        self.assertIn("filesystem", guest_item["missing_any_of_inputs"])

    def test_lifecycle_closure_elb_requires_backend_health_and_security_group(self) -> None:
        args = self.lifecycle_args(
            service=["ELB"],
            param=[
                "loadbalancer_id=lb-1",
                "listener_id=listener-1",
                "pool_id=pool-1",
                "member_id=member-1",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        gate_codes = {item["code"] for item in gate["gates"]}
        self.assertIn("backend_unreachable", gate_codes)
        self.assertIn("security_group_dependency", gate_codes)
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("ONLINE" in check for check in verification["checks"]))
        self.assertEqual(
            verification["readiness_targets"],
            [
                "loadbalancer_id=lb-1",
                "listener_id=listener-1",
                "pool_id=pool-1",
                "member_id=member-1",
            ],
        )

    def test_lifecycle_closure_rds_requires_backup_and_connection_readiness(self) -> None:
        args = self.lifecycle_args(
            service=["RDS"],
            param=[
                "instance_id=rds-1",
                "config_id=config-1",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "RDS")
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        gate_codes = {item["code"] for item in gate["gates"]}
        self.assertIn("backup_required", gate_codes)
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("connection probe" in check for check in verification["checks"]))
        readiness_ops = {item["operation"] for item in service["stages"][0]["readiness_plan"]["services"][0]["checks"]}
        self.assertIn("ShowBackupPolicy", readiness_ops)
        self.assertIn("ShowInstanceConfiguration", readiness_ops)

    def test_lifecycle_closure_obs_uses_obs_adapter_and_public_policy_gate(self) -> None:
        args = self.lifecycle_args(
            service=["OBS"],
            param=["bucket=example-bucket"],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "OBS")
        readiness = service["stages"][0]["readiness_plan"]["services"][0]["checks"]
        self.assertTrue(all(check["runner"] == "scripts/hcloud_obs_readonly.py" for check in readiness))
        operations = {check["operation"] for check in readiness}
        self.assertIn("StatBucket", operations)
        self.assertIn("GetBucketPolicy", operations)
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        self.assertIn("public_bucket_exposure", {item["code"] for item in gate["gates"]})
        planning = next(stage for stage in service["stages"] if stage["id"] == "operation_parameter_planning")
        self.assertEqual(planning["change_plan"]["delegated_planner"], "scripts/hcloud_obs_change_plan.py")

    def test_lifecycle_closure_dns_requires_ttl_and_resolution_verification(self) -> None:
        args = self.lifecycle_args(
            service=["DNS"],
            param=[
                "zone_id=zone-1",
                "recordset_id=record-1",
                "record_name=www.example.com",
                "record_type=A",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertIn("ttl", service["missing_recommended_inputs"])
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("DNS resolution" in check for check in verification["checks"]))
        self.assertEqual(verification["readiness_targets"], ["zone_id=zone-1", "recordset_id=record-1"])

    def test_lifecycle_closure_scm_requires_https_verification(self) -> None:
        args = self.lifecycle_args(
            service=["SCM"],
            param=[
                "certificate_id=cert-1",
                "domain_name=www.example.com",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "SCM")
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        self.assertIn("https_outage", {item["code"] for item in gate["gates"]})
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("HTTPS handshake" in check for check in verification["checks"]))

    def test_lifecycle_closure_cdn_requires_origin_cache_and_http_probes(self) -> None:
        args = self.lifecycle_args(
            service=["CDN"],
            param=[
                "domain_id=domain-1",
                "domain_name=www.example.com",
                "origin=origin.example.com",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        self.assertIn("origin_or_cache_outage", {item["code"] for item in gate["gates"]})
        verification = next(stage for stage in service["stages"] if stage["id"] == "post_change_verification")
        self.assertTrue(any("HTTP/HTTPS" in check for check in verification["checks"]))
        planning = next(stage for stage in service["stages"] if stage["id"] == "operation_parameter_planning")
        self.assertEqual(planning["change_plan"]["operation"], "UpdateDomainFullConfig")

    def test_lifecycle_closure_ces_lts_combines_metric_and_log_evidence(self) -> None:
        args = self.lifecycle_args(
            service=["CES"],
            param=[
                "log_group_id=group-1",
                "log_stream_id=stream-1",
                "start_time=2026-06-06T00:00:00Z",
                "end_time=2026-06-06T01:00:00Z",
            ],
        )

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service"], "CES_LTS")
        context = service["stages"][0]
        self.assertEqual(context["readiness_plan"]["services"][0]["service"], "CES")
        self.assertIn("lts_readonly_plan", context["extra_evidence_plans"])
        planning = next(stage for stage in service["stages"] if stage["id"] == "operation_parameter_planning")
        self.assertEqual(planning["change_plan"]["change_planner"], "none")
        gate = next(stage for stage in service["stages"] if stage["id"] == "risk_security_gate")
        self.assertIn("sensitive_logs", {item["code"] for item in gate["gates"]})

    def test_lifecycle_closure_default_covers_all_p0_services(self) -> None:
        args = self.lifecycle_args(service=None)

        result = hcloud_lifecycle_closure_plan.build_lifecycle_plan(args)

        services = {item["service"] for item in result["services"]}
        self.assertEqual(
            services,
            {"VPC", "EIP", "EVS", "ELB", "RDS", "OBS", "DNS", "SCM", "CDN", "CES_LTS"},
        )

    def test_governance_closure_default_covers_all_p1_services(self) -> None:
        args = self.governance_args()

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertIn("planned_evidence_command_count", result["governance_summary"])
        self.assertEqual(
            set(result["selected_services"]),
            {"TMS", "CTS", "CBR", "RMS_CONFIG", "BILLING_BSS", "WAF", "DLI", "CODEARTSREPO"},
        )
        self.assertTrue(all(service["execution_supported"] is False for service in result["services"]))
        self.assertTrue(any("No tag" in boundary for boundary in result["global_boundaries"]))

    def test_governance_closure_billing_builds_request_specs_without_execution(self) -> None:
        args = self.governance_args(
            service=["Billing"],
            param=[
                "bill_cycle=2026-05",
                "begin_time=2026-05-01",
                "end_time=2026-05-31",
            ],
        )

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        self.assertEqual(service["service_key"], "BILLING_BSS")
        evidence = next(stage for stage in service["stages"] if stage["id"] == "read_only_evidence")
        specs = evidence["billing_request_specs"]
        self.assertEqual({spec["operation"] for spec in specs}, {"monthly-sum", "cost-data", "resource-records"})
        self.assertTrue(all(spec["success"] for spec in specs))
        evidence_plans = evidence["evidence_command_plans"]
        self.assertEqual(evidence_plans["summary"]["planned_command_count"], 3)
        self.assertEqual(len(evidence_plans["billing_hcloud_command_plans"]), 3)
        self.assertIn("explicit live billing read approval", evidence_plans["execution_boundary"])
        risk = next(stage for stage in service["stages"] if stage["id"] == "risk_and_privacy_gate")
        self.assertEqual(
            risk["risk_profiles"][0]["risk_profile"]["submit_policy"],
            "readonly_hcloud_plan_requires_live_billing_read_approval",
        )
        self.assertTrue(all("requires_auth" in spec["request_spec"] for spec in specs))
        self.assertTrue(all("hcloud_command_plan" in spec for spec in specs))
        promotion = next(stage for stage in service["stages"] if stage["id"] == "promotion_readiness")
        self.assertEqual(promotion["profiles"][0]["service"], "BSS")

    def test_governance_closure_rms_alias_combines_rms_and_config(self) -> None:
        args = self.governance_args(service=["Config"])

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["selected_services"], ["RMS_CONFIG"])
        service = result["services"][0]
        self.assertEqual(service["services"], ["RMS", "Config"])
        evidence = next(stage for stage in service["stages"] if stage["id"] == "read_only_evidence")
        self.assertEqual({item["service"] for item in evidence["readiness_operations"]}, {"RMS", "Config"})
        evidence_plans = evidence["evidence_command_plans"]
        self.assertGreater(evidence_plans["summary"]["discovery_plan_count"], 0)
        self.assertGreater(evidence_plans["summary"]["resource_query_plan_count"], 0)
        promotion = next(stage for stage in service["stages"] if stage["id"] == "promotion_readiness")
        self.assertEqual({item["service"] for item in promotion["profiles"]}, {"RMS", "Config"})

    def test_governance_closure_tms_generates_readonly_evidence_commands(self) -> None:
        args = self.governance_args(
            service=["TMS"],
            param=[
                "resource_id=res-1",
                "resource_type=ecs",
                "resource_types=ecs",
                "tag_key=owner",
                "tags=owner:team-a",
            ],
        )

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        evidence = next(stage for stage in service["stages"] if stage["id"] == "read_only_evidence")
        plans = evidence["evidence_command_plans"]
        self.assertGreaterEqual(plans["summary"]["planned_command_count"], 4)
        self.assertTrue(any(plan["operation"] == "ListProviders" and plan["commands"] for plan in plans["discovery_plans"]))
        self.assertTrue(any(plan["operation"] == "ShowTagQuota" and plan["command"] for plan in plans["resource_query_plans"]))

    def test_governance_closure_waf_keeps_policy_changes_hard_gated(self) -> None:
        args = self.governance_args(service=["WAF"])

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        service = result["services"][0]
        risk = next(stage for stage in service["stages"] if stage["id"] == "risk_and_privacy_gate")
        self.assertEqual(risk["mutation_boundary"], "planner_only_no_submit")
        self.assertEqual(
            risk["risk_profiles"][0]["risk_profile"]["mutation_policy"],
            "planner_only_hard_guard_until_curated",
        )
        review = next(stage for stage in service["stages"] if stage["id"] == "review_plan")
        self.assertTrue(any("policy" in check.lower() for check in review["checks"]))

    def test_governance_closure_rejects_unsupported_service(self) -> None:
        args = self.governance_args(service=["NOT_A_SERVICE"])

        result = hcloud_governance_closure_plan.build_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("NOT_A_SERVICE", result["unsupported_services"])

    def test_p2_scenario_default_covers_all_groups(self) -> None:
        args = self.p2_args()

        result = hcloud_p2_scenario_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(
            set(result["selected_groups"]),
            {
                "CCE",
                "NAT",
                "DCS",
                "RFS",
                "UCS",
                "DEPENDENCY_IAM_KPS_IMS",
                "SECURITY_POSTURE",
                "DATABASE_FAMILY",
            },
        )
        self.assertIn("planned_evidence_command_count", result["scenario_summary"])
        self.assertTrue(all(group["execution_supported"] is False for group in result["groups"]))

    def test_p2_scenario_cce_generates_cluster_readiness_commands(self) -> None:
        args = self.p2_args(group=["CCE"], param=["cluster_id=cluster-1"])

        result = hcloud_p2_scenario_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        group = result["groups"][0]
        self.assertEqual(group["scenario_summary"]["status"], "review_ready")
        evidence = next(stage for stage in group["stages"] if stage["id"] == "read_only_evidence")["evidence"]
        self.assertTrue(any(plan["operation"] == "ListClusters" and plan["commands"] for plan in evidence["discovery_plans"]))
        self.assertTrue(any(plan["operation"] == "ShowCluster" and plan["command"] for plan in evidence["resource_query_plans"]))
        self.assertEqual(evidence["summary"]["missing_param_query_count"], 0)

    def test_p2_scenario_security_group_remains_metadata_evidence_gap(self) -> None:
        args = self.p2_args(group=["SECURITY"])

        result = hcloud_p2_scenario_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        group = result["groups"][0]
        self.assertEqual(group["group"], "SECURITY_POSTURE")
        self.assertEqual(group["scenario_summary"]["status"], "metadata_evidence_gap")
        evidence = next(stage for stage in group["stages"] if stage["id"] == "read_only_evidence")["evidence"]
        self.assertEqual({entry["service"] for entry in evidence["profiles"]}, {"HSS", "SecMaster", "CFW", "DBSS", "KMS"})
        self.assertFalse(any(str(plan["operation"]).startswith("Download") for plan in evidence["resource_query_plans"]))
        risk = next(stage for stage in group["stages"] if stage["id"] == "risk_boundary")
        self.assertEqual(risk["mutation_boundary"], "planner_only_no_submit")

    def test_p2_scenario_database_family_stays_metadata_only(self) -> None:
        args = self.p2_args(group=["DATABASE"])

        result = hcloud_p2_scenario_closure_plan.build_plan(args)

        self.assertTrue(result["success"], result)
        group = result["groups"][0]
        self.assertEqual(group["group"], "DATABASE_FAMILY")
        self.assertTrue(group["scenario_summary"]["metadata_only"])
        self.assertEqual(group["scenario_summary"]["status"], "metadata_evidence_gap")
        self.assertIn("GaussDB", group["services"])
        self.assertIn("DWS", group["services"])
        risk = next(stage for stage in group["stages"] if stage["id"] == "risk_boundary")
        self.assertTrue(any("RDS-style" in check for check in risk["checks"]))

    def test_p2_scenario_rejects_unsupported_group(self) -> None:
        args = self.p2_args(group=["NOT_A_GROUP"])

        result = hcloud_p2_scenario_closure_plan.build_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("NOT_A_GROUP", result["unsupported_groups"])

    def test_closure_maturity_audit_reports_planner_boundaries(self) -> None:
        result = hcloud_closure_maturity_audit.build_audit()

        self.assertTrue(result["success"], result)
        self.assertFalse(result["all_services_ecs_level"])
        tiers = {tier["id"]: tier for tier in result["tiers"]}
        self.assertEqual(tiers["ecs_end_to_end_sample"]["status"], "sample_reference")
        self.assertIn("acceptance_evidence_plan", tiers["p0_task_level_planner"]["closure_outputs"])
        self.assertEqual(tiers["p1_governance_planner_only"]["execution_boundary"], "planner_only_or_request_spec_only")
        self.assertEqual(tiers["p2_scenario_planner_only"]["execution_boundary"], "planner_only_no_submit")
        self.assertEqual(tiers["metadata_backed_evidence_gap"]["status"], "evidence_gap_until_promoted")
        self.assertEqual(result["summary"]["p0_service_count"], len(hcloud_lifecycle_closure_plan.CLOSURE_SERVICES))
        evidence = result["evidence_provenance"]
        self.assertEqual(evidence["curation_profiles"]["service_count"], 30)
        self.assertEqual(evidence["curation_profiles"]["status_counts"], {"candidate": 11, "curated": 19})
        self.assertEqual(evidence["closure_target_profiles"]["service_count"], 6)
        self.assertEqual(evidence["closure_target_profiles"]["semantics"], "target_evidence_contract_not_run_history")
        self.assertGreater(evidence["live_smoke_evidence"]["operation_count"], 0)
        self.assertEqual(evidence["live_smoke_evidence"]["timestamped_operation_count"], 0)
        self.assertEqual(evidence["live_smoke_evidence"]["environment_described_operation_count"], 0)
        self.assertEqual(evidence["live_smoke_evidence"]["source_revision_described_operation_count"], 0)
        self.assertEqual(evidence["live_smoke_evidence"]["freshness_status"], "unknown_missing_observed_at")
        self.assertFalse(evidence["recent_live_validation_claimed"])

    def test_closure_maturity_requires_source_revision_for_complete_provenance(self) -> None:
        confidence = {
            "services": {
                "UCS": {
                    "operations": {
                        "ListClusters": {
                            "confidence": "live-read-smoked",
                            "last_smoke": {
                                "observed_at": "2026-08-04T08:00:00Z",
                                "evidence_source": {"tool": "scripts/hcloud_catalog_readonly_smoke.py"},
                                "environment": {"region": "cn-north-4"},
                            },
                        }
                    }
                },
                "RFS": {
                    "operations": {
                        "ListStacks": {
                            "confidence": "live-read-smoked",
                            "last_smoke": {
                                "observed_at": "2026-08-04T08:00:01Z",
                                "evidence_source": {
                                    "tool": "scripts/hcloud_catalog_readonly_smoke.py",
                                    "skill_commit": "a" * 40,
                                },
                                "environment": {"region": "cn-north-4"},
                            },
                        }
                    }
                },
            }
        }
        with patch.object(
            hcloud_closure_maturity_audit.hcloud_common,
            "load_json",
            side_effect=[{"services": {}}, {"services": {}}, confidence],
        ):
            summary = hcloud_closure_maturity_audit.evidence_provenance_summary()

        evidence = summary["live_smoke_evidence"]
        self.assertEqual(evidence["sourced_operation_count"], 2)
        self.assertEqual(evidence["source_revision_described_operation_count"], 1)
        self.assertEqual(evidence["provenance_complete_operation_count"], 1)

    def test_acceptance_evidence_result_evaluates_local_statuses(self) -> None:
        plan = hcloud_lifecycle_closure_plan.build_lifecycle_plan(
            self.lifecycle_args(
                service=["EIP"],
                param=[
                    "publicip_id=eip-1",
                    "target_resource_id=server-1",
                    "probe_url=https://example.com/health",
                ],
            )
        )
        evidence = {
            "evidence": {
                "publicip_readback": "passed",
                "binding_target_readback": {"status": "passed", "summary": "bound to server-1"},
                "public_protocol_probe": {"status": "warning", "summary": "HTTP returned 503"},
            }
        }

        result = hcloud_acceptance_evidence_result.evaluate_plan(plan, evidence)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["overall_status"], "warning")
        service = result["services"][0]
        self.assertEqual(service["service"], "EIP")
        self.assertEqual(service["summary"]["passed"], 2)
        self.assertEqual(service["summary"]["warning"], 1)
        protocol = next(item for item in service["item_results"] if item["id"] == "public_protocol_probe")
        self.assertEqual(protocol["reason"], "HTTP returned 503")

    def test_acceptance_evidence_result_marks_missing_unsupplied_evidence(self) -> None:
        plan = hcloud_lifecycle_closure_plan.build_lifecycle_plan(
            self.lifecycle_args(service=["EVS"], param=["volume_id=vol-1", "server_id=server-1", "mountpoint=/data"])
        )

        result = hcloud_acceptance_evidence_result.evaluate_plan(
            plan,
            {"evidence": {"volume_readback": "passed"}},
        )

        self.assertEqual(result["overall_status"], "missing")
        service = result["services"][0]
        guest = next(item for item in service["item_results"] if item["id"] == "guest_device_filesystem")
        self.assertEqual(guest["status"], "missing")
        self.assertIn("filesystem", guest["reason"])

    def test_acceptance_probe_plan_builds_non_executing_templates(self) -> None:
        plan = hcloud_lifecycle_closure_plan.build_lifecycle_plan(
            self.lifecycle_args(
                service=["EIP"],
                param=[
                    "publicip_id=eip-1",
                    "target_resource_id=server-1",
                    "probe_url=https://example.com/health",
                ],
            )
        )

        result = hcloud_acceptance_probe_plan.build_probe_plan(plan)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["execution_boundary"], "templates_only_no_live_probe")
        service = result["services"][0]
        probe = next(item for item in service["probes"] if item["id"] == "public_protocol_probe")
        self.assertEqual(probe["status"], "planned")
        self.assertEqual(probe["execution_boundary"], "not_executed")
        self.assertTrue(any("curl" in template for template in probe["probe_templates"]))

    def test_offline_eip_acceptance_flow_end_to_end(self) -> None:
        lifecycle_plan = hcloud_lifecycle_closure_plan.build_lifecycle_plan(
            self.lifecycle_args(
                service=["EIP"],
                param=[
                    "publicip_id=eip-1",
                    "target_resource_id=server-1",
                    "probe_url=https://example.com/health",
                ],
            )
        )

        probe_plan = hcloud_acceptance_probe_plan.build_probe_plan(lifecycle_plan)
        result = hcloud_acceptance_evidence_result.evaluate_plan(
            lifecycle_plan,
            {
                "evidence": {
                    "publicip_readback": "passed",
                    "binding_target_readback": "passed",
                    "public_protocol_probe": "passed",
                }
            },
        )

        self.assertTrue(lifecycle_plan["success"], lifecycle_plan)
        self.assertEqual(probe_plan["services"][0]["planned_probe_count"], 3)
        self.assertEqual(result["overall_status"], "passed")
        self.assertEqual(result["services"][0]["summary"]["passed"], 3)

    def test_resource_verify_cli_reads_safe_exec_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "result.json"
            path.write_text(
                json.dumps({"parsed_json": {"volumes": [{"id": "vol-1", "status": "in-use", "attachments": [{"server_id": "server-1"}]}]}}),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                service="EVS",
                json_file=str(path),
                target_id=["vol-1"],
                target_name=[],
                expect_status=["IN-USE"],
                expect_field=[],
                expect_cidr=None,
                expect_bound_to="server-1",
                require_match=True,
                pretty=False,
            )

            result = hcloud_resource_verify.verify_payload(args, hcloud_resource_verify.load_json(path))

        self.assertTrue(result["success"], result)

    def test_resource_verify_cli_reports_missing_file_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "missing.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "hcloud_resource_verify.py"),
                    "--service",
                    "CDN",
                    "--json-file",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertFalse(result["success"])
        self.assertIn("missing.json", result["error"])


if __name__ == "__main__":
    unittest.main()
