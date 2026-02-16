import datetime
import json
import os
import signal
import sys
import time
import logging
from typing import Any, Dict

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from checkpoint import load_checkpoint, save_checkpoint, is_completed, mark_completed
from parser_fgt_v1 import parse_fortigate_line
from sink_jsonl import append_event, append_dlq, append_metrics
from source_file import (
    ACTIVE_PATH,
    list_rotated_files,
    stat_file,
    read_whole_file_lines,
    follow_active_binary,
    active_inode,
    active_size,
)
from metrics import MetricsWindow

METRICS_INTERVAL_SEC = 10
CHECKPOINT_FLUSH_INTERVAL_SEC = 2

IDLE_SLEEP_SEC = 0.2
ACTIVE_POLL_MAX_WAIT_SEC = 0.5

_HEARTBEAT_INTERVAL_SEC = 10
_SHOULD_STOP = False


def _handle_stop_signal(signum: int, frame: Any) -> None:
    global _SHOULD_STOP
    _SHOULD_STOP = True


def _now_ts() -> int:
    return int(time.time())


def _ingest_ts() -> int:
    return int(time.time())


def _ensure_dirs() -> None:
    os.makedirs("/data/fortigate-runtime/output/parsed", exist_ok=True)
    os.makedirs("/data/fortigate-runtime/work", exist_ok=True)


def _utc_iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _local_events_filename(ts: int) -> str:
    lt = time.localtime(ts)
    return f"events-{lt.tm_year:04d}{lt.tm_mon:02d}{lt.tm_mday:02d}-{lt.tm_hour:02d}.jsonl"


def _local_metrics_filename(ts: int) -> str:
    lt = time.localtime(ts)
    return f"metrics-{lt.tm_year:04d}{lt.tm_mon:02d}{lt.tm_mday:02d}-{lt.tm_hour:02d}.jsonl"


def _init_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)sZ level=%(levelname)s msg=%(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def _write_dlq(ck: Dict[str, Any], reason: str, raw: str, source: Dict[str, Any]) -> None:
    dlq = {
        "schema_version": 1,
        "ingest_ts": _utc_iso_now(),
        "reason": reason,
        "source": source,
        "raw": raw,
    }
    try:
        append_dlq(_ingest_ts(), dlq)
        ck["counters"]["dlq_out_total"] += 1
        ck["counters"]["parse_fail_total"] += 1
    except Exception:
        ck["counters"]["write_fail_total"] += 1


def _write_event(ck: Dict[str, Any], event: Dict[str, Any], source: Dict[str, Any]) -> None:
    event["ingest_ts"] = _utc_iso_now()
    event["source"] = {"path": source.get("path"), "inode": source.get("inode"), "offset": source.get("offset")}
    try:
        append_event(_ingest_ts(), event)
        ck["counters"]["events_out_total"] += 1
        if event.get("event_ts"):
            ck["active"]["last_event_ts_seen"] = event["event_ts"]
    except Exception:
        ck["counters"]["write_fail_total"] += 1


def process_rotated_files(ck: Dict[str, Any]) -> int:
    processed = 0

    for path in list_rotated_files():
        try:
            inode, size, mtime = stat_file(path)
        except FileNotFoundError:
            continue

        if is_completed(ck, path, inode, size, mtime):
            continue

        for line, src in read_whole_file_lines(path):
            processed += 1

            raw = line
            ck["counters"]["lines_in_total"] += 1
            ck["counters"]["bytes_in_total"] += len(raw.encode("utf-8", errors="replace"))

            now_year = datetime.datetime.now().year
            event, dlq = parse_fortigate_line(raw, now_year)
            if event is not None:
                _write_event(ck, event, src)
            else:
                reason = dlq.get("reason", "parse_fail") if dlq else "parse_fail"
                _write_dlq(ck, reason, raw, src)

        mark_completed(ck, path, inode, size, mtime)

    return processed


def _handle_active_truncate_if_any(ck: Dict[str, Any]) -> bool:
    sz = active_size()
    if sz is None:
        return False

    off = int(ck["active"].get("offset", 0))
    if sz < off:
        src = {"path": ACTIVE_PATH, "inode": ck["active"].get("inode"), "offset": off, "size": sz}
        _write_dlq(ck, "active_truncated_reset_offset", "", src)
        ck["active"]["offset"] = 0
        return True

    return False


def process_active_tail(ck: Dict[str, Any], max_seconds: float = 2.0) -> int:
    processed = 0
    start = time.time()

    cur_inode = active_inode()
    if cur_inode is None:
        time.sleep(0.1)
        return 0

    if ck["active"].get("inode") is None:
        ck["active"]["inode"] = cur_inode
        ck["active"]["offset"] = 0

    if ck["active"]["inode"] != cur_inode:
        ck["active"]["inode"] = cur_inode
        ck["active"]["offset"] = 0

    _handle_active_truncate_if_any(ck)

    offset = int(ck["active"].get("offset", 0))

    for line, new_offset in follow_active_binary(offset, max_wait_sec=ACTIVE_POLL_MAX_WAIT_SEC):
        processed += 1

        new_inode = active_inode()
        if new_inode is not None and new_inode != ck["active"]["inode"]:
            ck["active"]["inode"] = new_inode
            ck["active"]["offset"] = 0
            break

        raw = line
        ck["counters"]["lines_in_total"] += 1
        ck["counters"]["bytes_in_total"] += len(raw.encode("utf-8", errors="replace"))

        src = {"path": ACTIVE_PATH, "inode": ck["active"]["inode"], "offset": new_offset}
        now_year = datetime.datetime.now().year
        event, dlq = parse_fortigate_line(raw, now_year)
        if event is not None:
            _write_event(ck, event, src)
        else:
            reason = dlq.get("reason", "parse_fail") if dlq else "parse_fail"
            _write_dlq(ck, reason, raw, src)

        ck["active"]["offset"] = int(new_offset)
        offset = int(new_offset)

        if (time.time() - start) >= max_seconds:
            break

    return processed


def _flush_checkpoint(ck: Dict[str, Any]) -> None:
    try:
        save_checkpoint(ck)
    except Exception:
        ck["counters"]["checkpoint_fail_total"] += 1


def _counters_snapshot(ck: Dict[str, Any]) -> Dict[str, int]:
    c = ck.get("counters", {})
    def g(k: str) -> int:
        try:
            return int(c.get(k, 0))
        except Exception:
            return 0
    return {
        "lines_in_total": g("lines_in_total"),
        "bytes_in_total": g("bytes_in_total"),
        "events_out_total": g("events_out_total"),
        "dlq_out_total": g("dlq_out_total"),
        "parse_fail_total": g("parse_fail_total"),
        "write_fail_total": g("write_fail_total"),
        "checkpoint_fail_total": g("checkpoint_fail_total"),
    }


def _delta(now: Dict[str, int], prev: Dict[str, int]) -> Dict[str, int]:
    out = {}
    for k, v in now.items():
        out[k] = v - int(prev.get(k, 0))
    return out


def _emit_heartbeat(
    start_ts: int,
    ck: Dict[str, Any],
    prev_counters: Dict[str, int],
    last_hb_ts: int,
) -> Dict[str, int]:
    now_ts = _now_ts()
    cur = _counters_snapshot(ck)
    d = _delta(cur, prev_counters)

    act_inode = ck.get("active", {}).get("inode")
    act_off = ck.get("active", {}).get("offset")
    act_sz = active_size()
    lag = None
    try:
        if act_sz is not None and act_off is not None:
            lag = int(act_sz) - int(act_off)
    except Exception:
        lag = None

    payload = {
        "kind": "heartbeat",
        "ts": _utc_iso_now(),
        "uptime_sec": now_ts - start_ts,
        "active": {
            "path": ACTIVE_PATH,
            "inode": act_inode,
            "offset": act_off,
            "size": act_sz,
            "lag_bytes": lag,
        },
        "last_event_ts_seen": ck.get("active", {}).get("last_event_ts_seen"),
        "out_files": {
            "events": _local_events_filename(now_ts),
            "metrics": _local_metrics_filename(now_ts),
        },
        "counters_total": cur,
        "counters_delta": d,
        "interval_sec": max(1, now_ts - last_hb_ts),
    }

    logging.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return cur


def main() -> int:
    global _SHOULD_STOP

    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    _init_logging()
    _ensure_dirs()

    start_ts = _now_ts()
    ck = load_checkpoint()
    mw = MetricsWindow()

    last_metrics = _now_ts()
    last_flush = _now_ts()
    last_hb = _now_ts()
    prev_counters = _counters_snapshot(ck)

    logging.info(
        json.dumps(
            {
                "kind": "start",
                "ts": _utc_iso_now(),
                "active_path": ACTIVE_PATH,
                "checkpoint_flush_sec": CHECKPOINT_FLUSH_INTERVAL_SEC,
                "metrics_interval_sec": METRICS_INTERVAL_SEC,
                "heartbeat_interval_sec": _HEARTBEAT_INTERVAL_SEC,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )

    try:
        while True:
            if _SHOULD_STOP:
                _flush_checkpoint(ck)
                try:
                    now = _now_ts()
                    metric = mw.build_metrics(ck, now)
                    append_metrics(now, metric)
                except Exception:
                    pass
                logging.info(json.dumps({"kind": "stop", "ts": _utc_iso_now()}, ensure_ascii=False, separators=(",", ":")))
                return 0

            n_rot = process_rotated_files(ck)
            n_act = process_active_tail(ck, max_seconds=2.0)

            now = _now_ts()

            if now - last_flush >= CHECKPOINT_FLUSH_INTERVAL_SEC:
                _flush_checkpoint(ck)
                last_flush = now

            if now - last_metrics >= METRICS_INTERVAL_SEC:
                metric = mw.build_metrics(ck, now)
                try:
                    append_metrics(now, metric)
                except Exception:
                    ck["counters"]["write_fail_total"] += 1
                last_metrics = now

            if now - last_hb >= _HEARTBEAT_INTERVAL_SEC:
                prev_counters = _emit_heartbeat(start_ts, ck, prev_counters, last_hb)
                last_hb = now

            if n_rot == 0 and n_act == 0:
                time.sleep(IDLE_SLEEP_SEC)

    except KeyboardInterrupt:
        _flush_checkpoint(ck)
        logging.info(json.dumps({"kind": "stop", "ts": _utc_iso_now()}, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception:
        _flush_checkpoint(ck)
        logging.exception("crash")
        return 2


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
