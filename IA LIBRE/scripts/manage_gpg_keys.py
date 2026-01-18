#!/usr/bin/env python3
import argparse, subprocess, json, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = ROOT / "data" / "gpg-keys"
AUTHORIZED = KEYS_DIR / "authorized_keys.json"
def import_all():
    for p in KEYS_DIR.glob("*.asc"):
        subprocess.run(["gpg","--import",str(p)])
    proc = subprocess.run(["gpg","--with-colons","--fingerprint"], capture_output=True, text=True)
    fps = [line.split(":")[9] for line in proc.stdout.splitlines() if line.startswith("fpr:")]
    print("Imported:", fps)
def list_keys():
    proc = subprocess.run(["gpg","--list-keys","--with-colons","--fingerprint"], capture_output=True, text=True)
    print(proc.stdout)
def verify_manifest():
    auth = {}
    if AUTHORIZED.exists():
        auth = json.loads(AUTHORIZED.read_text(encoding="utf-8"))
    proc = subprocess.run(["gpg","--with-colons","--fingerprint"], capture_output=True, text=True)
    fprs = [line.split(":")[9] for line in proc.stdout.splitlines() if line.startswith("fpr:")]
    missing = [k for k in auth.keys() if k not in fprs]
    extra = [k for k in fprs if k not in auth]
    print({"missing":missing,"extra":extra})
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("cmd",choices=["import","list","verify"])
    args=ap.parse_args()
    if args.cmd=="import": import_all()
    elif args.cmd=="list": list_keys()
    elif args.cmd=="verify": verify_manifest()
if __name__=="__main__": main()