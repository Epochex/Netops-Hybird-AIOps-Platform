# Automatic Scripts

This directory stores one-shot automation scripts for core node components only.

## Scripts

### `release_core_app.sh`

Builds `netops-core-app`, imports the image on local core node runtime, updates
`core-correlator` image, and waits for rollout.

#### Usage

```bash
cd /data/Netops-causality-remediation
./core/automatic_scripts/release_core_app.sh
```

#### Optional arguments

```bash
# release with explicit image tag
./core/automatic_scripts/release_core_app.sh v20260303
```

#### What it does

1. `docker build` from `core/docker/Dockerfile.app`
2. `docker save` to tarball under `/tmp`
3. imports image to local core runtime (`k3s ctr images import`)
4. `kubectl set image` for `netops-core/core-correlator`
5. `kubectl rollout status` waits until ready

## Notes

- Ensure `docker`, `kubectl`, and `k3s` are available on the core node.
- Edge forwarder release is handled separately by `edge/edge_forwarder/scripts/deploy_edge_forwarder.sh`.
- For reproducibility, always keep deployment env values in YAML and avoid long-term drift from ad-hoc `kubectl set env`.
