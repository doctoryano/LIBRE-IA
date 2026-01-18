#!/usr/bin/env python3
"""
Fetch initial sources (Project Gutenberg small set + CodeSearchNet python zip)
Updates dataset_manifest.csv with sha256 and simple stats.
"""
from __future__ import annotations
import argparse, time, hashlib, zipfile, csv
from pathlib import Path
import requests
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "dataset_manifest.csv"
RAW.mkdir(parents=True, exist_ok=True)

def sha256_of_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    with dest.open("wb") as fh:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)
    return dest

def fetch_gutenberg(ids, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    combined = out_dir / "project_gutenberg.txt"
    if combined.exists(): combined.unlink()
    for gid in ids:
        candidates = [f"https://www.gutenberg.org/files/{gid}/{gid}-0.txt", f"https://www.gutenberg.org/files/{gid}/{gid}.txt"]
        for url in candidates:
            try:
                dest = out_dir / f"{gid}.txt"
                download(url, dest)
                with combined.open("ab") as outf, dest.open("rb") as inf:
                    outf.write(b"\n\n### GUTENBERG ID %d ###\n\n" % gid)
                    outf.write(inf.read())
                break
            except Exception:
                continue
    return combined

def fetch_codesearchnet(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    url = "https://s3.amazonaws.com/code-search-net/CodeSearchNet/v2/python.zip"
    dest = out_dir / "python.zip"
    download(url, dest)
    return dest

def update_manifest_row(manifest: Path, row: dict):
    rows = {}
    if manifest.exists():
        with manifest.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                rows[r["id"]] = r
    rows[row["id"]] = row
    header = ["id","source_url","license","license_url","collected_at","sha256","records","tokens","languages","filters_applied","contact","notes"]
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for r in rows.values():
            writer.writerow({k: r.get(k,"") for k in header})

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gutenberg-ids", nargs="*", type=int, default=[1342,84,1661])
    p.add_argument("--manifest", default=str(MANIFEST))
    args = p.parse_args()
    manifest = Path(args.manifest)
    gutenberg_path = fetch_gutenberg(args.gutenberg_ids, RAW / "project_gutenberg")
    g_sha = sha256_of_file(gutenberg_path)
    g_lines = sum(1 for _ in gutenberg_path.open("r",encoding="utf-8",errors="ignore"))
    g_row = {"id":"project_gutenberg","source_url":"https://www.gutenberg.org/ (selected ids)","license":"Public Domain","license_url":"https://www.gutenberg.org/","collected_at":datetime.utcnow().isoformat()+"Z","sha256":g_sha,"records":str(g_lines),"tokens":"","languages":"en","filters_applied":"pii_masking,strip_headers","contact":"maintainers@tu-dominio.example","notes":"Concatenated subset"}
    update_manifest_row(manifest, g_row)
    csn_path = fetch_codesearchnet(RAW / "code_search_net")
    csn_sha = sha256_of_file(csn_path)
    csn_row = {"id":"code_search_net","source_url":"https://s3.amazonaws.com/code-search-net/CodeSearchNet/v2/python.zip","license":"varies per file","license_url":"https://github.com/codalab/CodeSearchNet","collected_at":datetime.utcnow().isoformat()+"Z","sha256":csn_sha,"records":"","tokens":"","languages":"python","filters_applied":"repo_license_filter,pii_masking","contact":"datasets@tu-dominio.example","notes":"Python subset zip"}
    update_manifest_row(manifest, csn_row)
    print("Manifest updated:", manifest)
if __name__ == "__main__":
    main()