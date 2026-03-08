#!/usr/bin/env bash
set -euo pipefail

# One-shot release helper for core components on core node (r450).
# This script intentionally does NOT manage edge components.

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

APP_NAME="netops-core-app"
TAG_DEFAULT="$(date +%Y%m%d-%H%M%S)-$(git rev-parse --short HEAD)"
TAG="${1:-$TAG_DEFAULT}"
LOCAL_IMPORT_CMD="k3s ctr images import"
TAR_PATH="/tmp/${APP_NAME}_${TAG}.tar"
IMAGE="${APP_NAME}:${TAG}"
NAMESPACE="netops-core"
ALLOW_SAME_TAG="${ALLOW_SAME_TAG:-0}"

usage() {
  cat <<EOF
Usage:
  ./core/automatic_scripts/release_core_app.sh [tag]

Examples:
  ./core/automatic_scripts/release_core_app.sh
  ./core/automatic_scripts/release_core_app.sh v20260303
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[ERROR] docker not found. Please install docker first." >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "[ERROR] kubectl not found." >&2
  exit 1
fi

current_corr_image="$(kubectl -n "${NAMESPACE}" get deploy core-correlator -o jsonpath='{.spec.template.spec.containers[0].image}')"
current_sink_image="$(kubectl -n "${NAMESPACE}" get deploy core-alerts-sink -o jsonpath='{.spec.template.spec.containers[0].image}')"
if [[ "${ALLOW_SAME_TAG}" != "1" && ( "${current_corr_image}" == "${IMAGE}" || "${current_sink_image}" == "${IMAGE}" ) ]]; then
  echo "[ERROR] target image tag already in use: ${IMAGE}" >&2
  echo "Set a new immutable tag (recommended), or ALLOW_SAME_TAG=1 to override." >&2
  exit 1
fi

deploy_exists() {
  local deployment="$1"
  kubectl -n "${NAMESPACE}" get deployment "${deployment}" >/dev/null 2>&1
}

set_image_if_exists() {
  local deployment="$1"
  local container="$2"
  local image="$3"
  if ! deploy_exists "${deployment}"; then
    echo "skip image update: deployment/${deployment} not found"
    return 0
  fi
  kubectl -n "${NAMESPACE}" set image "deployment/${deployment}" "${container}=${image}"
}

rollout_if_exists() {
  local deployment="$1"
  if ! deploy_exists "${deployment}"; then
    echo "skip rollout: deployment/${deployment} not found"
    return 0
  fi
  kubectl -n "${NAMESPACE}" rollout status "deployment/${deployment}"
}

echo "[1/7] Building image ${IMAGE}"
docker build -t "$IMAGE" -f core/docker/Dockerfile.app .

echo "[2/7] Saving tar to ${TAR_PATH}"
docker save "$IMAGE" -o "$TAR_PATH"

echo "[3/7] Importing image on local node (r450)"
$LOCAL_IMPORT_CMD "$TAR_PATH"

echo "[4/7] Updating core-correlator image to ${IMAGE}"
set_image_if_exists core-correlator core-correlator "${IMAGE}"

echo "[5/7] Updating core-alerts-sink image to ${IMAGE}"
set_image_if_exists core-alerts-sink core-alerts-sink "${IMAGE}"
set_image_if_exists core-alerts-store core-alerts-store "${IMAGE}"
set_image_if_exists core-aiops-agent core-aiops-agent "${IMAGE}"

echo "[6/7] Waiting rollout"
rollout_if_exists core-correlator
rollout_if_exists core-alerts-sink
rollout_if_exists core-alerts-store
rollout_if_exists core-aiops-agent

verify_import() {
  local deployment="$1"
  local container="$2"
  local module="$3"
  local tries=6
  local i
  for ((i=1; i<=tries; i++)); do
    if kubectl -n "${NAMESPACE}" exec "deploy/${deployment}" -c "${container}" -- \
      python -c "import ${module}" >/dev/null 2>&1; then
      echo "import check passed: ${module} in ${deployment}/${container}"
      return 0
    fi
    echo "import check retry ${i}/${tries}: ${module} in ${deployment}/${container}"
    sleep 3
  done
  echo "[ERROR] import check failed: ${module} in ${deployment}/${container}" >&2
  kubectl -n "${NAMESPACE}" logs "deploy/${deployment}" -c "${container}" --tail=80 >&2 || true
  return 1
}

verify_deploy_image() {
  local deployment="$1"
  local expected="$2"
  local actual
  actual="$(kubectl -n "${NAMESPACE}" get deploy "${deployment}" -o jsonpath='{.spec.template.spec.containers[0].image}')"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "[ERROR] deployment ${deployment} image mismatch: actual=${actual} expected=${expected}" >&2
    return 1
  fi
  echo "image check passed: ${deployment}=${actual}"
}

echo "[7/7] Verifying runtime module imports"
verify_deploy_image core-correlator "${IMAGE}"
verify_deploy_image core-alerts-sink "${IMAGE}"
verify_import core-correlator core-correlator core.correlator.main
verify_import core-alerts-sink core-alerts-sink core.alerts_sink.main
if deploy_exists core-alerts-store; then
  verify_deploy_image core-alerts-store "${IMAGE}"
  verify_import core-alerts-store core-alerts-store core.alerts_store.main
fi
if deploy_exists core-aiops-agent; then
  verify_deploy_image core-aiops-agent "${IMAGE}"
  verify_import core-aiops-agent core-aiops-agent core.aiops_agent.main
fi

echo "Done. Released core image: ${IMAGE} (core deployments updated, import checks passed)"
