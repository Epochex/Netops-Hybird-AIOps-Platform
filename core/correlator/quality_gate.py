from collections import deque
from typing import Any


class QualityGate:
    """Drop invalid and duplicated events before rule processing."""

    def __init__(self, dedup_cache_size: int = 200_000):
        self._dedup_cache_size = max(dedup_cache_size, 10_000)
        self._seen = set()
        self._order = deque()

    def evaluate(self, event: dict[str, Any]) -> tuple[bool, str]:
        parse_status = str(event.get("parse_status") or "ok").lower()
        if parse_status != "ok":
            return False, "parse_status_not_ok"

        required = ("event_id", "event_ts", "type", "subtype")
        for key in required:
            value = event.get(key)
            if value is None or value == "":
                return False, f"missing_{key}"

        event_id = str(event.get("event_id"))
        if self._is_duplicate(event_id):
            return False, "duplicate_event_id"

        return True, "accepted"

    def _is_duplicate(self, event_id: str) -> bool:
        if event_id in self._seen:
            return True

        self._seen.add(event_id)
        self._order.append(event_id)

        while len(self._order) > self._dedup_cache_size:
            old = self._order.popleft()
            self._seen.discard(old)

        return False
