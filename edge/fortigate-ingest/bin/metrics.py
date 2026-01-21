import os
import time
from typing import Any, Dict, Optional

ACTIVE_PATH = "/data/fortigate-runtime/input/fortigate.log"

class MetricsWindow:
    def __init__(self) -> None:
        self.last_emit_ts = int(time.time())
        self.prev_counters: Optional[Dict[str, int]] = None

    def _stat_active_size(self) -> Optional[int]:
        try:
            return os.stat(ACTIVE_PATH).st_size
        except FileNotFoundError:
            return None

    def build_metrics(self, ck: Dict[str, Any], now_ts: int) -> Dict[str, Any]:
        counters = ck.get("counters", {})
        active = ck.get("active", {})

        size_bytes = self._stat_active_size()
        offset = active.get("offset", 0)
        lag_bytes = None
        if size_bytes is not None and isinstance(offset, int):
            lag_bytes = size_bytes - offset

        if self.prev_counters is None:
            self.prev_counters = dict(counters)
        dt = max(1, now_ts - self.last_emit_ts)

        def delta(k: str) -> int:
            return int(counters.get(k, 0)) - int(self.prev_counters.get(k, 0))

        metric = {
            "ts": now_ts,
            "active_file_size_bytes": size_bytes,
            "active_read_offset_bytes": offset,
            "active_lag_bytes": lag_bytes,
            "lines_in_total": counters.get("lines_in_total", 0),
            "bytes_in_total": counters.get("bytes_in_total", 0),
            "events_out_total": counters.get("events_out_total", 0),
            "dlq_out_total": counters.get("dlq_out_total", 0),
            "parse_fail_total": counters.get("parse_fail_total", 0),
            "write_fail_total": counters.get("write_fail_total", 0),
            "checkpoint_fail_total": counters.get("checkpoint_fail_total", 0),
            "lines_in_per_sec": delta("lines_in_total") / dt,
            "bytes_in_per_sec": delta("bytes_in_total") / dt,
            "events_out_per_sec": delta("events_out_total") / dt,
            "dlq_out_per_sec": delta("dlq_out_total") / dt,
            "parse_fail_per_sec": delta("parse_fail_total") / dt,
            "last_event_ts_seen": active.get("last_event_ts_seen")
        }

        self.prev_counters = dict(counters)
        self.last_emit_ts = now_ts
        return metric
