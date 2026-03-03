#!/usr/bin/env python3
"""
Sample edge-side throughput for capacity planning.

Metrics over a sampling window:
1) FortiGate active log write speed (bytes/sec)
2) Ingest processing speed from checkpoint counters (lines/events/bytes per sec)
3) TCP egress speed from this host to core node (all ports + Kafka port)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


DEFAULT_ACTIVE_LOG = "/data/fortigate-runtime/input/fortigate.log"
DEFAULT_CHECKPOINT = "/data/fortigate-runtime/work/checkpoint.json"
DEFAULT_PARSED_DIR = "/data/fortigate-runtime/output/parsed"


BYTES_SENT_RE = re.compile(r"bytes_sent:(\d+)")
BYTES_ACKED_RE = re.compile(r"bytes_acked:(\d+)")


@dataclass
class ConnStats:
    peer_port: int
    bytes_sent: int
    bytes_acked: int


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sample edge log/ingest/core-send rates.")
    p.add_argument("--duration", type=int, default=60, help="Sample duration seconds (default: 60)")
    p.add_argument("--interval", type=float, default=1.0, help="Network sampling interval seconds (default: 1.0)")
    p.add_argument("--core-ip", required=True, help="Core node IP (e.g. 192.168.1.27)")
    p.add_argument("--core-port", type=int, default=9092, help="Kafka broker port on core (default: 9092)")
    p.add_argument("--active-log", default=DEFAULT_ACTIVE_LOG, help="Active log path")
    p.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT, help="Checkpoint JSON path")
    p.add_argument("--parsed-dir", default=DEFAULT_PARSED_DIR, help="Parsed output directory")
    p.add_argument("--json-only", action="store_true", help="Print only JSON result")
    return p.parse_args()


def parse_endpoint(ep: str) -> Tuple[str, int]:
    ep = ep.strip()
    if ep.startswith("["):
        rb = ep.rfind("]:")
        if rb != -1:
            host = ep[1:rb]
            return normalize_ip(host), int(ep[rb + 2 :])
    host, port = ep.rsplit(":", 1)
    return normalize_ip(host), int(port)


def normalize_ip(ip: str) -> str:
    if ip.startswith("::ffff:"):
        return ip.split("::ffff:", 1)[1]
    return ip


def snapshot_core_tcp(core_ip: str) -> Dict[str, ConnStats]:
    """
    Snapshot established TCP connections to core_ip from this host.
    Key is local->peer tuple string. Values include bytes_sent/bytes_acked.
    """
    cmd = ["ss", "-tin", "dst", core_ip]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = proc.stdout.splitlines()

    result: Dict[str, ConnStats] = {}
    for i, line in enumerate(out):
        if not line.startswith("ESTAB"):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_ep = parts[3]
        peer_ep = parts[4]
        try:
            _, peer_port = parse_endpoint(peer_ep)
        except Exception:
            continue

        detail = out[i + 1] if (i + 1) < len(out) else ""
        m_sent = BYTES_SENT_RE.search(detail)
        m_acked = BYTES_ACKED_RE.search(detail)
        sent = int(m_sent.group(1)) if m_sent else 0
        acked = int(m_acked.group(1)) if m_acked else 0

        key = f"{local_ep}->{peer_ep}"
        result[key] = ConnStats(peer_port=peer_port, bytes_sent=sent, bytes_acked=acked)
    return result


def load_checkpoint(path: str) -> Dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_file_stat(path: str) -> Tuple[int, int]:
    st = os.stat(path)
    return st.st_ino, st.st_size


def dir_size_bytes(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for fn in files:
            fp = os.path.join(root, fn)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total


def safe_delta(new_v: int, old_v: int) -> int:
    d = new_v - old_v
    return d if d >= 0 else 0


def fmt_rate(v: float) -> str:
    return f"{v:,.2f}"


def main() -> int:
    args = parse_args()

    t0 = time.time()
    ck0 = load_checkpoint(args.checkpoint)
    ino0, size0 = get_file_stat(args.active_log)
    parsed0 = dir_size_bytes(args.parsed_dir)
    tcp_prev = snapshot_core_tcp(args.core_ip)

    net_all_sent = 0
    net_all_acked = 0
    net_kafka_sent = 0
    net_kafka_acked = 0

    end_ts = t0 + args.duration
    while True:
        now = time.time()
        if now >= end_ts:
            break
        time.sleep(min(args.interval, end_ts - now))
        cur = snapshot_core_tcp(args.core_ip)

        for key, stats in cur.items():
            prev = tcp_prev.get(key)
            if prev is None:
                ds = stats.bytes_sent
                da = stats.bytes_acked
            else:
                ds = safe_delta(stats.bytes_sent, prev.bytes_sent)
                da = safe_delta(stats.bytes_acked, prev.bytes_acked)

            net_all_sent += ds
            net_all_acked += da
            if stats.peer_port == args.core_port:
                net_kafka_sent += ds
                net_kafka_acked += da

        tcp_prev = cur

    t1 = time.time()
    elapsed = max(0.001, t1 - t0)

    ck1 = load_checkpoint(args.checkpoint)
    ino1, size1 = get_file_stat(args.active_log)
    parsed1 = dir_size_bytes(args.parsed_dir)

    counters0 = ck0.get("counters", {})
    counters1 = ck1.get("counters", {})

    bytes_in_delta = safe_delta(int(counters1.get("bytes_in_total", 0)), int(counters0.get("bytes_in_total", 0)))
    lines_in_delta = safe_delta(int(counters1.get("lines_in_total", 0)), int(counters0.get("lines_in_total", 0)))
    events_out_delta = safe_delta(int(counters1.get("events_out_total", 0)), int(counters0.get("events_out_total", 0)))
    dlq_out_delta = safe_delta(int(counters1.get("dlq_out_total", 0)), int(counters0.get("dlq_out_total", 0)))

    log_rotated = (ino0 != ino1)
    if not log_rotated and size1 >= size0:
        log_write_bytes = size1 - size0
        log_write_bps = log_write_bytes / elapsed
    else:
        log_write_bytes = None
        log_write_bps = None

    parsed_write_bytes = safe_delta(parsed1, parsed0)
    parsed_write_bps = parsed_write_bytes / elapsed

    result = {
        "sample": {
            "start_epoch": t0,
            "end_epoch": t1,
            "elapsed_sec": elapsed,
            "duration_requested_sec": args.duration,
            "interval_sec": args.interval,
        },
        "input_log": {
            "path": args.active_log,
            "inode_start": ino0,
            "inode_end": ino1,
            "rotated_during_sample": log_rotated,
            "bytes_written": log_write_bytes,
            "bytes_per_sec": log_write_bps,
        },
        "ingest": {
            "bytes_in_delta": bytes_in_delta,
            "lines_in_delta": lines_in_delta,
            "events_out_delta": events_out_delta,
            "dlq_out_delta": dlq_out_delta,
            "bytes_in_per_sec": bytes_in_delta / elapsed,
            "lines_in_per_sec": lines_in_delta / elapsed,
            "events_out_per_sec": events_out_delta / elapsed,
            "dlq_out_per_sec": dlq_out_delta / elapsed,
        },
        "sink_to_disk": {
            "parsed_dir": args.parsed_dir,
            "bytes_written_delta": parsed_write_bytes,
            "bytes_written_per_sec": parsed_write_bps,
        },
        "to_core_tcp": {
            "core_ip": args.core_ip,
            "all_ports": {
                "bytes_sent_delta": net_all_sent,
                "bytes_acked_delta": net_all_acked,
                "bytes_sent_per_sec": net_all_sent / elapsed,
                "bytes_acked_per_sec": net_all_acked / elapsed,
            },
            "kafka_port_only": {
                "port": args.core_port,
                "bytes_sent_delta": net_kafka_sent,
                "bytes_acked_delta": net_kafka_acked,
                "bytes_sent_per_sec": net_kafka_sent / elapsed,
                "bytes_acked_per_sec": net_kafka_acked / elapsed,
            },
        },
        "notes": [
            "kafka_port_only approximates producer->broker throughput if your producer uses the given core port.",
            "all_ports includes every TCP flow to core_ip (k8s control-plane traffic may be included).",
            "if input_log rotated during sampling, input log bytes_per_sec is set to null to avoid wrong values.",
        ],
    }

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=False))
        return 0

    print("=== Edge Throughput Sample ===")
    print(f"elapsed_sec: {elapsed:.2f}")
    print("")
    print("[1] Input log write speed")
    if log_write_bps is None:
        print("  rotated during sample: yes, bytes_per_sec unavailable")
    else:
        print(f"  bytes_written: {log_write_bytes:,}")
        print(f"  bytes_per_sec: {fmt_rate(log_write_bps)}")
    print("")
    print("[2] Ingest speed (from checkpoint counters)")
    print(f"  bytes_in_per_sec:   {fmt_rate(result['ingest']['bytes_in_per_sec'])}")
    print(f"  lines_in_per_sec:   {fmt_rate(result['ingest']['lines_in_per_sec'])}")
    print(f"  events_out_per_sec: {fmt_rate(result['ingest']['events_out_per_sec'])}")
    print(f"  dlq_out_per_sec:    {fmt_rate(result['ingest']['dlq_out_per_sec'])}")
    print("")
    print("[3] Send to core")
    print(f"  all_ports bytes_sent_per_sec: {fmt_rate(result['to_core_tcp']['all_ports']['bytes_sent_per_sec'])}")
    print(
        f"  kafka:{args.core_port} bytes_sent_per_sec: "
        f"{fmt_rate(result['to_core_tcp']['kafka_port_only']['bytes_sent_per_sec'])}"
    )
    print("")
    print("JSON_RESULT:")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
