#!/usr/bin/env python3
"""
scripts/archive_and_encrypt.py

Create a compressed archive of a path and encrypt it with GPG.

Usage examples:
  # Use an existing key in local GPG keyring (recipient = fingerprint or email)
  python scripts/archive_and_encrypt.py --path outputs/sovereign-qlora --recipient "steward@example.org"

  # Use a public key file (no import to main keyring; uses temporary GNUPG home)
  python scripts/archive_and_encrypt.py --path outputs/sovereign-qlora --pubkey data/gpg-keys/steward_pubkey.asc

Outputs:
 - <outdir>/<basename>_<timestamp>.tar.gz.gpg
 - prints JSON summary to stdout with keys: archive_path, encrypted_path, sha256_archive

Notes:
 - This script is intended to run in CI or an isolated host.
 - The private key (steward) must be held offline; only the steward public key is needed here.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import tempfile
import time
import hashlib
import subprocess
from pathlib import Path

def sha256_of(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def make_archive(src: Path, out_dir: Path, timestamp: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    base = src.name
    tar_name = f"{base}_{timestamp}.tar.gz"
    tar_path = out_dir / tar_name
    # create tar.gz
    with tempfile.TemporaryDirectory() as td:
        tmp_tar = Path(td) / tar_name
        # Use shutil.make_archive by providing base_name without extension
        shutil.make_archive(str(tmp_tar.with_suffix('')), 'gztar', root_dir=src.parent, base_dir=src.name)
        shutil.move(str(tmp_tar), str(tar_path))
    return tar_path

def encrypt_with_pubkey_archive(tar_path: Path, out_dir: Path, recipient: str = None, pubkey_path: Path = None):
    out_dir.mkdir(parents=True, exist_ok=True)
    enc_name = tar_path.name + ".gpg"
    enc_path = out_dir / enc_name
    if pubkey_path:
        # use temporary GNUPGHOME to import pubkey and encrypt
        gnupg_home = Path(tempfile.mkdtemp(prefix="gnupg_"))
        os.chmod(gnupg_home, 0o700)
        try:
            env = os.environ.copy()
            env["GNUPGHOME"] = str(gnupg_home)
            # import pubkey
            subprocess.run(["gpg", "--batch", "--import", str(pubkey_path)], check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            # find fingerprint of the imported key
            proc = subprocess.run(["gpg", "--batch", "--with-colons", "--fingerprint"], check=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # encrypt
            if recipient:
                rec = recipient
            else:
                # pick the first fpr from keyring
                rec = None
                for line in proc.stdout.splitlines():
                    if line.startswith("fpr:"):
                        rec = line.split(":")[9]
                        break
                if not rec:
                    raise RuntimeError("No recipient fingerprint found after importing pubkey")
            subprocess.run(["gpg", "--batch", "--yes", "--trust-model", "always", "--output", str(enc_path), "--encrypt", "--recipient", rec, str(tar_path)], check=True, env=env)
        finally:
            # remove temporary GNUPGHOME (no private keys were imported)
            shutil.rmtree(gnupg_home, ignore_errors=True)
    else:
        # Use system gpg and recipient must be in keyring
        if not recipient:
            raise RuntimeError("No recipient provided and no pubkey_path given")
        subprocess.run(["gpg", "--batch", "--yes", "--trust-model", "always", "--output", str(enc_path), "--encrypt", "--recipient", recipient, str(tar_path)], check=True)
    return enc_path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--path", required=True, help="Path to archive (file or directory)")
    p.add_argument("--out-dir", default="data/forensics", help="Directory to place archives")
    p.add_argument("--recipient", help="GPG recipient (fingerprint or uid present in keyring)")
    p.add_argument("--pubkey", help="Public key file (ASCII/PEM/ASC). If provided, a temporary gnupg home is used.")
    args = p.parse_args()

    src = Path(args.path)
    if not src.exists():
        print(json.dumps({"error": "path_not_found", "path": str(src)}))
        raise SystemExit(2)
    out_dir = Path(args.out_dir)
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    tar_path = make_archive(src, out_dir, timestamp)
    sha = sha256_of(tar_path)
    try:
        enc_path = encrypt_with_pubkey_archive(tar_path, out_dir, recipient=args.recipient, pubkey_path=Path(args.pubkey) if args.pubkey else None)
    except subprocess.CalledProcessError as e:
        print(json.dumps({"error": "gpg_failed", "detail": str(e)}))
        raise SystemExit(3)
    # After encryption we may optionally remove the tar (but caller decides). Keep tar for verification; caller can delete.
    summary = {
        "archive_path": str(tar_path),
        "archive_sha256": sha,
        "encrypted_path": str(enc_path),
        "timestamp": timestamp
    }
    print(json.dumps(summary))
    return 0

if __name__ == "__main__":
    main()