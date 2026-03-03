#!/usr/bin/env bash
set -euo pipefail

# One-shot release helper for netops-core-app in k3s/containerd cluster.
# Steps:
# 1) docker build image
# 2) docker save tarball
# 3) import to local r450 containerd
# 4) scp + import to r230 containerd
# 5) patch deployment image tags
# 6) wait rollout status

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="netops-core-app"
TAG="${1:-$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)}"
TARGET="${2:-all}" # all|edge|core
EDGE_HOST="${EDGE_HOST:-192.168.1.23}"
EDGE_USER="${EDGE_USER:-root}"
LOCAL_IMPORT_CMD="k3s ctr images import"
REMOTE_IMPORT_CMD="k3s ctr images import"
TAR_PATH="/tmp/${APP_NAME}_${TAG}.tar"
IMAGE="${APP_NAME}:${TAG}"

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker not found. Please install docker first." >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "[ERROR] kubectl not found." >&2
  exit 1
fi

if [[ "$TARGET" != "all" && "$TARGET" != "edge" && "$TARGET" != "core" ]]; then
  echo "[ERROR] TARGET must be one of: all|edge|core" >&2
  exit 1
fi

echo "[1/7] Building image ${IMAGE}"
docker build -t "$IMAGE" -f core/docker/Dockerfile.app .

echo "[2/7] Saving tar to ${TAR_PATH}"
docker save "$IMAGE" -o "$TAR_PATH"

echo "[3/7] Importing image on local node (r450)"
$LOCAL_IMPORT_CMD "$TAR_PATH"

echo "[4/7] Copying tar to edge node ${EDGE_USER}@${EDGE_HOST}"
scp "$TAR_PATH" "${EDGE_USER}@${EDGE_HOST}:${TAR_PATH}"

echo "[5/7] Importing image on edge node (r230)"
ssh "${EDGE_USER}@${EDGE_HOST}" "$REMOTE_IMPORT_CMD ${TAR_PATH}"

if [[ "$TARGET" == "all" || "$TARGET" == "edge" ]]; then
  echo "[6/7] Updating edge-forwarder image to ${IMAGE}"
  kubectl -n edge set image deployment/edge-forwarder edge-forwarder="$IMAGE"
fi
if [[ "$TARGET" == "all" || "$TARGET" == "core" ]]; then
  echo "[6/7] Updating core-correlator image to ${IMAGE}"
  kubectl -n netops-core set image deployment/core-correlator core-correlator="$IMAGE"
fi

echo "[7/7] Waiting rollout"
if [[ "$TARGET" == "all" || "$TARGET" == "edge" ]]; then
  kubectl -n edge rollout status deployment/edge-forwarder
fi
if [[ "$TARGET" == "all" || "$TARGET" == "core" ]]; then
  kubectl -n netops-core rollout status deployment/core-correlator
fi

echo "Done. Released image: ${IMAGE}"
