#!/usr/bin/env python3
import argparse, subprocess, json
from pathlib import Path
def find_sig(path: Path):
    for ext in (".asc",".sig",".gpg"):
        cand = path.with_suffix(path.suffix + ext)
        if cand.exists(): return cand
        base = path.with_suffix(ext)
        if base.exists(): return base
    return None

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--file","-f",required=True)
    args=p.parse_args()
    path = Path(args.file)
    sig = find_sig(path)
    if not sig:
        print(json.dumps({"file":str(path),"signature_path":None,"verified":False,"gpg_output":"no_signature_found"}))
        raise SystemExit(2)
    proc = subprocess.run(["gpg","--batch","--verify",str(sig),str(path)], capture_output=True, text=True)
    out = proc.stdout + proc.stderr
    verified = proc.returncode == 0
    print(json.dumps({"file":str(path),"signature_path":str(sig),"verified":verified,"gpg_output":out}))
    raise SystemExit(0 if verified else 3)

if __name__=="__main__":
    main()