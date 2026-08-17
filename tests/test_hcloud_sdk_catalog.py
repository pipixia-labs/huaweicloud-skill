"""Tests for bounded recursive Huawei Cloud SDK request-schema inspection."""

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
SPEC = importlib.util.spec_from_file_location("hcloud_sdk_catalog", SCRIPTS / "hcloud_sdk_catalog.py")
assert SPEC and SPEC.loader
hcloud_sdk_catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_sdk_catalog)


def write_model(model_dir: Path, filename: str, class_name: str, types: dict[str, str], required: set[str]) -> None:
    """Write a minimal generated-SDK-style model used by the schema parser."""

    params = ", ".join(f"{name}=None" for name in types)
    assignments = []
    for name in types:
        if name in required:
            assignments.append(f"        self.{name} = {name}")
        else:
            assignments.extend(
                [
                    f"        if {name} is not None:",
                    f"            self.{name} = {name}",
                ]
            )
    source = (
        f"class {class_name}:\n"
        f"    openapi_types = {types!r}\n"
        f"    attribute_map = {dict((name, name) for name in types)!r}\n"
        "    sensitive_list = []\n"
        f"    def __init__(self, {params}):\n"
        + "\n".join(assignments)
        + "\n"
    )
    (model_dir / filename).write_text(source, encoding="utf-8")


class HcloudSdkCatalogSchemaTest(unittest.TestCase):
    """Validate recursive schemas without importing or executing SDK model code."""

    def test_expand_model_schema_resolves_nested_lists_and_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            version_dir = Path(tmp_dir) / "v2"
            model_dir = version_dir / "model"
            model_dir.mkdir(parents=True)
            write_model(
                model_dir,
                "delete_servers_request.py",
                "DeleteServersRequest",
                {"body": "DeleteServersRequestBody"},
                {"body"},
            )
            write_model(
                model_dir,
                "delete_servers_request_body.py",
                "DeleteServersRequestBody",
                {
                    "servers": "list[ServerId]",
                    "server_groups": "dict(str, list[ServerId])",
                    "delete_volume": "bool",
                },
                {"servers"},
            )
            write_model(model_dir, "server_id.py", "ServerId", {"id": "str"}, {"id"})

            schema = hcloud_sdk_catalog.expand_model_schema(
                version_dir,
                "DeleteServersRequest",
                max_depth=3,
            )

        body = next(field for field in schema["fields"] if field["name"] == "body")
        servers = next(field for field in body["schema"]["fields"] if field["name"] == "servers")
        server_id = next(field for field in servers["schema"]["items"]["fields"] if field["name"] == "id")
        server_groups = next(field for field in body["schema"]["fields"] if field["name"] == "server_groups")
        self.assertTrue(body["required"])
        self.assertTrue(servers["required"])
        self.assertEqual(servers["schema"]["type"], "array")
        self.assertEqual(server_id["type"], "str")
        self.assertTrue(server_id["required"])
        self.assertEqual(server_groups["schema"]["type"], "object")
        self.assertEqual(server_groups["schema"]["key_type"], "str")
        self.assertEqual(server_groups["schema"]["additional_properties"]["type"], "array")

    def test_expand_model_schema_stops_at_requested_depth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            version_dir = Path(tmp_dir) / "v2"
            model_dir = version_dir / "model"
            model_dir.mkdir(parents=True)
            write_model(model_dir, "root.py", "Root", {"child": "Child"}, {"child"})
            write_model(model_dir, "child.py", "Child", {"value": "str"}, {"value"})

            schema = hcloud_sdk_catalog.expand_model_schema(version_dir, "Root", max_depth=0)

        child = schema["fields"][0]
        self.assertEqual(child["schema"], {"type": "model", "model": "Child", "truncated": True})


if __name__ == "__main__":
    unittest.main()
