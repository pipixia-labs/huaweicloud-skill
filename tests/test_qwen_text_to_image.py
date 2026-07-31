"""Tests for Huawei MaaS Qwen image asset generation helper."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

try:
    from PIL import Image
except ImportError as exc:
    Image = None
    PIL_IMPORT_ERROR = exc
else:
    PIL_IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qwen_text_to_image.py"
SPEC = importlib.util.spec_from_file_location("qwen_text_to_image", SCRIPT)
assert SPEC and SPEC.loader
qwen_text_to_image = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = qwen_text_to_image
SPEC.loader.exec_module(qwen_text_to_image)

MAAS_SCRIPT = ROOT / "scripts" / "maas_text_to_image.py"
MAAS_SPEC = importlib.util.spec_from_file_location("maas_text_to_image", MAAS_SCRIPT)
assert MAAS_SPEC and MAAS_SPEC.loader
maas_text_to_image = importlib.util.module_from_spec(MAAS_SPEC)
sys.modules[MAAS_SPEC.name] = maas_text_to_image
MAAS_SPEC.loader.exec_module(maas_text_to_image)


def png_bytes() -> bytes:
    image = Image.new("RGB", (8, 6), color=(240, 100, 80))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def parse_action_progress_line(line: str) -> dict[str, object]:
    assert line.startswith(qwen_text_to_image.ACTION_PROGRESS_PREFIX)
    return json.loads(line.removeprefix(qwen_text_to_image.ACTION_PROGRESS_PREFIX))


class FakeHTTPResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = mock.Mock()
        self.headers.get_content_type.return_value = content_type

    def __enter__(self) -> FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


@unittest.skipIf(Image is None, f"Pillow is required for image fixture tests: {PIL_IMPORT_ERROR}")
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

    def test_maas_entrypoint_reuses_compatibility_implementation(self) -> None:
        self.assertIs(maas_text_to_image.main, qwen_text_to_image.main)

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

    def test_legacy_entrypoint_is_plan_only_before_key_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.dict(os.environ, {"MAAS_API_KEY": "secret-key"}, clear=True):
            with mock.patch.object(qwen_text_to_image.urllib.request, "urlopen") as urlopen_mock:
                with io.StringIO() as stdout, redirect_stdout(stdout):
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
                    payload = json.loads(stdout.getvalue())

            self.assertFalse((Path(tmp_dir) / "qwen_manifest.json").exists())
            self.assertFalse((Path(tmp_dir) / "hero.webp").exists())

        self.assertEqual(result, 1)
        self.assertEqual(payload["error_type"], "UNIFIED_RUNTIME_PLAN_ONLY")
        urlopen_mock.assert_not_called()

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
