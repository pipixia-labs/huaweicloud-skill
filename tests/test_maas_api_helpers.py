"""Tests for Huawei Cloud MaaS API helper scripts."""

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

import hcloud_environment_doctor  # noqa: E402
import hcloud_scenario_router  # noqa: E402
import maas_chat  # noqa: E402
import maas_common  # noqa: E402
import maas_image_generation  # noqa: E402
import maas_models  # noqa: E402
import maas_usage_request_plan  # noqa: E402
import maas_video_generation  # noqa: E402

REQUIRED_OFFICIAL_DOC_URLS = {
    "https://support.huaweicloud.com/maas/index.html",
    "https://support.huaweicloud.com/model-call-maas/usermanual_maas_0008.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-004.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-005.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-006.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-008.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-011.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-012.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-063.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-064.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-065.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-066.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-067.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-019.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-021.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-023.html",
    "https://support.huaweicloud.com/model-call-maas/model-call-017.html",
    "https://support.huaweicloud.com/api-maas/api-maas-0002.html",
}


def write_fake_png(path: Path, content: bytes = b"fake-image-bytes") -> Path:
    """Write bytes to a .png path for data URI helper tests."""
    path.write_bytes(content)
    return path


class MaasAPIHelpersTest(unittest.TestCase):
    """Validate MaaS helpers without making live MaaS calls."""

    def test_local_model_catalog_filters_core_capabilities(self) -> None:
        catalog = maas_models.load_catalog()

        text_models = maas_models.filter_models(catalog, capability="text")
        image_models = maas_models.filter_models(catalog, capability="image_generation")
        video_models = maas_models.filter_models(catalog, capability="video_generation")

        self.assertIn("deepseek-v3.2", {item["model"] for item in text_models})
        self.assertIn("qwen-image", {item["model"] for item in image_models})
        self.assertIn("Wan2.2-T2V-A14B", {item["model"] for item in video_models})

    def test_official_maas_doc_links_are_preserved_for_agents(self) -> None:
        catalog = maas_models.load_catalog()
        catalog_urls = {item["url"] for item in catalog.get("official_docs", [])}
        reference_text = (ROOT / "references" / "maas-model-calls.md").read_text(encoding="utf-8")

        self.assertLessEqual(REQUIRED_OFFICIAL_DOC_URLS, catalog_urls)
        for url in REQUIRED_OFFICIAL_DOC_URLS:
            with self.subTest(url=url):
                self.assertIn(url, reference_text)

    def test_maas_reference_assets_do_not_store_local_development_paths(self) -> None:
        maas_assets = [
            ROOT / "references" / "maas-model-calls.md",
            ROOT / "references" / "maas-model-catalog.json",
            ROOT / "references" / "playbooks" / "maas-api-readiness.md",
            ROOT / "references" / "playbooks" / "maas-usage-governance.md",
        ]
        forbidden = (
            "/" + "Users/",
            "huaweicloud-data/" + "source-data",
            "0_cloud" + "_agent",
            "basic" + "_networks",
            "pytorch" + "_research",
        )

        for path in maas_assets:
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, text)

    def test_online_model_lookup_plan_does_not_require_key_or_network(self) -> None:
        args = maas_models.parse_args(["--online"])

        with mock.patch.dict(os.environ, {}, clear=True):
            plan = maas_models.build_online_plan(args)

        self.assertTrue(plan["success"])
        self.assertEqual(plan["method"], "GET")
        self.assertTrue(plan["endpoint"].endswith("/v2/models"))
        self.assertFalse(plan["api_key_presence"]["MAAS_API_KEY"]["set"])

    def test_chat_dry_run_builds_standard_v2_payload(self) -> None:
        args = maas_chat.parse_args(["--prompt", "你好", "--temperature", "0.2", "--dry-run"])

        plan = maas_chat.build_plan(args)

        self.assertTrue(plan["dry_run"])
        self.assertTrue(plan["endpoint"].endswith("/v2/chat/completions"))
        self.assertEqual(plan["payload"]["model"], maas_chat.DEFAULT_TEXT_MODEL)
        self.assertEqual(plan["payload"]["messages"][0]["content"], "你好")
        self.assertEqual(plan["payload"]["temperature"], 0.2)

    def test_chat_vision_payload_uses_v1_and_summarizes_local_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = write_fake_png(Path(tmp_dir) / "diagram.png")
            args = maas_chat.parse_args(["--prompt", "描述图片", "--image", str(image_path), "--dry-run"])

            plan = maas_chat.build_plan(args)

        content = plan["payload"]["messages"][0]["content"]
        image_url = content[1]["image_url"]["url"]
        self.assertTrue(plan["endpoint"].endswith("/v1/chat/completions"))
        self.assertEqual(plan["payload"]["model"], maas_chat.DEFAULT_VISION_MODEL)
        self.assertTrue(image_url.startswith("data:image/png;base64,<base64:"))
        self.assertNotIn("fake-image-bytes", json.dumps(plan, ensure_ascii=False))

    def test_chat_stream_execute_is_blocked_before_key_or_network(self) -> None:
        args = maas_chat.parse_args(["--prompt", "你好", "--stream"])

        with mock.patch.dict(os.environ, {}, clear=True):
            result = maas_chat.execute(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")

    def test_image_generation_execute_is_blocked_before_key_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = maas_image_generation.parse_args(
                ["--prompt", "生成一张云产品插图", "--file", "hero.webp", "--out-dir", tmp_dir]
            )
            result = maas_image_generation.execute(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")

    def test_video_create_is_blocked_before_key_or_network(self) -> None:
        args = maas_video_generation.parse_args(["--prompt", "云服务器控制台动画", "--size", "720x1280"])

        result = maas_video_generation.create_task(args)

        self.assertFalse(result["success"])
        self.assertEqual(result["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")

    def test_image_generation_plan_includes_edit_image_and_watermark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_path = write_fake_png(Path(tmp_dir) / "source.png")
            args = maas_image_generation.parse_args(
                [
                    "--prompt",
                    "生成一张云产品插图",
                    "--file",
                    "hero.webp",
                    "--image",
                    str(image_path),
                    "--out-dir",
                    tmp_dir,
                    "--model",
                    "qwen_image_edit",
                    "--watermark",
                    "--dry-run",
                ]
            )

            plan = maas_image_generation.build_plan(args)

        item = plan["items"][0]
        self.assertTrue(plan["dry_run"])
        self.assertEqual(item["model"], "qwen_image_edit")
        self.assertEqual(item["file"], "hero.webp")
        self.assertTrue(item["image"].startswith("data:image/png;base64,<base64:"))
        self.assertTrue(item["watermark"])

    def test_image_generation_rejects_nested_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            args = maas_image_generation.parse_args(
                ["--prompt", "bad", "--file", "../bad.webp", "--out-dir", tmp_dir, "--dry-run"]
            )

            with self.assertRaises(maas_image_generation.MaasImageError):
                maas_image_generation.load_items(args)

    def test_video_create_payload_defaults_to_image_to_video_for_keyframes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            first = write_fake_png(Path(tmp_dir) / "first.png", b"first")
            last = write_fake_png(Path(tmp_dir) / "last.png", b"last")
            args = maas_video_generation.parse_args(
                [
                    "--prompt",
                    "云服务器控制台动画",
                    "--first-frame",
                    str(first),
                    "--last-frame",
                    str(last),
                    "--size",
                    "720*1280",
                    "--size-separator",
                    "*",
                    "--duration",
                    "5",
                ]
            )

            payload = maas_video_generation.build_create_payload(args)

        self.assertEqual(payload["model"], maas_video_generation.DEFAULT_IMAGE_TO_VIDEO_MODEL)
        self.assertEqual(payload["parameters"]["size"], "720*1280")
        self.assertEqual(payload["parameters"]["duration"], 5)
        self.assertEqual([item["type"] for item in payload["input"]["media"]], ["first_frame", "last_frame"])

    def test_video_query_uses_task_endpoint_and_reports_terminal_result(self) -> None:
        args = maas_video_generation.parse_args(["--action", "query", "--task-id", "task-1"])
        fake_response = {
            "status_code": 200,
            "url": "https://api.modelarts-maas.com/v1/video/generations/task-1",
            "body": {
                "task_id": "task-1",
                "status": "succeeded",
                "content": {"result_url": "https://example.com/video.mp4"},
            },
        }

        with mock.patch.dict(os.environ, {"MAAS_API_KEY": "secret-key"}, clear=True):
            with mock.patch.object(maas_common, "request_json", return_value=fake_response) as request_json:
                result = maas_video_generation.query_task(args)

        request_json.assert_called_once()
        self.assertEqual(request_json.call_args.args[:2], ("GET", "/v1/video/generations/task-1"))
        self.assertTrue(result["terminal"])
        self.assertEqual(result["result_url"], "https://example.com/video.mp4")

    def test_environment_doctor_accepts_modelarts_maas_api_key_without_exposing_it(self) -> None:
        with mock.patch.dict(os.environ, {"MODELARTS_MAAS_API_KEY": "secret-key"}, clear=True):
            auth = hcloud_environment_doctor.inspect_auth(set())
            maas = hcloud_environment_doctor.inspect_maas({"maas"})

        payload = json.dumps({"auth": auth, "maas": maas}, ensure_ascii=False)
        self.assertTrue(auth["details"]["auth_modes"]["maas_api_key_set"])
        self.assertEqual(maas["status"], "ok")
        self.assertNotIn("secret-key", payload)

    def test_scenario_router_routes_maas_model_tasks(self) -> None:
        result = hcloud_scenario_router.route("用 MaaS 大模型生成图片并创建视频", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "maas-model-api-calls")
        self.assertIn("references/maas-model-calls.md", match["guides"])
        self.assertIn("scripts/maas_video_generation.py", match["planners"])

    def test_maas_usage_request_plan_builds_dry_run_without_secrets(self) -> None:
        args = maas_usage_request_plan.parse_args(
            [
                "--from",
                "2026-06-01",
                "--to",
                "2026-06-08",
                "--service-type",
                "custom-endpoint",
            ]
        )

        with mock.patch.dict(os.environ, {"HW_ACCESS_KEY": "ak-secret", "HW_SECRET_KEY": "sk-secret"}, clear=True):
            plan = maas_usage_request_plan.build_plan(args)

        payload = json.dumps(plan, ensure_ascii=False)
        self.assertTrue(plan["dry_run"])
        self.assertEqual(plan["method"], "POST")
        self.assertIn("/v1/{project_id}/maas/monitoring/show-statistics", plan["endpoint"])
        self.assertEqual(plan["date_range"]["from"], "2026-06-01")
        self.assertEqual(plan["date_range"]["to"], "2026-06-08")
        self.assertEqual(plan["request_body"]["service_type"], 4)
        self.assertEqual(plan["request_body"]["start_time"], 1780272000000)
        self.assertEqual(plan["request_body"]["end_time"], 1780876800000)
        self.assertEqual(plan["response_notes"]["time_unit"], "start_time and end_time are UTC millisecond timestamps.")
        self.assertEqual(plan["response_notes"]["token_unit"], "Returned token values are in thousands; multiply by 1000 before reporting actual token counts.")
        self.assertTrue(plan["auth"]["credential_presence"]["HW_ACCESS_KEY"]["set"])
        self.assertNotIn("ak-secret", payload)
        self.assertNotIn("sk-secret", payload)

    def test_maas_usage_request_plan_reports_huawei_credential_aliases(self) -> None:
        args = maas_usage_request_plan.parse_args(["--preset", "last-7-days"])

        with mock.patch.dict(
            os.environ,
            {
                "HUAWEI_ACCESS_KEY": "ak-secret",
                "HUAWEI_SECRET_KEY": "sk-secret",
                "HUAWEI_PROJECT_ID": "project-secret",
                "HUAWEI_REGION": "cn-southwest-2",
            },
            clear=True,
        ):
            plan = maas_usage_request_plan.build_plan(args, today=maas_usage_request_plan.date(2026, 7, 3))

        payload = json.dumps(plan, ensure_ascii=False)
        self.assertTrue(plan["auth"]["credential_presence"]["HUAWEI_ACCESS_KEY"]["set"])
        self.assertTrue(plan["auth"]["credential_presence"]["HUAWEI_PROJECT_ID"]["set"])
        self.assertNotIn("ak-secret", payload)
        self.assertNotIn("sk-secret", payload)
        self.assertNotIn("project-secret", payload)

    def test_maas_usage_request_plan_execute_redacts_signed_request(self) -> None:
        args = maas_usage_request_plan.parse_args(["--preset", "last-7-days", "--execute", "--timeout", "3"])

        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/json", "X-Request-Id": "req-1"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"statistics":[{"total_token":1,"total_request_count":2,"total_error_count":0}]}'

        with mock.patch.dict(
            os.environ,
            {
                "HUAWEI_ACCESS_KEY": "ak-secret",
                "HUAWEI_SECRET_KEY": "sk-secret",
                "HUAWEI_PROJECT_ID": "project-secret",
                "HUAWEI_REGION": "cn-southwest-2",
            },
            clear=True,
        ), mock.patch.object(maas_usage_request_plan, "urlopen", return_value=FakeResponse()) as urlopen_mock:
            plan = maas_usage_request_plan.build_plan(args, today=maas_usage_request_plan.date(2026, 7, 3))

        payload = json.dumps(plan, ensure_ascii=False)
        self.assertTrue(plan["execution"]["execution_success"])
        self.assertEqual(plan["execution"]["status_code"], 200)
        self.assertTrue(plan["execution"]["response_summary"]["usage_field_presence"]["total_token"])
        self.assertNotIn("Authorization", plan["execution"]["signed_header_names"])
        self.assertNotIn("ak-secret", payload)
        self.assertNotIn("sk-secret", payload)
        self.assertNotIn("project-secret", payload)
        self.assertTrue(urlopen_mock.called)

    def test_maas_usage_request_plan_warns_for_long_or_old_ranges(self) -> None:
        args = maas_usage_request_plan.parse_args(["--from", "2026-05-01", "--to", "2026-06-15"])

        plan = maas_usage_request_plan.build_plan(args, today=maas_usage_request_plan.date(2026, 7, 3))

        warnings = " ".join(plan["warnings"])
        self.assertIn("longer than 30 days", warnings)
        self.assertIn("older data may be unavailable", warnings)

    def test_scenario_router_routes_maas_usage_tasks(self) -> None:
        result = hcloud_scenario_router.route("查 MaaS 最近 7 天 token 用量 请求次数 和错误率", limit=1)

        self.assertTrue(result["success"], json.dumps(result, ensure_ascii=False))
        match = result["matches"][0]
        self.assertEqual(match["id"], "maas-usage-governance")
        self.assertIn("references/playbooks/maas-usage-governance.md", match["primary_playbooks"])
        self.assertIn("scripts/maas_usage_request_plan.py", match["planners"])
        self.assertIn("references/playbooks/billing-cost-governance.md", match["primary_playbooks"])
        self.assertFalse(match["terraform_candidate"])


if __name__ == "__main__":
    unittest.main()
