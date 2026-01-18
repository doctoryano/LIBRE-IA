#!/usr/bin/env bash
# scripts/steward_decrypt.sh
# Usage (recommended, run on steward workstation, NOT on CI runner):
#   # copy the encrypted archive <archive>.tar.gz.gpg to steward workstation
#   ./scripts/steward_decrypt.sh --in data/forensics/sovereign-...tar.gz.gpg --out /secure/location --recipient-key ~/.gnupg/private-key (optional)
#
# This script helps the steward to:
#  - verify archive SHA256 (if provided)
#  - decrypt .gpg using local GPG private key
#  - extract the archive to the destination directory
#
set -euo pipefail

usage() {
  cat <<EOF
Usage: $0 --in <archive.tar.gz.gpg> [--out <dir>] [--verify-sha <hex>]

Notes:
 - Run this on the steward's offline/trusted machine where the steward's private key is available.
 - Do NOT transfer steward private keys to CI or to any runner.
EOF
  exit 1
}

IN=""
OUT_DIR=""
VERIFY_SHA=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --in) IN="$2"; shift 2;;
    --out) OUT_DIR="$2"; shift 2;;
    --verify-sha) VERIFY_SHA="$2"; shift 2;;
    -h|--help) usage;;
    *) echo "Unknown arg $1"; usage;;
  esac
done

if [[ -z "$IN" ]]; then usage; fi
if [[ -z "$OUT_DIR" ]]; then OUT_DIR="./decrypted_forensics"; fi

mkdir -p "$OUT_DIR"
IN_PATH="$IN"
if [[ ! -f "$IN_PATH" ]]; then
  echo "Input archive not found: $IN_PATH" >&2
  exit 2
fi

# Optional verify provided SHA256 of the encrypted file (not recommended to rely on this alone)
if [[ -n "$VERIFY_SHA" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$IN_PATH" | awk '{print $1}')
  else
    actual=$(shasum -a 256 "$IN_PATH" | awk '{print $1}')
  fi
  echo "Provided SHA: $VERIFY_SHA"
  echo "Actual   SHA: $actual"
  if [[ "$actual" != "$VERIFY_SHA" ]]; then
    echo "SHA mismatch! Aborting." >&2
    exit 3
  fi
  echo "SHA verified."
fi

# Decrypt using gpg (will prompt for passphrase if private key is protected)
DECRYPTED_TAR="${OUT_DIR}/decrypted_$(basename "${IN_PATH%.gpg}")"
echo "Decrypting $IN_PATH -> $DECRYPTED_TAR (this will use the local steward private key)..."
gpg --batch --yes --output "$DECRYPTED_TAR" --decrypt "$IN_PATH"

if [[ ! -f "$DECRYPTED_TAR" ]]; then
  echo "Decryption seems to have failed (no output file)." >&2
  exit 4
fi

echo "Decrypt OK. Extracting to $OUT_DIR/contents_$(date -u +%Y%m%dT%H%M%SZ)"
EXTRACT_DIR="${OUT_DIR}/contents_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$EXTRACT_DIR"
tar -xzvf "$DECRYPTED_TAR" -C "$EXTRACT_DIR"

echo "Extraction completed. Securely store the archive and extracted files according to your chain-of-custody policy."
echo "Decrypted tar: $DECRYPTED_TAR"
echo "Contents: $EXTRACT_DIR"
exit 0