# NetOps Project State

- Last updated: 2026-03-30 UTC
- Scope of this note: current repository state, live chain shape, and active boundaries

## Current Objective

The repository is no longer trying to prove that raw logs can be parsed.
The active objective is to keep the full chain stable:

1. FortiGate syslog reaches the edge node
2. edge ingest turns raw text into replayable structured facts
3. facts flow into Kafka and become deterministic alerts
4. alerts land in both audit storage and hot query storage
5. AIOps emits bounded suggestions from the alert contract
6. the runtime console projects the result as an operator-readable chain

The key evaluation criteria at this stage are practical rather than cosmetic:

- the chain must process real device traffic, not only fixtures
- evidence fields must survive from edge parsing into core alerts
- runtime outputs must be auditable from files and queryable from ClickHouse
- the UI must reflect the real runtime path without pretending execution already exists

## Live Chain

The current live path is:

`FortiGate -> edge/fortigate-ingest -> edge/edge_forwarder -> netops.facts.raw.v1 -> core/correlator -> netops.alerts.v1 -> alerts_sink / alerts_store / aiops_agent -> netops.aiops.suggestions.v1 -> frontend runtime gateway`

Important runtime facts:

- edge ingest reads `/data/fortigate-runtime/input/fortigate.log*`
- parsed facts are written to `/data/fortigate-runtime/output/parsed/events-*.jsonl`
- alerts are written to `/data/netops-runtime/alerts/alerts-*.jsonl`
- suggestions are written to `/data/netops-runtime/aiops/suggestions-*.jsonl`
- ClickHouse stores the hot alert view used for recent-history lookup and AIOps context

## Current Working State

Code already present in the repository:

- replay-safe FortiGate ingest and structured fact output
- edge forwarding into Kafka raw topic
- deterministic correlation and alert emission
- JSONL audit persistence for alerts
- ClickHouse-backed hot alert storage
- bounded AIOps suggestion path with alert-scope and cluster-scope outputs
- runtime gateway and operator console

What the repository does not currently claim:

- autonomous remediation against devices
- approval workflows that mutate live state
- a production-grade closed-loop execution plane
- model-driven first-pass detection on the full raw stream

## Active Constraints

The present architecture reflects current operating limits.

- The environment is resource-constrained; inference cannot be treated as a free hot-path dependency.
- Replay and audit still matter more than narrative fluency.
- The frontend is a projection layer over runtime artifacts, not a control plane.
- JSONL and ClickHouse are both kept because audit and hot retrieval are different jobs.

## Related Documents

- [FortiGate ingest field reference](./FORTIGATE_INGEST_FIELD_REFERENCE_EN.md)
- [Frontend runtime architecture](./FRONTEND_RUNTIME_ARCHITECTURE_20260328_EN.md)
- [Core module README](../core/README.md)
- [Edge module README](../edge/README.md)
- [Frontend module README](../frontend/README.md)
