#!/usr/bin/env python3
"""
scripts/ci_benchmark_http.py (updated)

Now accepts optional --detector-manifest path. If present and detector files exist,
the script computes SHA256 of the detector proto + model and embeds them in the final JSON
under "face_detector": { "manifest": <path>, "proto": {"path":..., "sha256":...}, "model": {...} }.

Usage:
  python scripts/ci_benchmark_http.py --server-url http://localhost:8000 --out reports/ci_report.json --detector-manifest data/models/face_detector/manifest.json
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import Dict, Optional
import requests
import hashlib
from scripts.gpu_monitor import GPUMonitor
from scripts.sandbox_runner import run_code_in_sandbox, ensure_sandbox_image_built

MINI_HUMANEVAL = [
    {
        "id": "factorial",
        "prompt": "Implement a function factorial(n) that returns the factorial of a non-negative integer n.\n",
        "signature": "def factorial(n):",
        "tests": ["assert factorial(5) == 120", "assert factorial(0) == 1"]
    },
    {
        "id": "is_palindrome",
        "prompt": "Implement is_palindrome(s) ignoring spaces and case.\n",
        "signature": "def is_palindrome(s):",
        "tests": ["assert is_palindrome('radar') is True", "assert is_palindrome('hello') is False"]
    },
    {
        "id": "sum_of_list",
        "prompt": "Implement sum_of_list(lst) returns sum.\n",
        "signature": "def sum_of_list(lst):",
        "tests": ["assert sum_of_list([1,2,3]) == 6", "assert sum_of_list([]) == 0"]
    }
]

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def call_completion(server_url: str, prompt: str, max_tokens: int = 128, model: Optional[str] = None) -> Dict:
    url = server_url.rstrip("/") + "/v1/completions"
    payload = {"model": model, "prompt": prompt, "max_tokens": max_tokens, "temperature": 0.0}
    headers = {"Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(url, json=payload, headers=headers, timeout=300)
    t1 = time.time()
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    return {"elapsed_s": t1 - t0, "response": data}

def extract_generated_text(response: Dict) -> str:
    if isinstance(response, dict):
        if "choices" in response and isinstance(response["choices"], list) and response["choices"]:
            c = response["choices"][0]
            if isinstance(c, dict) and ("text" in c or "message" in c):
                return c.get("text") or (c.get("message") and c["message"].get("content", ""))
        if "generated_text" in response:
            return response["generated_text"]
    return str(response)

def build_face_detector_block(manifest_path: Optional[str]) -> Dict:
    """
    If manifest path exists and files present, compute their SHA256 and return a dict.
    """
    if not manifest_path:
        return {}
    mpath = Path(manifest_path)
    if not mpath.exists():
        return {"manifest": str(mpath), "note": "manifest not found"}
    try:
        j = json.loads(mpath.read_text(encoding="utf-8"))
    except Exception:
        return {"manifest": str(mpath), "note": "invalid manifest JSON"}

    proto_rel = j.get("proto_url", "")
    model_rel = j.get("model_url", "")
    # Map default filenames (as fetch script writes)
    proto_path = Path(mpath.parent) / "deploy.prototxt"
    model_path = Path(mpath.parent) / "res10_300x300_ssd_iter_140000_fp16.caffemodel"
    out = {"manifest": str(mpath), "proto": {}, "model": {}}
    if proto_path.exists():
        out["proto"]["path"] = str(proto_path)
        out["proto"]["sha256"] = sha256_of(proto_path)
    else:
        out["proto"]["path"] = str(proto_path)
        out["proto"]["sha256"] = None
    if model_path.exists():
        out["model"]["path"] = str(model_path)
        out["model"]["sha256"] = sha256_of(model_path)
    else:
        out["model"]["path"] = str(model_path)
        out["model"]["sha256"] = None
    return out

def run(server_url: str, out: Path, model: Optional[str], detector_manifest: Optional[str]):
    ensure_sandbox_image_built(build_if_missing=True)
    face_block = build_face_detector_block(detector_manifest)
    results = []
    total_kwh = 0.0
    for task in MINI_HUMANEVAL:
        prompt = f"# Task {task['id']}\n{task['prompt']}\n{task['signature']}\n"
        monitor = GPUMonitor(sample_interval=0.5, record_samples=False)
        monitor.start()
        try:
            comp = call_completion(server_url, prompt, max_tokens=128, model=model)
        except Exception as e:
            monitor_summary = monitor.stop_and_summary()
            results.append({"task_id": task["id"], "error": f"completion_error:{e}", "monitor": monitor_summary})
            continue
        gen_text = extract_generated_text(comp["response"])
        idx = gen_text.find(task["signature"])
        gen_code = gen_text[idx:] if idx != -1 else gen_text
        ok, rout, rerr, rmeta = run_code_in_sandbox(gen_code, task["tests"], timeout=8, mem_limit_mb=256, cpus=0.5)
        monitor_summary = monitor.stop_and_summary()
        duration = monitor_summary.get("duration_s", 0.0)
        avg_power = monitor_summary.get("avg_power_w", 0.0)
        kwh = (avg_power * duration) / 1000.0
        energy_mix = float(os.getenv("ENERGY_MIX_KG_CO2_KWH", "0.4"))
        kg_co2 = kwh * energy_mix
        total_kwh += kwh
        results.append({
            "task_id": task["id"],
            "completion_elapsed_s": comp["elapsed_s"],
            "generated_text": gen_text,
            "exec_passed": ok,
            "exec_stdout": rout,
            "exec_stderr": rerr,
            "exec_meta": rmeta,
            "gpu_monitor": monitor_summary,
            "kwh": kwh,
            "kg_co2": kg_co2
        })
    report = {
        "server_url": server_url,
        "model": model,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_kwh": total_kwh,
        "total_kg_co2": total_kwh * float(os.getenv("ENERGY_MIX_KG_CO2_KWH", "0.4")),
        "face_detector": face_block,
        "tasks": results
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Report written to", out)

def parse_args():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--server-url", default="http://localhost:8000")
    p.add_argument("--out", default="reports/ci_report.json")
    p.add_argument("--model", default=None)
    p.add_argument("--detector-manifest", default=None)
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    run(args.server_url, Path(args.out), args.model, args.detector_manifest)