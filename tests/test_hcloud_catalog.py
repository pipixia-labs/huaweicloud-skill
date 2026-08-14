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
                    "Params": [{"Name": ["limit"], "Required": False, "Position": "query", "Minimum": 10, "Maximum": 1000}],
                },
            )
            self.write_json(
                meta_repo / "template" / "ucs" / "ShowFleet_v1_en.yaml",
                {
                    "Description": "Show fleet.",
                    "Request": {"Method": "GET", "Path": "/v1/clustergroups/{clustergroupid}", "HasBodyParams": False},
                    "Params": [
                        {"Name": ["Client-Request-Id"], "Required": True, "Position": "header", "ParamType": "string"},
                        {"Name": ["clustergroupid"], "Required": True, "Position": "path", "ParamType": "string"},
                    ],
                },
            )
            self.write_json(
                meta_repo / "template" / "ucs" / "CreateClusterKubeconfig_v1_en.yaml",
                {
                    "Description": "Create kubeconfig.",
                    "Request": {"Method": "POST", "Path": "/v1/clusters/{clusterid}/kubeconfig", "HasBodyParams": True},
                    "Params": [
                        {"Name": ["project_id"], "Required": True, "Position": "path"},
                        {"Name": ["clusterid"], "Required": True, "Position": "path"},
                        {"Name": ["duration"], "Required": False, "Position": "query"},
                    ],
                },
            )
            apis = json.loads((meta_repo / "template" / "ucs" / "apis_en.json").read_text(encoding="utf-8"))
            apis["apiList"]["ShowFleet"] = {
                "Name": "ShowFleet",
                "Versions": ["v1"],
                "Suggests": {"v1": "Showing a fleet"},
            }
            self.write_json(meta_repo / "template" / "ucs" / "apis_en.json", apis)

            catalog = build_hcloud_catalog.build_catalog(meta_repo)
            fingerprint = build_hcloud_catalog.build_fingerprint(catalog)

        self.assertEqual(catalog["source"]["service_count"], 1)
        self.assertEqual(catalog["source"]["operation_count"], 3)
        service = hcloud_catalog.resolve_service(catalog, "ucs")
        self.assertIsNotNone(service)
        list_operation = hcloud_catalog.resolve_operation(service, "listclustergroup")
        create_operation = hcloud_catalog.resolve_operation(service, "CreateClusterKubeconfig")
        show_operation = hcloud_catalog.resolve_operation(service, "ShowFleet")
        self.assertTrue(hcloud_catalog.is_discovery_operation(list_operation))
        self.assertTrue(hcloud_catalog.supports_limit(list_operation))
        limit_param = hcloud_catalog.parameter_by_name(list_operation, "limit")
        self.assertEqual(limit_param["minimum"], 10)
        self.assertEqual(limit_param["maximum"], 1000)
        self.assertEqual(
            hcloud_catalog.bounded_limit_value(list_operation, 5)[1],
            {"param": "limit", "requested": 5, "used": 10, "minimum": 10, "maximum": 1000, "reason": "metadata_minimum"},
        )
        self.assertFalse(hcloud_catalog.is_read_only(create_operation))
        self.assertEqual(hcloud_catalog.normalized_required_params(create_operation), ["clusterid"])
        self.assertEqual(hcloud_catalog.normalized_required_params(show_operation), ["clustergroupid"])
        self.assertEqual(hcloud_catalog.required_param_names(show_operation), ["clustergroupid"])
        self.assertEqual(hcloud_catalog.required_header_param_names(show_operation), ["Client-Request-Id"])
        self.assertNotIn("client_request_id", hcloud_catalog.normalized_required_params(show_operation))
        self.assertEqual(fingerprint["source"]["operation_count"], 3)
        self.assertIn("catalog_hash", fingerprint)

    def test_split_catalog_index_loads_service_operations_lazily(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            catalog = {
                "schema_version": 1,
                "source": {"service_count": 1, "operation_count": 1},
                "services": {
                    "ucs": {
                        "name": "UCS",
                        "service_key": "ucs",
                        "template_dir": "ucs",
                        "category": "Containers",
                        "operation_count": 1,
                        "operations": {
                            "ListClusterGroup": {
                                "name": "ListClusterGroup",
                                "action": "List",
                                "read_only": True,
                                "params": [],
                            }
                        },
                    }
                },
            }
            index_path = root / "hcloud-service-catalog.index.json"
            service_dir = root / "hcloud-service-catalog"
            index, service_payloads = build_hcloud_catalog.split_service_catalog(catalog, service_dir, index_path)
            index_path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
            for service_file, payload in service_payloads.items():
                service_file.parent.mkdir(parents=True, exist_ok=True)
                service_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            loaded_index = hcloud_catalog.load_catalog(index_path)

            self.assertTrue(loaded_index["split"])
            self.assertNotIn("operations", loaded_index["services"]["ucs"])
            service = hcloud_catalog.resolve_service(loaded_index, "UCS")
            self.assertIsNotNone(service)
            operation = hcloud_catalog.resolve_operation(service, "ListClusterGroup")
            self.assertIsNotNone(operation)
            self.assertTrue(hcloud_catalog.is_discovery_operation(operation))

    def test_build_catalog_marks_raw_origin_parameter_metadata_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            template_dir = Path(tmp_dir)
            self.write_json(
                template_dir / "ListCosts_origin_cn.yaml",
                {
                    "name": "ListCosts",
                    "paths": {"/v4/costs/query": {"post": {}}},
                },
            )

            operation = build_hcloud_catalog.build_operation(
                template_dir,
                {
                    "Name": "ListCosts",
                    "Versions": ["v2"],
                    "Suggests": {"v2": "查询成本数据"},
                },
                "cn",
            )

        self.assertIsNotNone(operation)
        self.assertEqual(operation["detail_file"], "ListCosts_origin_cn.yaml")
        self.assertFalse(operation["parameter_metadata_complete"])

    def test_build_catalog_preserves_version_specific_operation_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meta_repo = Path(tmp_dir)
            self.write_json(
                meta_repo / "services_en.json",
                {
                    "items": [
                        {
                            "Category": "Networking",
                            "IsGlobal": False,
                            "Service": {"Text": "VPC", "Description": "Virtual Private Cloud"},
                        }
                    ]
                },
            )
            self.write_json(
                meta_repo / "template" / "vpc" / "apis_en.json",
                {
                    "apiList": {
                        "listsecuritygroups": {
                            "Name": "ListSecurityGroups",
                            "Versions": ["v3", "v2"],
                            "Suggests": {
                                "v2": "Query security groups with the legacy API.",
                                "v3": "Query security groups with the current API.",
                            },
                        }
                    }
                },
            )
            self.write_json(
                meta_repo / "template" / "vpc" / "ListSecurityGroups_v2_en.yaml",
                {
                    "Description": "V2 security groups.",
                    "Request": {"Method": "GET", "Path": "/v1/{project_id}/security-groups"},
                    "Params": [
                        {"Name": ["project_id"], "Required": True, "Position": "path"},
                        {"Name": ["vpc_id"], "Required": False, "Position": "query"},
                    ],
                },
            )
            self.write_json(
                meta_repo / "template" / "vpc" / "ListSecurityGroups_v3_en.yaml",
                {
                    "Description": "V3 security groups.",
                    "Request": {"Method": "GET", "Path": "/v3/{project_id}/vpc/security-groups"},
                    "Params": [
                        {"Name": ["project_id"], "Required": True, "Position": "path"},
                        {"Name": ["name", "[N]"], "Required": False, "Position": "query"},
                    ],
                },
            )

            catalog = build_hcloud_catalog.build_catalog(meta_repo)

        self.assertEqual(catalog["schema_version"], 2)
        service = hcloud_catalog.resolve_service(catalog, "VPC")
        self.assertIsNotNone(service)
        operation = hcloud_catalog.resolve_operation(service, "ListSecurityGroups/v2")
        self.assertIsNotNone(operation)
        self.assertEqual(operation["selected_version"], "v3")
        self.assertEqual(operation["optional_params"], ["name"])
        self.assertEqual(operation["version_details"]["v2"]["optional_params"], ["vpc_id"])
        self.assertEqual(operation["version_details"]["v3"]["optional_params"], ["name"])
        self.assertEqual(
            hcloud_catalog.operation_version_detail(operation, "v2")["path"],
            "/v1/{project_id}/security-groups",
        )
        self.assertEqual(hcloud_catalog.operation_versions(operation), ["v3", "v2"])

    def test_confidence_sidecar_references_catalog_operations(self) -> None:
        catalog = hcloud_catalog.load_catalog(ROOT / "references" / "hcloud-service-catalog.index.json")
        confidence = hcloud_catalog.load_confidence(ROOT / "references" / "hcloud-service-confidence.json")

        for service_name, service_entry in confidence.get("services", {}).items():
            with self.subTest(service=service_name):
                service = hcloud_catalog.resolve_service(catalog, service_name)
                self.assertIsNotNone(service)
                self.assertIn(service_entry.get("confidence"), {"catalog-derived", "live-read-smoked", "curated"})
                for operation_name, operation_entry in service_entry.get("operations", {}).items():
                    operation = hcloud_catalog.resolve_operation(service, operation_name)
                    self.assertIsNotNone(operation, f"{service_name}:{operation_name} missing from catalog")
                    self.assertIn(operation_entry.get("confidence"), {"catalog-derived", "live-read-smoked", "curated"})

        self.assertEqual(
            hcloud_catalog.operation_unsupported_optional_args(confidence, "UCS", "ListManagedClusters"),
            {"limit"},
        )

    def test_build_catalog_merges_cn_operations_without_overwriting_en(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meta_repo = Path(tmp_dir)
            self.write_json(
                meta_repo / "services_en.json",
                {
                    "updateTime": 123,
                    "items": [
                        {
                            "Category": "Compute",
                            "IsGlobal": False,
                            "Service": {"Text": "ECS", "Description": "Elastic Cloud Server"},
                        }
                    ],
                },
            )
            self.write_json(
                meta_repo / "services_cn.json",
                {
                    "updateTime": 456,
                    "items": [
                        {
                            "Category": "计算",
                            "IsGlobal": False,
                            "Service": {"Text": "ECS", "Description": "Elastic Cloud Server CN"},
                        }
                    ],
                },
            )
            self.write_json(
                meta_repo / "template" / "ecs" / "apis_en.json",
                {
                    "apiList": {
                        "ListServers": {
                            "Name": "ListServers",
                            "Versions": ["v1"],
                            "Suggests": {"v1": "List servers"},
                        }
                    }
                },
            )
            self.write_json(
                meta_repo / "template" / "ecs" / "apis_cn.json",
                {
                    "apiList": {
                        "ListServers": {
                            "Name": "ListServers",
                            "Versions": ["v1"],
                            "Suggests": {"v1": "List servers from CN"},
                        },
                        "ListServerGroups": {
                            "Name": "ListServerGroups",
                            "Versions": ["v1"],
                            "Suggests": {"v1": "List server groups from CN"},
                        },
                    }
                },
            )
            self.write_json(
                meta_repo / "template" / "ecs" / "ListServers_v1_en.yaml",
                {"Description": "List servers.", "Request": {"Method": "GET", "Path": "/v1/servers"}},
            )
            self.write_json(
                meta_repo / "template" / "ecs" / "ListServerGroups_v1_cn.yaml",
                {"Description": "List server groups.", "Request": {"Method": "GET", "Path": "/v1/server-groups"}},
            )

            catalog = build_hcloud_catalog.build_catalog(meta_repo)

        self.assertEqual(catalog["source"]["service_count"], 1)
        self.assertEqual(catalog["source"]["operation_count"], 2)
        self.assertEqual(catalog["source"]["services_update_times"], {"en": 123, "cn": 456})
        service = hcloud_catalog.resolve_service(catalog, "ECS")
        self.assertIsNotNone(service)
        self.assertEqual(service["metadata_language"], "mixed")
        self.assertEqual(service["operation_language_counts"], {"cn": 1, "en": 1})
        list_servers = hcloud_catalog.resolve_operation(service, "ListServers")
        list_groups = hcloud_catalog.resolve_operation(service, "ListServerGroups")
        self.assertEqual(list_servers["summary"], "List servers")
        self.assertEqual(list_servers["metadata_language"], "en")
        self.assertEqual(list_servers["detail_language"], "en")
        self.assertEqual(list_groups["metadata_language"], "cn")
        self.assertEqual(list_groups["detail_language"], "cn")

    def test_build_catalog_uses_cn_service_metadata_when_en_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meta_repo = Path(tmp_dir)
            self.write_json(
                meta_repo / "services_cn.json",
                {
                    "updateTime": 456,
                    "items": [
                        {
                            "Category": "Security",
                            "IsGlobal": False,
                            "Service": {"Text": "HSS", "Description": "Host Security Service"},
                        }
                    ],
                },
            )
            self.write_json(
                meta_repo / "template" / "hss" / "apis_cn.json",
                {
                    "apiList": {
                        "ListHostRisks": {
                            "Name": "ListHostRisks",
                            "Versions": ["v5"],
                            "Suggests": {"v5": "List host risks"},
                        }
                    }
                },
            )
            self.write_json(
                meta_repo / "template" / "hss" / "ListHostRisks_v5_cn.yaml",
                {
                    "Description": "List host risks.",
                    "Request": {"Method": "GET", "Path": "/v5/{project_id}/host-risks", "HasBodyParams": False},
                    "Params": [
                        {"Name": ["project_id"], "Required": True, "Position": "path"},
                        {"Name": ["host_id"], "Required": False, "Position": "query"},
                    ],
                },
            )

            catalog = build_hcloud_catalog.build_catalog(meta_repo)

        self.assertEqual(catalog["source"]["service_count"], 1)
        self.assertEqual(catalog["source"]["operation_count"], 1)
        service = hcloud_catalog.resolve_service(catalog, "hss")
        self.assertIsNotNone(service)
        self.assertEqual(service["name"], "HSS")
        self.assertEqual(service["service_metadata_language"], "cn")
        self.assertEqual(service["metadata_language"], "cn")
        operation = hcloud_catalog.resolve_operation(service, "ListHostRisks")
        self.assertEqual(operation["metadata_language"], "cn")
        self.assertEqual(operation["detail_file"], "ListHostRisks_v5_cn.yaml")
        self.assertEqual(operation["optional_params"], ["host_id"])

    def test_build_catalog_excludes_hcs_metadata_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            meta_repo = Path(tmp_dir)
            self.write_json(
                meta_repo / "services_cn.json",
                {
                    "items": [
                        {
                            "Category": "HCS",
                            "IsGlobal": True,
                            "Service": {"Text": "HCSECS", "Description": "Private-cloud ECS"},
                        },
                        {
                            "Category": "人工智能",
                            "IsGlobal": False,
                            "Service": {"Text": "AgentArts", "Description": "Agent platform"},
                        },
                    ]
                },
            )
            self.write_json(
                meta_repo / "template" / "hcsecs" / "apis_cn.json",
                {"apiList": {"ListServers": {"Name": "ListServers", "Versions": ["v1"]}}},
            )
            self.write_json(
                meta_repo / "template" / "agentarts" / "apis_cn.json",
                {"apiList": {"ListCoreGateways": {"Name": "ListCoreGateways", "Versions": ["v1"]}}},
            )

            public_catalog = build_hcloud_catalog.build_catalog(meta_repo)
            all_metadata_catalog = build_hcloud_catalog.build_catalog(meta_repo, include_hcs=True)

        self.assertEqual(public_catalog["source"]["runtime_scope"], "public-cloud")
        self.assertEqual(public_catalog["source"]["excluded_categories"], ["HCS"])
        self.assertEqual(set(public_catalog["services"]), {"agentarts"})
        self.assertEqual(all_metadata_catalog["source"]["runtime_scope"], "all-metadata")
        self.assertEqual(set(all_metadata_catalog["services"]), {"agentarts", "hcsecs"})


if __name__ == "__main__":
    unittest.main()
