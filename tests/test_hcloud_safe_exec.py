"""Tests for hcloud safe execution redaction helpers."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SCRIPT = ROOT / "scripts" / "hcloud_safe_exec.py"
SPEC = importlib.util.spec_from_file_location("hcloud_safe_exec", SCRIPT)
assert SPEC and SPEC.loader
hcloud_safe_exec = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hcloud_safe_exec)


class SafeExecRedactionTest(unittest.TestCase):
    """Validate redaction without calling hcloud."""

    def test_collect_inline_secrets_handles_equals_and_two_token_forms(self) -> None:
        secrets = hcloud_safe_exec.collect_inline_secrets(
            [
                "--secret-key=secret-one",
                "--access-key",
                "secret-two",
                "-k=secret-three",
                "-t",
                "secret-four",
                "--name",
                "plain",
            ]
        )

        self.assertEqual(secrets, {"secret-one", "secret-two", "secret-three", "secret-four"})

    def test_redact_command_handles_two_token_secret_forms(self) -> None:
        command = ["hcloud", "configure", "set", "--secret-key", "secret-two", "--name", "plain"]

        redacted = hcloud_safe_exec.redact_command(command, {"secret-two"})

        self.assertEqual(redacted, ["hcloud", "configure", "set", "--secret-key", "***", "--name", "plain"])

    def test_redact_json_redacts_secret_keys_and_known_values(self) -> None:
        payload = {
            "accessToken": "token-value",
            "nested": {
                "note": "prefix secret-value suffix",
                "items": [{"adminPass": "password-value"}],
            },
        }

        redacted = hcloud_safe_exec.redact_json(payload, {"secret-value"})

        self.assertEqual(redacted["accessToken"], "***")
        self.assertEqual(redacted["nested"]["note"], "prefix *** suffix")
        self.assertEqual(redacted["nested"]["items"][0]["adminPass"], "***")

    def test_collect_json_input_secrets_reads_sensitive_fields_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "input.json"
            path.write_text(json.dumps({"body": {"server": {"adminPass": "password-value"}}}), encoding="utf-8")
            args = SimpleNamespace(json_input_file=str(path), json_input_text=None)

            secrets = hcloud_safe_exec.collect_json_input_secrets(args)

        self.assertEqual(secrets, {"password-value"})

    def test_collect_json_secrets_detects_sensitive_output_keys(self) -> None:
        payload = {
            "servers": [
                {
                    "OS-EXT-SRV-ATTR:user_data": "encoded-user-data",
                    "metadata": {"private_key": "key-value"},
                }
            ]
        }

        secrets = hcloud_safe_exec.collect_json_secrets(payload)

        self.assertEqual(secrets, {"encoded-user-data", "key-value"})

    def test_classify_common_error_extracts_cloud_error_from_json(self) -> None:
        parsed = {"error_code": "ECS.0123", "error_msg": "project_id does not exist in this region"}

        details = hcloud_safe_exec.classify_common_error("OPENAPI_ERROR", "", "", parsed)

        self.assertIsNotNone(details)
        self.assertEqual(details["category"], "region_or_endpoint")
        self.assertEqual(details["cloud_error_code"], "ECS.0123")
        self.assertEqual(details["cloud_error_message"], "project_id does not exist in this region")
        self.assertIn("region", details["advice"].lower())

    def test_classify_common_error_extracts_obs_style_text_error(self) -> None:
        stdout = (
            "List buckets failed, status [403], error code [InvalidAccessKeyId], "
            "error message [The OBS Access Key Id you provided does not exist.]"
        )

        details = hcloud_safe_exec.classify_common_error(None, stdout, "", None)

        self.assertIsNotNone(details)
        self.assertEqual(details["category"], "credential")
        self.assertEqual(details["cloud_error_code"], "InvalidAccessKeyId")
        self.assertIn("AK/SK", details["advice"])

    def test_cli_error_is_classified_as_local_cli_runtime(self) -> None:
        stderr = "[CLI_ERROR] KooCLI failed while processing command"

        error_type = hcloud_safe_exec.classify_error("", stderr)
        details = hcloud_safe_exec.classify_common_error(error_type, "", stderr, None)

        self.assertEqual(error_type, "CLI_ERROR")
        self.assertIsNotNone(details)
        self.assertEqual(details["category"], "cli_runtime")
        self.assertIn(".hcloud/logs", details["advice"])

    def test_permission_error_includes_iam_action_hint(self) -> None:
        parsed = {"error_code": "ECS.403", "error_msg": "AccessDenied: not authorized"}

        details = hcloud_safe_exec.classify_common_error(
            "OPENAPI_ERROR",
            "",
            "",
            parsed,
            service="ECS",
            operation="ListCloudServers",
        )

        self.assertIsNotNone(details)
        self.assertEqual(details["category"], "permission")
        self.assertEqual(details["permission_hint"]["service"], "ECS")
        self.assertEqual(details["permission_hint"]["match"], "operation")
        self.assertIn("ecs:cloudServers:list", details["permission_hint"]["required_actions"])

    def test_cli_redacts_parsed_json_and_parsed_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({"
                "'adminPass': 'password-value', "
                "'note': 'token-value', "
                "'server': {'OS-EXT-SRV-ATTR:user_data': 'encoded-user-data'}"
                "}))\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)
            input_path = tmp_path / "input.json"
            input_path.write_text(
                json.dumps({"adminPass": "password-value", "accessToken": "token-value"}),
                encoding="utf-8",
            )
            parsed_path = tmp_path / "parsed.json"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "ECS",
                    "--operation",
                    "ListServersDetails",
                    f"--json-input-file={input_path}",
                    "--expect-json",
                    f"--parsed-json-file={parsed_path}",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

            result = json.loads(completed.stdout)
            parsed_file = json.loads(parsed_path.read_text(encoding="utf-8"))

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            result["parsed_json"],
            {"adminPass": "***", "note": "***", "server": {"OS-EXT-SRV-ATTR:user_data": "***"}},
        )
        self.assertEqual(
            parsed_file,
            {"adminPass": "***", "note": "***", "server": {"OS-EXT-SRV-ATTR:user_data": "***"}},
        )
        self.assertNotIn("password-value", completed.stdout)
        self.assertNotIn("token-value", completed.stdout)
        self.assertNotIn("encoded-user-data", completed.stdout)

    def test_cli_emits_error_details_from_failed_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print('[OPENAPI_ERROR] request failed')\n"
                "print(json.dumps({'error_code': 'VPC.1001', 'error_msg': 'Invalid region cn-x'}))\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "VPC",
                    "--operation",
                    "ListVpcs",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "OPENAPI_ERROR")
        self.assertEqual(result["error_details"]["category"], "region_or_endpoint")
        self.assertIn("region", result["advice"].lower())

    def test_cli_emits_permission_hint_from_failed_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print('[OPENAPI_ERROR] request failed')\n"
                "print(json.dumps({'error_code': 'VPC.403', 'error_msg': 'AccessDenied: permission denied'}))\n"
                "sys.exit(1)\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "VPC",
                    "--operation",
                    "ListSecurityGroupRules",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

            result = json.loads(completed.stdout)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_details"]["category"], "permission")
        self.assertIn("permission_hint", result["error_details"])
        self.assertIn("vpc:securityGroupRules:list", result["error_details"]["permission_hint"]["required_actions"])


if __name__ == "__main__":
    unittest.main()
