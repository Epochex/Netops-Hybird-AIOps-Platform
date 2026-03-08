import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from kafka import KafkaConsumer, TopicPartition


def _parse_alert_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_consumer(bootstrap_servers: str) -> KafkaConsumer:
    return KafkaConsumer(
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        value_deserializer=lambda b: b.decode("utf-8"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Observe alert quality for the last N hours from Kafka topic.")
    parser.add_argument("--bootstrap-servers", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    parser.add_argument("--topic", default=os.getenv("KAFKA_TOPIC_ALERTS", "netops.alerts.v1"))
    parser.add_argument("--lookback-hours", type=float, default=3.0)
    parser.add_argument("--idle-exit-sec", type=int, default=15)
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(args.lookback_hours, 0.1))
    cutoff_ms = int(cutoff.timestamp() * 1000)

    consumer = _build_consumer(args.bootstrap_servers)
    partitions = sorted(list(consumer.partitions_for_topic(args.topic) or []))
    if not partitions:
        print(json.dumps({"error": "topic_not_found_or_no_partitions", "topic": args.topic}, ensure_ascii=True))
        return

    tps = [TopicPartition(args.topic, p) for p in partitions]
    consumer.assign(tps)
    offsets_for_times = consumer.offsets_for_times({tp: cutoff_ms for tp in tps})
    for tp in tps:
        target = offsets_for_times.get(tp)
        if target is None:
            consumer.seek_to_end(tp)
        else:
            consumer.seek(tp, target.offset)

    stats: dict[str, Any] = {
        "window_start_utc": cutoff.isoformat(),
        "window_end_utc": now.isoformat(),
        "messages_scanned": 0,
        "alerts_in_window_event_ts": 0,
        "alerts_in_window_emit_ts": 0,
        "severity_counts_event_ts": Counter(),
        "severity_counts_emit_ts": Counter(),
        "rule_counts_event_ts": Counter(),
        "rule_counts_emit_ts": Counter(),
        "warning_rule_counts": Counter(),
        "warning_top_service": Counter(),
        "warning_top_source": Counter(),
    }

    last_seen = time.time()
    while True:
        batch = consumer.poll(timeout_ms=1000, max_records=3000)
        got = False
        for records in batch.values():
            for msg in records:
                got = True
                stats["messages_scanned"] += 1
                try:
                    alert = json.loads(msg.value)
                except json.JSONDecodeError:
                    continue

                emit_ts = datetime.fromtimestamp((msg.timestamp or 0) / 1000, tz=timezone.utc)
                in_emit_window = emit_ts >= cutoff
                if in_emit_window:
                    stats["alerts_in_window_emit_ts"] += 1
                    severity_emit = str(alert.get("severity") or "unknown")
                    rule_emit = str(alert.get("rule_id") or "unknown")
                    stats["severity_counts_emit_ts"][severity_emit] += 1
                    stats["rule_counts_emit_ts"][rule_emit] += 1

                alert_ts = _parse_alert_ts(alert.get("alert_ts"))
                if alert_ts is None or alert_ts < cutoff:
                    continue

                stats["alerts_in_window_event_ts"] += 1
                severity = str(alert.get("severity") or "unknown")
                rule_id = str(alert.get("rule_id") or "unknown")
                stats["severity_counts_event_ts"][severity] += 1
                stats["rule_counts_event_ts"][rule_id] += 1

                if severity == "warning":
                    stats["warning_rule_counts"][rule_id] += 1
                    excerpt = alert.get("event_excerpt") or {}
                    service = str((excerpt or {}).get("service") or "unknown")
                    source = str((excerpt or {}).get("src_device_key") or (excerpt or {}).get("srcip") or "unknown")
                    stats["warning_top_service"][service] += 1
                    stats["warning_top_source"][source] += 1

        if got:
            last_seen = time.time()
            continue
        if time.time() - last_seen >= args.idle_exit_sec:
            break

    warnings_event = int(stats["severity_counts_event_ts"].get("warning", 0))
    total_event = int(stats["alerts_in_window_event_ts"])
    warning_rate_event = (warnings_event / total_event) if total_event else 0.0
    warnings_emit = int(stats["severity_counts_emit_ts"].get("warning", 0))
    total_emit = int(stats["alerts_in_window_emit_ts"])
    warning_rate_emit = (warnings_emit / total_emit) if total_emit else 0.0

    output = {
        "window_start_utc": stats["window_start_utc"],
        "window_end_utc": stats["window_end_utc"],
        "messages_scanned": int(stats["messages_scanned"]),
        "alerts_in_window_event_ts": total_event,
        "alerts_in_window_emit_ts": total_emit,
        "warning_rate_event_ts": round(warning_rate_event, 6),
        "warning_rate_emit_ts": round(warning_rate_emit, 6),
        "severity_counts_event_ts": dict(stats["severity_counts_event_ts"]),
        "severity_counts_emit_ts": dict(stats["severity_counts_emit_ts"]),
        "rule_counts_event_ts": dict(stats["rule_counts_event_ts"]),
        "rule_counts_emit_ts": dict(stats["rule_counts_emit_ts"]),
        "warning_rule_counts": dict(stats["warning_rule_counts"]),
        "warning_top_service": stats["warning_top_service"].most_common(10),
        "warning_top_source": stats["warning_top_source"].most_common(10),
    }
    print(json.dumps(output, ensure_ascii=True))

    consumer.close()


if __name__ == "__main__":
    main()
