"""Tests for bounded Huawei Cloud provider quote evidence."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, filename: str):  # noqa: ANN201
    """Load one repository script for isolated tests."""

    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hcloud_billing_result_summarize = load_module(
    "hcloud_billing_result_summarize_cost_test",
    "hcloud_billing_result_summarize.py",
)
hcloud_billing_live_read = load_module(
    "hcloud_billing_live_read_cost_test",
    "hcloud_billing_live_read.py",
)
hcloud_cost_estimate = load_module(
    "hcloud_cost_estimate",
    "hcloud_cost_estimate.py",
)
hcloud_change_plan = load_module(
    "hcloud_change_plan_cost_test",
    "hcloud_change_plan.py",
)
hcloud_ecs_create_plan = load_module(
    "hcloud_ecs_create_plan_cost_test",
    "hcloud_ecs_create_plan.py",
)


def cost_args(**overrides):  # noqa: ANN201
    """Return a complete namespace for the single-change cost helper."""

    values = {
        "service": "ECS",
        "region": "cn-north-4",
        "project_id": "project-1",
        "charge_mode": "on_demand",
        "pricing_preset": None,
        "resource_spec": ["s6.small.1"],
        "quantity": 2,
        "resource_size": [],
        "size_measure_id": [],
        "usage_value": [1.0],
        "available_zone": None,
        "period_type": [],
        "period_num": [],
        "fee_installment_mode": None,
        "execute": False,
        "confirm_live_billing_read": None,
        "timeout": 120,
        "max_output_chars": 20000,
        "output_file": None,
        "pretty": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class HcloudCostEstimateTest(unittest.TestCase):
    """Validate quote semantics without making cloud calls."""

    def test_on_demand_pricing_summary_is_non_paginated_and_bounded(self) -> None:
        result = hcloud_billing_result_summarize.build_pricing_summary(
            {
                "service": "BSS",
                "operation": "ListOnDemandResourceRatings",
                "parsed_json": {
                    "amount": "8.80",
                    "discount_amount": "1.20",
                    "official_website_amount": "10.00",
                    "measure_id": 1,
                    "currency": "",
                    "product_rating_results": [
                        {"id": "private-product-id", "amount": "8.80"}
                    ],
                },
            },
            request_spec={"body": {"project_id": "private-project"}},
            observed_at="2026-08-18T10:00:00Z",
        )

        self.assertTrue(result["success"], result)
        quote = result["pricing_quote"]
        self.assertEqual(quote["quoted_amount"], "8.80")
        self.assertEqual(quote["official_website_amount"], "10.00")
        self.assertEqual(quote["currency"], "CNY")
        self.assertTrue(quote["currency_defaulted_to_cny"])
        self.assertEqual(quote["component_count"], 1)
        self.assertEqual(result["pagination"]["mode"], "not_applicable")
        self.assertNotIn("private-product-id", json.dumps(result))
        self.assertNotIn("private-project", json.dumps(result))

    def test_period_pricing_does_not_select_an_optional_discount(self) -> None:
        result = hcloud_billing_result_summarize.build_pricing_summary(
            {
                "service": "BSS",
                "operation": "ListRateOnPeriodDetail",
                "parsed_json": {
                    "currency": "CNY",
                    "official_website_rating_result": {
                        "official_website_amount": "120.00",
                        "product_rating_results": [{"id": "product-1"}],
                    },
                    "optional_discount_rating_results": [
                        {"discount_amount": "20.00", "amount": "100.00"}
                    ],
                },
            },
            request_spec={},
            observed_at="2026-08-18T10:00:00Z",
        )

        quote = result["pricing_quote"]
        self.assertEqual(quote["quoted_amount"], "120.00")
        self.assertEqual(quote["discount_selection"], "not_selected")
        self.assertEqual(quote["optional_discount_alternative_count"], 1)
        self.assertNotIn("100.00", json.dumps(result))

    def test_cost_plan_reuses_bss_pricing_and_never_fabricates_amount(self) -> None:
        result = hcloud_cost_estimate.build_cost_estimate(cost_args())

        self.assertTrue(result["success"], result)
        self.assertEqual(result["mode"], "plan")
        estimate = result["cost_estimate"]
        self.assertEqual(estimate["status"], "unknown")
        self.assertIsNone(estimate["amount"])
        self.assertEqual(estimate["reason_code"], "PROVIDER_QUOTE_NOT_EXECUTED")
        self.assertEqual(estimate["scope"]["quantity"], 2)
        self.assertFalse(estimate["historical_billing_fact"])
        self.assertFalse(estimate["purchase_commitment"])
        self.assertEqual(
            result["pricing_read"]["billing_request_plan"]["title"],
            "ListOnDemandResourceRatings",
        )

    def test_pricing_live_read_executes_once_without_pagination(self) -> None:
        args = hcloud_cost_estimate.live_read_args(
            cost_args(
                execute=True,
                confirm_live_billing_read="READ_BILLING_DATA",
            ),
            "ecs",
        )
        execution_result = {
            "executed": True,
            "success": True,
            "summary": {
                "success": True,
                "pricing_quote": {"quoted_amount": "1.00"},
                "pagination": {"mode": "not_applicable", "complete": True},
            },
        }
        with (
            mock.patch.object(
                hcloud_billing_live_read,
                "run_safe_exec",
                return_value=execution_result,
            ) as run_once,
            mock.patch.object(
                hcloud_billing_live_read,
                "run_paginated_safe_exec",
            ) as run_paginated,
        ):
            result = hcloud_billing_live_read.build_live_read(args)

        self.assertTrue(result["success"], result)
        self.assertEqual(
            result["live_read_plan"]["pagination"]["mode"],
            "not_applicable",
        )
        run_once.assert_called_once()
        run_paginated.assert_not_called()

    def test_executed_cost_estimate_uses_provider_quote_fields(self) -> None:
        pricing_read = {
            "success": True,
            "execution": {
                "result": {
                    "summary": {
                        "pricing_quote": {
                            "quoted_amount": "8.80",
                            "official_website_amount": "10.00",
                            "discount_amount": "1.20",
                            "currency": "CNY",
                            "discount_selection": "provider_aggregate_result",
                            "optional_discount_alternative_count": 0,
                            "observed_at": "2026-08-18T10:00:00Z",
                        }
                    }
                }
            },
        }
        with mock.patch.object(
            hcloud_cost_estimate.hcloud_billing_live_read,
            "build_live_read",
            return_value=pricing_read,
        ):
            result = hcloud_cost_estimate.build_cost_estimate(
                cost_args(
                    execute=True,
                    confirm_live_billing_read="READ_BILLING_DATA",
                )
            )

        estimate = result["cost_estimate"]
        self.assertTrue(result["success"], result)
        self.assertEqual(estimate["status"], "quoted")
        self.assertEqual(estimate["amount"], "8.80")
        self.assertEqual(estimate["quote_time"], "2026-08-18T10:00:00Z")
        self.assertFalse(estimate["historical_billing_fact"])
        self.assertFalse(estimate["purchase_commitment"])

    def test_eip_requires_an_explicit_product_component(self) -> None:
        result = hcloud_cost_estimate.build_cost_estimate(
            cost_args(service="EIP", resource_spec=["5_bgp"])
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "AMBIGUOUS_PRICING_PRESET")
        self.assertIn("eip-bw", result["allowed_pricing_presets"])
        self.assertIsNone(result["cost_estimate"]["amount"])

    def test_generic_change_plan_contains_explicit_unknown_cost_scope(self) -> None:
        result = hcloud_change_plan.build_plan(
            SimpleNamespace(
                service="VPC",
                operation="CreateVpc",
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                json_input_file=None,
                arg=["--name=test-vpc", "--cidr=192.168.0.0/16"],
                no_dryrun=True,
                allow_public_web=False,
                metadata_category=None,
            )
        )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["cost_estimate"]["status"], "unknown")
        self.assertIsNone(result["cost_estimate"]["amount"])
        self.assertEqual(result["cost_estimate"]["scope"]["service"], "VPC")

    def test_postpaid_ecs_create_plan_derives_a_compute_only_quote_plan(self) -> None:
        payload = {
            "path": {"project_id": "project-1"},
            "body": {
                "server": {
                    "name": "cost-test",
                    "availability_zone": "cn-north-4a",
                    "flavorRef": "s6.small.1",
                    "imageRef": "image-1",
                    "vpcid": "vpc-1",
                    "nics": [{"subnet_id": "subnet-1"}],
                    "root_volume": {"volumetype": "SAS"},
                    "count": 2,
                    "key_name": "key-1",
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            request_file = Path(tmp_dir) / "ecs.json"
            request_file.write_text(json.dumps(payload), encoding="utf-8")
            result = hcloud_ecs_create_plan.build_result(
                SimpleNamespace(
                    json_input_file=str(request_file),
                    operation="CreatePostPaidServers",
                    region="cn-north-4",
                    profile=None,
                    mode="dryrun",
                    confirm_submit=False,
                    allow_placeholders=False,
                    max_count=10,
                    allow_large_count=False,
                    allow_public_web=False,
                    journal=None,
                    security_group_evidence_file=None,
                )
            )

        self.assertTrue(result["success"], result)
        estimate = result["cost_estimate"]
        self.assertEqual(estimate["status"], "unknown")
        self.assertEqual(estimate["reason_code"], "PROVIDER_QUOTE_NOT_EXECUTED")
        self.assertEqual(estimate["scope"]["quantity"], 2)
        self.assertEqual(estimate["scope"]["resource_spec"], ["s6.small.1"])
        self.assertIn("ECS compute", estimate["scope"]["components_included"])
        self.assertIn("EVS root volume", estimate["scope"]["components_excluded"])

    def test_period_ecs_create_plan_requires_explicit_period(self) -> None:
        payload = {
            "path": {"project_id": "project-1"},
            "body": {
                "server": {
                    "availability_zone": "cn-north-4a",
                    "flavorRef": "s6.small.1",
                    "count": 1,
                }
            },
        }

        result = hcloud_ecs_create_plan.build_ecs_cost_estimate(
            payload,
            SimpleNamespace(operation="CreateServers", region="cn-north-4"),
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(
            result["reason_code"],
            "PERIOD_PRICING_SCOPE_INCOMPLETE",
        )
        self.assertIsNone(result["amount"])

    def test_period_ecs_create_plan_uses_explicit_period(self) -> None:
        payload = {
            "path": {"project_id": "project-1"},
            "body": {
                "server": {
                    "availability_zone": "cn-north-4a",
                    "flavorRef": "s6.small.1",
                    "count": 1,
                    "extendparam": {
                        "periodType": "month",
                        "periodNum": 1,
                    },
                }
            },
        }

        result = hcloud_ecs_create_plan.build_ecs_cost_estimate(
            payload,
            SimpleNamespace(operation="CreateServers", region="cn-north-4"),
        )

        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason_code"], "PROVIDER_QUOTE_NOT_EXECUTED")
        self.assertEqual(result["scope"]["charge_mode"], "period")
        self.assertEqual(result["scope"]["period_type"], ["month"])
        self.assertEqual(result["scope"]["period_num"], [1])


if __name__ == "__main__":
    unittest.main()
