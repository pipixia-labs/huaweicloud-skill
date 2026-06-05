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


if __name__ == "__main__":
    unittest.main()
