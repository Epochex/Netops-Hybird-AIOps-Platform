# FortiGate Ingest Field Reference

This note keeps the field contract out of the root README and focuses on the parts that matter for parsing, replay, and downstream analytics.

## Purpose

`edge/fortigate-ingest` does more than split FortiGate syslog into keys.
It has to preserve enough information for four later jobs:

- resume safely from files and offsets
- normalize event identity and timestamps
- support deterministic core-side correlation
- keep source provenance visible for replay and audit

The parser pipeline is centered on:

- `edge/fortigate-ingest/bin/source_file.py`
- `edge/fortigate-ingest/bin/parser_fgt_v1.py`
- `edge/fortigate-ingest/bin/sink_jsonl.py`
- `edge/fortigate-ingest/bin/checkpoint.py`

## Input Shape

The input is FortiGate syslog with device-level and flow-level fields such as:

- event time: `date`, `time`, `eventtime`, `tz`
- device identity: `devname`, `devid`
- flow identity: `srcip`, `srcport`, `dstip`, `dstport`, `proto`, `service`
- decision fields: `action`, `policyid`, `policytype`
- asset hints: `srcmac`, `mastersrcmac`, `srchwvendor`, `devtype`, `srcfamily`, `osname`

The raw line is useful, but not yet safe to share as a core-side contract.

## Output Contract

The output is JSONL with a stable event contract. The fields below are the ones the rest of the repository depends on most.

| Field group | Representative fields | Why they matter |
| --- | --- | --- |
| Replay and provenance | `source.path`, `source.inode`, `source.offset`, `ingest_ts` | let the edge runtime resume safely and explain where a fact came from |
| Stable identity | `event_id`, `src_device_key`, `sessionid` | support deduplication, device-level grouping, and later correlation |
| Normalized time | `event_ts`, `eventtime`, `tz` | give downstream rules a sortable and replayable event-time contract |
| Network semantics | `srcip`, `srcport`, `dstip`, `dstport`, `proto`, `service` | preserve the flow shape that correlation rules depend on |
| Decision context | `action`, `policyid`, `policytype`, `level`, `subtype` | capture the enforcement outcome and traffic class |
| Asset profile hints | `srcmac`, `mastersrcmac`, `srchwvendor`, `devtype`, `srcfamily`, `srcswversion` | support later device profiling and localization |
| Parser traceability | `parse_status`, `kv_subset` | retain a compact raw-key snapshot for validation and future schema evolution |

## Why `src_device_key` Matters

The repository needs a device-level key that survives replay and downstream aggregation.
Raw FortiGate fields are useful but inconsistent across cases. `src_device_key` is the practical compromise that lets later stages reason about repeat offenders, cluster patterns, and device-localized incidents without carrying the full parser state everywhere.

## Why `kv_subset` Is Preserved

The parsed JSONL record is a normalized contract, but the repository still needs a compact trace back to the original key-value material.
`kv_subset` preserves that bridge. It is not meant to be the main analytics surface; it exists so schema evolution, parser validation, and incident review do not require going back to the original log file for every question.

## Boundary

This document is intentionally narrower than a full parser implementation note.
For system-level context, start from the root README. For current runtime posture, see [PROJECT_STATE_EN.md](./PROJECT_STATE_EN.md).
