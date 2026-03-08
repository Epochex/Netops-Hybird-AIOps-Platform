import json
import logging
import os
from datetime import datetime, timezone

from kafka import KafkaConsumer

from core.infra.config import env_int, env_str
from core.infra.logging_utils import configure_logging

LOGGER = logging.getLogger(__name__)


def _build_consumer(bootstrap_servers: str, topic: str, group_id: str, auto_offset_reset: str) -> KafkaConsumer:
    return KafkaConsumer(
        topic,
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        group_id=group_id,
        enable_auto_commit=True,
        auto_offset_reset=auto_offset_reset,
        value_deserializer=lambda b: b.decode("utf-8"),
    )


def _hourly_file(base_dir: str, alert_ts: str | None) -> str:
    ts = None
    if isinstance(alert_ts, str) and alert_ts:
        text = alert_ts.replace("Z", "+00:00")
        try:
            ts = datetime.fromisoformat(text)
        except ValueError:
            ts = None
    if ts is None:
        ts = datetime.now(timezone.utc)
    ts = ts.astimezone(timezone.utc)
    filename = f"alerts-{ts.strftime('%Y%m%d-%H')}.jsonl"
    return os.path.join(base_dir, filename)


def _append_jsonl(path: str, payload: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fp:
        fp.write(payload)
        fp.write("\n")


def main() -> None:
    configure_logging("core-alerts-sink")

    bootstrap_servers = env_str("KAFKA_BOOTSTRAP_SERVERS", "netops-kafka.netops-core.svc.cluster.local:9092")
    topic_alerts = env_str("KAFKA_TOPIC_ALERTS", "netops.alerts.v1")
    consumer_group = env_str("ALERTS_SINK_GROUP_ID", "core-alerts-sink-v1")
    auto_offset_reset = env_str("KAFKA_AUTO_OFFSET_RESET", "latest").lower()
    if auto_offset_reset not in {"earliest", "latest"}:
        LOGGER.warning("invalid KAFKA_AUTO_OFFSET_RESET=%s, fallback to latest", auto_offset_reset)
        auto_offset_reset = "latest"

    output_dir = env_str("ALERTS_OUTPUT_DIR", "/data/netops-runtime/alerts")
    log_interval_sec = env_int("ALERTS_SINK_LOG_INTERVAL_SEC", 30)

    consumer = _build_consumer(bootstrap_servers, topic_alerts, consumer_group, auto_offset_reset)
    stats = {"ingested": 0, "written": 0, "json_error": 0}
    last_log_ts = datetime.now(timezone.utc)

    LOGGER.info(
        "alerts-sink started: topic=%s group=%s offset_reset=%s output_dir=%s",
        topic_alerts,
        consumer_group,
        auto_offset_reset,
        output_dir,
    )

    for msg in consumer:
        stats["ingested"] += 1
        raw = msg.value

        try:
            alert = json.loads(raw)
        except json.JSONDecodeError:
            stats["json_error"] += 1
            continue

        path = _hourly_file(output_dir, alert.get("alert_ts"))
        _append_jsonl(path, json.dumps(alert, separators=(",", ":"), ensure_ascii=True))
        stats["written"] += 1

        now = datetime.now(timezone.utc)
        if (now - last_log_ts).total_seconds() >= log_interval_sec:
            LOGGER.info("alerts-sink stats: %s", json.dumps(stats, ensure_ascii=True, sort_keys=True))
            last_log_ts = now


if __name__ == "__main__":
    main()
