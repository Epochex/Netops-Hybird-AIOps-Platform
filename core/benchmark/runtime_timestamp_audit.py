import argparse
import json
from pathlib import Path
from typing import Any


def _read_last_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
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


def _find_latest(path: Path, pattern: str) -> Path | None:
    files = sorted(path.glob(pattern))
    if not files:
        return None
    files.sort(key=lambda p: p.stat().st_mtime)
    return files[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit runtime output timestamp semantics for alerts and aiops suggestions.")
    parser.add_argument("--alerts-dir", default="/data/netops-runtime/alerts")
    parser.add_argument("--aiops-dir", default="/data/netops-runtime/aiops")
    args = parser.parse_args()

    alerts_dir = Path(args.alerts_dir)
    aiops_dir = Path(args.aiops_dir)
    alert_file = _find_latest(alerts_dir, "alerts-*.jsonl")
    suggestion_file = _find_latest(aiops_dir, "suggestions-*.jsonl")

    result: dict[str, Any] = {"alerts": {}, "aiops": {}}

    if alert_file is not None:
        alert_payload = _read_last_json(alert_file) or {}
        result["alerts"] = {
            "latest_file": alert_file.name,
            "file_mtime_epoch": round(alert_file.stat().st_mtime, 3),
            "payload_alert_ts": alert_payload.get("alert_ts"),
            "rule_id": alert_payload.get("rule_id"),
            "source_event_id": alert_payload.get("source_event_id"),
        }

    if suggestion_file is not None:
        suggestion_payload = _read_last_json(suggestion_file) or {}
        result["aiops"] = {
            "latest_file": suggestion_file.name,
            "file_mtime_epoch": round(suggestion_file.stat().st_mtime, 3),
            "payload_suggestion_ts": suggestion_payload.get("suggestion_ts"),
            "alert_id": suggestion_payload.get("alert_id"),
            "rule_id": suggestion_payload.get("rule_id"),
        }

    result["interpretation"] = {
        "alerts_hourly_file_uses": "alert.alert_ts when present",
        "aiops_hourly_file_uses": "current processing time",
        "warning": (
            "If alerts files lag behind aiops file names, first compare latest payload timestamps "
            "before assuming alerts-sink failure."
        ),
    }

    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
