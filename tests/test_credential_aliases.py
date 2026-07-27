"""Tests for portable Huawei Cloud credential environment aliases."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import credential_aliases  # noqa: E402


class CredentialAliasesTest(unittest.TestCase):
    """Validate paired credential resolution without exposing secret values."""

    def test_every_supported_access_secret_family_resolves_as_one_pair(self) -> None:
        for family in credential_aliases.CLOUD_CREDENTIAL_FAMILIES:
            with (
                self.subTest(family=family.name),
                mock.patch.dict(
                    os.environ,
                    {
                        family.access_key: f"{family.name}-access-secret",
                        family.secret_key: f"{family.name}-secret-secret",
                        "HUAWEICLOUD_REGION": "cn-north-4",
                    },
                    clear=True,
                ),
            ):
                resolved = credential_aliases.resolve_cloud_credentials()
                redacted = credential_aliases.redact_credential_resolution(resolved)
                payload = json.dumps(redacted, ensure_ascii=False)

            self.assertEqual(resolved["family"], family.name)
            self.assertTrue(resolved["pair_complete"])
            self.assertTrue(resolved["complete"])
            self.assertEqual(redacted["sources"]["access_key"], family.access_key)
            self.assertEqual(redacted["sources"]["secret_key"], family.secret_key)
            self.assertNotIn(f"{family.name}-access-secret", payload)
            self.assertNotIn(f"{family.name}-secret-secret", payload)

    def test_resolution_never_combines_access_and_secret_from_different_families(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HW_ACCESS_KEY": "first-family-access",
                "HUAWEICLOUD_SECRET_ACCESS_KEY": "second-family-secret",
                "HUAWEICLOUD_REGION": "cn-north-4",
            },
            clear=True,
        ):
            resolved = credential_aliases.resolve_cloud_credentials()

        self.assertEqual(resolved["family"], "hw")
        self.assertEqual(resolved["access_key"], "first-family-access")
        self.assertIsNone(resolved["secret_key"])
        self.assertFalse(resolved["pair_complete"])
        self.assertFalse(resolved["complete"])

    def test_complete_family_wins_over_earlier_partial_family(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HW_ACCESS_KEY": "partial-access",
                "HUAWEICLOUD_SDK_AK": "sdk-access",
                "HUAWEICLOUD_SDK_SK": "sdk-secret",
                "HUAWEICLOUD_REGION": "cn-north-4",
            },
            clear=True,
        ):
            resolved = credential_aliases.resolve_cloud_credentials()

        self.assertEqual(resolved["family"], "huaweicloud_sdk")
        self.assertEqual(resolved["access_key"], "sdk-access")
        self.assertEqual(resolved["secret_key"], "sdk-secret")
        self.assertTrue(resolved["complete"])

    def test_project_context_and_maas_aliases_return_presence_not_secret_values(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "HUAWEICLOUD_PROJECT_ID": "project-1",
                "HUAWEICLOUD_DOMAIN_ID": "domain-1",
                "MODELARTS_MAAS_API_KEY": "maas-secret-value",
            },
            clear=True,
        ):
            project = credential_aliases.resolve_first_value(credential_aliases.PROJECT_ID_ENV_NAMES)
            maas = credential_aliases.resolve_maas_api_key()
            presence = credential_aliases.credential_environment_presence()

        self.assertEqual(project, ("project-1", "HUAWEICLOUD_PROJECT_ID"))
        self.assertEqual(maas, ("maas-secret-value", "MODELARTS_MAAS_API_KEY"))
        payload = json.dumps(presence, ensure_ascii=False)
        self.assertTrue(presence["HUAWEICLOUD_PROJECT_ID"]["set"])
        self.assertTrue(presence["MODELARTS_MAAS_API_KEY"]["set"])
        self.assertNotIn("project-1", payload)
        self.assertNotIn("domain-1", payload)
        self.assertNotIn("maas-secret-value", payload)


if __name__ == "__main__":
    unittest.main()
