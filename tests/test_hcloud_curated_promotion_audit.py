"""Tests for curated registry promotion readiness audit."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, path: Path):
    """Load a script module from a path for local unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hcloud_curated_promotion_audit = load_module(
    "hcloud_curated_promotion_audit",
    SCRIPTS / "hcloud_curated_promotion_audit.py",
)


class HcloudCuratedPromotionAuditTest(unittest.TestCase):
    """Validate curated promotion readiness criteria."""

    def write_json(self, path: Path, payload: object) -> None:
        """Write JSON test data."""
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_dcs_rfs_ucs_are_promoted_as_read_only_curated_services(self) -> None:
        registry = json.loads((ROOT / "references" / "service-registry.json").read_text(encoding="utf-8"))
        profiles = json.loads((ROOT / "references" / "service-curation-profiles.json").read_text(encoding="utf-8"))

        for service in ("DCS", "RFS", "UCS"):
            with self.subTest(service=service):
                self.assertIn(service, registry["services"])
                entry = registry["services"][service]
                self.assertEqual(entry["coverage"], "medium")
                self.assertGreaterEqual(len(entry["query_operations"]), 2)
                self.assertGreaterEqual(len(entry["resource_query_operations"]), 3)
                self.assertEqual(entry["change_operations"], [])
                self.assertEqual(profiles["services"][service]["status"], "curated")

        result = hcloud_curated_promotion_audit.audit(
            services=["DCS", "RFS", "UCS"],
            min_live_ops=2,
            include_curated=True,
        )
        statuses = {item["service"]: item["status"] for item in result["candidates"]}
        self.assertEqual(statuses, {"DCS": "already_curated", "RFS": "already_curated", "UCS": "already_curated"})
        self.assertEqual(result["eligible_count"], 0)
        self.assertEqual(result["already_curated_count"], 3)
        self.assertEqual(result["curated_service_health"]["blocked_count"], 0)

    def test_audit_reports_eligible_blocked_and_curated_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog_path = root / "catalog.json"
            registry_path = root / "registry.json"
            confidence_path = root / "confidence.json"
            profiles_path = root / "profiles.json"
            self.write_json(
                catalog_path,
                {
                    "schema_version": 1,
                    "source": {"service_count": 3, "operation_count": 7},
                    "services": {
                        "dcs": {
                            "name": "DCS",
                            "category": "Middleware",
                            "operation_count": 3,
                            "operations": {
                                "ListInstances": {
                                    "name": "ListInstances",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ListAvailableZones": {
                                    "name": "ListAvailableZones",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ShowInstance": {
                                    "name": "ShowInstance",
                                    "action": "Show",
                                    "read_only": True,
                                    "params": [
                                        {"name": "instance_id", "required": True, "position": "path"},
                                    ],
                                },
                            },
                        },
                        "rfs": {
                            "name": "RFS",
                            "category": "Management & Governance",
                            "operation_count": 2,
                            "operations": {
                                "ListPrivateHooks": {
                                    "name": "ListPrivateHooks",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ShowStack": {
                                    "name": "ShowStack",
                                    "action": "Show",
                                    "read_only": True,
                                    "params": [
                                        {"name": "stack_name", "required": True, "position": "path"},
                                    ],
                                },
                            },
                        },
                        "ecs": {
                            "name": "ECS",
                            "category": "Compute",
                            "operation_count": 1,
                            "operations": {
                                "ListServersDetails": {
                                    "name": "ListServersDetails",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                }
                            },
                        },
                    },
                },
            )
            self.write_json(registry_path, {"services": {"ECS": {}}})
            self.write_json(profiles_path, {"schema_version": 1, "services": {}})
            self.write_json(
                confidence_path,
                {
                    "schema_version": 1,
                    "services": {
                        "DCS": {
                            "operations": {
                                "ListInstances": {"confidence": "live-read-smoked"},
                                "ListAvailableZones": {"confidence": "live-read-smoked"},
                            }
                        },
                        "RFS": {
                            "operations": {
                                "ListPrivateHooks": {"confidence": "live-read-smoked"},
                            }
                        },
                    },
                },
            )

            result = hcloud_curated_promotion_audit.audit(
                services=["DCS", "RFS", "ECS"],
                catalog_path=catalog_path,
                registry_path=registry_path,
                confidence_path=confidence_path,
                profiles_path=profiles_path,
                min_live_ops=2,
            )

        self.assertTrue(result["success"], result)
        self.assertEqual(result["eligible_count"], 0)
        by_service = {item["service"]: item for item in result["candidates"]}
        self.assertEqual(by_service["ECS"]["status"], "already_curated")
        self.assertEqual(by_service["RFS"]["status"], "blocked")
        self.assertIn("live_read_smoked_operations:1/2", by_service["RFS"]["missing"])
        self.assertEqual(by_service["DCS"]["status"], "blocked")
        self.assertNotIn("live_read_smoked_operations:2/2", by_service["DCS"]["missing"])
        self.assertIn("curation_profile", by_service["DCS"]["missing"])
        self.assertIn("用好云", by_service["DCS"]["value"]["tenant_goal_tags"])
        self.assertTrue(result["criteria"]["includes_value_ranking"])
        ranked_services = [item["service"] for item in result["value_ranked_candidates"]]
        self.assertIn("DCS", ranked_services)

    def test_candidate_is_eligible_when_profile_and_evidence_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog_path = root / "catalog.json"
            registry_path = root / "registry.json"
            confidence_path = root / "confidence.json"
            profiles_path = root / "profiles.json"
            self.write_json(
                catalog_path,
                {
                    "schema_version": 1,
                    "services": {
                        "dcs": {
                            "name": "DCS",
                            "category": "Middleware",
                            "operation_count": 3,
                            "operations": {
                                "ListInstances": {
                                    "name": "ListInstances",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ListAvailableZones": {
                                    "name": "ListAvailableZones",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ShowInstance": {
                                    "name": "ShowInstance",
                                    "action": "Show",
                                    "read_only": True,
                                    "params": [
                                        {"name": "instance_id", "required": True, "position": "path"},
                                    ],
                                },
                            },
                        },
                    },
                },
            )
            self.write_json(registry_path, {"services": {}})
            self.write_json(
                confidence_path,
                {
                    "schema_version": 1,
                    "services": {
                        "DCS": {
                            "operations": {
                                "ListInstances": {"confidence": "live-read-smoked"},
                                "ListAvailableZones": {"confidence": "live-read-smoked"},
                            }
                        },
                    },
                },
            )
            self.write_json(
                profiles_path,
                {
                    "schema_version": 1,
                    "services": {
                        "DCS": {
                            "status": "candidate",
                            "target_coverage": "medium",
                            "lifecycle_stage": "promotion_candidate",
                            "user_value": "Validate cache readiness before production traffic.",
                            "tenant_goal_tags": ["用好云"],
                            "scenario_tags": ["cache", "readiness"],
                            "readiness_operations": ["ListInstances"],
                            "resource_query_operations": ["ShowInstance"],
                            "playbooks": ["references/playbooks/dcs-readiness.md"],
                            "risk_profile": {
                                "mutation_policy": "planner_only_until_curated",
                                "default_risk": "medium",
                                "submit_policy": "no_submit_before_curated_promotion",
                                "verification_policy": "readback",
                            },
                        }
                    },
                },
            )

            result = hcloud_curated_promotion_audit.audit(
                services=["DCS"],
                catalog_path=catalog_path,
                registry_path=registry_path,
                confidence_path=confidence_path,
                profiles_path=profiles_path,
                min_live_ops=2,
            )

        self.assertEqual(result["eligible_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["status"], "eligible")
        self.assertEqual(candidate["missing"], [])
        self.assertEqual(candidate["profile"]["status"], "candidate")
        self.assertEqual(candidate["profile"]["lifecycle_stage"], "promotion_candidate")
        self.assertEqual(candidate["profile"]["user_value"], "Validate cache readiness before production traffic.")
        self.assertEqual(candidate["value"]["promotion_priority"], "high")
        self.assertIn("用好云", candidate["value"]["tenant_goal_tags"])
        self.assertIn("readiness", candidate["value"]["scenario_tags"])
        self.assertEqual(result["value_ranked_candidates"][0]["service"], "DCS")
        self.assertIn("cache", result["value_ranked_candidates"][0]["scenario_tags"])

    def test_include_curated_reports_registry_profile_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog_path = root / "catalog.json"
            registry_path = root / "registry.json"
            confidence_path = root / "confidence.json"
            profiles_path = root / "profiles.json"
            self.write_json(catalog_path, {"schema_version": 1, "services": {}})
            self.write_json(confidence_path, {"schema_version": 1, "services": {}})
            self.write_json(
                registry_path,
                {
                    "services": {
                        "ECS": {
                            "coverage": "high",
                            "query_operations": ["ListServersDetails"],
                            "resource_query_operations": ["ShowServer"],
                            "playbooks": ["references/playbooks/ecs-inventory.md"],
                        }
                    }
                },
            )
            self.write_json(
                profiles_path,
                {
                    "schema_version": 1,
                    "services": {
                        "ECS": {
                            "status": "curated",
                            "target_coverage": "high",
                            "readiness_operations": ["ListServersDetails"],
                            "resource_query_operations": ["ShowServer"],
                            "playbooks": ["references/playbooks/ecs-inventory.md"],
                            "risk_profile": {
                                "mutation_policy": "specialized_planner",
                                "default_risk": "high",
                                "submit_policy": "explicit_confirmation_only",
                                "verification_policy": "resource_readback",
                            },
                        }
                    },
                },
            )

            result = hcloud_curated_promotion_audit.audit(
                services=[],
                catalog_path=catalog_path,
                registry_path=registry_path,
                confidence_path=confidence_path,
                profiles_path=profiles_path,
                include_curated=True,
            )

        health = result["curated_service_health"]
        self.assertEqual(health["service_count"], 1)
        self.assertEqual(health["ok_count"], 1)
        self.assertEqual(health["blocked_count"], 0)
        self.assertEqual(health["findings"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
