# Qwen Image Generation for Huawei Cloud Site Deployments

Use this reference only when a Huawei Cloud web deployment needs generated bitmap assets, such as static independent sites, product pages, venue pages, or app marketing pages. This is an auxiliary asset workflow, not a KooCLI service.

## Default Workflow

1. Decide the exact site assets needed before calling Qwen, including file names, aspect ratios, subject matter, and where each image will be used.
2. Write a prompt JSON file with one item per image:

```json
{
  "items": [
    {
      "file": "hero.webp",
      "size": "1664*928",
      "prompt": "A bright premium children's toy store interior..."
    }
  ]
}
```

3. Run the helper from the skill directory:

```bash
DASHSCOPE_API_KEY=<key> python3 scripts/qwen_text_to_image.py \
  --prompt-file prompts.json \
  --out-dir ./assets \
  --model qwen-image-2.0-pro \
  --endpoint auto \
  --format webp
```

4. Inspect generated files with Pillow, `file`, or `view_image`.
5. Use the downloaded local assets in HTML/CSS; do not deploy temporary Qwen image URLs.
6. Deploy to ECS/OBS/CDN and verify the public HTTP response and rendered screenshots.

## Safety and Secrecy

- Read the API key only from `DASHSCOPE_API_KEY`.
- Never write the key into prompts, HTML, CSS, JavaScript, manifest, command journals, logs, or final answers.
- Do not expose raw temporary image URLs in public site code.
- Keep prompts free of trademarks, copyrighted characters, celebrities, and unsafe child-product claims unless the user has a legitimate approved need.

## Defaults

- Model: `qwen-image-2.0-pro`
- Endpoint: `auto`, which tries international DashScope first and then China DashScope.
- Final format: WebP for web pages unless the user explicitly needs PNG.
- Manifest: `<out-dir>/qwen_manifest.json`

## Failure Handling

- `401` or `403`: Try the other DashScope endpoint when `--endpoint=auto`; if both fail, report that the key or endpoint is unauthorized.
- `429`: Stop or retry later; do not loop aggressively.
- Timeout or `5xx`: Retry only when it is low risk and bounded.
- Bad image quality: regenerate with a more concrete prompt and inspect before deployment.

## Output Expectations

Final deployment reports should mention:

- image files generated,
- model used,
- target site asset directory,
- deployment path and public URL,
- HTTP/screenshot verification results.
