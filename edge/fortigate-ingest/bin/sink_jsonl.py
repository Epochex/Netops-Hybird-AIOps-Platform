import json
import os
import time
from typing import Any, Dict

PARSED_DIR = "/data/fortigate-runtime/output/parsed"
EVENTS_PREFIX = "events"
DLQ_PREFIX = "dlq"
METRICS_PREFIX = "metrics"


def _hour_key(ts_epoch: int) -> str:
    t = time.localtime(ts_epoch)
    return f"{t.tm_year:04d}{t.tm_mon:02d}{t.tm_mday:02d}-{t.tm_hour:02d}"


def _path_for(prefix: str, hour_key: str) -> str:
    return os.path.join(PARSED_DIR, f"{prefix}-{hour_key}.jsonl")


def _append_line(path: str, line: str) -> None:
    os.makedirs(PARSED_DIR, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def append_jsonl(prefix: str, ts_epoch: int, obj: Dict[str, Any]) -> None:
    hour_key = _hour_key(ts_epoch)
    path = _path_for(prefix, hour_key)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n"
    _append_line(path, line)


def append_event(ts_epoch: int, event: Dict[str, Any]) -> None:
    append_jsonl(EVENTS_PREFIX, ts_epoch, event)


def append_dlq(ts_epoch: int, dlq: Dict[str, Any]) -> None:
    append_jsonl(DLQ_PREFIX, ts_epoch, dlq)


def append_metrics(ts_epoch: int, metric_obj: Dict[str, Any]) -> None:
    append_jsonl(METRICS_PREFIX, ts_epoch, metric_obj)
