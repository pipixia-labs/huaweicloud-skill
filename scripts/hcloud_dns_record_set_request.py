#!/usr/bin/env python3
"""Prepare the reviewed DNS A-record request shape without sending it.

This small service-specific mapper is intentionally separate from the global
contracts.  It turns only the curated DNS trial's semantic inputs into the
generated catalog's request parameter names, validates the narrow A-record
subset that has review evidence, and returns a fingerprinted local request.
The request payload is never emitted in a controlled-submit handoff; a host
adapter must re-derive it from the fingerprint-bound Execution Intent.
"""

from __future__ import annotations

import copy
import ipaddress
from typing import Any

import hcloud_unified_contracts


MAPPING_ID = "dns_record_set_a_v1"
ACTION_SPEC_ID = "huaweicloud.dns.create_record_set.v1"


def validate_dns_a_record_intent(execution_intent: dict[str, Any]) -> list[str]:
    """Validate the reviewed, secret-free DNS A-record semantic input subset."""
    errors: list[str] = []
    action_spec_ref = execution_intent.get("action_spec_ref")
    if not isinstance(action_spec_ref, dict) or action_spec_ref.get("id") != ACTION_SPEC_ID:
        errors.append("DNS request mapper requires the curated DNS create-record-set Action Spec")
    catalog_ref = execution_intent.get("catalog_ref")
    if not isinstance(catalog_ref, dict) or catalog_ref.get("service") != "DNS" or catalog_ref.get("operation") != "CreateRecordSet":
        errors.append("DNS request mapper requires catalog_ref DNS/CreateRecordSet")
    parameters = execution_intent.get("parameters")
    if not isinstance(parameters, dict):
        return [*errors, "DNS request mapper requires an object parameters field"]
    zone_id = parameters.get("zone_id")
    if not isinstance(zone_id, str) or len(zone_id) != 32 or not zone_id.isalnum():
        errors.append("zone_id must be a 32-character alphanumeric DNS zone identifier")
    name = parameters.get("record_name")
    if not isinstance(name, str) or not name.endswith(".") or any(char.isspace() for char in name):
        errors.append("record_name must be a whitespace-free FQDN ending with a period")
    record_type = parameters.get("record_type")
    if record_type != "A":
        errors.append("DNS trial mapper currently supports only record_type A")
    ttl = parameters.get("ttl")
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= 2_147_483_647:
        errors.append("ttl must be an integer from 1 to 2147483647")
    values = parameters.get("record_values")
    if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values):
        errors.append("record_values must be a non-empty list of IPv4 address strings")
    elif record_type == "A":
        for value in values:
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                errors.append(f"record_values contains an invalid IP address: {value}")
                continue
            if parsed.version != 4:
                errors.append(f"record_values requires IPv4 addresses for record_type A: {value}")
    return sorted(set(errors))


def build_dns_a_record_request(execution_intent: dict[str, Any]) -> dict[str, Any]:
    """Build a local DNS request object from an already admission-bound intent."""
    errors = validate_dns_a_record_intent(execution_intent)
    if errors:
        return {"success": False, "errors": errors}
    parameters = execution_intent["parameters"]
    request: dict[str, Any] = {
        "mapping_id": MAPPING_ID,
        "catalog_ref": copy.deepcopy(execution_intent["catalog_ref"]),
        "parameters": {
            "zone_id": parameters["zone_id"],
            "name": parameters["record_name"],
            "type": parameters["record_type"],
            "ttl": parameters["ttl"],
            "records": list(parameters["record_values"]),
        },
    }
    request["request_fingerprint"] = hcloud_unified_contracts.fingerprint(
        request,
        excluded_fields={"request_fingerprint"},
    )
    return {"success": True, "prepared_request": request}
