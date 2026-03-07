# Automatic Scripts

This directory stores one-shot automation scripts for build, image distribution, and rollout.

## Scripts

### `release_core_app.sh`

Builds `netops-core-app`, imports image to both cluster nodes (`r450` local + `r230` remote),
updates deployment image tags, and waits for rollout.

#### Usage

```bash
cd /data/Netops-causality-remediation
./core/automatic_scripts/release_core_app.sh
```

#### Optional arguments

```bash
# release with explicit tag to both deployments
./core/automatic_scripts/release_core_app.sh v20260303 all

# release only edge-forwarder
./core/automatic_scripts/release_core_app.sh v20260303 edge

# release only core deployments (core-correlator + core-alerts-sink)
./core/automatic_scripts/release_core_app.sh v20260303 core
```

#### Environment variables

```bash
EDGE_HOST=192.168.1.23 EDGE_USER=root ./core/automatic_scripts/release_core_app.sh
```

#### What it does

1. `docker build` from `core/docker/Dockerfile.app`
2. `docker save` to tarball under `/tmp`
3. `k3s ctr images import` on local node (`r450`)
4. `scp` tarball to edge node (`r230`)
5. remote `k3s ctr images import` on edge node
6. `kubectl set image` for target deployment(s)
   - `edge`: `edge-forwarder`
   - `core`: `core-correlator`, `core-alerts-sink`
7. `kubectl rollout status` wait until ready

## Notes

- Ensure `docker`, `kubectl`, `ssh`, and `scp` are available on the execution host.
- For reproducibility, always keep deployment env values in YAML and avoid long-term drift from ad-hoc `kubectl set env`.
