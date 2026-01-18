#!/usr/bin/env python3
"""
scripts/train_qlora_sovereign.py

QLoRA training runner with SafetyEthicsCallback that:
 - attempts to archive+encrypt the checkpoint directory to a secure location via scripts/archive_and_encrypt.py
 - then deletes the local checkpoint dir (fail-closed)
 - creates an emergency marker file in reports/ for human auditors.

Usage (example):
  export STEWARD_PUBKEY=data/gpg-keys/steward_pubkey.asc
  python scripts/train_qlora_sovereign.py --train-file data/datasets/sovereign_instruct_5k.jsonl --model-name-or-path decapoda-research/llama-7b-hf --output-dir outputs/sovereign-qlora --ethics-model-path models/ethics-classifier

IMPORTANT:
 - This script is a training orchestration tool — adapt paths, batch sizes and model selection to your infra.
 - The script calls the external archive/encrypt helper; ensure scripts/archive_and_encrypt.py is present and gpg is available.
"""
from __future__ import annotations
import os, sys, json, shutil, argparse, logging, subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("train_qlora_sovereign")

# Safety utils (classifier pipeline)
try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    HAS_TRANSFORMERS = True
except Exception:
    HAS_TRANSFORMERS = False

class EmergencyStop(Exception):
    pass

class SafetyEthicsCallback:
    def __init__(self, ethics_model_path: Optional[str], threshold: float = 0.9, device: int = 0):
        self.threshold = float(threshold)
        self.ethics_model_path = ethics_model_path
        self.device = device
        self.pipeline = None
        if ethics_model_path and HAS_TRANSFORMERS:
            try:
                self.pipeline = pipeline("text-classification", model=ethics_model_path, device=device)
                logger.info("Loaded ethics classifier from %s", ethics_model_path)
            except Exception as e:
                logger.warning("Could not load ethics classifier, falling back to heuristics: %s", e)
                self.pipeline = None

        # heuristics patterns
        import re
        self.patterns = [
            re.compile(r"(surveil|wiretap|monitor individuals|spy|surveillance)", re.IGNORECASE),
            re.compile(r"(weapon|bomb|detonate|build a bomb|firearm|rifle|grenade)", re.IGNORECASE)
        ]

    def inspect_text(self, text: str) -> Optional[str]:
        # prefer classifier
        if self.pipeline:
            try:
                res = self.pipeline(text if len(text) < 1000 else text[:1000], truncation=True)
                # Expect model labels: SAFE/FLAG or LABEL_0/LABEL_1; operator must ensure semantics
                for r in res:
                    label = r.get("label","")
                    score = float(r.get("score", 0.0))
                    # Interpret as flagged if label suggests FLAG or score >= threshold
                    if ("FLAG" in label.upper() or "1" in label or score >= self.threshold):
                        return f"classifier_flag:{label}:{score}"
            except Exception as e:
                logger.warning("Ethics classifier error: %s", e)
        # fallback heuristics
        hits = 0
        for p in self.patterns:
            if p.search(text):
                hits += 1
            if hits >= 1:
                return "heuristic_flag"
        return None

def archive_and_encrypt_then_remove(path: Path, steward_pubkey: Optional[str], out_dir: str = "data/forensics"):
    """
    Calls scripts/archive_and_encrypt.py to archive & encrypt `path`.
    steward_pubkey: path to steward public key file (preferred). If None, requires recipient in keyring (env STEWARD_GPG_RECIP).
    Returns (success:bool, summary_dict)
    """
    script = Path(__file__).resolve().parent / "archive_and_encrypt.py"
    if not script.exists():
        # fallback to calling via module name
        script = Path("scripts/archive_and_encrypt.py")
    cmd = [sys.executable, str(script), "--path", str(path), "--out-dir", out_dir]
    if steward_pubkey:
        cmd += ["--pubkey", steward_pubkey]
    else:
        recip = os.getenv("STEWARD_GPG_RECIP")
        if recip:
            cmd += ["--recipient", recip]
        else:
            raise RuntimeError("No steward public key provided (STEWARD_GPG_RECIP or STEWARD_PUBKEY required)")
    logger.info("Archiving & encrypting checkpoint with command: %s [args hidden]", cmd[0])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        summary = json.loads(proc.stdout.strip())
        logger.info("Archive+encrypt summary: %s", summary)
        # remove the original folder after successful archive
        shutil.rmtree(path, ignore_errors=True)
        return True, summary
    except subprocess.CalledProcessError as e:
        logger.error("Archive/encrypt failed: %s stdout=%s stderr=%s", e.returncode, e.stdout, e.stderr)
        return False, {"error": "archive_failed", "stdout": e.stdout, "stderr": e.stderr}
    except Exception as e:
        logger.exception("Unexpected error during archive_and_encrypt: %s", e)
        return False, {"error": str(e)}

def train_with_safeguards(args):
    # Minimal checks (real training skeleton omitted for brevity)
    train_file = Path(args.train_file)
    if not train_file.exists():
        logger.error("train file not found: %s", train_file)
        sys.exit(2)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize safety callback
    ethics = SafetyEthicsCallback(args.ethics_model_path, threshold=args.ethics_threshold, device=args.device)

    # Here you would instantiate your model/Trainer/PEFT as in previous skeleton.
    # For illustrative purposes we'll show where to trigger emergency handling.

    try:
        # PSEUDO training loop (replace with Trainer.train() hooks or custom loop)
        for epoch in range(int(args.epochs)):
            logger.info("Epoch %d/%s", epoch+1, args.epochs)
            # Normally, iterate batches; here we check each example text for demo
            import json
            with train_file.open("r", encoding="utf-8") as fh:
                for ln in fh:
                    ex = json.loads(ln)
                    text = ex.get("instruction","") + "\n" + ex.get("output","")
                    flag = ethics.inspect_text(text)
                    if flag:
                        logger.error("Safety trigger detected: %s", flag)
                        raise EmergencyStop(flag)
            # ... End of epoch
        # If training completes:
        logger.info("Training completed (placeholder). Save model to %s", output_dir)
    except EmergencyStop as e:
        logger.error("EMERGENCY STOP: %s", e)
        # Archive & encrypt output_dir for forensics
        steward_pubkey = os.getenv("STEWARD_PUBKEY") or os.getenv("STEWARD_PUBKEY_PATH")
        success, summary = archive_and_encrypt_then_remove(output_dir, steward_pubkey, out_dir=args.forensics_dir)
        # create marker report
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        marker = reports_dir / f"emergency_stop_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        marker.write_text(json.dumps({"time": datetime.utcnow().isoformat()+"Z", "reason": str(e), "archive_summary": summary}, indent=2))
        logger.info("Emergency marker written to %s", marker)
        # Optionally notify via other channels (CI will handle upload)
        sys.exit(99)
    except Exception as e:
        logger.exception("Training failed: %s", e)
        sys.exit(1)
    finally:
        # any cleanup
        pass

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--train-file", required=True)
    p.add_argument("--model-name-or-path", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument("--ethics-model-path", default=None)
    p.add_argument("--ethics-threshold", type=float, default=0.9)
    p.add_argument("--device", type=int, default=0)
    p.add_argument("--forensics-dir", default="data/forensics")
    p.add_argument("--epochs", type=int, default=1)
    return p.parse_args()

def main():
    args = parse_args()
    train_with_safeguards(args)

if __name__ == "__main__":
    main()