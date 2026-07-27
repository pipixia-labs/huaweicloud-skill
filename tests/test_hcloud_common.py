"""Tests for shared Huawei Cloud skill script helpers."""

from __future__ import annotations

import contextlib
import importlib.util
import io
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
    """Load a script module for isolated unit tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hcloud_common = load_module("hcloud_common", SCRIPTS / "hcloud_common.py")
hcloud_safe_exec = load_module("hcloud_safe_exec", SCRIPTS / "hcloud_safe_exec.py")


class HcloudCommonTest(unittest.TestCase):
    """Validate shared helpers used by CLI scripts."""

    def test_emit_json_supports_pretty_and_compact_output(self) -> None:
        compact = io.StringIO()
        pretty = io.StringIO()

        with contextlib.redirect_stdout(compact):
            hcloud_common.emit_json({"success": True}, pretty=False)
        with contextlib.redirect_stdout(pretty):
            hcloud_common.emit_json({"success": True}, pretty=True)

        self.assertEqual(compact.getvalue().strip(), '{"success": true}')
        self.assertIn('\n  "success": true\n', pretty.getvalue())

    def test_load_registry_uses_supplied_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "registry.json"
            path.write_text(json.dumps({"services": {"ECS": {}}}), encoding="utf-8")

            registry = hcloud_common.load_registry(path)

        self.assertEqual(registry["services"], {"ECS": {}})

    def test_collect_known_secrets_handles_missing_or_invalid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.json"
            invalid = Path(tmp_dir) / "invalid.json"
            valid = Path(tmp_dir) / "valid.json"
            invalid.write_text("{not-json", encoding="utf-8")
            valid.write_text(
                json.dumps(
                    {
                        "profiles": [
                            {
                                "accessKeyId": "ak-value",
                                "secretAccessKey": "sk-value",
                                "securityToken": "token-value",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(hcloud_common.collect_known_secrets(missing), set())
            self.assertEqual(hcloud_common.collect_known_secrets(invalid), set())
            self.assertEqual(
                hcloud_common.collect_known_secrets(valid),
                {"ak-value", "sk-value", "token-value"},
            )

    def test_hcloud_safe_exec_reuses_common_redaction_functions(self) -> None:
        payload = {"adminPass": "password-value", "note": "prefix token-value"}
        command = ["hcloud", "configure", "set", "--secret-key", "secret-value"]

        self.assertIs(hcloud_safe_exec.redact_json, hcloud_common.redact_json)
        self.assertEqual(
            hcloud_common.redact_json(payload, {"token-value"}),
            {"adminPass": "***", "note": "prefix ***"},
        )
        self.assertEqual(
            hcloud_common.redact_command(command, {"secret-value"}),
            ["hcloud", "configure", "set", "--secret-key", "***"],
        )

    def test_safe_exec_command_prefix_uses_absolute_bundled_script(self) -> None:
        prefix = hcloud_common.safe_exec_command_prefix()

        self.assertEqual(prefix[0], sys.executable)
        self.assertTrue(Path(prefix[1]).is_absolute())
        self.assertEqual(Path(prefix[1]).name, "hcloud_safe_exec.py")

    def test_bundled_script_command_uses_current_runtime(self) -> None:
        prefix = hcloud_common.bundled_script_command("hcloud_ecs_verify_active.py")

        self.assertEqual(prefix[0], sys.executable)
        self.assertEqual(Path(prefix[1]), SCRIPTS / "hcloud_ecs_verify_active.py")

    def test_redaction_avoids_generic_token_and_short_numeric_values(self) -> None:
        payload = {
            "nextPageToken": "page-token-value",
            "accessToken": "credential-token-value",
            "note": "keep page-token-value but hide credential-token-value",
        }

        redacted = hcloud_common.redact_json(payload, {"credential-token-value", "12345678"})

        self.assertFalse(hcloud_common.looks_like_secret_arg("nextPageToken"))
        self.assertTrue(hcloud_common.looks_like_secret_arg("accessToken"))
        self.assertEqual(redacted["nextPageToken"], "page-token-value")
        self.assertEqual(redacted["accessToken"], "***")
        self.assertEqual(redacted["note"], "keep page-token-value but hide ***")
        self.assertEqual(hcloud_common.redact_text("order id 12345678", {"12345678"}), "order id 12345678")

    def test_credential_fields_are_masked_but_project_context_is_preserved(self) -> None:
        payload = {
            "ak": "access-secret-value",
            "sk": "secret-secret-value",
            "api_key": "api-secret-value",
            "Authorization": "Bearer bearer-secret-value",
            "client_secret": "client-secret-value",
            "project_id": "project-1",
            "domain_id": "domain-1",
            "region": "cn-north-4",
        }

        redacted = hcloud_common.redact_json(payload, set())

        self.assertEqual(redacted["ak"], hcloud_common.REDACTION_MARKER)
        self.assertEqual(redacted["sk"], hcloud_common.REDACTION_MARKER)
        self.assertEqual(redacted["api_key"], hcloud_common.REDACTION_MARKER)
        self.assertEqual(redacted["Authorization"], hcloud_common.REDACTION_MARKER)
        self.assertEqual(redacted["client_secret"], hcloud_common.REDACTION_MARKER)
        self.assertEqual(redacted["project_id"], "project-1")
        self.assertEqual(redacted["domain_id"], "domain-1")
        self.assertEqual(redacted["region"], "cn-north-4")

    def test_redaction_metadata_explains_all_asterisk_markers(self) -> None:
        metadata = hcloud_common.redaction_metadata()

        self.assertEqual(metadata["marker"], "***")
        self.assertEqual(metadata["masked_value_semantics"], "present_but_hidden")
        self.assertFalse(metadata["masked_value_means_missing"])
        self.assertTrue(hcloud_common.is_redaction_marker("***"))
        self.assertTrue(hcloud_common.is_redaction_marker("********"))
        self.assertFalse(hcloud_common.is_redaction_marker(""))
        self.assertFalse(hcloud_common.is_redaction_marker("project-1"))


if __name__ == "__main__":
    unittest.main()
