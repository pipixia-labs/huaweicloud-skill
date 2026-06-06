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
