# NetOps — FortiGate Ingest (File-based)  
`edge/fortigate-ingest`

> [!IMPORTANT]
> This repo component is a **file-based ingest + parse + JSONL sink** pipeline for FortiGate syslog logs stored on disk (active log + rotated logs).
> It provides: **checkpointed tailing**, **rotation handling**, **DLQ**, and **metrics JSONL** for observability.

---

## 1. What this does

### 1.1 Data flow (end-to-end)

```
FortiGate (office LAN) 
  -> syslog server / collector (writes file: fortigate.log + rotations)
  -> this agent reads files:
       - rotated: fortigate.log-YYYYMMDD-HHMMSS[.gz]  (batch)
       - active:  fortigate.log                       (tail with checkpoint)
  -> parse each line into structured JSON
  -> write JSONL outputs (hourly files):
       events-YYYYMMDD-HH.jsonl
       dlq-YYYYMMDD-HH.jsonl
       metrics-YYYYMMDD-HH.jsonl
```

### 1.2 What you get

- **Structured events** (`events-*.jsonl`): FortiGate syslog lines normalized into a stable schema (`schema_version=1`) suitable for:
  - traffic deny/allow analysis
  - policy hit distribution
  - src/dst/service profiling
  - rate anomaly detection
  - incident forensics (time windows + correlation keys)
- **Dead-letter queue** (`dlq-*.jsonl`): raw lines that failed parsing or agent-level warnings (e.g., active file truncated).
- **Metrics stream** (`metrics-*.jsonl`): per-10s pipeline performance counters and rates.

---

## 2. Repository layout (key paths)

```
Netops-causality-remediation/
└── edge/
    └── fortigate-ingest/
        └── bin/
            ├── main.py              # main loop: rotated scan + active tail + checkpoint + metrics
            ├── source_file.py       # file source: rotated listing + gzip reading + active tailing
            ├── parser_fgt_v1.py     # FortiGate syslog parser (schema v1)
            ├── sink_jsonl.py        # JSONL sink (hourly files)
            ├── checkpoint.py        # checkpoint load/save (atomic write)
            └── metrics.py           # counters + rates + lag metrics
```

Runtime directories (example on R230):

```
/data/fortigate-runtime/
├── input/
│   ├── fortigate.log
│   ├── fortigate.log-YYYYMMDD-HHMMSS
│   └── fortigate.log-YYYYMMDD-HHMMSS.gz
├── output/
│   └── parsed/
│       ├── events-YYYYMMDD-HH.jsonl
│       ├── dlq-YYYYMMDD-HH.jsonl
│       └── metrics-YYYYMMDD-HH.jsonl
└── work/
    ├── checkpoint.json
    └── check_parsed_quality.py
```

> [!NOTE]
> The exact runtime paths can be adjusted in `main.py` / your deployment wrapper.
> The important invariant: **input** contains `fortigate.log` (+ rotations), **parsed** receives JSONL outputs, and **work** persists checkpoint.

---

## 3. Ingest semantics (checkpointing, rotation, reliability)

### 3.1 Active file: `fortigate.log` (tail mode)

The agent tails `fortigate.log` **by byte offset**, and persists:

- `active.path`
- `active.inode`
- `active.offset` (bytes)
- `active.last_event_ts_seen`

#### Rotation detection

If inode changes, the agent assumes `fortigate.log` was rotated and replaced, and will:

- reset offset to `0` for the new active file
- continue tailing seamlessly

#### Truncation detection

If current file size `< checkpoint offset`, the agent assumes the file was truncated and will:

- emit a DLQ record with `reason="active_truncated_reset_offset"`
- reset offset to `0`

> [!WARNING]
> This pipeline is designed as **at-least-once** ingestion.
> Duplicate reads can occur at file boundaries (rotation/truncate), so downstream should deduplicate using `event_id` if strict uniqueness is required.

### 3.2 Rotated files: `fortigate.log-YYYYMMDD-HHMMSS[.gz]` (batch mode)

Rotated logs are processed in timestamp order. A rotated file is marked completed with a stable key:

```
key = path|inode|size|mtime
```

Completed keys are kept (capped, e.g., 5000 entries). Already-completed rotations are skipped.

This yields **exactly-once per rotated segment**, as long as the segment file metadata remains unchanged.

---

## 4. Output files and schemas

### 4.1 Output file naming

All sinks are **hourly** partitions based on local time:

- `events-YYYYMMDD-HH.jsonl`
- `dlq-YYYYMMDD-HH.jsonl`
- `metrics-YYYYMMDD-HH.jsonl`

### 4.2 Event schema (parser output)

Each successfully parsed log line becomes one JSON object (one line in JSONL):

```json
{
  "schema_version": 1,
  "event_id": "32-hex-chars-from-sha256(raw_line)",
  "host": "_gateway",
  "event_ts": "2026-02-21T00:17:00+01:00",

  "type": "traffic",
  "subtype": "local",
  "level": "notice",

  "devname": "xxx",
  "devid": "FGT60F...",
  "vd": "root",

  "action": "deny",
  "policyid": 0,
  "proto": 6,
  "service": "HTTPS",

  "srcip": "x.x.x.x",
  "srcport": 12345,
  "srcintf": "wan1",
  "srcintfrole": "wan",
  "dstip": "y.y.y.y",
  "dstport": 443,
  "dstintf": "root",
  "dstintfrole": "lan",

  "sentbyte": 0,
  "rcvdbyte": 0,
  "sentpkt": 0,
  "rcvdpkt": 0,

  "parse_status": "ok",
  "kv_subset": {
    "logid": "0000000013",
    "eventtime": 173xxxxxxx,
    "tz": "+0800"
  },

  "ingest_ts": "2026-02-21T00:17:03.123456Z",
  "source": {
    "path": "/data/fortigate-runtime/input/fortigate.log",
    "inode": 1234567,
    "offset": 987654321
  }
}
```

#### Correlation keys you can use immediately

- **Network flow / session correlation**
  - `sessionid`, `srcip`, `dstip`, `srcport`, `dstport`, `proto`
- **Policy / control-plane correlation**
  - `policyid`, `policytype`, `trandisp`, `app`, `appcat`
- **Interface / topology correlation**
  - `srcintf`, `dstintf`, `srcintfrole`, `dstintfrole`
- **Host/endpoint enrichment**
  - `srcmac`, `mastersrcmac`, `osname`, `srcswversion`, `srccountry`, `dstcountry`, `srcname`

> [!NOTE]
> The parser keeps a **bounded subset** of KV fields (`kv_subset`) to prevent unbounded schema growth.
> Extend this whitelist carefully to avoid exploding event size and disk usage.

### 4.3 DLQ schema (failures / anomalies)

DLQ lines contain at least:

```json
{
  "schema_version": 1,
  "ingest_ts": "2026-02-21T00:17:03.123456Z",
  "reason": "syslog_header_parse_fail",
  "source": {
    "path": "/data/fortigate-runtime/input/fortigate.log",
    "inode": 1234567,
    "offset": 987654321
  },
  "raw": "<original log line or bytes summary>"
}
```

Common `reason` values:

- `syslog_header_parse_fail`
- `non_text_or_binary`
- `active_truncated_reset_offset`
- `parser_exception:<...>`

### 4.4 Metrics schema (10s cadence)

One JSON per 10 seconds:

```json
{
  "ts": "2026-02-21T00:17:10+01:00",

  "active_file_size_bytes": 123456789,
  "active_read_offset_bytes": 120000000,
  "active_lag_bytes": 3456789,

  "lines_in_total": 1000000,
  "bytes_in_total": 250000000,
  "events_out_total": 990000,
  "dlq_out_total": 10000,
  "parse_fail_total": 10000,

  "lines_in_per_sec": 1200.5,
  "bytes_in_per_sec": 300000.0,
  "events_out_per_sec": 1188.2,
  "dlq_out_per_sec": 12.3,

  "last_event_ts_seen": "2026-02-21T00:17:00+01:00"
}
```

> [!IMPORTANT]
> `active_lag_bytes` is the simplest backpressure signal:
> - rising lag → parser/sink can't keep up
> - stable near 0 → tail is caught up

---

## 5. How to run (R230 example)

### 5.1 Preconditions

- Python 3.x available on the node running the agent
- Input files exist:
  - `/data/fortigate-runtime/input/fortigate.log`
  - rotated logs optional

### 5.2 Run

Example (adjust paths to your repo checkout):

```
cd /data/Netops-causality-remediation/edge/fortigate-ingest/bin
python3 main.py
```

> [!NOTE]
> `main.py` is designed to run as a long-lived process (systemd container, k8s pod, or bare-metal daemon).
> Ensure stdout/stderr are captured by your runtime (systemd journal, container logs, etc).

---

## 6. Data analysis you can do immediately (without a database)

All outputs are JSONL, so you can use `jq` or Python.

### 6.1 Top denied services (last hour)

```
jq -r 'select(.action=="deny") | .service // "UNKNOWN"' /data/fortigate-runtime/output/parsed/events-20260221-00.jsonl \
  | sort | uniq -c | sort -nr | head
```

### 6.2 Top source IPs hitting local-in deny

```
jq -r 'select(.type=="traffic" and .subtype=="local" and .action=="deny") | .srcip' events-*.jsonl \
  | sort | uniq -c | sort -nr | head
```

### 6.3 Find bursts (coarse) by minute

```
jq -r '.event_ts[0:16]' events-*.jsonl | sort | uniq -c | sort -nr | head
```

### 6.4 DLQ reasons

```
jq -r '.reason' dlq-*.jsonl | sort | uniq -c | sort -nr
```

> [!WARNING]
> JSONL scanning is O(file_size). For interactive querying across days/weeks, consider a query layer (PostgreSQL/ClickHouse/OpenSearch).

---

## 7. Do we need a database?

### 7.1 Not required (Phase-1)

You can stay file-based if you only need:

- periodic offline statistics
- small time windows (minutes-hours)
- manual forensics with jq/grep/Python
- simple dashboards built from `metrics-*.jsonl`

### 7.2 Becomes valuable (Phase-2)

A query layer becomes high ROI if you need:

- fast filtering by `srcip/dstip/sessionid/policyid`
- time-window aggregations (5m/1h) at scale
- join/correlation across multiple event types
- interactive root-cause workflows
- stable APIs for UI/agents

Recommended options (pick one, based on constraints):

- **PostgreSQL**: easiest operationally; good for structured queries + indexing.
- **ClickHouse**: strong for time-series/event analytics at high volume.
- **OpenSearch/Elasticsearch**: strong for search + filtering + text fields; higher ops cost.

> [!IMPORTANT]
> Database adoption should not block Phase-1 deliverables.
> The current JSONL outputs are already a clean interface for later ingestion into any storage.

---

## 8. Quality checks

A simple checklist:

- `metrics` shows `active_lag_bytes` not growing unbounded
- `events_out_per_sec` tracks `lines_in_per_sec` (minus DLQ)
- DLQ reason distribution is stable and explainable
- Parser does not generate runaway event sizes

If you maintain a script like:

- `/data/fortigate-runtime/work/check_parsed_quality.py`

document its usage here (and keep it reproducible).

---

## 9. Known limitations

- At-least-once ingestion; dedup downstream if strict uniqueness is required.
- Syslog time parsing depends on presence of `date/time/tz` fields; otherwise uses syslog header + assumed year.
- `kv_subset` is a whitelist; unknown fields may be dropped to keep schema stable and bounded.

---

## 10. Roadmap (next steps)

### Phase-1 (stabilize pipeline)
- Produce a one-page operational dashboard from `metrics-*.jsonl`
- Tighten DLQ taxonomy and sample retention
- Confirm rotation behaviors with your collector (logrotate/syslog-ng/rsyslog)

### Phase-2 (query + correlation)
- Ingest `events-*.jsonl` into PostgreSQL / ClickHouse / OpenSearch
- Provide query APIs for:
  - top offenders
  - policy hit summaries
  - session correlation
  - interface flap / VPN down sequences

### Phase-3 (causality + remediation)
- Rules + evidence graph generation (time + interface + policy dependencies)
- Remediation suggestions (safe-mode): commands/templates + approvals + audit

---

## 11. Operational notes (deployment)

> [!IMPORTANT]
> If running in Kubernetes:
> - code change requires **image rebuild** + **deployment rollout**.
> - ensure volumes are persistent for `/data/fortigate-runtime/` (input/output/work).

> [!WARNING]
> Do not rely on temporary `export ENV=...` patterns. Use persistent configuration methods:
> - systemd `EnvironmentFile=`
> - `/etc/profile.d/*.sh`
> - k8s ConfigMap/Secret + envFrom + volume mounts

---

## 12. License / ownership

Internal project; define according to organization policy.
