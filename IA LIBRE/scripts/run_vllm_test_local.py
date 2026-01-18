#!/usr/bin/env python3
"""
scripts/run_vllm_test_local.py (v2.2 - SOBERANA)

Benchmarks vLLM locally with:
 - mandatory Docker + sandbox execution (no insecure fallback)
 - GPU sampling (time-to-first-token, gen time, tokens, throughput)
 - energy estimation (kWh) and CO2 calculation using ENERGY_MIX_KG_CO2_KWH from .env
 - JSON report output

Usage:
  cp .env.example .env && edit .env
  python scripts/run_vllm_test_local.py --model-path /path/to/model --out reports/vllm_humaneval_report.json
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv is optional; env vars still may be set externally
    pass

# Read energy mix (kg CO2e per kWh)
ENERGY_MIX = float(os.getenv("ENERGY_MIX_KG_CO2_KWH", "0.4"))
GPU_SAMPLE_INTERVAL = float(os.getenv("GPU_SAMPLE_INTERVAL", "0.5"))
SANDBOX_MEM_MB = int(os.getenv("SANDBOX_MEM_MB", "256"))
SANDBOX_CPUS = float(os.getenv("SANDBOX_CPUS", "0.5"))

# Ensure Docker is required
if os.getenv("REQUIRE_DOCKER", "yes").lower() in ("1","yes","true"):
    import shutil
    if shutil.which("docker") is None:
        print("ERROR: Docker required but not found in PATH. Aborting (security policy).")
        sys.exit(2)

# Try imports
try:
    from transformers import AutoTokenizer  # optional for token counting
    HF_TOKENIZER_AVAILABLE = True
except Exception:
    HF_TOKENIZER_AVAILABLE = False

# Import GPU monitor and sandbox runner (must exist)
from scripts.gpu_monitor import GPUMonitor
from scripts.sandbox_runner import run_code_in_sandbox, ensure_sandbox_image_built

# vLLM generation helper (as before)
async def generate_with_vllm(model_path: str, prompt: str, max_tokens: int = 128, temperature: float = 0.0, timeout: int = 180):
    """
    Uses vllm to generate. Returns dict {text, ttft, gen_time, tokens}
    """
    start_total = time.time()
    try:
        from vllm import LLM, SamplingParams
    except Exception as e:
        raise RuntimeError(f"vllm import failed: {e}")

    def blocking_gen():
        t0 = time.time()
        out_chunks = []
        first_token_time = None
        try:
            with LLM(model=model_path) as llm:
                sampling_params = SamplingParams(temperature=temperature, max_tokens=max_tokens)
                for resp in llm.generate(prompt, sampling_params=sampling_params):
                    text = getattr(resp, "text", None) or str(resp)
                    if text:
                        if first_token_time is None:
                            first_token_time = time.time() - t0
                        out_chunks.append(text)
                total_time = time.time() - t0
                gen_text = "".join(out_chunks)
                return {"text": gen_text, "ttft": first_token_time or total_time, "gen_time": total_time}
        except Exception as e:
            raise RuntimeError(f"vllm generation error: {e}")

    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, blocking_gen)
    gen_text = res.get("text", "")
    # token counting
    if HF_TOKENIZER_AVAILABLE:
        try:
            tokenizer = AutoTokenizer.from_pretrained("gpt2", use_fast=True)
            tokens = len(tokenizer.tokenize(gen_text))
        except Exception:
            tokens = len(gen_text.split())
    else:
        tokens = len(gen_text.split())
    return {"text": gen_text, "ttft": res.get("ttft", 0.0), "gen_time": res.get("gen_time", 0.0), "tokens": tokens}

# Mini HumanEval tasks (same as before)
MINI_HUMANEVAL = [
    {
        "id": "factorial",
        "prompt": (
            "Implement a function factorial(n) that returns the factorial of a non-negative integer n.\n"
        ),
        "signature": "def factorial(n):",
        "tests": [
            "assert factorial(0) == 1",
            "assert factorial(5) == 120",
        ],
    },
    {
        "id": "is_palindrome",
        "prompt": (
            "Implement a function is_palindrome(s) that returns True if the string s is a palindrome, ignoring spaces and case.\n"
        ),
        "signature": "def is_palindrome(s):",
        "tests": [
            "assert is_palindrome('radar') is True",
            "assert is_palindrome('hello') is False",
        ],
    },
    {
        "id": "sum_of_list",
        "prompt": "Implement sum_of_list(lst) returning sum of numeric elements.\n",
        "signature": "def sum_of_list(lst):",
        "tests": [
            "assert sum_of_list([1,2,3]) == 6",
            "assert sum_of_list([]) == 0",
        ],
    },
]

@dataclass
class TaskResult:
    task_id: str
    prompt: str
    generated: str
    passed: bool
    error: Optional[str]
    runtime_s: float
    exec_stdout: Optional[str]
    exec_stderr: Optional[str]
    metrics: Dict

async def run_benchmark(model_path: str, tasks: List[Dict], out_report: Optional[Path], max_tokens: int = 128):
    # Ensure sandbox image exists
    ensure_sandbox_image_built(build_if_missing=True)

    results: List[TaskResult] = []
    start_all = time.time()
    # For each task:
    for t in tasks:
        t_start = time.time()
        prompt_text = f"# Task: {t['id']}\n# {t['prompt']}\n{t['signature']}\n"
        # Start GPU monitor
        monitor = GPUMonitor(sample_interval=GPU_SAMPLE_INTERVAL, record_samples=False)
        monitor.start()
        try:
            gen_info = await asyncio.wait_for(generate_with_vllm(model_path, prompt_text, max_tokens=max_tokens, temperature=0.0), timeout=300)
        except Exception as e:
            monitor_summary = monitor.stop_and_summary()
            # energy calc for zero gen_time -> use duration of monitor
            duration = monitor_summary.get("duration_s", 0.0)
            avg_power = monitor_summary.get("avg_power_w", 0.0)
            kwh = (avg_power * duration) / 1000.0
            kg_co2 = kwh * ENERGY_MIX
            tr = TaskResult(task_id=t['id'], prompt=prompt_text, generated="", passed=False, error=f"generation_error:{e}", runtime_s=time.time()-t_start, exec_stdout=None, exec_stderr=None, metrics={"monitor": monitor_summary, "kwh": kwh, "kg_co2": kg_co2})
            results.append(tr)
            continue

        # After generation, run tests inside sandbox (keep monitor running)
        generated_code = gen_info["text"]
        idx = generated_code.find(t["signature"])
        if idx != -1:
            generated_code = generated_code[idx:]

        # run code in sandbox
        try:
            ok, rout, rerr, rmeta = run_code_in_sandbox(generated_code, t["tests"], timeout=10, mem_limit_mb=int(SANDBOX_MEM_MB), cpus=float(SANDBOX_CPUS))
            passed = ok
            stdout = rout
            stderr = rerr
            exec_meta = rmeta
        except Exception as e:
            passed = False
            stdout = ""
            stderr = ""
            exec_meta = f"sandbox_error:{e}"

        # stop monitor and compute energy
        monitor_summary = monitor.stop_and_summary()
        duration = monitor_summary.get("duration_s", 0.0)
        avg_power = monitor_summary.get("avg_power_w", 0.0)
        kwh = (avg_power * duration) / 1000.0
        kg_co2 = kwh * ENERGY_MIX

        metrics = {
            "ttft_s": gen_info.get("ttft"),
            "gen_time_s": gen_info.get("gen_time"),
            "tokens": gen_info.get("tokens"),
            "exec_time_s": None,  # exec time could be computed from monitor durations or from rmeta if provided
            "gpu_monitor": monitor_summary,
            "kwh": kwh,
            "kg_co2": kg_co2,
            "exec_meta": exec_meta,
        }

        tr = TaskResult(
            task_id=t["id"],
            prompt=prompt_text,
            generated=generated_code,
            passed=passed,
            error=None if passed else exec_meta,
            runtime_s=time.time()-t_start,
            exec_stdout=stdout,
            exec_stderr=stderr,
            metrics=metrics,
        )
        results.append(tr)

    total_time = time.time() - start_all
    total_kwh = sum(r.metrics.get("kwh", 0.0) for r in results)
    report = {
        "model_path": model_path,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": total_time,
        "total_kwh": total_kwh,
        "total_kg_co2": total_kwh * ENERGY_MIX,
        "tasks": [asdict(r) for r in results],
        "summary": {
            "num_tasks": len(results),
            "num_passed": sum(1 for r in results if r.passed),
            "num_failed": sum(1 for r in results if not r.passed),
        }
    }
    if out_report:
        out_report.parent.mkdir(parents=True, exist_ok=True)
        out_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("Report saved to", out_report)
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return report

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--out", default="reports/vllm_humaneval_report.json")
    p.add_argument("--max-tokens", type=int, default=128)
    return p.parse_args()

def main():
    args = parse_args()
    model_path = args.model_path
    out = Path(args.out)
    if not Path(model_path).exists():
        print("Model path not found:", model_path)
        sys.exit(2)
    try:
        asyncio.run(run_benchmark(model_path, MINI_HUMANEVAL, out, max_tokens=args.max_tokens))
    except Exception as e:
        print("Benchmark failed:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()