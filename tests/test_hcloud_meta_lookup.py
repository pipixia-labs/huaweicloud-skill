"""Tests for local hcloud metadata lookup helpers."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hcloud_meta_lookup.py"
SPEC = importlib.util.spec_from_file_location("hcloud_meta_lookup", SCRIPT)
assert SPEC and SPEC.loader
hcloud_meta_lookup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_meta_lookup)


class MetaLookupTest(unittest.TestCase):
    """Validate metadata parsing without depending on a real hcloud cache."""

    def test_load_operation_detail_reads_json_compatible_yaml_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            template_dir = Path(tmp_dir)
            detail_path = template_dir / "ListServersDetails_en.yaml"
            detail_path.write_text(
                json.dumps(
                    {
                        "Description": "List servers.",
                        "Request": {"Method": "GET", "Path": "/v1/{project_id}/cloudservers/detail"},
                        "Params": [{"Name": ["project_id"], "Required": True, "Position": "path", "ParamType": "string"}],
                    }
                ),
                encoding="utf-8",
            )

            detail = hcloud_meta_lookup.load_operation_detail(template_dir, "ListServersDetails")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["detail_file_format"], "json")
        self.assertEqual(detail["param_count"], 1)

    def test_load_operation_detail_reports_yaml_boundary_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            template_dir = Path(tmp_dir)
            detail_path = template_dir / "ListThings_en.yaml"
            detail_path.write_text("Description: List things\nParams:\n  - Name: [project_id]\n", encoding="utf-8")

            detail = hcloud_meta_lookup.load_operation_detail(template_dir, "ListThings")

        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertIn(detail["detail_file_format"], {"yaml", "yaml_unavailable"})
        if detail["detail_file_format"] == "yaml_unavailable":
            self.assertIn("PyYAML is not installed", detail["error"])

    def test_cached_operations_merge_cn_fallback_and_versioned_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            template_dir = Path(tmp_dir)
            (template_dir / "apis_en.json").write_text(
                json.dumps(
                    {
                        "apiList": {
                            "ListThings": {
                                "Name": "ListThings",
                                "Versions": ["v1"],
                                "Suggests": {"v1": "List things"},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            (template_dir / "apis_cn.json").write_text(
                json.dumps(
                    {
                        "apiList": {
                            "ListThings": {
                                "Name": "ListThings",
                                "Versions": ["v1"],
                                "Suggests": {"v1": "List things from CN"},
                            },
                            "ListCnOnly": {
                                "Name": "ListCnOnly",
                                "Versions": ["v5"],
                                "Suggests": {"v5": "List CN-only things"},
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            (template_dir / "ListCnOnly_v5_cn.yaml").write_text(
                json.dumps(
                    {
                        "Description": "List CN-only things.",
                        "Request": {"Method": "GET", "Path": "/v5/things"},
                        "Params": [{"Name": ["project_id"], "Required": True, "Position": "path"}],
                    }
                ),
                encoding="utf-8",
            )

            operations, operation_index = hcloud_meta_lookup.load_cached_operations(template_dir)
            detail = hcloud_meta_lookup.load_operation_detail(template_dir, "ListCnOnly")

        self.assertEqual([operation["name"] for operation in operations], ["ListCnOnly", "ListThings"])
        self.assertEqual(operation_index[hcloud_meta_lookup.normalize_token("ListThings")]["metadata_language"], "en")
        cn_only = operation_index[hcloud_meta_lookup.normalize_token("ListCnOnly")]
        self.assertEqual(cn_only["metadata_language"], "cn")
        self.assertTrue(cn_only["detail_cached"])
        self.assertEqual(cn_only["detail_language"], "cn")
        self.assertIsNotNone(detail)
        assert detail is not None
        self.assertEqual(detail["detail_file"], "ListCnOnly_v5_cn.yaml")
        self.assertEqual(detail["detail_language"], "cn")


if __name__ == "__main__":
    unittest.main()
