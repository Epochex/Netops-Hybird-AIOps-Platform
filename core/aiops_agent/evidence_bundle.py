import hashlib
from datetime import datetime, timezone
from typing import Any

from core.aiops_agent.cluster_aggregator import ClusterTrigger


def build_cluster_evidence_bundle(
    alert: dict[str, Any],
    trigger: ClusterTrigger,
    recent_similar_1h: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    excerpt = alert.get("event_excerpt") or {}
    metrics = alert.get("metrics") or {}
    dimensions = alert.get("dimensions") or {}
    topology = alert.get("topology_context") or {}
    device_profile = alert.get("device_profile") or {}
    change_context = alert.get("change_context") or {}

    seed = (
        f"{alert.get('alert_id','')}|{trigger.key.rule_id}|{trigger.key.service}|"
        f"{trigger.key.src_device_key}|{trigger.last_alert_ts}"
    )
    bundle_id = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()

    asset_tags = _normalize_str_list(device_profile.get("asset_tags"))
    known_services = _normalize_str_list(device_profile.get("known_services"))
    change_refs = _normalize_str_list(change_context.get("change_refs"))

    return {
        "schema_version": 1,
        "bundle_id": bundle_id,
        "bundle_ts": now.isoformat(),
        "bundle_scope": "cluster",
        "alert_ref": {
            "alert_id": str(alert.get("alert_id") or ""),
            "rule_id": trigger.key.rule_id,
            "severity": trigger.key.severity,
        },
        "topology_context": {
            "service": trigger.key.service,
            "src_device_key": trigger.key.src_device_key,
            "srcip": str(excerpt.get("srcip") or topology.get("srcip") or ""),
            "dstip": str(excerpt.get("dstip") or topology.get("dstip") or ""),
            "site": str(topology.get("site") or device_profile.get("site") or ""),
            "zone": str(topology.get("zone") or ""),
            "neighbor_refs": _normalize_str_list(topology.get("neighbor_refs")),
        },
        "historical_context": {
            "recent_similar_1h": max(0, int(recent_similar_1h)),
            "cluster_size": trigger.cluster_size,
            "cluster_window_sec": trigger.window_sec,
            "cluster_first_alert_ts": trigger.first_alert_ts,
            "cluster_last_alert_ts": trigger.last_alert_ts,
            "cluster_sample_alert_ids": trigger.sample_alert_ids,
        },
        "rule_context": {
            "rule_id": trigger.key.rule_id,
            "severity": trigger.key.severity,
            "metrics": metrics,
            "dimensions": dimensions,
            "rule_hits": [
                {
                    "rule_id": trigger.key.rule_id,
                    "severity": trigger.key.severity,
                    "cluster_size": trigger.cluster_size,
                }
            ],
        },
        "window_context": {
            "cluster_size": trigger.cluster_size,
            "window_sec": trigger.window_sec,
            "sample_alert_ids": trigger.sample_alert_ids,
        },
        "device_context": {
            "src_device_key": trigger.key.src_device_key,
            "device_role": str(device_profile.get("device_role") or ""),
            "site": str(device_profile.get("site") or ""),
            "vendor": str(device_profile.get("vendor") or ""),
            "asset_tags": asset_tags,
            "known_services": known_services,
        },
        "change_context": {
            "suspected_change": bool(change_context.get("suspected_change")),
            "change_window_min": int(change_context.get("change_window_min") or 0),
            "change_refs": change_refs,
        },
    }


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text)
    return items
