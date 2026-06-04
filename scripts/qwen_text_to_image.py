#!/usr/bin/env python3
"""Generate local site image assets with Qwen text-to-image.

This helper is intentionally provider-scoped and cloud-deployment friendly:
it reads the DashScope key from the environment, downloads generated images
as local files, and writes a small manifest without credentials.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "qwen-image-2.0-pro"
DEFAULT_NEGATIVE_PROMPT = (
    "low resolution, blurry, watermark, logo, readable text, distorted hands, "
    "unsafe objects, scary mood, copyrighted character"
)
ENDPOINTS = {
    "intl": "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    "cn": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
}


@dataclass(frozen=True)
class PromptItem:
    """One image generation request."""

    file: str
    prompt: str
    size: str
    negative_prompt: str


class QwenImageError(RuntimeError):
    """Raised when Qwen image generation cannot complete."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate local image assets using Qwen text-to-image.")
    parser.add_argument("--prompt-file", help="JSON file containing prompt items.")
    parser.add_argument("--prompt", help="Single prompt text. Requires --file.")
    parser.add_argument("--file", help="Output file name for --prompt mode.")
    parser.add_argument("--out-dir", required=True, help="Directory where image assets are written.")
    parser.add_argument("--manifest", help="Manifest path. Defaults to <out-dir>/qwen_manifest.json.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Qwen image model. Default: {DEFAULT_MODEL}.")
    parser.add_argument(
        "--endpoint",
        default="auto",
        help="Endpoint selector: auto, cn, intl, or a full generation endpoint URL.",
    )
    parser.add_argument("--size", default="1328*1328", help="Default image size for items without size.")
    parser.add_argument("--negative-prompt", default=DEFAULT_NEGATIVE_PROMPT, help="Default negative prompt.")
    parser.add_argument("--format", choices=["webp", "png"], default="webp", help="Final local image format.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate even when target exists.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print the resolved plan without network calls.")
    parser.add_argument("--timeout", type=int, default=240, help="HTTP timeout in seconds.")
    return parser.parse_args(argv)


def load_prompt_items(args: argparse.Namespace) -> list[PromptItem]:
    if args.prompt:
        if not args.file:
            raise QwenImageError("--file is required when using --prompt")
        raw_items: list[dict[str, Any]] = [{"file": args.file, "prompt": args.prompt, "size": args.size}]
    elif args.prompt_file:
        try:
            data = json.loads(Path(args.prompt_file).read_text(encoding="utf-8"))
        except Exception as exc:
            raise QwenImageError(f"Could not read prompt file: {exc}") from exc
        if isinstance(data, list):
            raw_items = data
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            raw_items = data["items"]
        else:
            raise QwenImageError("Prompt file must be a list or an object with an items list")
    else:
        raise QwenImageError("Either --prompt-file or --prompt is required")

    items: list[PromptItem] = []
    for index, raw in enumerate(raw_items, start=1):
        if not isinstance(raw, dict):
            raise QwenImageError(f"Prompt item {index} must be an object")
        file_name = str(raw.get("file") or "").strip()
        prompt = str(raw.get("prompt") or "").strip()
        if not file_name or Path(file_name).name != file_name:
            raise QwenImageError(f"Prompt item {index} must have a safe file name")
        if not prompt:
            raise QwenImageError(f"Prompt item {index} is missing prompt")
        target_name = ensure_suffix(file_name, args.format)
        items.append(
            PromptItem(
                file=target_name,
                prompt=prompt,
                size=str(raw.get("size") or args.size),
                negative_prompt=str(raw.get("negative_prompt") or args.negative_prompt),
            )
        )
    return items


def ensure_suffix(file_name: str, image_format: str) -> str:
    suffix = "." + image_format
    path = Path(file_name)
    if path.suffix.lower() == suffix:
        return file_name
    return path.with_suffix(suffix).name


def endpoint_candidates(selector: str) -> list[str]:
    if selector == "auto":
        return [ENDPOINTS["intl"], ENDPOINTS["cn"]]
    if selector in ENDPOINTS:
        return [ENDPOINTS[selector]]
    parsed = urllib.parse.urlparse(selector)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return [selector]
    raise QwenImageError("--endpoint must be auto, cn, intl, or a full URL")


def build_payload(model: str, item: PromptItem) -> dict[str, Any]:
    return {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": item.prompt}],
                }
            ]
        },
        "parameters": {
            "negative_prompt": item.negative_prompt,
            "prompt_extend": True,
            "watermark": False,
            "size": item.size,
            "n": 1,
        },
    }


def call_qwen(api_key: str, endpoint: str, model: str, item: PromptItem, timeout: int) -> dict[str, Any]:
    body = json.dumps(build_payload(model, item), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
    try:
        return json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise QwenImageError("Qwen response was not JSON") from exc


def extract_image_url(response: dict[str, Any]) -> str:
    choices = response.get("output", {}).get("choices", [])
    if isinstance(choices, list):
        for choice in choices:
            content = choice.get("message", {}).get("content", []) if isinstance(choice, dict) else []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("image"), str):
                    return item["image"]

    results = response.get("output", {}).get("results", [])
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict):
                for key in ("url", "image"):
                    if isinstance(item.get(key), str):
                        return item[key]

    for key in ("image", "url"):
        value = response.get("output", {}).get(key)
        if isinstance(value, str):
            return value

    raise QwenImageError("Qwen response did not contain an image URL")


def read_image_bytes(image_url: str, timeout: int) -> tuple[bytes, str | None]:
    if image_url.startswith("data:"):
        header, encoded = image_url.split(",", 1)
        media_type = header[5:].split(";", 1)[0] or None
        return base64.b64decode(encoded), media_type

    request = urllib.request.Request(image_url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        media_type = response.headers.get_content_type()
        return response.read(), media_type


def write_image(raw: bytes, media_type: str | None, target: Path, image_format: str) -> None:
    if image_format == "png" and media_type == "image/png":
        target.write_bytes(raw)
        return

    try:
        from PIL import Image
        from io import BytesIO

        with Image.open(BytesIO(raw)) as image:
            if image_format == "webp":
                image.save(target, "WEBP", quality=88, method=6)
            else:
                image.save(target, "PNG")
    except ImportError as exc:
        guessed = mimetypes.guess_extension(media_type or "") or ".img"
        raise QwenImageError(
            f"Pillow is required to convert generated image bytes to {image_format}; source looked like {guessed}"
        ) from exc


def generate_item(
    api_key: str,
    endpoints: list[str],
    model: str,
    item: PromptItem,
    out_dir: Path,
    image_format: str,
    overwrite: bool,
    timeout: int,
) -> dict[str, Any]:
    target = out_dir / item.file
    if target.exists() and target.stat().st_size > 0 and not overwrite:
        return {
            "file": item.file,
            "prompt": item.prompt,
            "size": item.size,
            "status": "existing",
        }

    last_error: str | None = None
    for endpoint in endpoints:
        try:
            response = call_qwen(api_key, endpoint, model, item, timeout)
            image_url = extract_image_url(response)
            raw, media_type = read_image_bytes(image_url, timeout)
            write_image(raw, media_type, target, image_format)
            return {
                "file": item.file,
                "prompt": item.prompt,
                "size": item.size,
                "status": "generated",
                "model": model,
                "endpoint_host": urllib.parse.urlparse(endpoint).netloc,
                "request_id": response.get("request_id"),
            }
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {body[:300]}"
            if exc.code not in {401, 403, 429, 500, 502, 503, 504}:
                break
        except Exception as exc:
            last_error = str(exc)
    raise QwenImageError(f"Could not generate {item.file}: {last_error}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        items = load_prompt_items(args)
        endpoints = endpoint_candidates(args.endpoint)
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = Path(args.manifest) if args.manifest else out_dir / "qwen_manifest.json"

        plan = {
            "model": args.model,
            "endpoint_count": len(endpoints),
            "out_dir": str(out_dir),
            "items": [{"file": item.file, "size": item.size, "prompt": item.prompt} for item in items],
        }
        if args.dry_run:
            print(json.dumps({"success": True, "dry_run": True, "plan": plan}, ensure_ascii=False, indent=2))
            return 0

        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            raise QwenImageError("Missing DASHSCOPE_API_KEY environment variable")

        manifest = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": "Qwen DashScope image generation",
            "items": [],
        }
        for item in items:
            result = generate_item(
                api_key=api_key,
                endpoints=endpoints,
                model=args.model,
                item=item,
                out_dir=out_dir,
                image_format=args.format,
                overwrite=args.overwrite,
                timeout=args.timeout,
            )
            manifest["items"].append(result)
            print(f"{result['status']}: {result['file']}", flush=True)

        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"success": True, "manifest": str(manifest_path), "count": len(items)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
