#!/usr/bin/env python3
"""
Pin manifest tracker -> create branch + add tracker file + open PR for human review.

Usage:
  GITHUB_TOKEN=<token> python scripts/pin_manifest_tracker.py --repo owner/repo --manifest data/models/face_detector/manifest.json

Behavior:
 - Reads manifest, computes proto/model sha256 (if present)
 - Creates a new branch refs/heads/pin-face-detector-<ts>-<short>
 - Creates file docs/decisions/face_detector_verified_<ts>.json on that branch via Contents API
 - Opens a Pull Request from that branch into the repo's default branch with a descriptive title/body
"""
from __future__ import annotations
import os
import sys
import json
import time
import hashlib
import base64
from pathlib import Path
from datetime import datetime
import requests
import argparse

GITHUB_API = "https://api.github.com"

def sha256_of(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def load_manifest(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def build_tracker(manifest_path: Path):
    manifest = load_manifest(manifest_path)
    proto = manifest_path.parent / "deploy.prototxt"
    model = manifest_path.parent / "res10_300x300_ssd_iter_140000_fp16.caffemodel"
    proto_sha = sha256_of(proto) if proto.exists() else None
    model_sha = sha256_of(model) if model.exists() else None
    tracker = {
        "pinned_at": datetime.utcnow().isoformat()+"Z",
        "manifest_path": str(manifest_path),
        "proto": {"path": str(proto), "sha256": proto_sha},
        "model": {"path": str(model), "sha256": model_sha},
        "manifest": manifest,
        "ci_metadata": {
            "github_repository": os.getenv("GITHUB_REPOSITORY"),
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "github_actor": os.getenv("GITHUB_ACTOR"),
        }
    }
    return tracker

def gh(session, method, url, **kwargs):
    r = session.request(method, url, **kwargs)
    if r.status_code >= 400:
        raise RuntimeError(f"GitHub API error {r.status_code}: {r.text}")
    return r.json()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/repo")
    p.add_argument("--manifest", required=True, help="local manifest path")
    p.add_argument("--path-prefix", default="docs/decisions", help="destination dir in repo")
    args = p.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN required", file=sys.stderr); sys.exit(2)

    repo = args.repo
    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print("Manifest not found:", manifest_path, file=sys.stderr); sys.exit(3)

    session = requests.Session()
    session.headers.update({"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})

    # 1) get repo info to discover default branch and base ref sha
    repo_info = gh(session, "GET", f"{GITHUB_API}/repos/{repo}")
    default_branch = repo_info.get("default_branch", "main")

    ref_info = gh(session, "GET", f"{GITHUB_API}/repos/{repo}/git/refs/heads/{default_branch}")
    base_sha = ref_info["object"]["sha"]

    # 2) create new branch name
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    short = base_sha[:8]
    branch_name = f"pin-face-detector-{ts}-{short}"

    # create ref
    ref_payload = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
    gh(session, "POST", f"{GITHUB_API}/repos/{repo}/git/refs", json=ref_payload)
    print("Created branch:", branch_name)

    # 3) create tracker content and add file via Contents API on that branch
    tracker = build_tracker(manifest_path)
    filename = f"face_detector_verified_{ts}.json"
    repo_path = f"{args.path_prefix}/{filename}"
    content_bytes = json.dumps(tracker, indent=2, ensure_ascii=False).encode("utf-8")
    b64 = base64.b64encode(content_bytes).decode("ascii")
    message = f"Pin face detector manifest verification: {filename}"
    put_url = f"{GITHUB_API}/repos/{repo}/contents/{repo_path}"
    payload = {"message": message, "content": b64, "branch": branch_name}
    resp = session.put(put_url, json=payload)
    if resp.status_code not in (200,201):
        raise RuntimeError(f"Failed to create file: {resp.status_code} {resp.text}")
    print("Created file in branch:", repo_path)

    # 4) create pull request
    pr_title = f"[SOBERANA] Pin face detector manifest {ts}"
    pr_body = (
        "Pinning verified face detector manifest for audit. "
        "This PR was created automatically by CI and contains the tracker file with SHA256 fingerprints.\n\n"
        "Please review the manifest and the computed SHA256 before merging. This PR is intentionally human-reviewed."
    )
    pr_payload = {"title": pr_title, "head": branch_name, "base": default_branch, "body": pr_body}
    pr = gh(session, "POST", f"{GITHUB_API}/repos/{repo}/pulls", json=pr_payload)
    print("Created PR:", pr.get("html_url"))

if __name__ == "__main__":
    main()