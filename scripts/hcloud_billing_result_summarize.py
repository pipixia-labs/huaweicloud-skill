#!/usr/bin/env python3
"""Summarize and redact Huawei Cloud BSS/Billing query results."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import hcloud_common


SEMANTIC_CATALOG_PATH = hcloud_common.REFERENCES_DIR / "billing" / "semantic-catalog.json"
MONEY_FIELD_HINTS = (
    "amount",
    "cost",
    "debt",
    "cash",
    "credit",
    "coupon",
    "official",
    "discount",
)
DEFAULT_PROTECTED_KEYS = {
    "account_id",
    "account_name",
    "customer_id",
    "customer_name",
    "sub_customer_id",
    "indirect_partner_id",
    "resource_id",
    "res_instance_id",
    "resource_instance_id",
    "order_id",
    "trade_id",
    "coupon_id",
    "quota_id",
    "card_id",
}


def load_semantic_catalog(path: Path = SEMANTIC_CATALOG_PATH) -> dict[str, Any]:
    """Load billing semantic catalog metadata."""
    if not path.exists():
        return {"protected_identifiers": []}
    return hcloud_common.load_json(path)


def protected_keys(catalog: dict[str, Any] | None = None) -> set[str]:
    """Return field names that should be redacted in billing output."""
    catalog = catalog or load_semantic_catalog()
    return DEFAULT_PROTECTED_KEYS | {str(item) for item in catalog.get("protected_identifiers", [])}


def stable_redaction(value: Any) -> str:
    """Return a stable non-reversible redaction marker for one identifier."""
    text = str(value)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"***:{digest}"


def redact_protected_identifiers(value: Any, keys: set[str]) -> Any:
    """Recursively redact protected billing identifiers by key name."""
    if isinstance(value, dict):
        redacted = {}
        for key, child in value.items():
            if key in keys and child not in (None, "", []):
                redacted[key] = stable_redaction(child)
            else:
                redacted[key] = redact_protected_identifiers(child, keys)
        return redacted
    if isinstance(value, list):
        return [redact_protected_identifiers(item, keys) for item in value]
    return value


def unwrap_safe_exec_result(value: Any) -> tuple[Any, dict[str, Any] | None]:
    """Return parsed BSS payload from a safe_exec result or direct JSON value."""
    if isinstance(value, dict) and "parsed_json" in value and ("service" in value or "operation" in value):
        return value.get("parsed_json"), value
    return value, None


def iter_record_lists(value: Any) -> list[tuple[str, list[Any]]]:
    """Return top-level list fields that look like result records."""
    if not isinstance(value, dict):
        return []
    lists = []
    for key, child in value.items():
        if isinstance(child, list):
            lists.append((key, child))
    return lists


def collect_field_names(records: list[Any]) -> list[str]:
    """Return stable field names seen in a record list."""
    names: set[str] = set()
    for record in records:
        if isinstance(record, dict):
            names.update(str(key) for key in record)
    return sorted(names)


def collect_money_fields(value: Any) -> list[str]:
    """Return top-level fields that appear to contain money amounts."""
    if not isinstance(value, dict):
        return []
    fields = []
    for key in value:
        lowered = str(key).lower()
        if any(hint in lowered for hint in MONEY_FIELD_HINTS):
            fields.append(str(key))
    return sorted(fields)


def pagination_summary(payload: Any, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """Return pagination completeness metadata."""
    total_count = payload.get("total_count") if isinstance(payload, dict) else None
    record_count = sum(len(records) for _, records in iter_record_lists(payload))
    complete = False
    if isinstance(total_count, int) and offset is not None and limit is not None:
        complete = offset + limit >= total_count
    return {
        "total_count": total_count,
        "record_count": record_count,
        "offset": offset,
        "limit": limit,
        "complete_result_claim_allowed": bool(complete and total_count is not None),
        "reason": "Totals and rankings require all intended pages; one page is partial when total_count exceeds offset + limit.",
    }


def build_summary(
    raw_value: Any,
    *,
    offset: int | None = None,
    limit: int | None = None,
    include_redacted_records: bool = False,
) -> dict[str, Any]:
    """Build a safe billing result summary."""
    payload, safe_exec = unwrap_safe_exec_result(raw_value)
    keys = protected_keys()
    redacted_payload = redact_protected_identifiers(payload, keys)
    record_lists = iter_record_lists(redacted_payload)
    result: dict[str, Any] = {
        "success": payload is not None,
        "source": "safe_exec" if safe_exec is not None else "direct_json",
        "operation": safe_exec.get("operation") if isinstance(safe_exec, dict) else None,
        "redaction": {
            "protected_identifier_keys": sorted(keys),
            "strategy": "stable_hash_marker",
            "raw_identifiers_included": False,
        },
        "pagination": pagination_summary(redacted_payload, offset=offset, limit=limit),
        "summary": {
            "top_level_fields": sorted(redacted_payload.keys()) if isinstance(redacted_payload, dict) else [],
            "money_fields_present": collect_money_fields(redacted_payload),
            "record_lists": [
                {
                    "field": field,
                    "record_count": len(records),
                    "field_names": collect_field_names(records),
                }
                for field, records in record_lists
            ],
        },
        "output_boundary": {
            "summarize_by_default": True,
            "raw_output_allowed_only_after_scope_confirmation": True,
        },
    }
    if include_redacted_records:
        result["redacted_records"] = redacted_payload
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-file", type=Path, required=True, help="JSON file containing a safe_exec result or BSS JSON payload.")
    parser.add_argument("--offset", type=int, help="Known pagination offset from the command plan.")
    parser.add_argument("--limit", type=int, help="Known pagination limit from the command plan.")
    parser.add_argument("--include-redacted-records", action="store_true", help="Include redacted records in the output.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def main() -> int:
    """Summarize a billing result JSON file."""
    args = parse_args()
    raw_value = hcloud_common.load_json(args.json_file)
    result = build_summary(
        raw_value,
        offset=args.offset,
        limit=args.limit,
        include_redacted_records=args.include_redacted_records,
    )
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
