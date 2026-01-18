#!/usr/bin/env python3
"""
scripts/sandbox_runner.py

Run code safely inside an ephemeral Docker container with strict restrictions:
- network disabled (--network none)
- capabilities dropped (--cap-drop ALL)
- no-new-privileges
- read-only filesystem with a writable bind-mounted workdir
- memory and CPU limits
- container removed after execution (--rm)

Provides:
- run_code_in_sandbox(code_str, tests_list, timeout=5, mem_limit_mb=256, cpus=0.5, image='ia-libre/sandbox:latest')
  -> returns (passed: bool, stdout: str, stderr: str, meta: Optional[str])
- ensure_sandbox_image_built(build_if_missing: bool = True)

Notes:
- Requires Docker CLI available in PATH.
- For Windows, ensure Docker Desktop is running and supports --security-opt options.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Tuple, Optional

ROOT = Path(__file__).resolve().parent.parent
SANDBOX_IMAGE = os.environ.get("SANDBOX_IMAGE", "ia-libre/sandbox:latest")
SANDBOX_DOCKERFILE_DIR = ROOT / "docker"
SANDBOX_DOCKERFILE = SANDBOX_DOCKERFILE_DIR / "sandbox.Dockerfile"

def docker_available() -> bool:
    return shutil.which("docker") is not None

def ensure_sandbox_image_built(build_if_missing: bool = True) -> bool:
    """
    Check if image exists locally; if not and build_if_missing True, build it.
    """
    if not docker_available():
        raise RuntimeError("docker CLI not found in PATH")
    # check image
    try:
        subprocess.run(["docker", "image", "inspect", SANDBOX_IMAGE], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        if not build_if_missing:
            return False
        # build image
        if not SANDBOX_DOCKERFILE.exists():
            raise RuntimeError(f"Sandbox Dockerfile not found at {SANDBOX_DOCKERFILE}")
        ctx = str(SANDBOX_DOCKERFILE_DIR)
        print(f"Building sandbox image {SANDBOX_IMAGE} from {SANDBOX_DOCKERFILE} ...")
        # Build with tag
        subprocess.run(["docker", "build", "-f", str(SANDBOX_DOCKERFILE), "-t", SANDBOX_IMAGE, ctx], check=True)
        return True

def run_code_in_sandbox(code: str, tests: List[str], timeout: int = 5, mem_limit_mb: int = 256, cpus: float = 0.5, image: Optional[str] = None) -> Tuple[bool, str, str, Optional[str]]:
    """
    Executes code+tests inside a sandbox container.
    Returns (passed, stdout, stderr, meta)
    meta contains error string or docker output info.
    """
    if image is None:
        image = SANDBOX_IMAGE
    if not docker_available():
        return (False, "", "", "docker_not_available")

    # ensure image
    try:
        ensure_sandbox_image_built(build_if_missing=True)
    except Exception as e:
        return (False, "", "", f"image_build_failed:{e}")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        script_path = td_path / "run_test.py"
        # Construct runner script: write generated code and tests into a single script that prints JSON result
        script_lines = []
        script_lines.append("# Auto-generated sandbox runner")
        script_lines.append("import sys, json")
        script_lines.append("")  # space
        # Insert generated code
        script_lines.append("# --- Begin generated code ---")
        script_lines.append(code)
        script_lines.append("# --- End generated code ---")
        script_lines.append("")
        script_lines.append("result = {'passed': True, 'detail': None}")
        script_lines.append("try:")
        for t in tests:
            # indent test lines
            script_lines.append(f"    {t}")
        script_lines.append("except AssertionError as e:")
        script_lines.append("    result['passed'] = False")
        script_lines.append("    result['detail'] = str(e)")
        script_lines.append("except Exception as e:")
        script_lines.append("    result['passed'] = False")
        script_lines.append("    result['detail'] = 'EXCEPTION: ' + str(e)")
        script_lines.append("print(json.dumps(result))")
        script_text = "\n".join(script_lines)
        script_path.write_text(script_text, encoding="utf-8")

        # Prepare docker run parameters
        workdir_container = "/work"
        mem_flag = f"--memory={mem_limit_mb}m"
        cpus_flag = f"--cpus={cpus}"
        # Mount the temp dir into container as read-write, but keep container filesystem read-only otherwise
        # Use tmpfs for ephemeral /tmp
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m",
            mem_flag,
            cpus_flag,
            "--pids-limit", "64",
            "-v", f"{td_path}:{workdir_container}:rw,delegated",
            "-w", workdir_container,
            # run as non-root user inside container (user 9999)
            "--user", "9999:9999",
            image,
            "python", "-u", str(script_path.name)
        ]

        # Note: If the sandbox image does not have user 9999, the container may error; the image provided below creates a 'sandbox' user with uid 9999.
        try:
            proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as e:
            return (False, "", "", f"docker_run_failed:{e}")

        try:
            out, err = proc.communicate(timeout=timeout + 2)
        except subprocess.TimeoutExpired:
            proc.kill()
            return (False, "", "", "timeout")
        # Try to parse last line as JSON
        out_str = out or ""
        err_str = err or ""
        parsed = None
        try:
            # Some containers may output logs; parse last JSON blob
            lines = [ln for ln in out_str.splitlines() if ln.strip()]
            last = lines[-1] if lines else ""
            parsed = json.loads(last)
            passed = bool(parsed.get("passed", False))
            detail = parsed.get("detail", None)
            return (passed, out_str, err_str, detail)
        except Exception:
            # No valid JSON — return raw outputs
            return (False, out_str, err_str, "invalid_output")
```