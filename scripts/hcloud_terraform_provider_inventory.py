#!/usr/bin/env python3
"""Build Huawei Cloud Terraform provider resource/data-source inventories."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import hcloud_common


TERRAFORM_DIR = hcloud_common.REFERENCES_DIR / "terraform"
INVENTORY_DIR = TERRAFORM_DIR / "inventories"
RESOURCE_INVENTORY_PATH = INVENTORY_DIR / "provider-resource-inventory.md"
DATA_SOURCE_INVENTORY_PATH = INVENTORY_DIR / "provider-data-source-inventory.md"
DEFAULT_PROVIDER_ROOT = hcloud_common.ROOT.parent / "reference-projects" / "terraform-provider-huaweicloud"


def strip_provider_prefix(name: str) -> str:
    """Return provider item name without the huaweicloud prefix."""
    return name.removeprefix("huaweicloud_")


def family_for_name(name: str) -> str:
    """Return the first name token used as provider inventory family."""
    return name.split("_", 1)[0] if name else "unknown"


def discover_items(provider_root: Path, kind: str) -> list[str]:
    """Return provider resource or data-source names from docs markdown files."""
    docs_dir = provider_root / "docs" / kind
    if not docs_dir.exists():
        raise FileNotFoundError(f"provider docs directory not found: {docs_dir}")
    items = []
    for path in sorted(docs_dir.glob("*.md")):
        items.append(strip_provider_prefix(path.stem))
    return sorted(dict.fromkeys(items))


def group_items(items: list[str]) -> list[dict[str, Any]]:
    """Group provider item names by their first token."""
    grouped: dict[str, list[str]] = {}
    for item in items:
        grouped.setdefault(family_for_name(item), []).append(item)
    return [{"family": family, "count": len(names), "items": names} for family, names in sorted(grouped.items())]


def read_provider_snapshot(provider_root: Path) -> dict[str, Any]:
    """Return the top changelog version/date for a local provider snapshot."""
    changelog = provider_root / "CHANGELOG.md"
    snapshot = {
        "source": "reference-projects/terraform-provider-huaweicloud",
        "version": None,
        "date": None,
    }
    if not changelog.exists():
        return snapshot
    match = re.search(r"^##\s+([0-9.]+)\s+\(([^)]+)\)", changelog.read_text(encoding="utf-8"), re.MULTILINE)
    if match:
        snapshot["version"] = match.group(1)
        snapshot["date"] = match.group(2)
    return snapshot


def build_inventory(provider_root: Path, kind: str) -> dict[str, Any]:
    """Build a structured provider inventory from local provider docs."""
    items = discover_items(provider_root, kind)
    groups = group_items(items)
    return {
        "kind": kind,
        "count": len(items),
        "family_count": len(groups),
        "snapshot": read_provider_snapshot(provider_root),
        "groups": groups,
    }


def render_inventory(title: str, description: str, inventory: dict[str, Any]) -> str:
    """Render a provider inventory as Chinese markdown."""
    snapshot = inventory["snapshot"]
    version = snapshot.get("version") or "unknown"
    date = snapshot.get("date") or "unknown"
    source = snapshot["source"]
    lines = [
        f"# {title}",
        "",
        description,
        "",
        f"来源快照：`{source}`，provider changelog 顶部版本 `{version}`，日期 `{date}`。",
        f"覆盖统计：{inventory['count']} 个条目，{inventory['family_count']} 个家族。",
        "",
        "阅读方式：",
        "- 先按家族名查看 provider 是否覆盖某个方向。",
        "- 再结合 `provider-capability-index.md` 判断是否值得进入主线。",
        "- 再结合 `reference-example-inventory.md` 判断是否已经有成型 example。",
        "- 这份文件是生成索引；维护时用 `scripts/hcloud_terraform_provider_inventory.py` 从 provider docs 重建。",
        "",
    ]
    for group in inventory["groups"]:
        lines.append(f"## {group['family']} ({group['count']})")
        for item in group["items"]:
            lines.append(f"- `{item}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_inventories(resource_inventory: dict[str, Any], data_source_inventory: dict[str, Any]) -> None:
    """Write generated provider inventory markdown files."""
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    RESOURCE_INVENTORY_PATH.write_text(
        render_inventory(
            "Provider Resource Inventory",
            "这份文档把参考仓库 `docs/resources` 中的资源家族完整搬运到 skill 内部，作为 provider 资源覆盖面的总索引。",
            resource_inventory,
        ),
        encoding="utf-8",
    )
    DATA_SOURCE_INVENTORY_PATH.write_text(
        render_inventory(
            "Provider Data Source Inventory",
            "这份文档把参考仓库 `docs/data-sources` 中的 data source 家族完整搬运到 skill 内部，作为 discovery 能力面的总索引。",
            data_source_inventory,
        ),
        encoding="utf-8",
    )


def parse_inventory_items(path: Path) -> set[str]:
    """Return item names already listed in an inventory markdown file."""
    if not path.exists():
        return set()
    return set(re.findall(r"^- `([^`]+)`", path.read_text(encoding="utf-8"), re.MULTILINE))


def compare_inventory(generated: dict[str, Any], existing_path: Path) -> dict[str, Any]:
    """Compare generated inventory names with an existing markdown inventory."""
    generated_items = {item for group in generated["groups"] for item in group["items"]}
    existing_items = parse_inventory_items(existing_path)
    missing = sorted(generated_items - existing_items)
    stale = sorted(existing_items - generated_items)
    return {
        "path": str(existing_path.relative_to(hcloud_common.ROOT)),
        "generated_count": len(generated_items),
        "existing_count": len(existing_items),
        "missing_count": len(missing),
        "stale_count": len(stale),
        "missing_sample": missing[:50],
        "stale_sample": stale[:50],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider-root", type=Path, default=DEFAULT_PROVIDER_ROOT, help="Local terraform-provider-huaweicloud checkout.")
    parser.add_argument("--write", action="store_true", help="Write provider inventory markdown files.")
    parser.add_argument("--fail-on-drift", action="store_true", help="Return non-zero when committed inventories differ from provider docs.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """Build, compare, and optionally write Terraform provider inventories."""
    args = parse_args()
    provider_root = args.provider_root.resolve()
    resource_inventory = build_inventory(provider_root, "resources")
    data_source_inventory = build_inventory(provider_root, "data-sources")
    comparisons = {
        "resources": compare_inventory(resource_inventory, RESOURCE_INVENTORY_PATH),
        "data_sources": compare_inventory(data_source_inventory, DATA_SOURCE_INVENTORY_PATH),
    }
    if args.write:
        write_inventories(resource_inventory, data_source_inventory)
        comparisons = {
            "resources": compare_inventory(resource_inventory, RESOURCE_INVENTORY_PATH),
            "data_sources": compare_inventory(data_source_inventory, DATA_SOURCE_INVENTORY_PATH),
        }
    success = not args.fail_on_drift or all(
        item["missing_count"] == 0 and item["stale_count"] == 0 for item in comparisons.values()
    )
    result = {
        "success": success,
        "provider_root_exists": provider_root.exists(),
        "provider_snapshot": read_provider_snapshot(provider_root),
        "write": args.write,
        "inventories": {
            "resources": {
                "count": resource_inventory["count"],
                "family_count": resource_inventory["family_count"],
                "path": str(RESOURCE_INVENTORY_PATH.relative_to(hcloud_common.ROOT)),
            },
            "data_sources": {
                "count": data_source_inventory["count"],
                "family_count": data_source_inventory["family_count"],
                "path": str(DATA_SOURCE_INVENTORY_PATH.relative_to(hcloud_common.ROOT)),
            },
        },
        "drift": comparisons,
    }
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
