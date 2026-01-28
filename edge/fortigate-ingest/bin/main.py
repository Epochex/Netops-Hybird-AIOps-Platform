import datetime
import os
import signal
import sys
import time
from typing import Any, Dict, Optional

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

# 空转 sleep：避免 while True 空跑
IDLE_SLEEP_SEC = 0.2

# follow_active_binary 在无数据时最多等多久返回（秒）
ACTIVE_POLL_MAX_WAIT_SEC = 0.5

# 全局退出标志
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


def _write_dlq(ck: Dict[str, Any], reason: str, raw: str, source: Dict[str, Any]) -> None:
    dlq = {
        "schema_version": 1,
        "ingest_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
    event["ingest_ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    event["source"] = {"path": source.get("path"), "inode": source.get("inode"), "offset": source.get("offset")}
    try:
        append_event(_ingest_ts(), event)
        ck["counters"]["events_out_total"] += 1
        if event.get("event_ts"):
            ck["active"]["last_event_ts_seen"] = event["event_ts"]
    except Exception:
        ck["counters"]["write_fail_total"] += 1


def process_rotated_files(ck: Dict[str, Any]) -> int:
    """
    Process all rotated segments not yet completed.
    Return number of lines processed (for idle detection).
    """
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
    """
    If active file size < ck offset, reset offset to 0 and emit a DLQ record.
    Return True if a reset happened.
    """
    sz = active_size()
    if sz is None:
        return False

    off = int(ck["active"].get("offset", 0))
    if sz < off:
        # emit a DLQ record for audit/debug
        src = {"path": ACTIVE_PATH, "inode": ck["active"].get("inode"), "offset": off, "size": sz}
        _write_dlq(ck, "active_truncated_reset_offset", "", src)

        ck["active"]["offset"] = 0
        return True

    return False


def process_active_tail(ck: Dict[str, Any], max_seconds: float = 2.0) -> int:
    """
    Tail the active file for up to max_seconds.
    Return number of lines processed (for idle detection).
    """
    processed = 0
    start = time.time()

    cur_inode = active_inode()
    if cur_inode is None:
        time.sleep(0.1)
        return 0

    if ck["active"].get("inode") is None:
        ck["active"]["inode"] = cur_inode
        ck["active"]["offset"] = 0

    # rotation detected (inode changed)
    if ck["active"]["inode"] != cur_inode:
        ck["active"]["inode"] = cur_inode
        ck["active"]["offset"] = 0

    # truncate defense
    _handle_active_truncate_if_any(ck)

    offset = int(ck["active"].get("offset", 0))

    # follow_active_binary returns if idle for ACTIVE_POLL_MAX_WAIT_SEC
    for line, new_offset in follow_active_binary(offset, max_wait_sec=ACTIVE_POLL_MAX_WAIT_SEC):
        processed += 1

        # if inode flips while reading, stop and let next loop handle from offset 0
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


def main() -> int:
    global _SHOULD_STOP

    # signals
    signal.signal(signal.SIGTERM, _handle_stop_signal)
    signal.signal(signal.SIGINT, _handle_stop_signal)

    _ensure_dirs()

    ck = load_checkpoint()
    mw = MetricsWindow()

    last_metrics = _now_ts()
    last_flush = _now_ts()

    try:
        while True:
            if _SHOULD_STOP:
                # graceful shutdown: flush checkpoint and exit 0
                _flush_checkpoint(ck)
                # best-effort final metrics
                try:
                    now = _now_ts()
                    metric = mw.build_metrics(ck, now)
                    append_metrics(now, metric)
                except Exception:
                    pass
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

            # idle backoff to avoid busy loop
            if n_rot == 0 and n_act == 0:
                time.sleep(IDLE_SLEEP_SEC)

    except KeyboardInterrupt:
        _flush_checkpoint(ck)
        return 0
    except Exception:
        # crash path: try to persist checkpoint for post-mortem, then exit non-zero
        _flush_checkpoint(ck)
        return 2


if __name__ == "__main__":
    rc = main()
    raise SystemExit(rc)
