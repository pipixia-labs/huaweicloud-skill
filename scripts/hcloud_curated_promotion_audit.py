#!/usr/bin/env python3
"""Audit metadata-backed services against curated registry promotion criteria."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import hcloud_catalog
import hcloud_common


DEFAULT_CANDIDATES = ("DCS", "RFS", "UCS", "WAF", "CodeArtsRepo", "DLI")
PROFILES_PATH = hcloud_common.REFERENCES_DIR / "service-curation-profiles.json"
REQUIRED_PROFILE_FIELDS = {
    "status",
    "target_coverage",
    "readiness_operations",
    "resource_query_operations",
    "playbooks",
    "risk_profile",
}
REQUIRED_RISK_PROFILE_FIELDS = {
    "mutation_policy",
    "default_risk",
    "submit_policy",
    "verification_policy",
}


def load_curation_profiles(path: Path = PROFILES_PATH) -> dict[str, Any]:
    """Load curated service maintenance and promotion candidate profiles."""
    if not path.exists():
        return {"schema_version": 1, "services": {}}
    return hcloud_common.load_json(path)


def profile_for_service(profiles: dict[str, Any], service_name: str) -> dict[str, Any] | None:
    """Return a curation profile by loose service name matching."""
    wanted = hcloud_catalog.normalize_token(service_name)
    for name, profile in profiles.get("services", {}).items():
        if hcloud_catalog.normalize_token(str(name)) == wanted and isinstance(profile, dict):
            return profile
    return None


def profile_missing_fields(profile: dict[str, Any] | None, expected_status: str | None = None) -> list[str]:
    """Return missing or incomplete profile fields."""
    if not profile:
        return ["curation_profile"]
    missing = [f"profile_field:{field}" for field in sorted(REQUIRED_PROFILE_FIELDS) if field not in profile]
    if expected_status and profile.get("status") != expected_status:
        missing.append(f"profile_status:{profile.get('status') or 'missing'}")
    risk_profile = profile.get("risk_profile")
    if not isinstance(risk_profile, dict):
        missing.append("risk_profile")
    else:
        missing.extend(
            f"risk_profile_field:{field}"
            for field in sorted(REQUIRED_RISK_PROFILE_FIELDS)
            if not risk_profile.get(field)
        )
    return missing


def playbook_missing_items(profile: dict[str, Any] | None, root: Path = hcloud_common.ROOT) -> list[str]:
    """Return missing playbook fields or files for a profile."""
    if not profile:
        return []
    playbooks = profile.get("playbooks")
    if not isinstance(playbooks, list) or not playbooks:
        return ["playbook"]
    missing = []
    for playbook in playbooks:
        playbook_path = root / str(playbook)
        if not playbook_path.exists():
            missing.append(f"playbook_file:{playbook}")
    return missing


def catalog_operation_missing_items(
    catalog_service: dict[str, Any],
    profile: dict[str, Any] | None,
    field: str,
) -> list[str]:
    """Return profile operations that do not resolve in the generated catalog."""
    if not profile:
        return []
    operations = profile.get(field)
    if not isinstance(operations, list):
        return [f"profile_field:{field}"]
    missing = []
    for operation_name in operations:
        if not hcloud_catalog.resolve_operation(catalog_service, str(operation_name)):
            missing.append(f"{field}:{operation_name}")
    return missing


def live_read_smoked_operations(confidence: dict[str, Any], service_name: str, catalog_service: dict[str, Any]) -> list[str]:
    """Return live-smoked read-only operations that still exist in the catalog."""
    service_confidence = hcloud_catalog.service_confidence(confidence, service_name)
    operations = service_confidence.get("operations", {})
    if not isinstance(operations, dict):
        return []
    result = []
    for operation_name, entry in operations.items():
        if not isinstance(entry, dict) or entry.get("confidence") != "live-read-smoked":
            continue
        operation = hcloud_catalog.resolve_operation(catalog_service, str(operation_name))
        if operation and hcloud_catalog.is_read_only(operation):
            result.append(str(operation.get("name") or operation_name))
    return sorted(dict.fromkeys(result))


def resource_query_candidates(catalog_service: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    """Return read-only operations that can become explicit resource query paths."""
    result = []
    for operation in catalog_service.get("operations", {}).values():
        if not isinstance(operation, dict) or not hcloud_catalog.is_read_only(operation):
            continue
        required = hcloud_catalog.required_param_names(operation)
        if not required:
            continue
        result.append(
            {
                "operation": operation.get("name"),
                "required_params": required,
                "summary": operation.get("summary"),
            }
        )
    result.sort(key=lambda item: str(item.get("operation", "")).lower())
    return result[:limit]


def promotion_candidate(
    service_name: str,
    catalog: dict[str, Any],
    registry: dict[str, Any],
    confidence: dict[str, Any],
    profiles: dict[str, Any],
    min_live_ops: int,
) -> dict[str, Any]:
    """Audit one service against the medium-coverage curated promotion line."""
    registry_services = registry.get("services", {})
    service_token = hcloud_catalog.normalize_token(service_name)
    if service_token in {hcloud_catalog.normalize_token(name) for name in registry_services}:
        return {
            "service": service_name,
            "status": "already_curated",
            "eligible": False,
            "missing": [],
        }

    catalog_service = hcloud_catalog.resolve_service(catalog, service_name)
    if not catalog_service:
        return {
            "service": service_name,
            "status": "missing_catalog_service",
            "eligible": False,
            "missing": ["catalog_service"],
        }

    live_ops = live_read_smoked_operations(confidence, service_name, catalog_service)
    profile = profile_for_service(profiles, service_name)
    discovery_ops = [
        str(operation.get("name"))
        for operation in hcloud_catalog.discovery_operations(catalog_service, 12)
        if operation.get("name")
    ]
    resource_ops = resource_query_candidates(catalog_service)
    missing = []
    if len(live_ops) < min_live_ops:
        missing.append(f"live_read_smoked_operations:{len(live_ops)}/{min_live_ops}")
    if not resource_ops:
        missing.append("resource_query_candidate")
    if not discovery_ops:
        missing.append("readiness_discovery_candidate")
    missing.extend(profile_missing_fields(profile, expected_status="candidate"))
    missing.extend(playbook_missing_items(profile))
    missing.extend(catalog_operation_missing_items(catalog_service, profile, "readiness_operations"))
    missing.extend(catalog_operation_missing_items(catalog_service, profile, "resource_query_operations"))

    return {
        "service": str(catalog_service.get("name") or service_name),
        "status": "eligible" if not missing else "blocked",
        "eligible": not missing,
        "category": catalog_service.get("category"),
        "operation_count": catalog_service.get("operation_count"),
        "live_read_smoked_operations": live_ops,
        "live_read_smoked_operation_count": len(live_ops),
        "readiness_discovery_candidates": discovery_ops,
        "resource_query_candidates": resource_ops,
        "profile": profile_summary(profile),
        "missing": missing,
        "next_steps": promotion_next_steps(missing),
    }


def profile_summary(profile: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a compact profile summary for audit output."""
    if not profile:
        return None
    return {
        "status": profile.get("status"),
        "target_coverage": profile.get("target_coverage"),
        "readiness_operations": profile.get("readiness_operations", []),
        "resource_query_operations": profile.get("resource_query_operations", []),
        "playbooks": profile.get("playbooks", []),
        "risk_profile": profile.get("risk_profile", {}),
    }


def curated_service_health(
    registry: dict[str, Any],
    profiles: dict[str, Any],
    root: Path = hcloud_common.ROOT,
) -> dict[str, Any]:
    """Audit existing curated registry services for profile, playbook, and risk metadata."""
    findings = []
    for service_name, service_entry in registry.get("services", {}).items():
        profile = profile_for_service(profiles, service_name)
        missing = []
        missing.extend(profile_missing_fields(profile, expected_status="curated"))
        missing.extend(playbook_missing_items(profile, root=root))
        missing.extend(registry_profile_operation_missing_items(service_entry, profile))
        registry_playbooks = service_entry.get("playbooks")
        if not isinstance(registry_playbooks, list) or not registry_playbooks:
            missing.append("registry_playbook")
        else:
            for playbook in registry_playbooks:
                if not (root / str(playbook)).exists():
                    missing.append(f"registry_playbook_file:{playbook}")
        if profile and isinstance(registry_playbooks, list):
            profile_playbooks = set(str(item) for item in profile.get("playbooks", []) if item)
            registry_playbook_set = set(str(item) for item in registry_playbooks if item)
            if profile_playbooks and profile_playbooks != registry_playbook_set:
                missing.append("registry_profile_playbook_mismatch")
        findings.append(
            {
                "service": service_name,
                "coverage": service_entry.get("coverage"),
                "status": "ok" if not missing else "blocked",
                "missing": sorted(dict.fromkeys(missing)),
                "profile": profile_summary(profile),
            }
        )
    return {
        "service_count": len(findings),
        "ok_count": sum(1 for item in findings if item.get("status") == "ok"),
        "blocked_count": sum(1 for item in findings if item.get("status") == "blocked"),
        "findings": findings,
    }


def registry_profile_operation_missing_items(
    service_entry: dict[str, Any],
    profile: dict[str, Any] | None,
) -> list[str]:
    """Return profile read operations missing from the curated registry entry."""
    if not profile:
        return []
    registered = {
        hcloud_catalog.normalize_token(str(operation))
        for field in ("query_operations", "resource_query_operations")
        for operation in service_entry.get(field, [])
    }
    missing = []
    for field in ("readiness_operations", "resource_query_operations"):
        operations = profile.get(field)
        if not isinstance(operations, list):
            continue
        for operation in operations:
            if hcloud_catalog.normalize_token(str(operation)) not in registered:
                missing.append(f"registry_operation:{field}:{operation}")
    return missing


def promotion_next_steps(missing: list[str]) -> list[str]:
    """Return concrete next steps for unmet promotion criteria."""
    steps = []
    if any(item.startswith("live_read_smoked_operations") for item in missing):
        steps.append("Run additional read-only live smoke until at least the required number of operations are command_shape_ok.")
    if "resource_query_candidate" in missing:
        steps.append("Pick at least one read-only target-scoped operation and document its required params.")
    if "readiness_discovery_candidate" in missing:
        steps.append("Define one read-only readiness discovery operation for post-change or inventory checks.")
    if "curation_profile" in missing:
        steps.append("Add a candidate entry to references/service-curation-profiles.json.")
    if any(item.startswith("profile_field:") for item in missing):
        steps.append("Complete the candidate profile fields required by the curation contract.")
    if "playbook" in missing or any(item.startswith("playbook_file:") for item in missing):
        steps.append("Add a service playbook before adding the service to service-registry.json.")
    if "risk_profile" in missing or any(item.startswith("risk_profile_field:") for item in missing):
        steps.append("Document mutation risk posture, even if first curated coverage remains read-only.")
    if any(item.startswith("readiness_operations:") for item in missing):
        steps.append("Fix profile readiness operations so they resolve in the generated catalog.")
    if any(item.startswith("resource_query_operations:") for item in missing):
        steps.append("Fix profile resource query operations so they resolve in the generated catalog.")
    return steps


def audit(
    services: list[str] | None = None,
    catalog_path: Path = hcloud_catalog.CATALOG_PATH,
    registry_path: Path = hcloud_common.REGISTRY_PATH,
    confidence_path: Path = hcloud_catalog.CONFIDENCE_PATH,
    profiles_path: Path = PROFILES_PATH,
    min_live_ops: int = 2,
    include_curated: bool = False,
) -> dict[str, Any]:
    """Audit candidate services for curated registry promotion readiness."""
    catalog = hcloud_catalog.load_catalog(catalog_path)
    registry = hcloud_common.load_registry(registry_path)
    confidence = hcloud_catalog.load_confidence(confidence_path)
    profiles = load_curation_profiles(profiles_path)
    candidates = [
        promotion_candidate(service, catalog, registry, confidence, profiles, min_live_ops)
        for service in (services or list(DEFAULT_CANDIDATES))
    ]
    result = {
        "success": True,
        "criteria": {
            "min_live_read_smoked_operations": min_live_ops,
            "requires_resource_query_candidate": True,
            "requires_readiness_discovery_candidate": True,
            "requires_curation_profile": True,
            "requires_playbook_file": True,
            "requires_risk_profile": True,
        },
        "candidate_count": len(candidates),
        "eligible_count": sum(1 for item in candidates if item.get("eligible")),
        "blocked_count": sum(1 for item in candidates if item.get("status") == "blocked"),
        "already_curated_count": sum(1 for item in candidates if item.get("status") == "already_curated"),
        "candidates": candidates,
    }
    if include_curated:
        result["curated_service_health"] = curated_service_health(registry, profiles)
    return result


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--service", action="append", help="Candidate service to audit. Can be repeated.")
    parser.add_argument("--catalog", default=str(hcloud_catalog.CATALOG_PATH), help="Generated catalog or catalog index path.")
    parser.add_argument("--registry", default=str(hcloud_common.REGISTRY_PATH), help="Curated service registry path.")
    parser.add_argument("--confidence", default=str(hcloud_catalog.CONFIDENCE_PATH), help="Confidence sidecar path.")
    parser.add_argument("--profiles", default=str(PROFILES_PATH), help="Service curation profiles path.")
    parser.add_argument("--min-live-ops", type=int, default=2, help="Minimum live-read-smoked operations required.")
    parser.add_argument("--include-curated", action="store_true", help="Also audit existing curated registry services.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()
    if args.min_live_ops < 1:
        parser.error("--min-live-ops must be greater than 0.")
    return args


def main() -> int:
    """Run curated promotion readiness audit."""
    args = parse_args()
    result = audit(
        services=args.service,
        catalog_path=Path(args.catalog),
        registry_path=Path(args.registry),
        confidence_path=Path(args.confidence),
        profiles_path=Path(args.profiles),
        min_live_ops=args.min_live_ops,
        include_curated=args.include_curated,
    )
    hcloud_common.emit_json(result, pretty=args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
