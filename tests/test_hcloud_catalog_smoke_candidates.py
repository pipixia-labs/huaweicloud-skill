"""Tests for metadata-backed live smoke candidate selection."""

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


hcloud_catalog_smoke_candidates = load_module(
    "hcloud_catalog_smoke_candidates",
    SCRIPTS / "hcloud_catalog_smoke_candidates.py",
)


class HcloudCatalogSmokeCandidatesTest(unittest.TestCase):
    """Validate candidate selection from catalog and question frequency."""

    def write_json(self, path: Path, payload: object) -> None:
        """Write JSON test data."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_question_frequency_is_optional_without_external_defaults(self) -> None:
        result = hcloud_catalog_smoke_candidates.collect_question_frequency(None)

        self.assertFalse(result["available"])
        self.assertIsNone(result["questions_dir"])
        self.assertEqual(result["files_checked"], 0)

    def test_select_candidates_prefers_frequent_metadata_backed_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog_path = root / "catalog.json"
            registry_path = root / "registry.json"
            confidence_path = root / "confidence.json"
            questions_dir = root / "questions"
            self.write_json(
                catalog_path,
                {
                    "source": {"service_count": 3, "operation_count": 5},
                    "services": {
                        "ecs": {
                            "name": "ECS",
                            "operations": {
                                "ListServersDetails": {
                                    "name": "ListServersDetails",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                }
                            },
                        },
                        "rfs": {
                            "name": "RFS",
                            "category": "Management & Governance",
                            "operation_count": 2,
                            "operations": {
                                "ListPrivateHooks": {
                                    "name": "ListPrivateHooks",
                                    "summary": "Listing private hooks",
                                    "action": "List",
                                    "read_only": True,
                                    "supports_limit": True,
                                    "params": [
                                        {"name": "limit", "required": False, "position": "query"},
                                        {
                                            "name": "Client-Request-Id",
                                            "required": True,
                                            "position": "header",
                                        },
                                    ],
                                },
                                "CreateStack": {
                                    "name": "CreateStack",
                                    "action": "Create",
                                    "read_only": False,
                                    "params": [],
                                },
                            },
                        },
                        "waf": {
                            "name": "WAF",
                            "category": "Security & Compliance",
                            "operation_count": 2,
                            "operations": {
                                "ListHost": {
                                    "name": "ListHost",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                                "ListPolicy": {
                                    "name": "ListPolicy",
                                    "action": "List",
                                    "read_only": True,
                                    "params": [],
                                },
                            },
                        },
                    },
                },
            )
            self.write_json(registry_path, {"services": {"ECS": {}}})
            self.write_json(
                confidence_path,
                {
                    "schema_version": 1,
                    "services": {
                        "WAF": {
                            "confidence": "catalog-derived",
                            "operations": {
                                "ListHost": {"confidence": "live-read-smoked"},
                            },
                        }
                    },
                },
            )
            self.write_json(
                questions_dir / "read_type" / "waf.json",
                [
                    {"question": "q1", "relevant_apis": ["WAF.ListHost"]},
                    {"question": "q2", "relevant_apis": ["WAF.ListPolicy"]},
                    {"question": "q3", "relevant_apis": ["RFS-ListPrivateHooks"]},
                    {"question": "q4", "relevant_apis": ["ECS.ListServersDetails"]},
                ],
            )

            result = hcloud_catalog_smoke_candidates.select_candidates(
                catalog_path=catalog_path,
                registry_path=registry_path,
                confidence_path=confidence_path,
                questions_dir=questions_dir,
                limit=2,
                operations_per_service=1,
                services=["RFS", "WAF", "ECS"],
            )

        self.assertTrue(result["success"], result)
        self.assertEqual([item["service"] for item in result["candidates"]], ["WAF", "RFS"])
        self.assertEqual(result["selection"]["service_filter"], ["RFS", "WAF", "ECS"])
        self.assertEqual(result["candidates"][0]["question_reference_count"], 2)
        self.assertEqual(result["candidates"][0]["suggested_operations"][0]["operation"], "ListPolicy")
        self.assertEqual(result["candidates"][1]["suggested_operations"][0]["required_headers"], ["Client-Request-Id"])
        self.assertNotIn("ECS", [item["service"] for item in result["candidates"]])


if __name__ == "__main__":
    unittest.main()
