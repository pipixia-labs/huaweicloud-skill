#!/usr/bin/env python3
"""Prepare a narrow, keypair-only ECS create request without sending it.

This adapter deliberately reuses ``hcloud_ecs_create_plan.validate_payload``
instead of reimplementing ECS request validation.  The reviewed subset accepts
one or more private ECSs with an existing keypair and an existing security
group whose readback evidence passes the common ingress policy.  Password
login, implicit default security groups, public-IP allocation, and arbitrary
server-body fragments remain outside this mapper.
"""

from __future__ import annotations

import copy
from typing import Any

import hcloud_ecs_create_plan
import hcloud_unified_contracts


MAPPING_ID = "ecs_create_keypair_v1"
ACTION_SPEC_ID = "huaweicloud.ecs.create_server.v1"
ROOT_VOLUME_TYPES = {"SAS", "SSD", "GPSSD", "GPSSD2", "ESSD2"}
REQUIRED_PARAMETERS = {
    "server_name",
    "availability_zone",
    "vpc_id",
    "subnet_id",
    "image_id",
    "flavor_id",
    "root_volume_type",
    "server_count",
    "key_name",
    "security_group_id",
    "security_group_rule_evidence",
}


def validate_ecs_keypair_intent(execution_intent: dict[str, Any]) -> list[str]:
    """Validate the reviewed semantic input required by the ECS request mapper."""
    errors: list[str] = []
    action_spec_ref = execution_intent.get("action_spec_ref")
    if not isinstance(action_spec_ref, dict) or action_spec_ref.get("id") != ACTION_SPEC_ID:
        errors.append("ECS request mapper requires the curated ECS create-server Action Spec")
    catalog_ref = execution_intent.get("catalog_ref")
    if not isinstance(catalog_ref, dict) or catalog_ref.get("service") != "ECS" or catalog_ref.get("operation") != "CreateServers":
        errors.append("ECS request mapper requires catalog_ref ECS/CreateServers")
    scope = execution_intent.get("scope")
    if not isinstance(scope, dict) or not isinstance(scope.get("project_id"), str) or not scope["project_id"].strip():
        errors.append("ECS request mapper requires a non-empty scope.project_id")
    parameters = execution_intent.get("parameters")
    if not isinstance(parameters, dict):
        return [*errors, "ECS request mapper requires an object parameters field"]
    unexpected = sorted(set(parameters) - REQUIRED_PARAMETERS)
    if unexpected:
        errors.append(f"ECS request mapper does not accept unreviewed semantic inputs: {', '.join(unexpected)}")
    for name in sorted(REQUIRED_PARAMETERS - set(parameters)):
        errors.append(f"ECS request mapper misses required semantic input {name}")
    for name in REQUIRED_PARAMETERS - {"server_count", "security_group_rule_evidence", "root_volume_type"}:
        value = parameters.get(name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"ECS semantic input {name} must be a non-empty string")
    count = parameters.get("server_count")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= hcloud_ecs_create_plan.DEFAULT_SAFE_MAX_COUNT:
        errors.append(f"server_count must be an integer from 1 to {hcloud_ecs_create_plan.DEFAULT_SAFE_MAX_COUNT}")
    root_volume_type = parameters.get("root_volume_type")
    if root_volume_type not in ROOT_VOLUME_TYPES:
        errors.append(f"root_volume_type must be one of: {', '.join(sorted(ROOT_VOLUME_TYPES))}")
    evidence = parameters.get("security_group_rule_evidence")
    if not isinstance(evidence, dict):
        errors.append("security_group_rule_evidence must be an object from a current security-group readback")
    return sorted(set(errors))


def build_ecs_keypair_request(execution_intent: dict[str, Any]) -> dict[str, Any]:
    """Build and validate the local ECS cli-jsonInput shape from semantic inputs."""
    errors = validate_ecs_keypair_intent(execution_intent)
    if errors:
        return {"success": False, "errors": errors}
    parameters = execution_intent["parameters"]
    cli_json_input = {
        "path": {"project_id": execution_intent["scope"]["project_id"]},
        "body": {
            "server": {
                "name": parameters["server_name"],
                "availability_zone": parameters["availability_zone"],
                "flavorRef": parameters["flavor_id"],
                "imageRef": parameters["image_id"],
                "vpcid": parameters["vpc_id"],
                "nics": [{"subnet_id": parameters["subnet_id"]}],
                "security_groups": [{"id": parameters["security_group_id"]}],
                "root_volume": {"volumetype": parameters["root_volume_type"]},
                "key_name": parameters["key_name"],
                "count": parameters["server_count"],
            }
        },
    }
    validation = hcloud_ecs_create_plan.validate_payload(
        cli_json_input,
        security_group_evidence=parameters["security_group_rule_evidence"],
        allow_public_web=False,
    )
    if not validation["valid"]:
        return {"success": False, "errors": list(validation["errors"])}
    request: dict[str, Any] = {
        "mapping_id": MAPPING_ID,
        "catalog_ref": copy.deepcopy(execution_intent["catalog_ref"]),
        "cli_json_input": cli_json_input,
    }
    request["request_fingerprint"] = hcloud_unified_contracts.fingerprint(
        request,
        excluded_fields={"request_fingerprint"},
    )
    return {"success": True, "prepared_request": request}
