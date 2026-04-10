from core.aiops_agent.app_config import AgentConfig
from core.aiops_agent.legacy_upgrade import upgrade_legacy_suggestion_payload


def _config() -> AgentConfig:
    return AgentConfig(
        bootstrap_servers="localhost:9092",
        topic_alerts="netops.alerts.v1",
        topic_suggestions="netops.aiops.suggestions.v1",
        consumer_group="core-aiops-agent-v1",
        auto_offset_reset="latest",
        min_severity="warning",
        output_dir="/tmp",
        log_interval_sec=3600,
        clickhouse_enabled=False,
        clickhouse_host="",
        clickhouse_http_port=8123,
        clickhouse_user="default",
        clickhouse_password="",
        clickhouse_db="netops",
        clickhouse_alerts_table="alerts",
        cluster_window_sec=600,
        cluster_min_alerts=3,
        cluster_cooldown_sec=300,
        provider="template",
        provider_endpoint_url="",
        provider_api_key="",
        provider_model="generic-aiops",
        provider_timeout_sec=30,
        provider_compute_target="external_gpu_service",
        provider_max_parallelism=1,
    )


def test_upgrade_legacy_alert_scope_suggestion_adds_reasoning_objects() -> None:
    legacy = {
        "schema_version": 2,
        "suggestion_id": "s-1",
        "suggestion_ts": "2026-04-10T13:52:58.887488+00:00",
        "suggestion_scope": "alert",
        "alert_id": "a-1",
        "rule_id": "deny_burst_v1",
        "severity": "warning",
        "priority": "P2",
        "summary": "deny_burst_v1 triggered",
        "context": {
            "service": "udp/3702",
            "src_device_key": "dev-1",
            "cluster_size": 1,
            "cluster_window_sec": 0,
            "cluster_first_alert_ts": "2026-04-10T13:52:58.887488+00:00",
            "cluster_last_alert_ts": "2026-04-10T13:52:58.887488+00:00",
            "cluster_sample_alert_ids": ["a-1"],
            "recent_similar_1h": 12,
            "evidence_bundle_id": "b-1",
            "inference_request_id": "r-1",
            "provider": "template",
        },
        "evidence_bundle": {
            "schema_version": 1,
            "bundle_id": "b-1",
            "bundle_ts": "2026-04-10T13:52:58.887202+00:00",
            "bundle_scope": "alert",
            "alert_ref": {"alert_id": "a-1", "rule_id": "deny_burst_v1", "severity": "warning"},
            "topology_context": {
                "service": "udp/3702",
                "src_device_key": "dev-1",
                "srcip": "192.168.1.20",
                "dstip": "192.168.30.35",
                "site": "lab-a",
                "zone": "edge",
                "neighbor_refs": ["sw-1"],
            },
            "historical_context": {
                "recent_similar_1h": 12,
                "cluster_size": 1,
                "cluster_window_sec": 0,
                "cluster_first_alert_ts": "2026-04-10T13:52:58.887488+00:00",
                "cluster_last_alert_ts": "2026-04-10T13:52:58.887488+00:00",
                "cluster_sample_alert_ids": ["a-1"],
            },
            "rule_context": {
                "rule_id": "deny_burst_v1",
                "severity": "warning",
                "metrics": {"deny_count": 99, "window_sec": 60, "threshold": 30},
                "dimensions": {"src_device_key": "dev-1"},
                "rule_hits": [{"rule_id": "deny_burst_v1", "severity": "warning", "cluster_size": 1}],
            },
            "window_context": {"cluster_size": 1, "window_sec": 0, "sample_alert_ids": ["a-1"]},
            "device_context": {
                "src_device_key": "dev-1",
                "device_role": "camera",
                "site": "lab-a",
                "vendor": "Dahua",
                "device_name": "cam-01",
                "osname": "",
                "family": "IP Camera",
                "srcmac": "aa:bb:cc:dd:ee:ff",
                "model": "",
                "version": "1.0",
                "asset_tags": ["iot"],
                "known_services": ["udp/3702"],
            },
            "change_context": {
                "suspected_change": True,
                "change_window_min": 0,
                "change_refs": ["crscore:30"],
                "score": 30,
                "action": "131072",
                "level": "high",
            },
        },
        "inference": {
            "schema_version": 1,
            "request_id": "r-1",
            "provider_name": "template",
            "provider_kind": "builtin",
            "inference_ts": "2026-04-10T13:52:58.887446+00:00",
            "summary": "deny_burst_v1 triggered",
            "hypotheses": ["Policy miss", "Path mismatch"],
            "recommended_actions": ["Inspect ClickHouse history", "Check policy intent"],
            "confidence_score": 0.71,
            "confidence_label": "medium",
            "confidence_reason": "legacy result",
            "raw_response": {"projection_basis": {"projector-trigger": []}},
        },
        "hypotheses": ["Policy miss", "Path mismatch"],
        "recommended_actions": ["Inspect ClickHouse history", "Check policy intent"],
        "confidence": 0.71,
        "confidence_label": "medium",
        "confidence_reason": "legacy result",
    }

    upgraded = upgrade_legacy_suggestion_payload(legacy, config=_config())

    assert upgraded["reasoning_runtime_seed"]["candidate_event_graph"]["graph_scope"] == "alert"
    assert upgraded["evidence_bundle"]["path_context"]["path_signature"]
    assert upgraded["evidence_bundle"]["evidence_pack_v2"]["summary"]["direct_count"] >= 1
    assert upgraded["hypothesis_set"]["items"]
    assert upgraded["review_verdict"]["checks"]["overreach_risk"]["status"] == "guarded"
    assert upgraded["runbook_draft"]["approval_boundary"]["approval_required"] is True
    assert upgraded["reasoning_stage_requests"]["hypothesis_critique"]["stage"] == "hypothesis_critique"
    assert upgraded["context"]["candidate_event_graph_id"]
    assert upgraded["context"]["review_verdict_id"]
