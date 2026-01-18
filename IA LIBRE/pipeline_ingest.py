#!/usr/bin/env python3
"""
pipeline_ingest.py
 - reads dataset_manifest.csv
 - downloads files (simple requests), verifies sha256 if provided
 - extracts archives (zip/tar)
 - runs scripts/clean_dataset.py per text file found
 - writes per-dataset report to data/reports/<id>.ingest_report.json
"""
from __future__ import annotations
import csv, json, logging, os, time, tarfile, zipfile, subprocess, hashlib
from pathlib import Path
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
REPORTS = ROOT / "data" / "reports"
for d in (RAW, CLEAN, REPORTS): d.mkdir(parents=True, exist_ok=True)

def sha256_of_file(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        tmp = dest.with_suffix(".download")
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)
    return dest

def extract_if_archive(path: Path, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as z:
            z.extractall(dest_dir)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as t:
            t.extractall(dest_dir)
    else:
        # treat as single file
        (dest_dir / path.name).write_bytes(path.read_bytes())

def find_text_files(p: Path):
    res=[]
    for f in p.rglob("*"):
        if f.is_file() and f.suffix.lower() in (".txt",".jsonl",".md",".py",".java",".js"):
            res.append(f)
    return res

def process_row(row):
    id_ = row.get("id") or "unknown"
    url = row.get("source_url")
    out = {"id": id_, "source_url": url, "ok": False, "errors": []}
    try:
        parsed = urlparse(url)
        fname = Path(parsed.path).name or f"{id_}.dat"
        dest = RAW / id_ / fname
        dest.parent.mkdir(parents=True, exist_ok=True)
        logging.info("Downloading %s -> %s", url, dest)
        download(url, dest)
        file_sha = sha256_of_file(dest)
        out["sha256"] = file_sha
        if row.get("sha256") and row.get("sha256") != "TO_FILL":
            if row.get("sha256") != file_sha:
                out["errors"].append("sha256_mismatch")
        # extract
        extracted = RAW / id_ / "extracted"
        extract_if_archive(dest, extracted)
        files = find_text_files(extracted) if extracted.exists() else [dest]
        if not files:
            out["errors"].append("no_text_files")
        clean_out = CLEAN / f"{id_}.jsonl"
        if clean_out.exists(): clean_out.unlink()
        for f in files:
            subprocess.run([str(Path("python").resolve()), str(Path("scripts/clean_dataset.py")), "--input", str(f), "--output", str(clean_out), "--drop_banned"], check=False)
        # basic audit
        report = {"id": id_, "sha256": file_sha, "clean_file": str(clean_out), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / f"{id_}.ingest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        out["ok"] = True
    except Exception as e:
        out["errors"].append(str(e))
    return out

def read_manifest(path: Path):
    rows=[]
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            rows.append(r)
    return rows

def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", default="dataset_manifest.csv")
    p.add_argument("--ids", nargs="*", help="process only these ids")
    p.add_argument("--workers", type=int, default=2)
    args = p.parse_args()
    manifest = Path(args.manifest)
    if not manifest.exists():
        print("Manifest not found:", manifest); return
    rows = read_manifest(manifest)
    if args.ids:
        rows = [r for r in rows if r.get("id") in args.ids]
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_row, r) for r in rows]
        for fut in futures:
            results.append(fut.result())
    (REPORTS / "ingest_summary.json").write_text(json.dumps({"results": results, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2), encoding="utf-8")
    print("Done. Reports in", REPORTS)

if __name__ == "__main__":
    main()