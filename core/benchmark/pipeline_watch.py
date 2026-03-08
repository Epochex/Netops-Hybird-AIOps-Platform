import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def run(cmd: list[str]) -> str:
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
    return out.strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def collect_pod_health() -> dict[str, Any]:
    out = run(["kubectl", "-n", "netops-core", "get", "pods", "-o", "json"])
    data = json.loads(out)
    health = {"core_correlator_ready": 0, "core_alerts_sink_ready": 0, "core_alerts_sink_restarts": 0}
    for item in data.get("items", []):
        labels = ((item.get("metadata") or {}).get("labels") or {})
        app = labels.get("app")
        statuses = (item.get("status") or {}).get("containerStatuses") or []
        ready = sum(1 for s in statuses if s.get("ready"))
        restarts = sum(int(s.get("restartCount") or 0) for s in statuses)
        if app == "core-correlator":
            health["core_correlator_ready"] += ready
        if app == "core-alerts-sink":
            health["core_alerts_sink_ready"] += ready
            health["core_alerts_sink_restarts"] += restarts
    return health


def collect_edge_line() -> dict[str, Any]:
    try:
        pod = run(["kubectl", "-n", "edge", "get", "pod", "-l", "app=edge-forwarder", "-o", "jsonpath={.items[0].metadata.name}"])
        line = run(["kubectl", "-n", "edge", "logs", pod, "--tail=120"])
    except Exception:
        return {"edge_last_scan": None}
    last = ""
    for x in line.splitlines():
        if "scan complete:" in x:
            last = x
    if not last:
        return {"edge_last_scan": None}
    sent = _extract_num(last, r"sent=(\d+)")
    dropped = _extract_num(last, r"dropped=(\d+)")
    drop_local = _extract_num(last, r"dropped_local_deny=(\d+)")
    drop_bcast = _extract_num(last, r"dropped_broadcast_mdns_nbns=(\d+)")
    return {
        "edge_last_scan": last,
        "edge_sent": sent,
        "edge_dropped": dropped,
        "edge_dropped_local_deny": drop_local,
        "edge_dropped_broadcast_mdns_nbns": drop_bcast,
    }


def _extract_num(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def collect_alert_emit_window(window_min: int, max_scan_sec: int) -> dict[str, Any]:
    script = f"""
import json, time
from collections import Counter
from datetime import datetime, timedelta, timezone
from kafka import KafkaConsumer, TopicPartition
window_min={window_min}
max_scan_sec={max_scan_sec}
now=datetime.now(timezone.utc)
cutoff=now-timedelta(minutes=window_min)
cutoff_ms=int(cutoff.timestamp()*1000)
scan_start=time.time()
consumer=KafkaConsumer(
    bootstrap_servers=['netops-kafka.netops-core.svc.cluster.local:9092'],
    enable_auto_commit=False,
    auto_offset_reset='earliest',
    value_deserializer=lambda b:b.decode('utf-8'),
)
topic='netops.alerts.v1'
parts=sorted(list(consumer.partitions_for_topic(topic) or []))
tps=[TopicPartition(topic,p) for p in parts]
consumer.assign(tps)
offsets=consumer.offsets_for_times({{tp:cutoff_ms for tp in tps}})
for tp in tps:
    x=offsets.get(tp)
    if x is None:
        consumer.seek_to_end(tp)
    else:
        consumer.seek(tp, x.offset)
sev=Counter(); rules=Counter(); kept=0; last=time.time()
while True:
    b=consumer.poll(timeout_ms=1000, max_records=2000)
    got=False
    for recs in b.values():
        for m in recs:
            got=True
            emit_ts=datetime.fromtimestamp((m.timestamp or 0)/1000, tz=timezone.utc)
            if emit_ts < cutoff:
                continue
            kept+=1
            try:
                a=json.loads(m.value)
            except Exception:
                continue
            s=str(a.get('severity') or 'unknown')
            r=str(a.get('rule_id') or 'unknown')
            sev[s]+=1
            rules[r]+=1
    if got:
        last=time.time()
    elif time.time()-last>=8:
        break
    if time.time()-scan_start>=max_scan_sec:
        break
warn=int(sev.get('warning',0))
out={{
  'alerts_emit_window': kept,
  'warning_emit_window': warn,
  'warning_rate_emit_window': round((warn/kept if kept else 0.0), 6),
  'rule_counts_emit_window': dict(rules),
  'severity_counts_emit_window': dict(sev),
}}
print(json.dumps(out, ensure_ascii=True))
consumer.close()
"""
    pod = run(["kubectl", "-n", "netops-core", "get", "pod", "-l", "app=core-correlator", "-o", "jsonpath={.items[0].metadata.name}"])
    out = run(["kubectl", "-n", "netops-core", "exec", "-i", pod, "--", "python", "-c", script])
    return json.loads(out.splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-run pipeline health + warning-noise observer")
    parser.add_argument("--duration-hours", type=float, default=8.0)
    parser.add_argument("--interval-sec", type=int, default=300)
    parser.add_argument("--window-min", type=int, default=30)
    parser.add_argument("--max-scan-sec", type=int, default=25)
    parser.add_argument("--output-jsonl", required=True)
    parser.add_argument("--summary-json", required=True)
    args = parser.parse_args()

    out_path = Path(args.output_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    start = now_utc()
    end = start + timedelta(hours=args.duration_hours)
    samples = 0
    max_warning_rate = 0.0
    alerts_emit_total = 0

    with open(out_path, "a", encoding="utf-8") as fp:
        while now_utc() < end:
            ts = now_utc().isoformat()
            row: dict[str, Any] = {"ts_utc": ts}
            row.update(collect_pod_health())
            row.update(collect_edge_line())
            row.update(collect_alert_emit_window(args.window_min, args.max_scan_sec))
            samples += 1
            alerts_emit_total += int(row.get("alerts_emit_window") or 0)
            max_warning_rate = max(max_warning_rate, float(row.get("warning_rate_emit_window") or 0.0))
            fp.write(json.dumps(row, ensure_ascii=True) + "\n")
            fp.flush()
            time.sleep(max(args.interval_sec, 10))

    summary = {
        "start_utc": start.isoformat(),
        "end_utc": now_utc().isoformat(),
        "duration_hours_target": args.duration_hours,
        "interval_sec": args.interval_sec,
        "window_min": args.window_min,
        "samples": samples,
        "alerts_emit_total": alerts_emit_total,
        "max_warning_rate_emit_window": round(max_warning_rate, 6),
        "judgement": "ok"
        if max_warning_rate <= 0.8
        else "need_tuning",
    }
    Path(args.summary_json).write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True))


if __name__ == "__main__":
    main()
