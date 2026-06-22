# Image Generation via Huawei Cloud MaaS

Use this reference when a Huawei Cloud web deployment needs generated bitmap assets, such as static independent sites, product pages, venue pages, or app marketing pages. For general MaaS text, image understanding, image generation/editing, and video generation tasks, use `references/maas-model-calls.md`.

The required provider is Huawei Cloud ModelArts MaaS. Do not use non-Huawei endpoints for this skill.

The compatibility helper is `scripts/maas_text_to_image.py`. `scripts/qwen_text_to_image.py` and `references/qwen-image-generation.md` remain compatibility aliases for older workflows. The general image helper is `scripts/maas_image_generation.py`. The default MaaS text-to-image model parameter remains `qwen-image`.

## Required API

- Endpoint: `https://api.modelarts-maas.com/v1/images/generations`
- Auth: `Authorization: Bearer <MAAS_API_KEY>`
- Default model: `qwen-image`
- Model selection: pass `--model <model>` only when the MaaS image generation API supports that model parameter and the request/response shape is compatible with this helper.
- Request fields: `model`, `prompt`, `size`, `response_format`, `seed`
- Required response format: `b64_json`

Canonical request body with the default model:

```json
{
  "model": "qwen-image",
  "prompt": "A bright premium children's toy store interior...",
  "size": "1024x1024",
  "response_format": "b64_json",
  "seed": 1
}
```

The response may return `data[0].b64_json` as either raw base64 or a data URI such as `data:image/png;base64,...`; strip the prefix before decoding.

## Default Workflow

1. Decide the exact site assets needed before calling MaaS, including file names, aspect ratios, subject matter, and where each image will be used.
2. Write a prompt JSON file with one item per image:

```json
{
  "items": [
    {
      "file": "hero.webp",
      "size": "1024x1024",
      "seed": 1,
      "prompt": "A bright premium children's toy store interior..."
    }
  ]
}
```

3. Run the helper from the skill directory:

```bash
MAAS_API_KEY=<key> python3 scripts/maas_text_to_image.py \
  --prompt-file prompts.json \
  --out-dir ./assets \
  --model qwen-image \
  --format webp
```

4. Inspect generated files with Pillow, `file`, or `view_image`.
5. Use the decoded local assets in HTML/CSS; do not deploy raw base64 strings.
6. Deploy to ECS/OBS/CDN and verify the public HTTP response and rendered screenshots.

## Safety and Secrecy

- Read the API key only from `MAAS_API_KEY` or `MODELARTS_MAAS_API_KEY`.
- Never write the key into prompts, HTML, CSS, JavaScript, manifest, command journals, logs, or final answers.
- Keep prompts free of trademarks, copyrighted characters, celebrities, and unsafe child-product claims unless the user has a legitimate approved need.
- Do not switch to non-Huawei endpoints for this skill. If MaaS is unavailable, report the blocker instead of falling back to another provider.
- Keep `qwen-image` as the default model. If another MaaS image generation model is selected, record the model parameter in the manifest and final deployment report.

## Defaults

- Model: `qwen-image`
- Endpoint: fixed Huawei Cloud MaaS endpoint `api.modelarts-maas.com`
- Response format: `b64_json`
- Size: `1024x1024`
- Seed: `1`
- Final local format: WebP for web pages unless the user explicitly needs PNG.
- Manifest: `<out-dir>/qwen_manifest.json` by default for backward compatibility. Pass `--manifest <path>` if a MaaS-named manifest is required.

## Failure Handling

- `401` or `403`: Report that the Huawei MaaS API key or account permission is unauthorized.
- `429`: Stop or retry later; do not loop aggressively.
- Timeout or `5xx`: Retry only when it is low risk and bounded.
- Base64 decode failure: check whether the response has a `data:image/...;base64,` prefix and strip it before decoding.
- Bad image quality: regenerate with a more concrete prompt and inspect before deployment.

## Output Expectations

Final deployment reports should mention:

- image files generated,
- model used,
- Huawei MaaS endpoint host,
- target site asset directory,
- deployment path and public URL,
- HTTP/screenshot verification results.
