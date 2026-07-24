"""Tests for SDK supplemental metadata and narrow read-only bridge."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_resource_discovery  # noqa: E402
import hcloud_resource_query  # noqa: E402
import hcloud_sdk_catalog  # noqa: E402
import hcloud_sdk_readonly  # noqa: E402
import hcloud_sdk_supplement_audit  # noqa: E402


class HcloudSdkSupplementTest(unittest.TestCase):
    """Validate SDK remains a small hcloud supplement."""

    def write_text(self, path: Path, content: str) -> None:
        """Write test source content."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def write_minimal_ecs_sdk(self, root: Path) -> None:
        """Create a tiny generated-SDK-like source tree."""
        package_root = root / "huaweicloud-sdk-ecs" / "huaweicloudsdkecs" / "v2"
        self.write_text(
            package_root / "ecs_client.py",
            '''
class EcsClient:
    @classmethod
    def new_builder(cls):
        raise NotImplementedError

    def list_flavors(self, request):
        http_info = self._list_flavors_http_info(request)
        return self._call_api(**http_info)

    @classmethod
    def _list_flavors_http_info(cls, request):
        http_info = {
            "method": "GET",
            "resource_path": "/v1/{project_id}/cloudservers/flavors",
            "request_type": request.__class__.__name__,
            "response_type": "ListFlavorsResponse"
            }
        query_params = []
        if 'availability_zone' in local_var_params:
            query_params.append(('availability_zone', local_var_params['availability_zone']))
        if 'limit' in local_var_params:
            query_params.append(('limit', local_var_params['limit']))
        header_params = {}
        header_params['Content-Type'] = "application/json"
        body = None
        return http_info
''',
        )
        self.write_text(
            package_root / "model" / "list_flavors_request.py",
            '''
class ListFlavorsRequest:
    sensitive_list = []
    openapi_types = {
        'availability_zone': 'str',
        'limit': 'int'
    }
    attribute_map = {
        'availability_zone': 'availability_zone',
        'limit': 'limit'
    }
''',
        )
        self.write_text(
            package_root / "region" / "ecs_region.py",
            '''
class EcsRegion:
    CN_NORTH_4 = Region("cn-north-4", "https://ecs.cn-north-4.myhuaweicloud.com")
''',
        )

    def write_minimal_vpc_sdk(self, root: Path) -> None:
        """Create a tiny VPC SDK source fixture for path-parameter tests."""
        package_root = root / "huaweicloud-sdk-vpc" / "huaweicloudsdkvpc" / "v2"
        self.write_text(
            package_root / "vpc_client.py",
            '''
class VpcClient:
    def show_vpc(self, request):
        http_info = self._show_vpc_http_info(request)
        return self._call_api(**http_info)

    @classmethod
    def _show_vpc_http_info(cls, request):
        http_info = {
            "method": "GET",
            "resource_path": "/v1/{project_id}/vpcs/{vpc_id}",
            "request_type": request.__class__.__name__,
            "response_type": "ShowVpcResponse"
        }
        query_params = []
        header_params = {}
        body = None
        return http_info
''',
        )
        self.write_text(
            package_root / "model" / "show_vpc_request.py",
            '''
class ShowVpcRequest:
    sensitive_list = []
    openapi_types = {
        'project_id': 'str',
        'vpc_id': 'str'
    }
    attribute_map = {
        'project_id': 'project_id',
        'vpc_id': 'vpc_id'
    }
''',
        )

    def without_installed_sdk_packages(self):
        """Temporarily hide installed SDK packages from catalog discovery."""
        original = hcloud_sdk_catalog.find_installed_service_packages
        hcloud_sdk_catalog.find_installed_service_packages = lambda service=None: []
        self.addCleanup(setattr, hcloud_sdk_catalog, "find_installed_service_packages", original)

    def use_source_fixture_as_installed(self, root: Path) -> None:
        """Expose a temporary SDK tree through the installed-package discovery seam."""
        original = hcloud_sdk_catalog.find_installed_service_packages
        hcloud_sdk_catalog.find_installed_service_packages = (
            lambda service=None: hcloud_sdk_catalog.find_service_packages(root, service)
        )
        self.addCleanup(
            setattr,
            hcloud_sdk_catalog,
            "find_installed_service_packages",
            original,
        )

    def test_sdk_catalog_parses_source_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.without_installed_sdk_packages()
            root = Path(tmp_dir)
            self.write_minimal_ecs_sdk(root)

            result = hcloud_sdk_catalog.inspect_sdk(root, service="ECS", operation="ListFlavors")

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        package = result["packages"][0]
        version = package["versions"][0]
        operation = version["operation"]
        self.assertEqual(package["source_kind"], "source_tree")
        self.assertEqual(operation["method"], "GET")
        self.assertTrue(operation["read_only"])
        self.assertEqual(operation["resource_path"], "/v1/{project_id}/cloudservers/flavors")
        self.assertEqual(operation["required_business_path_params"], [])
        self.assertEqual(operation["request_model"]["openapi_types"]["limit"], "int")
        limit_param = next(item for item in operation["request_params"] if item["name"] == "limit")
        self.assertEqual(limit_param["position"], "query")
        self.assertEqual(version["regions"][0]["id"], "cn-north-4")

    def test_sdk_catalog_default_does_not_discover_a_source_checkout(self) -> None:
        self.without_installed_sdk_packages()

        result = hcloud_sdk_catalog.inspect_sdk(
            service="ECS",
            operation="ListFlavors",
        )

        self.assertFalse(result["success"])
        self.assertIsNone(hcloud_sdk_catalog.DEFAULT_SDK_ROOT)
        self.assertIsNone(result["sdk_source_root"])
        self.assertFalse(result["sdk_source_root_exists"])
        self.assertEqual(result["package_discovery"], "installed_packages_only")

    def test_sdk_readonly_plan_is_allowlisted_and_supplemental(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.without_installed_sdk_packages()
            root = Path(tmp_dir)
            self.write_minimal_ecs_sdk(root)
            args = argparse.Namespace(
                sdk_root=root,
                service="ECS",
                operation="ListFlavors",
                param=["limit=5"],
                region="cn-north-4",
                endpoint=None,
                project_id=None,
                profile=None,
                execute=False,
                timeout=120,
            )

            result = hcloud_sdk_readonly.build_plan(args)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["primary_runtime"], "hcloud")
        self.assertEqual(result["role"], "supplemental_to_hcloud")
        self.assertEqual(result["sdk_metadata"]["source_kind"], "source_tree")
        self.assertEqual(result["registry_entry"]["hcloud_operation"], "ListFlavors")
        self.assertEqual(result["request_kwargs"], {"limit": 5})
        self.assertIn("hcloud_fallback_plan", result)
        self.assertFalse(result["mode"] == "execute")

    def test_sdk_supplement_registry_audit_passes_current_registry(self) -> None:
        result = hcloud_sdk_supplement_audit.audit_registry(require_metadata=False)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["operation_count"], 9)
        self.assertEqual(result["execute_allowed_count"], 8)
        self.assertEqual(result["error_count"], 0)

    def test_sdk_readonly_rejects_operation_not_in_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.without_installed_sdk_packages()
            root = Path(tmp_dir)
            self.write_minimal_ecs_sdk(root)
            args = argparse.Namespace(
                sdk_root=root,
                service="ECS",
                operation="DeleteServers",
                param=[],
                region="cn-north-4",
                endpoint=None,
                project_id=None,
                profile=None,
                execute=False,
                timeout=120,
            )

            result = hcloud_sdk_readonly.build_plan(args)

        self.assertFalse(result["success"])
        self.assertIn("not in sdk-supplement-registry", result["error"])

    def test_hcloud_resource_query_uses_sdk_type_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_ecs_sdk(root)
            self.use_source_fixture_as_installed(root)
            args = argparse.Namespace(
                service="ECS",
                operation="ListFlavors",
                param=["limit=not-an-int"],
                arg=[],
                region="cn-north-4",
                project_id=None,
                profile=None,
                execute=False,
                timeout=120,
                allow_sensitive_read=False,
            )

            result = hcloud_resource_query.build_plan(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "SDK supplement parameter validation failed.")
        self.assertEqual(result["sdk_param_validation"]["errors"][0]["param"], "limit")
        self.assertEqual(result["sdk_param_validation"]["errors"][0]["expected_type"], "int")
        self.assertEqual(result["sdk_supplement"]["sdk_operation"], "ListFlavors")

    def test_hcloud_resource_discovery_includes_sdk_supplement_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_ecs_sdk(root)
            self.use_source_fixture_as_installed(root)
            args = argparse.Namespace(
                service="ECS",
                operation="ListFlavors",
                region="cn-north-4",
                project_id=None,
                profile=None,
                limit=20,
                execute=False,
            )

            result = hcloud_resource_discovery.build_plan(args)

        self.assertTrue(result["success"], result)
        command_item = result["commands"][0]
        self.assertEqual(command_item["sdk_supplement"]["sdk_operation"], "ListFlavors")
        self.assertEqual(command_item["sdk_evidence"]["request_types"]["limit"], "int")

    def test_hcloud_resource_query_includes_vpc_sdk_path_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_minimal_vpc_sdk(root)
            self.use_source_fixture_as_installed(root)
            args = argparse.Namespace(
                service="VPC",
                operation="ShowVpc",
                param=["vpc_id=vpc-1"],
                arg=[],
                region="cn-north-4",
                project_id="project-1",
                profile=None,
                execute=False,
                timeout=120,
                allow_sensitive_read=False,
            )

            result = hcloud_resource_query.build_plan(args)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        self.assertEqual(result["sdk_supplement"]["sdk_operation"], "ShowVpc")
        self.assertEqual(result["sdk_evidence"]["required_business_path_params"], ["vpc_id"])
        self.assertEqual(result["sdk_evidence"]["request_types"]["vpc_id"], "str")


if __name__ == "__main__":
    unittest.main()
