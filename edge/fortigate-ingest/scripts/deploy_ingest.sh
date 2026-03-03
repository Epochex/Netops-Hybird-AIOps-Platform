#!/usr/bin/env bash
set -euo pipefail

# Edge-only deploy helper for fortigate-ingest.
# Steps:
# 1) build image
# 2) import image to k3s/containerd
# 3) apply manifest
# 4) set deployment image + wait rollout

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INGEST_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${INGEST_DIR}/../.." && pwd)"

DOCKERFILE="${INGEST_DIR}/Dockerfile.stageb"
CONTEXT_DIR="${INGEST_DIR}"
MANIFEST="${INGEST_DIR}/ingest_pod.yaml"

IMAGE_REPO="fortigate-ingest"
IMAGE_TAG="0.2"
ROLLOUT_TIMEOUT="180s"
BUILD_IMAGE=1
IMPORT_IMAGE=1
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  deploy_ingest.sh [options]

Options:
  --tag TAG             Image tag (default: 0.2)
  --repo NAME           Image repo (default: fortigate-ingest)
  --timeout DURATION    Rollout timeout (default: 180s)
  --skip-build          Skip image build
  --skip-import         Skip import to k3s runtime
  --dry-run             Print commands only
  -h, --help            Show help

Examples:
  edge/fortigate-ingest/scripts/deploy_ingest.sh
  edge/fortigate-ingest/scripts/deploy_ingest.sh --tag 0.3
  edge/fortigate-ingest/scripts/deploy_ingest.sh --skip-build --skip-import
EOF
}

log() {
  printf '[deploy-ingest] %s\n' "$*"
}

run_cmd() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    eval "$@"
  fi
}

detect_builder() {
  if command -v docker >/dev/null 2>&1; then
    echo "docker"
    return
  fi
  if command -v nerdctl >/dev/null 2>&1; then
    echo "nerdctl"
    return
  fi
  echo ""
}

import_image_to_runtime() {
  local image_ref="$1"
  local tmp_tar
  tmp_tar="$(mktemp "/tmp/${image_ref//[:\/]/_}.XXXXXX.tar")"
  trap 'rm -f "${tmp_tar}"' RETURN

  if command -v docker >/dev/null 2>&1; then
    run_cmd "docker save -o '${tmp_tar}' '${image_ref}'"
  elif command -v nerdctl >/dev/null 2>&1; then
    run_cmd "nerdctl save -o '${tmp_tar}' '${image_ref}'"
  else
    log "ERROR: no docker/nerdctl found for image save"
    exit 1
  fi

  if command -v k3s >/dev/null 2>&1; then
    run_cmd "k3s ctr images import '${tmp_tar}'"
    return
  fi
  if command -v ctr >/dev/null 2>&1; then
    run_cmd "ctr -n k8s.io images import '${tmp_tar}'"
    return
  fi

  log "ERROR: neither k3s nor ctr found"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --repo)
      IMAGE_REPO="$2"
      shift 2
      ;;
    --timeout)
      ROLLOUT_TIMEOUT="$2"
      shift 2
      ;;
    --skip-build)
      BUILD_IMAGE=0
      shift
      ;;
    --skip-import)
      IMPORT_IMAGE=0
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      log "ERROR: unknown option '$1'"
      usage
      exit 2
      ;;
  esac
done

IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"

if [[ ! -f "${DOCKERFILE}" ]]; then
  log "ERROR: Dockerfile not found: ${DOCKERFILE}"
  exit 2
fi
if [[ ! -f "${MANIFEST}" ]]; then
  log "ERROR: Manifest not found: ${MANIFEST}"
  exit 2
fi
if ! command -v kubectl >/dev/null 2>&1; then
  log "ERROR: kubectl not found"
  exit 2
fi

BUILDER="$(detect_builder)"
if [[ "${BUILD_IMAGE}" -eq 1 && -z "${BUILDER}" ]]; then
  log "ERROR: no docker/nerdctl found"
  exit 2
fi

log "repo root: ${REPO_ROOT}"
log "ingest dir: ${INGEST_DIR}"
log "image: ${IMAGE}"
log "build=${BUILD_IMAGE}, import=${IMPORT_IMAGE}"

if [[ "${BUILD_IMAGE}" -eq 1 ]]; then
  log "building image via ${BUILDER}"
  run_cmd "${BUILDER} build -t '${IMAGE}' -f '${DOCKERFILE}' '${CONTEXT_DIR}'"
fi

if [[ "${IMPORT_IMAGE}" -eq 1 ]]; then
  log "importing image to runtime"
  import_image_to_runtime "${IMAGE}"
fi

log "applying manifest"
run_cmd "kubectl apply -f '${MANIFEST}'"

log "set deployment image"
run_cmd "kubectl -n edge set image deployment/fortigate-ingest fortigate-ingest='${IMAGE}'"

log "waiting rollout"
run_cmd "kubectl -n edge rollout status deployment/fortigate-ingest --timeout='${ROLLOUT_TIMEOUT}'"

if [[ "${DRY_RUN}" -eq 0 ]]; then
  log "status:"
  kubectl -n edge get deploy fortigate-ingest -o wide || true
  kubectl -n edge get pods -l app=fortigate-ingest -o wide || true
fi

log "done"
