"""Tests for generic local KooCLI request preflight validation."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "hcloud_request_preflight",
    SCRIPTS / "hcloud_request_preflight.py",
)
assert SPEC and SPEC.loader
hcloud_request_preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_request_preflight)


def operation_detail(required_body_field: str) -> dict[str, object]:
    """Return complete catalog metadata for one fake operation version."""

    return {
        "detail_cached": True,
        "detail_file": "fixture.yaml",
        "parameter_metadata_complete": True,
        "method": "POST",
        "path": "/v1/{project_id}/things",
        "has_body_params": True,
        "params": [
            {
                "name": "project_id",
                "required": True,
                "position": "path",
                "type": "string",
            },
            {
                "name": required_body_field,
                "required": True,
                "position": "body",
                "type": "object",
            },
            {
                "name": "note",
                "required": False,
                "position": "body",
                "type": "string",
            },
        ],
        "required_params": [required_body_field],
        "optional_params": ["note"],
    }


def catalog_fixture(*, multi_version: bool = False) -> dict[str, object]:
    """Return a compact generated-catalog fixture."""

    if multi_version:
        operation = {
            "name": "CreateThing",
            "versions": ["v2", "v3"],
            "selected_version": "v3",
            "read_only": False,
            "version_details": {
                "v2": operation_detail("legacy"),
                "v3": operation_detail("current"),
            },
        }
    else:
        operation = {
            "name": "CreateThing",
            "versions": ["v2"],
            "selected_version": "v2",
            "read_only": False,
            **operation_detail("resource"),
        }
    return {
        "schema_version": 2,
        "services": {
            "test": {
                "name": "TEST",
                "service_key": "test",
                "operations": {"CreateThing": operation},
            }
        },
    }


def model_field(
    name: str,
    type_name: str,
    *,
    required: bool = False,
    schema: dict[str, object] | None = None,
) -> dict[str, object]:
    """Return one SDK-style serialized model field."""

    field: dict[str, object] = {
        "name": name,
        "serialized_name": name,
        "type": type_name,
        "required": required,
        "sensitive": False,
    }
    if schema is not None:
        field["schema"] = schema
    return field


def model_schema(name: str, fields: list[dict[str, object]]) -> dict[str, object]:
    """Return one bounded SDK model schema."""

    return {
        "type": "model",
        "model": name,
        "fields": fields,
        "max_depth": 3,
    }


def sdk_result_for_body_field(field_name: str, *, version: str = "v2") -> dict[str, object]:
    """Return SDK request evidence with representative nested EIP fields."""

    eip = model_schema(
        "Eip",
        [
            model_field("iptype", "str", required=True),
            model_field("bandwidth_size", "int", required=True),
        ],
    )
    publicip = model_schema(
        "PublicIp",
        [model_field("eip", "Eip", required=True, schema=eip)],
    )
    resource = model_schema(
        "Resource",
        [
            model_field("name", "str", required=True),
            model_field("publicip", "PublicIp", schema=publicip),
        ],
    )
    body = model_schema(
        "CreateThingRequestBody",
        [model_field(field_name, "Resource", required=True, schema=resource)],
    )
    request = model_schema(
        "CreateThingRequest",
        [model_field("body", "CreateThingRequestBody", schema=body)],
    )
    return {
        "success": True,
        "packages": [
            {
                "package": "huaweicloudsdktest",
                "versions": [
                    {
                        "version": version,
                        "operation": {
                            "name": "CreateThing",
                            "request_params": [
                                {
                                    "name": "body",
                                    "serialized_name": "body",
                                    "position": "body",
                                }
                            ],
                            "request_schema": request,
                        },
                    }
                ],
            }
        ],
    }


def error_codes(result: dict[str, object]) -> set[str]:
    """Return error codes from a preflight result."""

    return {str(item["code"]) for item in result["errors"]}  # type: ignore[index]


def warning_codes(result: dict[str, object]) -> set[str]:
    """Return warning codes from a preflight result."""

    return {str(item["code"]) for item in result["warnings"]}  # type: ignore[index]


class HcloudRequestPreflightTest(unittest.TestCase):
    """Validate conservative catalog and SDK request preflight behavior."""

    def test_rejects_invalid_koocli_json_envelope(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {"resource": {"name": "demo"}},
            catalog=catalog_fixture(),
            sdk_result=sdk_result_for_body_field("resource"),
        )

        self.assertFalse(result["success"])
        self.assertFalse(result["ready_for_dryrun"])
        self.assertIn("KOOCLI_JSON_LOCATION_INVALID", error_codes(result))

    def test_detects_nested_required_field_without_service_specific_rules(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {
                "path": {"project_id": "project-1"},
                "body": {
                    "resource": {
                        "name": "demo",
                        "publicip": {"eip": {"bandwidth_size": 5}},
                    }
                },
            },
            catalog=catalog_fixture(),
            sdk_result=sdk_result_for_body_field("resource"),
        )

        self.assertFalse(result["success"])
        self.assertIn("SDK_REQUIRED_FIELD_MISSING", error_codes(result))
        missing = next(item for item in result["errors"] if item["code"] == "SDK_REQUIRED_FIELD_MISSING")
        self.assertEqual(missing["path"], "body.resource.publicip.eip.iptype")

    def test_detects_nested_primitive_type_mismatch(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {
                "path": {"project_id": "project-1"},
                "body": {
                    "resource": {
                        "name": "demo",
                        "publicip": {
                            "eip": {"iptype": "5_bgp", "bandwidth_size": "5"}
                        },
                    }
                },
            },
            catalog=catalog_fixture(),
            sdk_result=sdk_result_for_body_field("resource"),
        )

        self.assertFalse(result["success"])
        self.assertIn("SDK_TYPE_MISMATCH", error_codes(result))

    def test_unknown_nested_sdk_field_warns_without_blocking_dryrun(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {
                "path": {"project_id": "project-1"},
                "body": {"resource": {"name": "demo", "future_field": True}},
            },
            catalog=catalog_fixture(),
            sdk_result=sdk_result_for_body_field("resource"),
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["ready_for_dryrun"])
        self.assertFalse(result["submit_authorization_granted"])
        self.assertNotIn("ready_for_submit", result)
        self.assertIn("SDK_UNKNOWN_FIELD", warning_codes(result))
        self.assertNotIn("request_contract", result["version_resolution"])

    def test_sdk_unavailable_is_partial_evidence_not_a_false_failure(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {
                "path": {"project_id": "project-1"},
                "body": {"resource": {"name": "demo"}},
            },
            catalog=catalog_fixture(),
            sdk_result={
                "success": False,
                "error": "SDK service package not found.",
                "install_hint": "pip install huaweicloudsdktest",
            },
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["validation_status"], "partial")
        self.assertIn("SDK_SCHEMA_UNAVAILABLE", warning_codes(result))

    def test_rejects_splitting_one_request_location_between_json_and_cli(self) -> None:
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing",
            {
                "path": {"project_id": "project-1"},
                "body": {"resource": {"name": "demo"}},
            },
            direct_arguments=["--note=from-cli"],
            catalog=catalog_fixture(),
            sdk_result=sdk_result_for_body_field("resource"),
        )

        self.assertFalse(result["success"])
        self.assertIn("KOOCLI_POSITION_SPLIT", error_codes(result))

    def test_explicit_version_uses_only_matching_sdk_schema(self) -> None:
        sdk_result = sdk_result_for_body_field("legacy", version="v2")
        sdk_result["packages"][0]["versions"].append(  # type: ignore[index]
            sdk_result_for_body_field("current", version="v3")["packages"][0]["versions"][0]  # type: ignore[index]
        )
        result = hcloud_request_preflight.preflight_request(
            "TEST",
            "CreateThing/v3",
            {
                "path": {"project_id": "project-1"},
                "body": {"current": {"name": "demo"}},
            },
            catalog=catalog_fixture(multi_version=True),
            sdk_result=sdk_result,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["version_resolution"]["selected_version"], "v3")
        self.assertEqual(result["sdk_schema"]["version"], "v3")

    def test_file_preflight_reports_invalid_json_without_cloud_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "request.json"
            path.write_text("{invalid", encoding="utf-8")
            result = hcloud_request_preflight.preflight_request_file(
                "TEST",
                "CreateThing",
                path,
                catalog=catalog_fixture(),
                sdk_result=sdk_result_for_body_field("resource"),
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["cloud_access"], "none")
        self.assertIn("KOOCLI_JSON_PARSE_FAILED", error_codes(result))


if __name__ == "__main__":
    unittest.main()
