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
            "skip_dryrun": False,
            "execute_verify": False,
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
            "execute_dryrun": False,
            "execute_submit": False,
            "confirm_submit": False,
            "skip_dryrun": False,
            "execute_readiness": False,
            "verify_operation": None,
            "verify_param": ["security_group_rule_id=rule-1"],
            "execute_verify": False,
            "timeout": 1,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

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

        rfs_fixed = json.loads(
            (ROOT / "tests" / "fixtures" / "hcloud-catalog-readonly-smoke-rfs-fixed.json").read_text(
                encoding="utf-8"
            )
        )
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
        self.assertIn("--arg=--dryrun", result["service_plan"]["commands"]["dryrun_or_plan"])
        self.assertIn("--expect-json", result["service_plan"]["commands"]["submit"])
        self.assertNotIn("submit", result)

    def test_eip_change_flow_requires_submit_confirmation(self) -> None:
        result = hcloud_eip_change_flow.build_flow(
            self.eip_flow_args(execute_submit=True, execute_dryrun=True)
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["submit_guard_failure"]["error"], "Submit execution requires --confirm-submit.")

    def test_eip_change_flow_executes_dryrun_and_verify_with_mocks(self) -> None:
        with patch.object(
            hcloud_eip_change_flow,
            "execute_command",
            return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1"}}},
        ) as dryrun_mock, patch.object(
            hcloud_eip_change_flow.hcloud_resource_query,
            "execute_command",
            return_value={"success": True, "parsed_json": {"publicip": {"id": "eip-1", "status": "DOWN"}}},
        ) as verify_mock:
            result = hcloud_eip_change_flow.build_flow(
                self.eip_flow_args(execute_dryrun=True, execute_verify=True)
            )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["dryrun"]["success"])
        self.assertTrue(result["verification"]["success"])
        self.assertEqual(result["verification"]["operation"], "ShowPublicip")
        dryrun_mock.assert_called_once()
        verify_mock.assert_called_once()

    def test_guarded_change_flow_builds_generic_plan(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(self.guarded_flow_args())

        self.assertTrue(result["success"], result)
        self.assertTrue(result["planning_only"])
        self.assertEqual(result["service"], "VPC")
        command = result["service_plan"]["commands"]["dryrun_or_plan"]
        self.assertIn("--arg=--cli-output=json", command)
        self.assertIn("--expect-json", command)
        self.assertIn("--arg=--dryrun", command)
        self.assertIn("post_change_readiness_plan", result)
        self.assertTrue(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["operation"], "ShowSecurityGroupRule")
        self.assertIn("--arg=--security_group_rule_id=rule-1", result["post_change_verification"]["command"])

    def test_guarded_change_flow_requires_submit_confirmation(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(execute_submit=True, execute_dryrun=True)
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["submit_guard_failure"]["error"], "Submit execution requires --confirm-submit.")
        self.assertTrue(result["planning_only"])

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

    def test_guarded_change_flow_executes_dryrun_and_readiness_with_mocks(self) -> None:
        with patch.object(
            hcloud_guarded_change_flow,
            "execute_command",
            return_value={"success": True, "parsed_json": {"ok": True}},
        ) as dryrun_mock, patch.object(
            hcloud_guarded_change_flow.hcloud_resource_discovery,
            "execute_plan",
            return_value={"success": True, "results": []},
        ) as readiness_mock:
            result = hcloud_guarded_change_flow.build_flow(
                self.guarded_flow_args(execute_dryrun=True, execute_readiness=True)
            )

        self.assertTrue(result["success"], result)
        self.assertTrue(result["dryrun"]["success"])
        self.assertTrue(result["post_change_verification"]["success"])
        self.assertTrue(result["post_change_readiness"]["success"])
        dryrun_mock.assert_called_once()
        readiness_mock.assert_called_once()

    def test_guarded_change_flow_extracts_verify_id_from_submit_result(self) -> None:
        with patch.object(
            hcloud_guarded_change_flow,
            "execute_command",
            side_effect=[
                {"success": True, "parsed_json": {"dryrun": True}},
                {"success": True, "parsed_json": {"security_group_rule": {"id": "rule-2"}}},
            ],
        ) as execute_mock, patch.object(
            hcloud_guarded_change_flow.hcloud_resource_query,
            "execute_command",
            return_value={"success": True, "parsed_json": {"security_group_rule": {"id": "rule-2"}}},
        ) as verify_mock:
            result = hcloud_guarded_change_flow.build_flow(
                self.guarded_flow_args(
                    verify_param=[],
                    execute_dryrun=True,
                    execute_submit=True,
                    confirm_submit=True,
                    execute_verify=True,
                )
            )

        self.assertTrue(result["success"], result)
        self.assertFalse(result["planning_only"])
        self.assertEqual(result["post_change_verification"]["operation"], "ShowSecurityGroupRule")
        self.assertIn("--arg=--security_group_rule_id=rule-2", result["post_change_verification"]["command"])
        self.assertEqual(execute_mock.call_count, 2)
        verify_mock.assert_called_once()

    def test_guarded_change_flow_reports_missing_verify_target(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(verify_param=[])
        )

        self.assertTrue(result["success"], result)
        self.assertFalse(result["post_change_verification"]["success"])
        self.assertEqual(result["post_change_verification"]["missing_params"], ["security_group_rule_id"])

    def test_guarded_change_flow_does_not_verify_wrong_vpc_resource(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(operation="CreateVpcPeering", arg=[], verify_param=[])
        )

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

    def test_guarded_change_flow_rejects_delegated_planner(self) -> None:
        result = hcloud_guarded_change_flow.build_flow(
            self.guarded_flow_args(service="OBS", operation="CreateBucket")
        )

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
        self.assertIn("ShowConfiguration", result["command"])
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
            },
        )
        skipped = [item for item in checks if item.get("skipped")]
        self.assertEqual({item["operation"] for item in skipped}, {"ShowVpc", "ShowSubnet", "ShowSecurityGroup"})
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
