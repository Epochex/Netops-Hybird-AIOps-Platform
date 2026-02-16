# FortiGate Parsed Event Contract (v1)

## Scope
This document defines the **stable contract** for parsed FortiGate log events produced by the edge ingest pipeline.

- Producer: edge/fortigate-ingest
- Output format: JSON Lines (one JSON object per line)
- Primary artifact: `/data/fortigate-runtime/output/parsed/events-YYYYMMDD-HH.jsonl`
- Metrics artifact: `/data/fortigate-runtime/output/parsed/metrics-YYYYMMDD-HH.jsonl`

## Stability Rules
This contract is split into two layers:

1) **Core Contract (stable)**
- Downstream systems may rely on these fields.
- **Breaking changes require `schema_version` bump.**

2) **Extended Fields (flexible)**
- Producer may add/remove fields without bumping `schema_version`,
  as long as Core Contract remains compatible.

## Core Contract (schema_version = 1)

### Required fields (MUST)
| Field | Type | Notes |
|------|------|------|
| `schema_version` | int | Must be `1` |
| `event_id` | string | Stable identifier (replay produces the same id) |
| `event_ts` | string\|null | ISO8601 with timezone, original event time if available |
| `ingest_ts` | string | ISO8601 UTC timestamp generated at ingest |
| `type` | string\|null | FortiGate `type` (e.g., `traffic`, `event`) |
| `subtype` | string\|null | FortiGate `subtype` |
| `level` | string\|null | FortiGate `level` |
| `devname` | string\|null | Device name |
| `devid` | string\|null | Device id |
| `vd` | string\|null | VDOM |
| `parse_status` | string | `ok` for successfully parsed events (recommended) |
| `source` | object | Provenance info |

### `source` object (MUST)
| Field | Type | Notes |
|------|------|------|
| `source.path` | string\|null | Input file path |
| `source.inode` | int\|null | Input inode if available |
| `source.offset` | int\|null | Offset if available |

### Strongly recommended fields (SHOULD)
| Field | Type | Notes |
|------|------|------|
| `srcip` | string\|null | Source IP |
| `dstip` | string\|null | Destination IP |
| `srcport` | int\|null | Source port |
| `dstport` | int\|null | Destination port |
| `proto` | int\|null | L4 protocol number |
| `service` | string\|null | Service name |
| `sessionid` | int\|null | Session id |
| `policyid` | int\|null | Policy id |

## Type Normalization Rules
- Numeric counters (bytes/packets/ports/ids) MUST be `int` or `null` (no string numbers).
- Timestamps:
  - `ingest_ts` MUST be UTC ISO8601.
  - `event_ts` SHOULD include timezone.
- Missing fields MUST be `null` (preferred) or omitted (avoid for Core fields).

## Compatibility Policy
Allowed without `schema_version` bump:
- Add new fields (Extended Fields)
- Add new values for enums (type/subtype/level) if still strings
- Add nested sub-objects under Extended Fields

Requires `schema_version` bump:
- Change meaning/type of any Core field
- Remove Core fields
- Change `event_id` stability semantics

## Example (minimal)
```json
{
  "schema_version": 1,
  "event_id": "21e02879a31a63bcbdcd9636535bfe37",
  "event_ts": "2026-01-30T07:53:02+01:00",
  "ingest_ts": "2026-02-16T19:31:12.831687+00:00",
  "type": "event",
  "subtype": "system",
  "level": "alert",
  "devname": "DAHUA_FORTIGATE",
  "devid": "FG100ETK20014183",
  "vd": "root",
  "parse_status": "ok",
  "source": {
    "path": "/data/fortigate-runtime/input/fortigate.log-20260202-000004.gz",
    "inode": 6160565,
    "offset": null
  }
}
