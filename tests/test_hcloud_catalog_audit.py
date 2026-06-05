"""Tests for generated catalog audit summaries."""

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


hcloud_catalog_audit = load_module("hcloud_catalog_audit", SCRIPTS / "hcloud_catalog_audit.py")


class HcloudCatalogAuditTest(unittest.TestCase):
    """Validate catalog audit counts used as documentation facts."""

    def write_json(self, path: Path, payload: object) -> None:
        """Write JSON test data."""
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_audit_reports_registry_and_metadata_backed_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog_path = root / "catalog.json"
            registry_path = root / "registry.json"
            self.write_json(
                catalog_path,
                {
                    "source": {"service_count": 2, "operation_count": 4},
                    "services": {
                        "ecs": {
                            "name": "ECS",
                            "template_dir": "ecs",
                            "operation_count": 3,
                            "operations": {
                                "ListServersDetails": {"name": "ListServersDetails"},
                                "ShowServer": {"name": "ShowServer"},
                                "CreateServers": {"name": "CreateServers"},
                            },
                        },
                        "waf": {
                            "name": "WAF",
                            "template_dir": "waf",
                            "category": "Security & Compliance",
                            "operation_count": 1,
                            "operations": {"ListHost": {"name": "ListHost"}},
                        },
                    },
                },
            )
            self.write_json(
                registry_path,
                {
                    "services": {
                        "ECS": {
                            "query_operations": ["ListServersDetails"],
                            "resource_query_operations": ["ShowServer"],
                            "change_operations": ["CreateServers"],
                        },
                        "OBS": {
                            "query_operations": [],
                            "resource_query_operations": [],
                            "change_operations": [],
                        },
                    }
                },
            )

            result = hcloud_catalog_audit.audit(catalog_path, registry_path)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["catalog"]["service_count"], 2)
        self.assertEqual(result["registry"]["service_count"], 2)
        self.assertEqual(result["registry"]["query_operation_count"], 1)
        self.assertEqual(result["registry"]["resource_query_operation_count"], 1)
        self.assertEqual(result["registry"]["change_operation_count"], 1)
        self.assertEqual(result["registry"]["registered_operation_count"], 3)
        self.assertEqual(result["metadata_backed"]["service_count"], 1)
        self.assertEqual(result["metadata_backed"]["services"][0]["name"], "WAF")
        self.assertEqual(result["metadata_backed_service_count"], 1)


if __name__ == "__main__":
    unittest.main()
