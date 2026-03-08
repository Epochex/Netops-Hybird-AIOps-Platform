# Automatic Scripts

This directory stores one-shot automation scripts for core node components only.

## Scripts

### `release_core_app.sh`

Builds `netops-core-app`, imports the image on local core node runtime, updates
core app deployments, and waits for rollout.

#### Usage

```bash
cd /data/Netops-causality-remediation
./core/automatic_scripts/release_core_app.sh
```

#### Optional arguments

```bash
# release with explicit tag
./core/automatic_scripts/release_core_app.sh v20260303
```

`release_core_app.sh` defaults to immutable tag format:
`YYYYMMDD-HHMMSS-<git_short_sha>`.

#### What it does

1. `docker build` from `core/docker/Dockerfile.app`
2. `docker save` to tarball under `/tmp`
3. `k3s ctr images import` on local node (`r450`)
4. `kubectl set image` for core deployments:
   - `core-correlator`
   - `core-alerts-sink`
   - `core-alerts-store` (if deployed)
   - `core-aiops-agent` (if deployed)
5. `kubectl rollout status` wait until all existing targets are ready
7. run runtime import checks in pods:
   - `python -c "import core.correlator.main"`
   - `python -c "import core.alerts_sink.main"`
   - `python -c "import core.alerts_store.main"` (if deployed)
   - `python -c "import core.aiops_agent.main"` (if deployed)
8. verify deployment images exactly match the target tag

## Notes

- Ensure `docker`, `kubectl`, and `k3s` are available on the core node.
- Edge forwarder release must use `edge/edge_forwarder/scripts/deploy_edge_forwarder.sh`.
- For reproducibility, always keep deployment env values in YAML and avoid long-term drift from ad-hoc `kubectl set env`.
- Script blocks reusing an image tag already deployed (unless `ALLOW_SAME_TAG=1`), to prevent stale-image ambiguity.
