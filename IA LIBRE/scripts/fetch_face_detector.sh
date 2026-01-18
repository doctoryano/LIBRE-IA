#!/usr/bin/env bash
#
# scripts/fetch_face_detector.sh
#
# Download face detector files into data/models/face_detector/ and compute/verify sha256.
# Also attempts to download detached signatures if manifest includes proto_sig_url/model_sig_url.
# Optional: verify SHA256 and GPG signatures (fail-closed).
#
# Usage:
#   ./scripts/fetch_face_detector.sh
#   ./scripts/fetch_face_detector.sh --manifest data/models/face_detector/manifest.json --verify --gpg
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/data/models/face_detector"
MANIFEST="$OUT_DIR/manifest.json"
mkdir -p "$OUT_DIR"

PROTO_URL_DEFAULT="https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt"
MODEL_URL_DEFAULT="https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/master/res10_300x300_ssd_iter_140000_fp16.caffemodel"

usage() {
  echo "Usage: $0 [--manifest PATH] [--verify] [--gpg]"
  echo "  --manifest PATH   : manifest JSON with proto_url, model_url, proto_sha256, model_sha256, optional proto_sig_url, model_sig_url"
  echo "  --verify          : verify downloaded files against manifest SHA256 fields (if present)"
  echo "  --gpg             : require and verify detached signatures (.asc/.sig/.gpg) for files (fail if missing/invalid)"
  exit 1
}

MANIFEST_ARG=""
VERIFY=0
REQUIRE_GPG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --manifest) MANIFEST_ARG="$2"; shift 2;;
    --verify) VERIFY=1; shift;;
    --gpg) REQUIRE_GPG=1; shift;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1"; usage ;;
  esac
done

if [[ -n "$MANIFEST_ARG" ]]; then
  MANIFEST="$MANIFEST_ARG"
fi

PROTO_URL="$PROTO_URL_DEFAULT"
MODEL_URL="$MODEL_URL_DEFAULT"
PROTO_SIG_URL=""
MODEL_SIG_URL=""
EXPECTED_PROTO_SHA=""
EXPECTED_MODEL_SHA=""

if [[ -f "$MANIFEST" ]]; then
  echo "[fetch_face_detector] Reading manifest: $MANIFEST"
  PROTO_URL=$(jq -r '.proto_url // empty' "$MANIFEST" || echo "$PROTO_URL_DEFAULT")
  MODEL_URL=$(jq -r '.model_url // empty' "$MANIFEST" || echo "$MODEL_URL_DEFAULT")
  PROTO_SIG_URL=$(jq -r '.proto_sig_url // empty' "$MANIFEST" || echo "")
  MODEL_SIG_URL=$(jq -r '.model_sig_url // empty' "$MANIFEST" || echo "")
  EXPECTED_PROTO_SHA=$(jq -r '.proto_sha256 // empty' "$MANIFEST" || echo "")
  EXPECTED_MODEL_SHA=$(jq -r '.model_sha256 // empty' "$MANIFEST" || echo "")
fi

PROTO_OUT="$OUT_DIR/deploy.prototxt"
MODEL_OUT="$OUT_DIR/res10_300x300_ssd_iter_140000_fp16.caffemodel"

download() {
  local url="$1"; local out="$2"
  echo "[fetch_face_detector] Downloading $url -> $out"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$out"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$out" "$url"
  else
    echo "curl or wget required"
    exit 2
  fi
}

sha256_of() {
  local f="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$f" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$f" | awk '{print $1}'
  else
    echo "sha256sum or shasum required" >&2
    return 1
  fi
}

# helper to map a signature URL to a local filename next to target (preserve ext if present)
download_sig_if_present() {
  local sig_url="$1"
  local target_path="$2"
  if [[ -z "$sig_url" ]]; then
    return 1
  fi
  local ext="${sig_url##*.}"
  # prefer .asc/.sig/.gpg endings but keep remote filename
  local fname="$(basename \"$sig_url\")"
  local out="$OUT_DIR/$fname"
  echo "[fetch_face_detector] Downloading signature $sig_url -> $out"
  download "$sig_url" "$out"
  return 0
}

verify_gpg_sig_for() {
  local file="$1"
  # Look for sign files next to file: try common suffixes and any downloaded sig files in OUT_DIR
  # Priority: exact basename + .asc/.sig/.gpg, then any file in OUT_DIR whose basename starts with target basename
  local base="$(basename "$file")"
  for ext in .asc .sig .gpg; do
    local sig="${file}${ext}"
    if [[ -f "$sig" ]]; then
      echo "[fetch_face_detector] Found signature file: $sig. Verifying with gpg..."
      if ! command -v gpg >/dev/null 2>&1; then
        echo "gpg not found in PATH; cannot verify signature for $file"
        return 2
      fi
      if gpg --batch --verify "$sig" "$file" >/dev/null 2>&1; then
        echo "[fetch_face_detector] GPG verification OK for $file"
        return 0
      else
        echo "GPG verification FAILED for $file"
        return 3
      fi
    fi
  done
  # Try any signature file downloaded into OUT_DIR that references the base name
  for s in "$OUT_DIR"/*; do
    if [[ -f "$s" ]]; then
      if [[ "$(basename "$s")" == "$base"* && ( "$s" == *.asc || "$s" == *.sig || "$s" == *.gpg ) ]]; then
        echo "[fetch_face_detector] Found signature candidate $s for $file. Verifying..."
        if ! command -v gpg >/dev/null 2>&1; then
          echo "gpg not found in PATH; cannot verify signature for $file"
          return 2
        fi
        if gpg --batch --verify "$s" "$file" >/dev/null 2>&1; then
          echo "[fetch_face_detector] GPG verification OK for $file using $s"
          return 0
        else
          echo "GPG verification FAILED for $file using $s"
          return 3
        fi
      fi
    fi
  done
  # no signature found
  return 1
}

# Download main files
download "$PROTO_URL" "$PROTO_OUT"
download "$MODEL_URL" "$MODEL_OUT"

# Attempt to download signatures if manifest provides URLs
if [[ -n "$PROTO_SIG_URL" ]]; then
  download_sig_if_present "$PROTO_SIG_URL" "$PROTO_OUT" || true
fi
if [[ -n "$MODEL_SIG_URL" ]]; then
  download_sig_if_present "$MODEL_SIG_URL" "$MODEL_OUT" || true
fi

PROTO_SHA=$(sha256_of "$PROTO_OUT")
MODEL_SHA=$(sha256_of "$MODEL_OUT")

echo "[fetch_face_detector] Downloaded files:"
echo " - Proto: $PROTO_OUT (sha256: $PROTO_SHA)"
echo " - Model: $MODEL_OUT (sha256: $MODEL_SHA)"

# Verify SHA256 if requested and expected present in manifest
if [[ "$VERIFY" -eq 1 ]]; then
  echo "[fetch_face_detector] Verifying SHA256 if expected values are present in manifest..."
  if [[ -n "$EXPECTED_PROTO_SHA" ]]; then
    if [[ "$PROTO_SHA" != "$EXPECTED_PROTO_SHA" ]]; then
      echo "ERROR: proto sha256 mismatch! expected $EXPECTED_PROTO_SHA got $PROTO_SHA"
      exit 3
    else
      echo "Proto sha256 OK"
    fi
  else
    echo "No expected proto sha in manifest"
  fi
  if [[ -n "$EXPECTED_MODEL_SHA" ]]; then
    if [[ "$MODEL_SHA" != "$EXPECTED_MODEL_SHA" ]]; then
      echo "ERROR: model sha256 mismatch! expected $EXPECTED_MODEL_SHA got $MODEL_SHA"
      exit 4
    else
      echo "Model sha256 OK"
    fi
  else
    echo "No expected model sha in manifest"
  fi
fi

# Optional GPG verification (fail if --gpg specified and signature absent or invalid)
if [[ "$REQUIRE_GPG" -eq 1 ]]; then
  echo "[fetch_face_detector] REQUIRE_GPG set: verifying detached signatures (fail-closed)"
  for f in "$PROTO_OUT" "$MODEL_OUT" "$MANIFEST"; do
    if [[ ! -f "$f" ]]; then
      continue
    fi
    verify_gpg_sig_for "$f"
    rc=$?
    if [[ $rc -eq 0 ]]; then
      continue
    elif [[ $rc -eq 1 ]]; then
      echo "ERROR: signature not found for $f (expected next to file as .asc/.sig/.gpg). Failing due to --gpg"
      exit 5
    else
      echo "ERROR: GPG verification failed for $f (rc=$rc). Failing due to --gpg"
      exit 6
    fi
  done
fi

echo "[fetch_face_detector] Done. Place manifest.json in $OUT_DIR to enable --verify checks."
exit 0