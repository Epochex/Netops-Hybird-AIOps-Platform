import argparse
import json
import subprocess
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kafka import KafkaConsumer, TopicPartition
from kafka.errors import NoBrokersAvailable


def _parse_ts(raw: Any) -> datetime | None:
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


def _utc_iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).isoformat()


def _latest_file(path: Path, pattern: str) -> Path | None:
    files = [p for p in path.glob(pattern) if p.is_file()]
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime)
    return files[-1]


def _read_last_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    last = ""
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                last = line
    if not last:
        return None
    return json.loads(last)


def _event_payload_ts(payload: dict[str, Any], topic_kind: str) -> datetime | None:
    if topic_kind == "raw":
        return _parse_ts(payload.get("event_ts")) or _parse_ts(payload.get("ingest_ts"))
    if topic_kind == "alerts":
        return _parse_ts(payload.get("alert_ts")) or _parse_ts((payload.get("event_excerpt") or {}).get("event_ts"))
    if topic_kind == "suggestions":
        return _parse_ts(payload.get("suggestion_ts"))
    return None


def _peek_topic_latest(bootstrap_servers: str, topic: str, topic_kind: str) -> dict[str, Any]:
    try:
        return _peek_topic_latest_direct(bootstrap_servers, topic, topic_kind)
    except NoBrokersAvailable:
        return _peek_topic_latest_via_kubectl(bootstrap_servers, topic, topic_kind)


def _peek_topic_latest_direct(bootstrap_servers: str, topic: str, topic_kind: str) -> dict[str, Any]:
    consumer = KafkaConsumer(
        bootstrap_servers=[x.strip() for x in bootstrap_servers.split(",") if x.strip()],
        enable_auto_commit=False,
        auto_offset_reset="latest",
        value_deserializer=lambda b: b.decode("utf-8"),
        consumer_timeout_ms=2000,
    )
    try:
        return _collect_topic_samples(consumer, topic, topic_kind) | {"transport": "direct"}
    finally:
        consumer.close()


def _collect_topic_samples(consumer: KafkaConsumer, topic: str, topic_kind: str) -> dict[str, Any]:
    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        return {"topic": topic, "available": False}

    samples: list[dict[str, Any]] = []
    for partition in sorted(partitions):
        tp = TopicPartition(topic, partition)
        consumer.assign([tp])
        end_offsets = consumer.end_offsets([tp])
        end_offset = int(end_offsets.get(tp, 0))
        if end_offset <= 0:
            continue

        consumer.seek(tp, end_offset - 1)
        records = consumer.poll(timeout_ms=2000, max_records=1).get(tp, [])
        if not records:
            continue

        record = records[-1]
        payload: dict[str, Any] | None
        try:
            payload = json.loads(record.value)
        except json.JSONDecodeError:
            payload = None

        broker_ts = None
        if record.timestamp is not None:
            broker_ts = datetime.fromtimestamp(record.timestamp / 1000, tz=timezone.utc)

        payload_ts = _event_payload_ts(payload or {}, topic_kind) if payload is not None else None
        samples.append(
            {
                "partition": partition,
                "offset": record.offset,
                "broker_ts": _utc_iso(broker_ts),
                "payload_ts": _utc_iso(payload_ts),
                "payload_kind": topic_kind,
                "payload_summary": _summarize_payload(payload or {}, topic_kind),
            }
        )

    latest_sample = _pick_latest_sample(samples)
    return {
        "topic": topic,
        "available": True,
        "partitions": len(partitions),
        "latest_partition_sample": latest_sample,
        "samples": samples,
    }


def _peek_topic_latest_via_kubectl(bootstrap_servers: str, topic: str, topic_kind: str) -> dict[str, Any]:
    snippet = r"""
import json
from datetime import datetime, timezone
from kafka import KafkaConsumer, TopicPartition

BOOTSTRAP = __import__("os").environ["LIVE_CHECK_BOOTSTRAP"]
TOPIC = __import__("os").environ["LIVE_CHECK_TOPIC"]
TOPIC_KIND = __import__("os").environ["LIVE_CHECK_TOPIC_KIND"]

def parse_ts(raw):
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

def utc_iso(dt):
    return "" if dt is None else dt.astimezone(timezone.utc).isoformat()

def payload_ts(payload, topic_kind):
    if topic_kind == "raw":
        return parse_ts(payload.get("event_ts")) or parse_ts(payload.get("ingest_ts"))
    if topic_kind == "alerts":
        excerpt = payload.get("event_excerpt") or {}
        return parse_ts(payload.get("alert_ts")) or parse_ts(excerpt.get("event_ts"))
    if topic_kind == "suggestions":
        return parse_ts(payload.get("suggestion_ts"))
    return None

def summarize(payload, topic_kind):
    if topic_kind == "raw":
        return {
            "event_id": str(payload.get("event_id") or ""),
            "event_ts": payload.get("event_ts"),
            "ingest_ts": payload.get("ingest_ts"),
            "type": payload.get("type"),
            "subtype": payload.get("subtype"),
            "action": payload.get("action"),
            "service": payload.get("service"),
            "src_device_key": payload.get("src_device_key"),
        }
    if topic_kind == "alerts":
        excerpt = payload.get("event_excerpt") or {}
        return {
            "alert_id": str(payload.get("alert_id") or ""),
            "alert_ts": payload.get("alert_ts"),
            "rule_id": payload.get("rule_id"),
            "severity": payload.get("severity"),
            "service": excerpt.get("service"),
            "src_device_key": excerpt.get("src_device_key"),
        }
    if topic_kind == "suggestions":
        context = payload.get("context") or {}
        return {
            "suggestion_id": str(payload.get("suggestion_id") or ""),
            "suggestion_ts": payload.get("suggestion_ts"),
            "rule_id": payload.get("rule_id"),
            "alert_id": payload.get("alert_id"),
            "service": context.get("service"),
            "src_device_key": context.get("src_device_key"),
        }
    return {}

consumer = KafkaConsumer(
    bootstrap_servers=[x.strip() for x in BOOTSTRAP.split(",") if x.strip()],
    enable_auto_commit=False,
    auto_offset_reset="latest",
    value_deserializer=lambda b: b.decode("utf-8"),
    consumer_timeout_ms=2000,
)
try:
    partitions = consumer.partitions_for_topic(TOPIC)
    if not partitions:
        print(json.dumps({"topic": TOPIC, "available": False}))
        raise SystemExit(0)
    samples = []
    for partition in sorted(partitions):
        tp = TopicPartition(TOPIC, partition)
        consumer.assign([tp])
        end_offsets = consumer.end_offsets([tp])
        end_offset = int(end_offsets.get(tp, 0))
        if end_offset <= 0:
            continue
        consumer.seek(tp, end_offset - 1)
        records = consumer.poll(timeout_ms=2000, max_records=1).get(tp, [])
        if not records:
            continue
        record = records[-1]
        try:
            payload = json.loads(record.value)
        except json.JSONDecodeError:
            payload = {}
        broker_ts = None
        if record.timestamp is not None:
            broker_ts = datetime.fromtimestamp(record.timestamp / 1000, tz=timezone.utc)
        samples.append({
            "partition": partition,
            "offset": record.offset,
            "broker_ts": utc_iso(broker_ts),
            "payload_ts": utc_iso(payload_ts(payload, TOPIC_KIND)),
            "payload_kind": TOPIC_KIND,
            "payload_summary": summarize(payload, TOPIC_KIND),
        })
    latest = max(samples, key=lambda item: (str(item.get("broker_ts") or ""), str(item.get("payload_ts") or ""), int(item.get("offset") or 0))) if samples else {}
    print(json.dumps({
        "topic": TOPIC,
        "available": True,
        "partitions": len(partitions),
        "latest_partition_sample": latest,
        "samples": samples,
        "transport": "kubectl-exec",
    }))
finally:
    consumer.close()
"""
    cmd = [
        "kubectl",
        "exec",
        "-n",
        "netops-core",
        "deploy/core-correlator",
        "--",
        "sh",
        "-lc",
        (
            f"LIVE_CHECK_BOOTSTRAP='{bootstrap_servers}' "
            f"LIVE_CHECK_TOPIC='{topic}' "
            f"LIVE_CHECK_TOPIC_KIND='{topic_kind}' "
            "python - <<'PY'\n"
            f"{snippet}\n"
            "PY"
        ),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return {
            "topic": topic,
            "available": False,
            "transport": "kubectl-exec",
            "error": (result.stderr or result.stdout).strip(),
        }
    try:
        return json.loads(result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {
            "topic": topic,
            "available": False,
            "transport": "kubectl-exec",
            "error": result.stdout.strip(),
        }


def _pick_latest_sample(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {}

    def sort_key(item: dict[str, Any]) -> tuple[str, str, int]:
        return (
            str(item.get("broker_ts") or ""),
            str(item.get("payload_ts") or ""),
            int(item.get("offset") or 0),
        )

    return max(samples, key=sort_key)


def _summarize_payload(payload: dict[str, Any], topic_kind: str) -> dict[str, Any]:
    if topic_kind == "raw":
        return {
            "event_id": str(payload.get("event_id") or ""),
            "event_ts": payload.get("event_ts"),
            "ingest_ts": payload.get("ingest_ts"),
            "type": payload.get("type"),
            "subtype": payload.get("subtype"),
            "action": payload.get("action"),
            "service": payload.get("service"),
            "src_device_key": payload.get("src_device_key"),
        }
    if topic_kind == "alerts":
        excerpt = payload.get("event_excerpt") or {}
        return {
            "alert_id": str(payload.get("alert_id") or ""),
            "alert_ts": payload.get("alert_ts"),
            "rule_id": payload.get("rule_id"),
            "severity": payload.get("severity"),
            "service": excerpt.get("service"),
            "src_device_key": excerpt.get("src_device_key"),
        }
    if topic_kind == "suggestions":
        context = payload.get("context") or {}
        return {
            "suggestion_id": str(payload.get("suggestion_id") or ""),
            "suggestion_ts": payload.get("suggestion_ts"),
            "rule_id": payload.get("rule_id"),
            "alert_id": payload.get("alert_id"),
            "service": context.get("service"),
            "src_device_key": context.get("src_device_key"),
        }
    return {}


def _iter_recent_alerts(alert_dir: Path, sample_limit: int) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for path in sorted(alert_dir.glob("alerts-*.jsonl")):
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    alert = json.loads(line)
                except json.JSONDecodeError:
                    continue
                alert["_source_file"] = path.name
                alerts.append(alert)

    alerts.sort(
        key=lambda x: (
            _parse_ts(x.get("alert_ts")) or datetime.min.replace(tzinfo=timezone.utc),
            str(x.get("alert_id") or ""),
        )
    )
    if sample_limit > 0:
        return alerts[-sample_limit:]
    return alerts


def _alert_presence_report(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(alerts)
    if total == 0:
        return {"sample_size": 0}

    src_device_key_present = 0
    service_present = 0
    device_profile_present = 0
    change_context_present = 0
    topology_context_present = 0
    latest_alert_ts = None
    latest_event_ts = None
    source_files: deque[str] = deque(maxlen=10)

    for alert in alerts:
        excerpt = alert.get("event_excerpt") or {}
        topology = alert.get("topology_context") or {}
        device_profile = alert.get("device_profile") or {}
        change_context = alert.get("change_context") or {}

        if excerpt.get("src_device_key"):
            src_device_key_present += 1
        if excerpt.get("service"):
            service_present += 1
        if topology.get("site") or topology.get("zone") or topology.get("srcintf") or topology.get("dstintf"):
            topology_context_present += 1
        if any(device_profile.get(k) for k in ["device_role", "vendor", "device_name", "asset_tags", "known_services"]):
            device_profile_present += 1
        if change_context.get("suspected_change") or change_context.get("change_refs") or change_context.get("score") is not None:
            change_context_present += 1

        alert_ts = _parse_ts(alert.get("alert_ts"))
        event_ts = _parse_ts(excerpt.get("event_ts"))
        if alert_ts is not None and (latest_alert_ts is None or alert_ts > latest_alert_ts):
            latest_alert_ts = alert_ts
        if event_ts is not None and (latest_event_ts is None or event_ts > latest_event_ts):
            latest_event_ts = event_ts
        source_file = str(alert.get("_source_file") or "")
        if source_file:
            source_files.append(source_file)

    return {
        "sample_size": total,
        "sample_latest_alert_ts": _utc_iso(latest_alert_ts),
        "sample_latest_event_ts": _utc_iso(latest_event_ts),
        "presence_rates": {
            "src_device_key": round(src_device_key_present / total, 6),
            "service": round(service_present / total, 6),
            "topology_context": round(topology_context_present / total, 6),
            "device_profile": round(device_profile_present / total, 6),
            "change_context": round(change_context_present / total, 6),
        },
        "recent_source_files": list(source_files),
    }


def _history_assessment(raw_sample: dict[str, Any], alert_report: dict[str, Any], stale_sec: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    raw_payload_ts = _parse_ts(((raw_sample.get("latest_partition_sample") or {}).get("payload_ts")))
    alert_event_ts = _parse_ts(alert_report.get("sample_latest_event_ts"))
    suggestion_ts = None

    assessment: dict[str, Any] = {
        "stale_threshold_sec": stale_sec,
        "history_backlog_suspected": False,
    }

    if raw_payload_ts is not None:
        assessment["latest_raw_payload_age_sec"] = int((now - raw_payload_ts).total_seconds())
        if (now - raw_payload_ts).total_seconds() > stale_sec:
            assessment["history_backlog_suspected"] = True

    if alert_event_ts is not None:
        assessment["latest_alert_event_age_sec"] = int((now - alert_event_ts).total_seconds())
        if (now - alert_event_ts).total_seconds() > stale_sec:
            assessment["history_backlog_suspected"] = True

    return assessment


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=True, sort_keys=True, indent=2)
        fp.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Check live runtime state across Kafka raw/alerts/suggestions and local sinks.")
    parser.add_argument("--bootstrap-servers", default="netops-kafka.netops-core.svc.cluster.local:9092")
    parser.add_argument("--topic-raw", default="netops.facts.raw.v1")
    parser.add_argument("--topic-alerts", default="netops.alerts.v1")
    parser.add_argument("--topic-suggestions", default="netops.aiops.suggestions.v1")
    parser.add_argument("--alerts-dir", default="/data/netops-runtime/alerts")
    parser.add_argument("--aiops-dir", default="/data/netops-runtime/aiops")
    parser.add_argument("--alert-sample-size", type=int, default=1000)
    parser.add_argument("--stale-threshold-sec", type=int, default=3600)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    alerts_dir = Path(args.alerts_dir)
    aiops_dir = Path(args.aiops_dir)
    report_ts = datetime.now(timezone.utc)

    raw_topic = _peek_topic_latest(args.bootstrap_servers, args.topic_raw, "raw")
    alerts_topic = _peek_topic_latest(args.bootstrap_servers, args.topic_alerts, "alerts")
    suggestions_topic = _peek_topic_latest(args.bootstrap_servers, args.topic_suggestions, "suggestions")

    latest_alert_file = _latest_file(alerts_dir, "alerts-*.jsonl")
    latest_suggestion_file = _latest_file(aiops_dir, "suggestions-*.jsonl")
    latest_alert_payload = _read_last_json(latest_alert_file) or {}
    latest_suggestion_payload = _read_last_json(latest_suggestion_file) or {}
    alert_report = _alert_presence_report(_iter_recent_alerts(alerts_dir, args.alert_sample_size))

    report = {
        "report_ts": report_ts.isoformat(),
        "kafka_topics": {
            "raw": raw_topic,
            "alerts": alerts_topic,
            "suggestions": suggestions_topic,
        },
        "local_sinks": {
            "alerts": {
                "latest_file": latest_alert_file.name if latest_alert_file else "",
                "latest_file_mtime": _utc_iso(
                    datetime.fromtimestamp(latest_alert_file.stat().st_mtime, tz=timezone.utc) if latest_alert_file else None
                ),
                "latest_payload_summary": _summarize_payload(latest_alert_payload, "alerts") if latest_alert_payload else {},
            },
            "suggestions": {
                "latest_file": latest_suggestion_file.name if latest_suggestion_file else "",
                "latest_file_mtime": _utc_iso(
                    datetime.fromtimestamp(latest_suggestion_file.stat().st_mtime, tz=timezone.utc) if latest_suggestion_file else None
                ),
                "latest_payload_summary": _summarize_payload(latest_suggestion_payload, "suggestions") if latest_suggestion_payload else {},
            },
        },
        "recent_alert_presence": alert_report,
        "history_assessment": _history_assessment(raw_topic, alert_report, max(args.stale_threshold_sec, 60)),
        "interpretation": {
            "alerts_files_follow": "alert.alert_ts",
            "suggestions_files_follow": "current processing time",
            "note": "A large raw/alert payload age while suggestions continue usually indicates backlog or replay, not sink failure.",
        },
    }

    output_json = args.output_json.strip()
    if not output_json:
        output_json = (
            "/data/netops-runtime/observability/"
            f"live-runtime-check-{report_ts.strftime('%Y%m%d-%H%M%S')}.json"
        )
    _write_report(Path(output_json), report)
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
