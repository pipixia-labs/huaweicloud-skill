"""Tests for generated hcloud catalog diff reports."""

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


hcloud_catalog_diff = load_module("hcloud_catalog_diff", SCRIPTS / "hcloud_catalog_diff.py")


class HcloudCatalogDiffTest(unittest.TestCase):
    """Validate catalog and fingerprint diff behavior."""

    def write_json(self, path: Path, payload: object) -> None:
        """Write JSON test data."""
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_full_catalog_diff_reports_operations_and_required_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_path = root / "old.json"
            new_path = root / "new.json"
            self.write_json(
                old_path,
                {
                    "services": {
                        "rfs": {
                            "name": "RFS",
                            "operations": {
                                "ListPrivateHooks": {
                                    "name": "ListPrivateHooks",
                                    "params": [{"name": "limit", "required": False, "position": "query"}],
                                },
                                "ShowStack": {
                                    "name": "ShowStack",
                                    "params": [{"name": "stack_name", "required": True, "position": "path"}],
                                },
                            },
                        }
                    }
                },
            )
            self.write_json(
                new_path,
                {
                    "services": {
                        "rfs": {
                            "name": "RFS",
                            "operations": {
                                "ListPrivateHooks": {
                                    "name": "ListPrivateHooks",
                                    "params": [{"name": "limit", "required": False, "position": "query"}],
                                },
                                "ShowStack": {
                                    "name": "ShowStack",
                                    "params": [{"name": "stack_id", "required": True, "position": "path"}],
                                },
                                "ListStacks": {"name": "ListStacks", "params": []},
                            },
                        },
                        "ucs": {"name": "UCS", "operations": {"ListClusters": {"name": "ListClusters"}}},
                    }
                },
            )

            result = hcloud_catalog_diff.compare_documents(old_path, new_path)

        self.assertTrue(result["success"], result)
        self.assertTrue(result["has_changes"])
        self.assertEqual(result["summary"]["added_service_count"], 1)
        self.assertEqual(result["summary"]["added_operation_count"], 1)
        self.assertEqual(result["summary"]["required_param_change_count"], 1)
        self.assertEqual(result["added_services"][0]["name"], "UCS")
        rfs = result["changed_services"][0]
        self.assertEqual(rfs["name"], "RFS")
        self.assertEqual(rfs["added_operations"], ["ListStacks"])
        self.assertEqual(
            rfs["required_param_changes"],
            [
                {
                    "operation": "ShowStack",
                    "old_required_params": ["stack_name"],
                    "new_required_params": ["stack_id"],
                }
            ],
        )

    def test_fingerprint_diff_reports_hash_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_path = root / "old-fingerprint.json"
            new_path = root / "new-fingerprint.json"
            self.write_json(
                old_path,
                {
                    "catalog_hash": "old",
                    "services": {
                        "rfs": {
                            "name": "RFS",
                            "operation_count": 1,
                            "operations_hash": "aaa",
                            "required_params_hash": "bbb",
                        }
                    },
                },
            )
            self.write_json(
                new_path,
                {
                    "catalog_hash": "new",
                    "services": {
                        "rfs": {
                            "name": "RFS",
                            "operation_count": 2,
                            "operations_hash": "ccc",
                            "required_params_hash": "bbb",
                        }
                    },
                },
            )

            result = hcloud_catalog_diff.compare_documents(old_path, new_path)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["document_kind"], "fingerprint")
        self.assertEqual(result["summary"]["changed_service_count"], 1)
        self.assertEqual(result["changed_services"][0]["changes"]["operation_count"], {"old": 1, "new": 2})
        self.assertEqual(result["changed_services"][0]["changes"]["operations_hash"], {"old": "aaa", "new": "ccc"})


if __name__ == "__main__":
    unittest.main()
