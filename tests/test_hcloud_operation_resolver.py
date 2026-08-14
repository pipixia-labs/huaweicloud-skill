"""Tests for deterministic hcloud operation API version resolution."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = SCRIPTS / "hcloud_operation_resolver.py"
SPEC = importlib.util.spec_from_file_location("hcloud_operation_resolver", SCRIPT)
assert SPEC and SPEC.loader
hcloud_operation_resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_operation_resolver)


def version_detail(*optional_params: str) -> dict[str, object]:
    """Return compact complete metadata for one fake API version."""

    return {
        "detail_cached": True,
        "detail_file": "fixture.json",
        "params": [],
        "required_params": [],
        "optional_params": list(optional_params),
    }


def catalog_fixture() -> dict[str, object]:
    """Return a catalog containing a representative V2/V3 operation."""

    return {
        "schema_version": 2,
        "services": {
            "vpc": {
                "name": "VPC",
                "service_key": "vpc",
                "template_dir": "vpc",
                "operations": {
                    "ListSecurityGroups": {
                        "name": "ListSecurityGroups",
                        "versions": ["v3", "v2"],
                        "selected_version": "v3",
                        "read_only": True,
                        "version_details": {
                            "v2": version_detail(
                                "enterprise_project_id",
                                "limit",
                                "marker",
                                "vpc_id",
                            ),
                            "v3": version_detail(
                                "description",
                                "enterprise_project_id",
                                "id",
                                "limit",
                                "marker",
                                "name",
                            ),
                        },
                    }
                },
            }
        },
    }


class HcloudOperationResolverTest(unittest.TestCase):
    """Validate parameter-aware version selection and correction output."""

    def test_vpc_id_selects_list_security_groups_v2(self) -> None:
        result = hcloud_operation_resolver.resolve_operation_version(
            "VPC",
            "ListSecurityGroups",
            {"vpc_id"},
            catalog=catalog_fixture(),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v2")
        self.assertEqual(result["confidence"], "exact_parameter_match")
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["candidates"][0]["unsupported_params"], ["vpc_id"])

    def test_unversioned_operation_uses_catalog_default_when_versions_match(self) -> None:
        result = hcloud_operation_resolver.resolve_operation_version(
            "VPC",
            "ListSecurityGroups",
            {"limit"},
            catalog=catalog_fixture(),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v3")
        self.assertEqual(result["confidence"], "catalog_default")

    def test_raw_origin_detail_does_not_reject_valid_nested_body_params(self) -> None:
        catalog = {
            "schema_version": 2,
            "services": {
                "bss": {
                    "name": "BSS",
                    "service_key": "bss",
                    "template_dir": "bss",
                    "operations": {
                        "ListCosts": {
                            "name": "ListCosts",
                            "versions": ["v2"],
                            "selected_version": "v2",
                            "read_only": True,
                            "detail_cached": True,
                            "detail_file": "ListCosts_origin_cn.yaml",
                            "params": [],
                            "required_params": [],
                            "optional_params": [],
                        }
                    },
                }
            },
        }

        result = hcloud_operation_resolver.resolve_operation_version(
            "BSS",
            "ListCosts",
            {
                "time_condition",
                "groupby",
                "cost_type",
                "amount_type",
                "offset",
                "limit",
            },
            catalog=catalog,
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["resolved_operation"], "ListCosts/v2")
        self.assertEqual(result["candidates"][0]["compatibility"], "unknown")
        self.assertFalse(result["candidates"][0]["parameter_metadata_complete"])
        self.assertEqual(result["candidates"][0]["unsupported_params"], [])

    def test_explicit_incompatible_version_returns_v2_correction(self) -> None:
        result = hcloud_operation_resolver.resolve_operation_version(
            "VPC",
            "ListSecurityGroups/v3",
            {"vpc_id"},
            catalog=catalog_fixture(),
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["confidence"], "explicit_parameter_conflict")
        self.assertEqual(result["corrected_operation"], "ListSecurityGroups/v2")
        self.assertTrue(result["retryable"])

    def test_explicit_compatible_version_is_preserved(self) -> None:
        result = hcloud_operation_resolver.resolve_operation_version(
            "VPC",
            "ListSecurityGroups/v2",
            {"vpc_id"},
            catalog=catalog_fixture(),
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v2")
        self.assertEqual(result["confidence"], "explicit_verified")

    def test_indexed_query_parameter_matches_its_metadata_root(self) -> None:
        params = hcloud_operation_resolver.provided_param_names_from_args(
            ["--name.1=example", "--cli-region=cn-north-4"]
        )
        result = hcloud_operation_resolver.resolve_operation_version(
            "VPC",
            "ListSecurityGroups",
            params,
            catalog=catalog_fixture(),
        )

        self.assertEqual(params, {"name"})
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v3")

    def test_parse_default_version_from_chinese_help(self) -> None:
        text = (
            "ListSecurityGroups有多个版本,默认使用该API版本v3."
            '若需指定其他版本,请将API名修改为"ListSecurityGroups/版本号"'
        )

        self.assertEqual(
            hcloud_operation_resolver.parse_default_version_from_help(text),
            "v3",
        )

    def test_cli_emits_a_direct_versioned_hcloud_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            catalog_path = Path(tmp_dir) / "catalog.json"
            catalog_path.write_text(
                json.dumps(catalog_fixture(), ensure_ascii=False),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "VPC",
                    "--operation",
                    "ListSecurityGroups",
                    "--param",
                    "vpc_id=vpc-123",
                    "--arg=--cli-region=cn-north-4",
                    f"--catalog-path={catalog_path}",
                    "--emit-command",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            completed.stdout.strip(),
            "hcloud VPC ListSecurityGroups/v2 --vpc_id=vpc-123 --cli-region=cn-north-4",
        )

    def test_cli_routes_high_volume_read_through_safe_exec(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--service",
                "ECS",
                "--operation",
                "ListFlavors",
                "--arg=--cli-region=cn-north-4",
                "--emit-command",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        command = completed.stdout.strip()

        self.assertEqual(completed.returncode, 0)
        self.assertIn("hcloud_safe_exec.py", command)
        self.assertIn("--service ECS", command)
        self.assertIn("--operation ListFlavors/", command)
        self.assertIn("--arg=--cli-output=json", command)
        self.assertIn("--output-mode=auto", command)
        self.assertIn("--expect-json", command)


if __name__ == "__main__":
    unittest.main()
