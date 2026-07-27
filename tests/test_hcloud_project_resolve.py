"""Tests for hcloud-first Huawei Cloud project ID resolution."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import hcloud_project_resolve  # noqa: E402


class HcloudProjectResolveTest(unittest.TestCase):
    """Validate deterministic local and IAM project resolution."""

    def test_explicit_project_id_precedes_environment_profile_and_remote(self) -> None:
        remote = mock.Mock()

        result = hcloud_project_resolve.resolve_project_id(
            region="cn-north-4",
            explicit_project_id="project-explicit",
            config_path=Path("/does/not/exist"),
            remote_lookup=remote,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["project_id"], "project-explicit")
        self.assertEqual(result["source"], "explicit")
        self.assertFalse(result["remote_lookup_performed"])
        remote.assert_not_called()

    def test_environment_project_id_precedes_profile_and_remote(self) -> None:
        remote = mock.Mock()
        with mock.patch.dict(
            os.environ,
            {"HUAWEICLOUD_PROJECT_ID": "project-env"},
            clear=True,
        ):
            result = hcloud_project_resolve.resolve_project_id(
                region="cn-north-4",
                config_path=Path("/does/not/exist"),
                remote_lookup=remote,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["project_id"], "project-env")
        self.assertEqual(result["source"], "environment")
        self.assertEqual(result["source_name"], "HUAWEICLOUD_PROJECT_ID")
        remote.assert_not_called()

    def test_matching_profile_cache_precedes_remote_lookup(self) -> None:
        remote = mock.Mock()
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "current": "default",
                        "profiles": [
                            {
                                "name": "default",
                                "region": "cn-north-4",
                                "projectId": "project-cache",
                                "accessKeyId": "must-not-be-returned",
                                "secretAccessKey": "must-not-be-returned",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                result = hcloud_project_resolve.resolve_project_id(
                    region="cn-north-4",
                    config_path=config_path,
                    remote_lookup=remote,
                )

        payload = json.dumps(result, ensure_ascii=False)
        self.assertTrue(result["success"])
        self.assertEqual(result["project_id"], "project-cache")
        self.assertEqual(result["source"], "hcloud_profile_cache")
        self.assertNotIn("must-not-be-returned", payload)
        remote.assert_not_called()

    def test_remote_iam_lookup_selects_unique_region_match(self) -> None:
        remote = mock.Mock(
            return_value={
                "success": True,
                "parsed_json": {
                    "projects": [
                        {"name": "cn-north-1", "id": "project-other"},
                        {"name": "cn-north-4", "id": "project-target"},
                    ]
                },
            }
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_project_resolve.resolve_project_id(
                region="cn-north-4",
                config_path=Path("/does/not/exist"),
                remote_lookup=remote,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["project_id"], "project-target")
        self.assertEqual(result["source"], "iam_keystone_list_projects")
        self.assertTrue(result["remote_lookup_performed"])
        remote.assert_called_once_with("cn-north-4")

    def test_remote_lookup_classifies_timeout_without_sdk_or_manual_signing(self) -> None:
        remote = mock.Mock(
            return_value={
                "success": False,
                "error_type": "NETWORK_ERROR",
                "stdout": "Connection timed out",
                "stderr": "",
            }
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_project_resolve.resolve_project_id(
                region="cn-north-4",
                config_path=Path("/does/not/exist"),
                remote_lookup=remote,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "IAM_NETWORK_TIMEOUT")
        self.assertTrue(result["retryable"])
        self.assertNotIn("sdk", json.dumps(result, ensure_ascii=False).lower())
        self.assertNotIn("signature", json.dumps(result, ensure_ascii=False).lower())

    def test_remote_lookup_rejects_ambiguous_region_matches(self) -> None:
        remote = mock.Mock(
            return_value={
                "success": True,
                "parsed_json": {
                    "projects": [
                        {"name": "cn-north-4", "id": "project-1"},
                        {"name": "cn-north-4", "id": "project-2"},
                    ]
                },
            }
        )

        with mock.patch.dict(os.environ, {}, clear=True):
            result = hcloud_project_resolve.resolve_project_id(
                region="cn-north-4",
                config_path=Path("/does/not/exist"),
                remote_lookup=remote,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "PROJECT_ID_AMBIGUOUS")
        self.assertFalse(result["retryable"])
        self.assertEqual(result["candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
