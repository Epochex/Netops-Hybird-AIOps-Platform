import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import clickhouse_connect
from kafka import KafkaConsumer, KafkaProducer

from core.infra.config import env_int, env_str
from core.infra.logging_utils import configure_logging

LOGGER = logging.getLogger(__name__)


def _build_consumer(bootstrap_servers: str, topic: str, group_id: str, auto_offset_reset: str) -> KafkaConsumer:
    return KafkaConsumer(
        topic,
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset=auto_offset_reset,
        value_deserializer=lambda b: b.decode("utf-8"),
    )


def _build_producer(bootstrap_servers: str) -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        acks="all",
        retries=10,
        compression_type="gzip",
        value_serializer=lambda x: x.encode("utf-8"),
    )


def _hourly_file(base_dir: str) -> str:
    now = datetime.now(timezone.utc)
    return os.path.join(base_dir, f"suggestions-{now.strftime('%Y%m%d-%H')}.jsonl")


def _append_jsonl(path: str, payload: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(payload)
        fp.write("\n")


def _recent_similar(client: Any, db: str, table: str, rule_id: str, service: str) -> int:
    if client is None:
        return 0
    try:
        result = client.query(
            f"""
            SELECT count()
            FROM {db}.{table}
            WHERE rule_id = %(rule_id)s
              AND service = %(service)s
              AND emit_ts >= now() - INTERVAL 1 HOUR
            """,
            parameters={"rule_id": rule_id, "service": service},
        )
        return int(result.first_item or 0)
    except Exception:
        LOGGER.exception("failed to query clickhouse context")
        return 0


def _build_suggestion(alert: dict[str, Any], recent_similar_1h: int) -> dict[str, Any]:
    alert_id = str(alert.get("alert_id") or "")
    rule_id = str(alert.get("rule_id") or "unknown")
    severity = str(alert.get("severity") or "unknown")
    excerpt = alert.get("event_excerpt") or {}
    service = str(excerpt.get("service") or "unknown")
    srcip = str(excerpt.get("srcip") or "unknown")
    src_key = str(excerpt.get("src_device_key") or "unknown")

    seed = f"{alert_id}|{datetime.now(timezone.utc).isoformat()}"
    suggestion_id = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()
    confidence = 0.65 if severity == "warning" else 0.8
    if recent_similar_1h > 20:
        confidence = min(confidence + 0.1, 0.95)

    return {
        "schema_version": 1,
        "suggestion_id": suggestion_id,
        "suggestion_ts": datetime.now(timezone.utc).isoformat(),
        "alert_id": alert_id,
        "rule_id": rule_id,
        "severity": severity,
        "priority": "P2" if severity == "warning" else "P1",
        "summary": f"{rule_id} triggered for service={service} src={srcip}",
        "context": {
            "service": service,
            "srcip": srcip,
            "src_device_key": src_key,
            "recent_similar_1h": recent_similar_1h,
        },
        "hypotheses": [
            "Edge-side noise filter may need refinement for this traffic class.",
            "Device policy baseline may be outdated for current service behavior.",
        ],
        "recommended_actions": [
            "Check edge-forwarder drop counters and recent scan mix for local/broadcast deny traffic.",
            "Inspect top source device/session traces for the last 15 minutes in ClickHouse.",
            "If repeated and expected, tune rule profile threshold/cooldown with canary rollout.",
        ],
        "confidence": round(confidence, 2),
    }


def main() -> None:
    configure_logging("core-aiops-agent")

    bootstrap_servers = env_str("KAFKA_BOOTSTRAP_SERVERS", "netops-kafka.netops-core.svc.cluster.local:9092")
    topic_alerts = env_str("KAFKA_TOPIC_ALERTS", "netops.alerts.v1")
    topic_suggestions = env_str("KAFKA_TOPIC_AIOPS_SUGGESTIONS", "netops.aiops.suggestions.v1")
    consumer_group = env_str("AIOPS_AGENT_GROUP_ID", "core-aiops-agent-v1")
    auto_offset_reset = env_str("KAFKA_AUTO_OFFSET_RESET", "latest").lower()
    if auto_offset_reset not in {"earliest", "latest"}:
        auto_offset_reset = "latest"

    min_severity = env_str("AIOPS_MIN_SEVERITY", "warning").lower()
    output_dir = env_str("AIOPS_OUTPUT_DIR", "/data/netops-runtime/aiops")
    log_interval_sec = env_int("AIOPS_LOG_INTERVAL_SEC", 30)

    ch_enabled = env_str("AIOPS_CLICKHOUSE_ENABLED", "true").lower() in {"1", "true", "yes"}
    ch_db = env_str("CLICKHOUSE_DB", "netops")
    ch_table = env_str("CLICKHOUSE_ALERTS_TABLE", "alerts")
    ch_client = None
    if ch_enabled:
        try:
            ch_client = clickhouse_connect.get_client(
                host=env_str("CLICKHOUSE_HOST", "clickhouse.netops-core.svc.cluster.local"),
                port=env_int("CLICKHOUSE_HTTP_PORT", 8123),
                username=env_str("CLICKHOUSE_USER", "default"),
                password=env_str("CLICKHOUSE_PASSWORD", ""),
            )
        except Exception:
            LOGGER.exception("failed to init clickhouse client, continue without context lookup")
            ch_client = None

    consumer = _build_consumer(bootstrap_servers, topic_alerts, consumer_group, auto_offset_reset)
    producer = _build_producer(bootstrap_servers)
    stats = {"ingested": 0, "suggestions_emitted": 0, "skipped_by_severity": 0, "json_error": 0, "commit_error": 0}
    tick = datetime.now(timezone.utc)

    LOGGER.info(
        "aiops-agent started: topic_alerts=%s topic_suggestions=%s min_severity=%s clickhouse_enabled=%s",
        topic_alerts,
        topic_suggestions,
        min_severity,
        ch_enabled,
    )

    severity_rank = {"warning": 1, "critical": 2}
    min_rank = severity_rank.get(min_severity, 1)

    for msg in consumer:
        stats["ingested"] += 1
        should_commit = False
        try:
            alert = json.loads(msg.value)
        except json.JSONDecodeError:
            stats["json_error"] += 1
            should_commit = True
            _commit_if_needed(consumer, should_commit, stats)
            continue

        severity = str(alert.get("severity") or "unknown").lower()
        if severity_rank.get(severity, 0) < min_rank:
            stats["skipped_by_severity"] += 1
            should_commit = True
            _commit_if_needed(consumer, should_commit, stats)
            continue

        excerpt = alert.get("event_excerpt") or {}
        similar_1h = _recent_similar(
            ch_client,
            ch_db,
            ch_table,
            str(alert.get("rule_id") or "unknown"),
            str(excerpt.get("service") or "unknown"),
        )
        suggestion = _build_suggestion(alert, similar_1h)
        payload = json.dumps(suggestion, ensure_ascii=True, separators=(",", ":"))

        producer.send(
            topic_suggestions,
            key=str(suggestion.get("suggestion_id") or "").encode("utf-8"),
            value=payload,
        ).get(timeout=30)
        _append_jsonl(_hourly_file(output_dir), payload)

        stats["suggestions_emitted"] += 1
        should_commit = True
        _commit_if_needed(consumer, should_commit, stats)

        now = datetime.now(timezone.utc)
        if (now - tick).total_seconds() >= log_interval_sec:
            LOGGER.info("aiops-agent stats: %s", json.dumps(stats, ensure_ascii=True, sort_keys=True))
            tick = now


def _commit_if_needed(consumer: KafkaConsumer, should_commit: bool, stats: dict[str, int]) -> None:
    if not should_commit:
        return
    try:
        consumer.commit()
    except Exception:
        stats["commit_error"] += 1
        LOGGER.exception("offset commit failed")


if __name__ == "__main__":
    main()
