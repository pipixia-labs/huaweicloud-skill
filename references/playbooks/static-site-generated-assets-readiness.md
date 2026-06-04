# Static Site Generated Assets Readiness

Use this playbook when deploying a Huawei Cloud static site or independent site that needs generated images.

1. Inventory the site pages and required image slots: hero, product cards, feature bands, thumbnails, and social previews.
2. Create a prompt file with safe file names, target sizes, and prompts that avoid readable text, watermarks, logos, copyrighted characters, and unsafe product claims.
3. Generate local assets:

```bash
DASHSCOPE_API_KEY=<key> python3 scripts/qwen_text_to_image.py \
  --prompt-file <prompts.json> \
  --out-dir <site>/assets \
  --model qwen-image-2.0-pro \
  --endpoint auto \
  --format webp
```

4. Verify every generated image:
   - file exists and is non-empty,
   - dimensions match the intended slot,
   - image opens successfully,
   - visual content is suitable for the brand and page.
5. Reference only local asset paths from HTML/CSS.
6. Deploy the complete site directory to ECS, OBS, or the chosen Huawei Cloud web surface.
7. Verify public availability with HTTP status checks and rendered screenshots on desktop and mobile viewports.

Do not report deployment complete until the public page and generated images return successful protocol checks.
