#!/usr/bin/env python3
"""
scripts/gpu_monitor.py

Lightweight GPU monitor that samples NVIDIA GPU power draw and utilization.

Usage:
    from scripts.gpu_monitor import GPUMonitor
    mon = GPUMonitor(sample_interval=0.5)
    mon.start()
    ... do workload ...
    summary = mon.stop_and_summary()
    print(summary)

Returns summary dict:
  {
    "samples": n,
    "duration_s": float,
    "avg_power_w": float,
    "max_power_w": float,
    "avg_util_pct": float,
    "max_util_pct": float,
    "timestamps": [...],  # optional, omitted by default to keep memory small
  }

Implementation:
 - Prefer pynvml (nvidia-ml-py3). If absent, falls back to parsing `nvidia-smi --query` output.
 - If no GPUs detected, returns zeros.
"""
from __future__ import annotations
import time
import threading
import shutil
import subprocess
from typing import Optional, List, Dict

try:
    import pynvml
    HAS_PYNVML = True
except Exception:
    HAS_PYNVML = False

class GPUMonitor:
    def __init__(self, sample_interval: float = 0.5, record_samples: bool = False):
        self.sample_interval = float(sample_interval)
        self.record_samples = bool(record_samples)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._samples: List[Dict] = []
        self._start_ts: Optional[float] = None
        self._end_ts: Optional[float] = None
        self._gpus_present = None

        if HAS_PYNVML:
            try:
                pynvml.nvmlInit()
                self._gpus_present = pynvml.nvmlDeviceGetCount() if pynvml else 0
            except Exception:
                self._gpus_present = 0
        else:
            # quick check for nvidia-smi
            self._gpus_present = 0 if shutil.which("nvidia-smi") is None else -1  # -1 = unknown count

    def _sample_once(self):
        timestamp = time.time()
        sample = {"ts": timestamp, "per_gpu": []}
        if HAS_PYNVML:
            try:
                n = pynvml.nvmlDeviceGetCount()
                total_power = 0.0
                max_power = 0.0
                total_util = 0.0
                max_util = 0.0
                for i in range(n):
                    h = pynvml.nvmlDeviceGetHandleByIndex(i)
                    # power (mW)
                    try:
                        p = pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0
                    except Exception:
                        p = 0.0
                    try:
                        util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
                    except Exception:
                        util = 0.0
                    sample["per_gpu"].append({"index": i, "power_w": p, "util_pct": util})
                    total_power += p
                    total_util += util
                    max_power = max(max_power, p)
                    max_util = max(max_util, util)
                sample["total_power_w"] = total_power
                sample["avg_util_pct"] = total_util / max(1, n)
                sample["max_power_w"] = max_power
                sample["max_util_pct"] = max_util
            except Exception:
                sample["total_power_w"] = 0.0
                sample["avg_util_pct"] = 0.0
                sample["max_power_w"] = 0.0
                sample["max_util_pct"] = 0.0
        else:
            # fallback to nvidia-smi query (slower)
            try:
                # query power.draw and utilization.gpu
                out = subprocess.check_output(["nvidia-smi", "--query-gpu=power.draw,utilization.gpu", "--format=csv,noheader,nounits"], text=True)
                total_power = 0.0
                total_util = 0.0
                max_power = 0.0
                max_util = 0.0
                per = []
                for line in out.splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 2:
                        p = float(parts[0]) if parts[0] else 0.0
                        util = float(parts[1]) if parts[1] else 0.0
                        per.append({"power_w": p, "util_pct": util})
                        total_power += p
                        total_util += util
                        max_power = max(max_power, p)
                        max_util = max(max_util, util)
                sample["per_gpu"] = per
                sample["total_power_w"] = total_power
                sample["avg_util_pct"] = (total_util / len(per)) if per else 0.0
                sample["max_power_w"] = max_power
                sample["max_util_pct"] = max_util
            except Exception:
                sample["total_power_w"] = 0.0
                sample["avg_util_pct"] = 0.0
                sample["max_power_w"] = 0.0
                sample["max_util_pct"] = 0.0

        return sample

    def _run(self):
        self._start_ts = time.time()
        while self._running:
            s = self._sample_once()
            with self._lock:
                if self.record_samples:
                    self._samples.append(s)
                else:
                    # keep rolling aggregate approx: append anyway but limit size to avoid memory blowup
                    self._samples.append(s)
                    if len(self._samples) > 10000:
                        # keep last 10000
                        self._samples = self._samples[-10000:]
            time.sleep(self.sample_interval)
        self._end_ts = time.time()

    def start(self):
        if not docker_available := shutil.which("docker"):  # not critical here; just check environment
            pass
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop_and_summary(self) -> Dict:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        duration = (self._end_ts or time.time()) - (self._start_ts or time.time())
        with self._lock:
            samples = list(self._samples)
        n = len(samples)
        if n == 0:
            return {
                "samples": 0,
                "duration_s": duration,
                "avg_power_w": 0.0,
                "max_power_w": 0.0,
                "avg_util_pct": 0.0,
                "max_util_pct": 0.0,
                "sample_interval_s": self.sample_interval,
            }
        total_power = sum(s.get("total_power_w", 0.0) for s in samples)
        max_power = max(s.get("max_power_w", 0.0) for s in samples)
        avg_util = sum(s.get("avg_util_pct", 0.0) for s in samples) / n
        max_util = max(s.get("max_util_pct", 0.0) for s in samples)
        avg_power = total_power / n
        return {
            "samples": n,
            "duration_s": duration,
            "avg_power_w": avg_power,
            "max_power_w": max_power,
            "avg_util_pct": avg_util,
            "max_util_pct": max_util,
            "sample_interval_s": self.sample_interval,
        }