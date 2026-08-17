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

    def test_mutation_timeout_requires_readback_before_retry(self) -> None:
        """A timed-out mutation may have reached Huawei Cloud and cannot be replayed blindly."""

        semantics = hcloud_safe_exec.build_execution_semantics(
            {
                "success": False,
                "error_type": "TIMEOUT",
                "error_details": {"category": "network"},
            },
            {"read_only": False},
        )

        self.assertEqual(semantics["operation_kind"], "mutation")
        self.assertEqual(semantics["request_outcome"], "outcome_unknown")
        self.assertTrue(semantics["resource_verification_required"])
        self.assertEqual(semantics["retry_strategy"], "verify_before_retry")
        self.assertFalse(semantics["completion_claim_allowed"])

    def test_read_timeout_is_a_failed_retryable_read(self) -> None:
        """A read can be retried because it does not duplicate a cloud-side mutation."""

        semantics = hcloud_safe_exec.build_execution_semantics(
            {
                "success": False,
                "error_type": "TIMEOUT",
                "error_details": {"category": "network"},
            },
            {"read_only": True},
        )

        self.assertEqual(semantics["operation_kind"], "read")
        self.assertEqual(semantics["request_outcome"], "failed")
        self.assertFalse(semantics["resource_verification_required"])
        self.assertEqual(semantics["retry_strategy"], "retry_allowed")

    def test_provider_rejected_mutation_is_not_transport_ambiguity(self) -> None:
        """A structured API rejection is a known failed request, not an unknown outcome."""

        semantics = hcloud_safe_exec.build_execution_semantics(
            {
                "success": False,
                "error_type": "OPENAPI_ERROR",
                "error_details": {
                    "category": "parameter",
                    "cloud_error_code": "Ecs.0000",
                    "cloud_error_message": "invalid request",
                },
            },
            {"read_only": False},
        )

        self.assertEqual(semantics["request_outcome"], "failed")
        self.assertEqual(semantics["retry_strategy"], "correct_before_retry")
        self.assertTrue(semantics["resource_verification_required"])

    def test_successful_mutation_still_requires_resource_verification(self) -> None:
        """Request acceptance alone must not be presented as completed cloud state."""

        semantics = hcloud_safe_exec.build_execution_semantics(
            {"success": True, "error_type": None},
            {"read_only": False},
        )

        self.assertEqual(semantics["request_outcome"], "succeeded")
        self.assertTrue(semantics["resource_verification_required"])
        self.assertEqual(semantics["retry_strategy"], "not_needed")
        self.assertFalse(semantics["completion_claim_allowed"])

    def test_normalize_hcloud_args_adds_only_missing_long_option_prefixes(self) -> None:
        """Normalize direct CLI input without changing already valid option tokens."""

        normalized = hcloud_safe_exec.normalize_hcloud_args(
            ["server_id=server-1", "--limit=5", "-h"]
        )

        self.assertEqual(normalized, ["--server_id=server-1", "--limit=5", "-h"])

    def test_normalize_hcloud_args_rejects_empty_or_multiline_tokens(self) -> None:
        """Reject malformed tokens before they reach hcloud or output-policy logic."""

        for raw in ("", "   ", "server_id=one\n--limit=5", "name=value\rnext"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    hcloud_safe_exec.normalize_hcloud_args([raw])

    def test_cli_normalizes_bare_arg_and_preserves_prefixed_arg(self) -> None:
        """Fix direct --arg usage while preserving the established internal call format."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "ECS",
                    "--operation",
                    "ShowServer",
                    "--arg=server_id=server-1",
                    "--arg=--cli-region=cn-north-4",
                    "--skip-version-resolve",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            result["parsed_json"],
            ["ECS", "ShowServer", "--server_id=server-1", "--cli-region=cn-north-4"],
        )

    def test_cli_preserves_command_part_positionals_and_prefixed_options(self) -> None:
        """Keep generic hcloud subcommands and positional arguments unchanged."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--command-part=obs",
                    "--command-part=ls",
                    "--arg=obs://example-bucket",
                    "--arg=--limit=5",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(
            result["parsed_json"],
            ["obs", "ls", "obs://example-bucket", "--limit=5"],
        )

    def test_cli_rejects_empty_arg_before_hcloud_execution(self) -> None:
        """Fail malformed direct input before any cloud command can run."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            marker_path = tmp_path / "executed"
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "ECS",
                    "--operation",
                    "ShowServer",
                    "--arg=",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(marker_path.exists())
        self.assertIn("--arg values must not be empty", completed.stderr)

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

    def test_collect_json_input_param_names_supports_policy_preflight(self) -> None:
        args = SimpleNamespace(
            json_input_file=None,
            json_input_text=json.dumps(
                {
                    "log_group_id": "group-1",
                    "query": {
                        "start_time": 1,
                        "end_time": 2,
                    },
                }
            ),
        )

        names = hcloud_safe_exec.collect_json_input_param_names(args)

        self.assertTrue(
            {"log_group_id", "query", "start_time", "end_time"}.issubset(names)
        )

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
            result_path = tmp_path / "result.json"

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
                    f"--result-file={result_path}",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

            result = json.loads(completed.stdout)
            parsed_file = json.loads(parsed_path.read_text(encoding="utf-8"))
            full_result_file = json.loads(result_path.read_text(encoding="utf-8"))
            parsed_mode = stat.S_IMODE(parsed_path.stat().st_mode)
            result_mode = stat.S_IMODE(result_path.stat().st_mode)

        self.assertEqual(completed.returncode, 0)
        self.assertIsNone(result["parsed_json"])
        self.assertTrue(result["parsed_json_suppressed"])
        self.assertEqual(result["output_policy"]["selected_mode"], "summary")
        self.assertEqual(result["parsed_json_summary"]["json_type"], "dict")
        self.assertEqual(
            parsed_file,
            {"adminPass": "***", "note": "***", "server": {"OS-EXT-SRV-ATTR:user_data": "***"}},
        )
        self.assertEqual(full_result_file["parsed_json"], parsed_file)
        self.assertEqual(parsed_mode, 0o600)
        self.assertEqual(result_mode, 0o600)
        self.assertTrue(
            full_result_file["output_policy"]["full_payload_persisted"]
        )
        self.assertNotIn("password-value", completed.stdout)
        self.assertNotIn("token-value", completed.stdout)
        self.assertNotIn("encoded-user-data", completed.stdout)

    def test_output_policy_matches_exact_operation_and_family(self) -> None:
        exact = hcloud_safe_exec.hcloud_output_policy.resolve_output_policy(
            "ECS",
            "ListFlavors/v2",
            requested_mode="auto",
            provided_params=set(),
            allow_large_output=False,
        )
        family = hcloud_safe_exec.hcloud_output_policy.resolve_output_policy(
            "BSS",
            "ListCustomerBillsFeeRecords",
            requested_mode="auto",
            provided_params=set(),
            allow_large_output=False,
        )
        reviewed_full = hcloud_safe_exec.hcloud_output_policy.resolve_output_policy(
            "ECS",
            "ListFlavors",
            requested_mode="full",
            provided_params=set(),
            allow_large_output=True,
        )

        self.assertEqual(exact["effective_mode"], "summary")
        self.assertEqual(exact["default_limit"], {"param": "limit", "value": 20})
        self.assertEqual(exact["policy_source"], "operation")
        self.assertEqual(family["effective_mode"], "summary")
        self.assertEqual(family["policy_id"], "account-records")
        self.assertEqual(reviewed_full["effective_mode"], "full")
        self.assertFalse(reviewed_full["blocked"])

    def test_high_volume_command_applies_default_limit_and_emits_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps({'flavors': [{'id': str(i), 'name': f'c{i}'} for i in range(100)]}))\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "ECS",
                    "--operation",
                    "ListFlavors",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 0)
        self.assertIn("--limit=20", result["command"])
        self.assertIsNone(result["parsed_json"])
        self.assertEqual(result["parsed_json_summary"]["primary_array_count"], 100)
        self.assertEqual(result["parsed_json_summary"]["sample_count"], 3)
        self.assertNotIn('"id": "99"', completed.stdout)

    def test_generic_oversized_json_switches_to_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'items': [{'id': i, 'blob': 'x' * 1000} for i in range(20)]}))\n",
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

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["output_policy"]["selected_mode"], "summary")
        self.assertTrue(result["output_policy"]["artifact_required_for_full_payload"])
        self.assertIsNone(result["parsed_json"])
        self.assertEqual(result["parsed_json_summary"]["primary_array_count"], 20)
        self.assertLess(len(completed.stdout), 12000)

    def test_file_only_policy_generates_redacted_artifact(self) -> None:
        artifact_path: Path | None = None
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                hcloud_path = tmp_path / "hcloud"
                hcloud_path.write_text(
                    "#!/usr/bin/env python3\n"
                    "import json\n"
                    "print(json.dumps({'content': 'repository-content'}))\n",
                    encoding="utf-8",
                )
                hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--service",
                        "CodeArtsRepo",
                        "--operation",
                        "ShowFileContent",
                        "--expect-json",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
                )

            result = json.loads(completed.stdout)
            artifact_path = Path(result["artifacts"][0]["path"])
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(result["output_policy"]["selected_mode"], "file-only")
            self.assertIsNone(result["parsed_json"])
            self.assertEqual(result["parsed_json_summary"]["sample"], [])
            self.assertEqual(artifact, {"content": "repository-content"})
            self.assertNotIn("repository-content", completed.stdout)
        finally:
            if artifact_path and artifact_path.exists():
                artifact_path.unlink()

    def test_explicit_full_high_volume_output_requires_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            marker_path = tmp_path / "executed"
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "ECS",
                    "--operation",
                    "ListFlavors",
                    "--expect-json",
                    "--output-mode=full",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )
            executed = marker_path.exists()

        result = json.loads(completed.stdout)

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(executed)
        self.assertEqual(result["error_type"], "OUTPUT_POLICY_REQUIRED")
        self.assertIn("--output-mode=summary", result["corrected_command"])

    def test_missing_log_bounds_return_corrected_command_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            marker_path = tmp_path / "executed"
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--service",
                    "LTS",
                    "--operation",
                    "ListLogs",
                    "--arg=--log_group_id=group-1",
                    "--arg=--log_stream_id=stream-1",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )
            executed = marker_path.exists()

        result = json.loads(completed.stdout)

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(executed)
        self.assertEqual(result["error_type"], "OUTPUT_POLICY_REQUIRED")
        self.assertEqual(
            result["output_policy"]["missing_required"],
            ["start_time", "end_time"],
        )
        self.assertIn(
            "--arg=--start_time=<required:start_time>",
            result["corrected_command_template"],
        )

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

    def test_cli_supplies_user_and_home_defaults_to_hcloud_subprocess(self) -> None:
        """KooCLI receives shell defaults even when the sandbox omits them."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import os\n"
                "print(f\"USER={os.environ.get('USER', '')};HOME={os.environ.get('HOME', '')}\")\n",
                encoding="utf-8",
            )
            hcloud_path.chmod(hcloud_path.stat().st_mode | stat.S_IXUSR)
            sandbox_env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"USER", "HOME"}
            }
            sandbox_env["PATH"] = f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--command-part=obs",
                    "--command-part=ls",
                ],
                capture_output=True,
                text=True,
                check=False,
                env=sandbox_env,
            )

        result = json.loads(completed.stdout)

        self.assertEqual(completed.returncode, 0)
        self.assertTrue(result["success"])
        self.assertEqual(result["stdout"], "USER=hcloud;HOME=/tmp\n")

    def test_hcloud_subprocess_env_preserves_runtime_values(self) -> None:
        """A credential runtime's own home and user values are never replaced."""

        env = hcloud_safe_exec.build_hcloud_subprocess_env(
            {"USER": "sandbox-user", "HOME": "/tmp/runtime-home"}
        )

        self.assertEqual(env["USER"], "sandbox-user")
        self.assertEqual(env["HOME"], "/tmp/runtime-home")

    def test_cli_resolves_unversioned_operation_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "print(json.dumps(sys.argv[1:]))\n",
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
                    "ListSecurityGroups",
                    "--arg=--vpc_id=vpc-123",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v2")
        self.assertEqual(result["version_resolution"]["confidence"], "exact_parameter_match")
        self.assertEqual(
            result["parsed_json"],
            ["VPC", "ListSecurityGroups/v2", "--vpc_id=vpc-123"],
        )

    def test_cli_rejects_explicit_version_parameter_conflict_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            marker_path = tmp_path / "executed"
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                f"Path({str(marker_path)!r}).write_text('executed', encoding='utf-8')\n",
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
                    "ListSecurityGroups/v3",
                    "--arg=--vpc_id=vpc-123",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(marker_path.exists())
        self.assertEqual(result["error_type"], "VERSION_RESOLUTION_ERROR")
        self.assertEqual(result["corrected_operation"], "ListSecurityGroups/v2")
        self.assertEqual(result["corrected_command"][2], "ListSecurityGroups/v2")

    def test_read_only_usage_error_retries_one_alternate_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "operation = sys.argv[2]\n"
                "if operation.endswith('/v3'):\n"
                "    print('[USE_ERROR] unsupported operation version')\n"
                "    raise SystemExit(1)\n"
                "print(json.dumps({'operation': operation}))\n",
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
                    "ListSecurityGroups",
                    "--expect-json",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(result["success"])
        self.assertEqual(result["resolved_operation"], "ListSecurityGroups/v2")
        self.assertEqual(result["parsed_json"], {"operation": "ListSecurityGroups/v2"})
        self.assertEqual(len(result["attempts"]), 2)
        self.assertEqual(
            result["version_correction"]["reason"],
            "read_only_version_usage_error",
        )

    def test_mutation_usage_error_is_never_retried_with_another_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "print('[USE_ERROR] unsupported operation version')\n"
                "raise SystemExit(1)\n",
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
                    "CreateSecurityGroup",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(result["success"])
        self.assertEqual(result["resolved_operation"], "CreateSecurityGroup/v3")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertNotIn("version_correction", result)
        self.assertEqual(result["execution_semantics"]["request_outcome"], "failed")
        self.assertEqual(result["execution_semantics"]["retry_strategy"], "correct_before_retry")

    def test_cli_marks_timed_out_mutation_as_unknown_outcome(self) -> None:
        """The emitted CLI contract must preserve transport ambiguity for mutations."""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            hcloud_path = tmp_path / "hcloud"
            hcloud_path.write_text(
                "#!/usr/bin/env python3\n"
                "import time\n"
                "time.sleep(2)\n",
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
                    "CreateSecurityGroup",
                    "--timeout=1",
                ],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}"},
            )

        result = json.loads(completed.stdout)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(result["error_type"], "TIMEOUT")
        self.assertEqual(result["execution_semantics"]["operation_kind"], "mutation")
        self.assertEqual(result["execution_semantics"]["request_outcome"], "outcome_unknown")
        self.assertEqual(result["execution_semantics"]["retry_strategy"], "verify_before_retry")


if __name__ == "__main__":
    unittest.main()
