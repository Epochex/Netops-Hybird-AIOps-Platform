from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Iterable

from common.data_features import LCORE_D_SOURCE_URL, AdaptiveFeatureExtractor, iter_records_from_paths, row_to_canonical_event
from common.infra.logging_utils import configure_logging

LOGGER = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else raw


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream LCORE-D rows into the edge forwarder's JSONL input directory.")
    parser.add_argument("--input", action="append", default=None, help="Input CSV/JSON/ZIP path. Repeatable.")
    parser.add_argument("--output-jsonl", default=_env_str("LCORE_OUTPUT_JSONL", "/data/netops-runtime/LCORE-D/output/events-lcore-d.jsonl"))
    parser.add_argument("--plan-json", default=_env_str("LCORE_PLAN_JSON", "/data/netops-runtime/LCORE-D/work/feature-plan.json"))
    parser.add_argument("--checkpoint-json", default=_env_str("LCORE_CHECKPOINT_JSON", "/data/netops-runtime/LCORE-D/work/stream-checkpoint.json"))
    parser.add_argument("--dataset-id", default=_env_str("LCORE_DATASET_ID", "lcore-d"))
    parser.add_argument("--source-uri", default=_env_str("LCORE_SOURCE_URI", LCORE_D_SOURCE_URL))
    parser.add_argument("--sample-rows", type=int, default=_env_int("LCORE_SAMPLE_ROWS", 5000))
    parser.add_argument("--events-per-second", type=float, default=_env_float("LCORE_EVENTS_PER_SECOND", 20.0))
    parser.add_argument("--max-records", type=int, default=_env_int("LCORE_MAX_RECORDS", 0), help="0 means stream until EOF.")
    parser.add_argument("--checkpoint-every", type=int, default=_env_int("LCORE_CHECKPOINT_EVERY", 100))
    parser.add_argument("--reset-output", action="store_true", default=_env_str("LCORE_RESET_OUTPUT", "false").lower() in {"1", "true", "yes"})
    return parser.parse_args()


def _default_inputs() -> list[str]:
    raw = _env_str("LCORE_INPUT", "/data/netops-runtime/LCORE-D/raw")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"next_row_index": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOGGER.warning("could not read checkpoint, starting at row 0: %s", path)
        return {"next_row_index": 0}
    if not isinstance(data, dict):
        return {"next_row_index": 0}
    data.setdefault("next_row_index", 0)
    return data


def _save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(checkpoint, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _records(inputs: Iterable[str]) -> Iterable[dict[str, Any]]:
    return iter_records_from_paths(inputs)


def main() -> None:
    configure_logging("lcore-streamer")
    args = _parse_args()

    inputs = args.input if args.input else _default_inputs()
    if not inputs:
        raise SystemExit("no LCORE input paths configured")

    output_path = Path(args.output_jsonl)
    plan_path = Path(args.plan_json)
    checkpoint_path = Path(args.checkpoint_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.parent.mkdir(parents=True, exist_ok=True)

    extractor = AdaptiveFeatureExtractor(
        dataset_id=args.dataset_id,
        source_uri=args.source_uri,
        max_sample_rows=args.sample_rows,
    )
    plan = extractor.build_plan(_records(inputs))
    plan_path.write_text(json.dumps(plan.to_dict(), ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    checkpoint = {"next_row_index": 0} if args.reset_output else _load_checkpoint(checkpoint_path)
    next_row_index = int(checkpoint.get("next_row_index", 0))
    if args.reset_output:
        output_path.write_text("", encoding="utf-8")
        _save_checkpoint(checkpoint_path, checkpoint)

    interval = 0.0 if args.events_per_second <= 0 else 1.0 / args.events_per_second
    streamed = 0
    started = time.monotonic()

    LOGGER.info(
        "lcore streamer started: inputs=%s output=%s eps=%.2f start_row=%d scenario_values=%s",
        inputs,
        output_path,
        args.events_per_second,
        next_row_index,
        plan.scenario_values,
    )

    with output_path.open("a", encoding="utf-8", buffering=1) as fp:
        for row_index, row in enumerate(_records(inputs)):
            if row_index < next_row_index:
                continue
            if args.max_records > 0 and streamed >= args.max_records:
                break

            event = row_to_canonical_event(row, plan, row_index)
            event["dataset_context"]["stream_source"] = "edge.lcore_streamer"
            event["dataset_context"]["stream_row_index"] = row_index
            event["ingest_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            fp.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")

            streamed += 1
            checkpoint["next_row_index"] = row_index + 1
            checkpoint["last_event_id"] = event["event_id"]
            checkpoint["last_event_ts"] = event["event_ts"]

            if streamed % max(args.checkpoint_every, 1) == 0:
                _save_checkpoint(checkpoint_path, checkpoint)

            if interval > 0:
                time.sleep(interval)

    _save_checkpoint(checkpoint_path, checkpoint)
    elapsed = max(time.monotonic() - started, 1e-6)
    LOGGER.info(
        "lcore streamer complete: streamed=%d elapsed_sec=%.2f effective_eps=%.2f next_row_index=%d",
        streamed,
        elapsed,
        streamed / elapsed,
        checkpoint["next_row_index"],
    )


if __name__ == "__main__":
    main()
