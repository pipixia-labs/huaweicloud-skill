"""Tests for generated hcloud catalog helpers."""

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
    spec.loader.exec_module(module)
    return module


build_hcloud_catalog = load_module("build_hcloud_catalog", SCRIPTS / "build_hcloud_catalog.py")
hcloud_catalog = load_module("hcloud_catalog", SCRIPTS / "hcloud_catalog.py")


class HcloudCatalogTest(unittest.TestCase):
    """Validate compact catalog generation and read helpers."""

    def write_json(self, path: Path, payload: object) -> None:
        """Write JSON test metadata."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def test_build_catalog_and_resolve_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meta_repo = Path(tmp_dir)
            self.write_json(
                meta_repo / "services_en.json",
                {
                    "updateTime": 123,
                    "items": [
                        {
                            "Category": "Containers",
                            "IsGlobal": False,
                            "Service": {"Text": "UCS", "Description": "Ubiquitous Cloud Native Service"},
                        }
                    ],
                },
            )
            self.write_json(
                meta_repo / "template" / "ucs" / "apis_en.json",
                {
                    "apiList": {
                        "ListClusterGroup": {
                            "Name": "ListClusterGroup",
                            "Versions": ["v1"],
                            "Suggests": {"v1": "Obtaining the Fleet List"},
                        },
                        "CreateClusterKubeconfig": {
                            "Name": "CreateClusterKubeconfig",
                            "Versions": ["v1"],
                            "Suggests": {"v1": "Creating cluster kubeconfig"},
                        },
                    }
                },
            )
            self.write_json(
                meta_repo / "template" / "ucs" / "ListClusterGroup_v1_en.yaml",
                {
                    "Description": "List fleets.",
                    "Request": {"Method": "GET", "Path": "/v1/clustergroups", "HasBodyParams": False},
                    "Params": [{"Name": ["limit"], "Required": False}],
                },
            )
            self.write_json(
                meta_repo / "template" / "ucs" / "CreateClusterKubeconfig_v1_en.yaml",
                {
                    "Description": "Create kubeconfig.",
                    "Request": {"Method": "POST", "Path": "/v1/clusters/{clusterid}/kubeconfig", "HasBodyParams": True},
                    "Params": [
                        {"Name": ["project_id"], "Required": True},
                        {"Name": ["clusterid"], "Required": True},
                        {"Name": ["duration"], "Required": False},
                    ],
                },
            )

            catalog = build_hcloud_catalog.build_catalog(meta_repo)

        self.assertEqual(catalog["source"]["service_count"], 1)
        self.assertEqual(catalog["source"]["operation_count"], 2)
        service = hcloud_catalog.resolve_service(catalog, "ucs")
        self.assertIsNotNone(service)
        list_operation = hcloud_catalog.resolve_operation(service, "listclustergroup")
        create_operation = hcloud_catalog.resolve_operation(service, "CreateClusterKubeconfig")
        self.assertTrue(hcloud_catalog.is_discovery_operation(list_operation))
        self.assertTrue(hcloud_catalog.supports_limit(list_operation))
        self.assertFalse(hcloud_catalog.is_read_only(create_operation))
        self.assertEqual(hcloud_catalog.normalized_required_params(create_operation), ["clusterid"])


if __name__ == "__main__":
    unittest.main()
