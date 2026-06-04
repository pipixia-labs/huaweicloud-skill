"""Tests for Huawei MaaS Qwen image asset generation helper."""

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

    def test_build_payload_uses_huawei_maas_shape(self) -> None:
        item = qwen_text_to_image.PromptItem(
            file="hero.webp",
            prompt="A toy store",
            size="1024x1024",
            seed=1,
        )

        payload = qwen_text_to_image.build_payload("qwen-image", item)

        self.assertEqual(
            payload,
            {
                "model": "qwen-image",
                "prompt": "A toy store",
                "size": "1024x1024",
                "response_format": "b64_json",
                "seed": 1,
            },
        )
        self.assertNotIn("input", payload)
        self.assertNotIn("parameters", payload)

    def test_extract_and_decode_b64_json_data_uri(self) -> None:
        encoded = "data:image/png;base64," + __import__("base64").b64encode(png_bytes()).decode("ascii")
        response = {"data": [{"url": None, "b64_json": encoded}]}

        raw, media_type = qwen_text_to_image.decode_b64_image(qwen_text_to_image.extract_b64_json(response))

        self.assertEqual(media_type, "image/png")
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size, (8, 6))

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
            with io.StringIO() as stdout, io.StringIO() as stderr:
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    result = qwen_text_to_image.main(
                        [
                            "--prompt",
                            "A toy store",
                            "--file",
                            "hero.webp",
                            "--out-dir",
                            tmp_dir,
                        ]
                    )
                error_output = stderr.getvalue()

        self.assertEqual(result, 1)
        self.assertIn("缺少华为云 ModelArts MaaS API Key", error_output)
        self.assertIn("MAAS_API_KEY", error_output)

    def test_huawei_maas_call_writes_manifest_without_key(self) -> None:
        calls: list[dict[str, object]] = []
        encoded = "data:image/png;base64," + __import__("base64").b64encode(png_bytes()).decode("ascii")
        maas_response = {
            "model": "qwen-image",
            "created": 1780537419677,
            "data": [{"url": None, "b64_json": encoded}],
            "usage": {},
            "error": None,
        }

        def fake_urlopen(request: object, timeout: int = 0, context: object | None = None) -> FakeHTTPResponse:
            self.assertTrue(hasattr(request, "full_url"))
            self.assertEqual(request.full_url, qwen_text_to_image.DEFAULT_ENDPOINT)
            body = json.loads(request.data.decode("utf-8"))
            calls.append({"url": request.full_url, "body": body, "headers": dict(request.header_items())})
            return FakeHTTPResponse(json.dumps(maas_response).encode("utf-8"))

        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {"MAAS_API_KEY": "secret-key"}, clear=True):
                with mock.patch.object(qwen_text_to_image.urllib.request, "urlopen", side_effect=fake_urlopen):
                    result = self.run_main_silenced(
                        [
                            "--prompt",
                            "A toy store",
                            "--file",
                            "hero.webp",
                            "--out-dir",
                            tmp_dir,
                            "--model",
                            "qwen-image",
                            "--size",
                            "1024x1024",
                            "--seed",
                            "1",
                        ]
                    )

            manifest = json.loads((Path(tmp_dir) / "qwen_manifest.json").read_text(encoding="utf-8"))
            output = Path(tmp_dir) / "hero.webp"
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                generated_size = image.size

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            calls[0]["body"],
            {
                "model": "qwen-image",
                "prompt": "A toy store",
                "size": "1024x1024",
                "response_format": "b64_json",
                "seed": 1,
            },
        )
        self.assertEqual(manifest["provider"], "Huawei Cloud ModelArts MaaS image generation")
        self.assertEqual(manifest["endpoint_host"], "api.modelarts-maas.com")
        self.assertEqual(manifest["items"][0]["model"], "qwen-image")
        self.assertNotIn("secret-key", json.dumps(manifest, ensure_ascii=False))
        self.assertEqual(generated_size, (8, 6))

    def test_prompt_file_rejects_nested_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            prompt_file = Path(tmp_dir) / "prompts.json"
            prompt_file.write_text(json.dumps([{"file": "../bad.webp", "prompt": "bad"}]), encoding="utf-8")
            args = qwen_text_to_image.parse_args(["--prompt-file", str(prompt_file), "--out-dir", tmp_dir])

            with self.assertRaises(qwen_text_to_image.QwenImageError):
                qwen_text_to_image.load_prompt_items(args)

    def test_size_accepts_star_but_normalizes_to_huawei_x_format(self) -> None:
        self.assertEqual(qwen_text_to_image.normalize_size("1024*1024"), "1024x1024")


if __name__ == "__main__":
    unittest.main()
