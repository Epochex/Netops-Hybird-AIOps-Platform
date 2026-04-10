from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from core.aiops_agent.app_config import load_config
from core.aiops_agent.legacy_upgrade import (
    is_legacy_suggestion_payload,
    upgrade_legacy_suggestion_payload,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upgrade legacy AIOps suggestion JSONL files to the current schema.")
    parser.add_argument(
        "--runtime-dir",
        default="/data/netops-runtime/aiops",
        help="Directory containing suggestions-*.jsonl files.",
    )
    parser.add_argument(
        "--glob",
        default="suggestions-*.jsonl",
        help="Glob pattern for suggestion files.",
    )
    parser.add_argument(
        "--backup-dir",
        default="",
        help="Optional directory to store original files before rewrite.",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=0,
        help="Optional limit to the most recent N files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report how many files/records would be upgraded without rewriting files.",
    )
    args = parser.parse_args()

    runtime_dir = Path(args.runtime_dir).resolve()
    files = sorted(runtime_dir.glob(args.glob))
    if args.limit_files > 0:
        files = files[-args.limit_files :]

    config = load_config()
    upgraded_records = 0
    touched_files = 0

    for path in files:
        original_lines = path.read_text(encoding="utf-8").splitlines()
        changed = False
        next_lines: list[str] = []
        for line in original_lines:
            text = line.strip()
            if not text:
                continue
            payload = json.loads(text)
            if is_legacy_suggestion_payload(payload):
                payload = upgrade_legacy_suggestion_payload(payload, config=config)
                changed = True
                upgraded_records += 1
            next_lines.append(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))

        if not changed:
            continue

        touched_files += 1
        if args.dry_run:
            continue

        if args.backup_dir:
            backup_dir = Path(args.backup_dir).resolve()
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_dir / path.name)

        path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "runtime_dir": str(runtime_dir),
                "files_scanned": len(files),
                "files_touched": touched_files,
                "records_upgraded": upgraded_records,
                "dry_run": args.dry_run,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
