# Core Phase-2 Minimal Implementation

This directory contains the minimal, deployable phase-2 stack for the core node.

## Module Layout

- `core/infra`: shared config, logging, checkpoint helpers
- `core/edge_forwarder`: reads edge JSONL events and forwards to Kafka raw topic
- `core/correlator`: consumes raw topic and emits alert topic using deterministic rules
- `core/alerts_sink`: consumes alert topic and persists hourly JSONL in runtime volume
- `core/benchmark`: load test and throughput probe scripts for Kafka pipeline sizing
- `core/deployments`: k3s manifests for KRaft Kafka + forwarder + correlator
- `core/docker`: container build file for forwarder/correlator

## Data Plane Topics

- `netops.facts.raw.v1`: edge fact events
- `netops.alerts.v1`: correlator alerts
- `netops.dlq.v1`: reserved for malformed records / replay failures

## Build

```bash
docker build -t netops-core-app:0.1 -f core/docker/Dockerfile.app .
```

## Deploy Order

```bash
kubectl apply -f core/deployments/00-namespace.yaml
kubectl apply -f core/deployments/10-kafka-kraft.yaml
kubectl apply -f core/deployments/20-topic-init-job.yaml
kubectl apply -f core/deployments/30-edge-forwarder.yaml
kubectl apply -f core/deployments/40-core-correlator.yaml
kubectl apply -f core/deployments/50-core-alerts-sink.yaml
```

## Benchmark

### 1) Kafka producer load test (core side)

```bash
python -m core.benchmark.kafka_load_producer \
  --bootstrap-servers netops-kafka.netops-core.svc.cluster.local:9092 \
  --topic netops.facts.raw.v1 \
  --messages 200000 \
  --payload-bytes 1024 \
  --batch-size 1000 \
  --workers 4
```

### 2) Topic throughput / lag probe

```bash
python -m core.benchmark.kafka_topic_probe \
  --bootstrap-servers netops-kafka.netops-core.svc.cluster.local:9092 \
  --topic netops.facts.raw.v1 \
  --group-id benchmark-probe-v1 \
  --duration-sec 60
```

### 3) r230 producer rate (edge-forwarder runtime)

`edge-forwarder` logs now include per-scan metrics:
- `eps` (events per second)
- `mbps` (MB per second)
- `cumulative_sent`, `cumulative_bytes`

```bash
kubectl logs -n edge deploy/edge-forwarder --tail=200 -f
```

## Release Automation

To avoid manual build/save/import/set-image steps each time, use:

```bash
./core/scripts/release_core_app.sh
```

Optional arguments:

```bash
# release only edge-forwarder
./core/scripts/release_core_app.sh <tag> edge

# release only core-correlator
./core/scripts/release_core_app.sh <tag> core
```

Notes:
- script builds image from `core/docker/Dockerfile.app`
- imports image into both nodes (`r450` local + `r230` via ssh/scp)
- updates deployment image tag and waits for rollout
