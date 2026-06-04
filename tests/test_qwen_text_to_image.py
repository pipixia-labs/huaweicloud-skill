"""Tests for Qwen image asset generation helper."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qwen_text_to_image.py"
SPEC = importlib.util.spec_from_file_location("qwen_text_to_image", SCRIPT)
assert SPEC and SPEC.loader
qwen_text_to_image = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qwen_text_to_image
SPEC.loader.exec_module(qwen_text_to_image)


def png_bytes() -> bytes:
    image = Image.new("RGB", (8, 6), color=(240, 100, 80))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeHTTPResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = mock.Mock()
        self.headers.get_content_type.return_value = content_type

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class QwenTextToImageTest(unittest.TestCase):
    def run_main_silenced(self, args: list[str]) -> int:
        with io.StringIO() as stdout, io.StringIO() as stderr:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                return qwen_text_to_image.main(args)

    def test_extract_image_url_from_choices_response(self) -> None:
        response = {"output": {"choices": [{"message": {"content": [{"image": "https://example.com/image.png"}]}}]}}

        self.assertEqual(qwen_text_to_image.extract_image_url(response), "https://example.com/image.png")

    def test_dry_run_does_not_require_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            completed = self.run_main_silenced(
                [
                    "--prompt",
                    "A toy store",
                    "--file",
                    "hero.webp",
                    "--out-dir",
                    tmp_dir,
                    "--dry-run",
                ]
            )

        self.assertEqual(completed, 0)

    def test_missing_api_key_fails_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.dict(os.environ, {}, clear=True):
            result = self.run_main_silenced(
                [
                    "--prompt",
                    "A toy store",
                    "--file",
                    "hero.webp",
                    "--out-dir",
                    tmp_dir,
                ]
            )

        self.assertEqual(result, 1)

    def test_endpoint_auto_falls_back_after_401_and_writes_manifest_without_key(self) -> None:
        calls: list[str] = []
        image_payload = png_bytes()
        qwen_response = {
            "request_id": "request-123",
            "output": {"choices": [{"message": {"content": [{"image": "https://example.com/generated.png"}]}}]},
        }

        def fake_urlopen(request: object, timeout: int = 0) -> FakeHTTPResponse:
            if hasattr(request, "full_url") and "dashscope-intl" in request.full_url:
                calls.append("intl")
                raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", hdrs=None, fp=io.BytesIO(b"bad key"))
            if hasattr(request, "full_url") and "dashscope.aliyuncs.com" in request.full_url:
                calls.append("cn")
                return FakeHTTPResponse(json.dumps(qwen_response).encode("utf-8"))
            calls.append("image")
            return FakeHTTPResponse(image_payload, "image/png")

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"DASHSCOPE_API_KEY": "secret-key"}, clear=True):
                with mock.patch.object(qwen_text_to_image.urllib.request, "urlopen", side_effect=fake_urlopen):
                    result = self.run_main_silenced(
                        [
                            "--prompt",
                            "A toy store",
                            "--file",
                            "hero.webp",
                            "--out-dir",
                            tmp_dir,
                            "--endpoint",
                            "auto",
                        ]
                    )

            manifest = json.loads((Path(tmp_dir) / "qwen_manifest.json").read_text(encoding="utf-8"))
            output = Path(tmp_dir) / "hero.webp"
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                generated_size = image.size

        self.assertEqual(result, 0)
        self.assertEqual(calls[:3], ["intl", "cn", "image"])
        self.assertEqual(manifest["items"][0]["model"], qwen_text_to_image.DEFAULT_MODEL)
        self.assertEqual(manifest["items"][0]["endpoint_host"], "dashscope.aliyuncs.com")
        self.assertNotIn("secret-key", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(generated_size, (8, 6))

    def test_prompt_file_rejects_nested_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_file = Path(tmp_dir) / "prompts.json"
            prompt_file.write_text(json.dumps([{"file": "../bad.webp", "prompt": "bad"}]), encoding="utf-8")
            args = qwen_text_to_image.parse_args(["--prompt-file", str(prompt_file), "--out-dir", tmp_dir])

            with self.assertRaises(qwen_text_to_image.QwenImageError):
                qwen_text_to_image.load_prompt_items(args)


if __name__ == "__main__":
    unittest.main()
