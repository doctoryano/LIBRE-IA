#!/usr/bin/env python3
import argparse, requests, subprocess, json, os, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
KEYS_DIR = ROOT / "data" / "gpg-keys"
AUTHORIZED = KEYS_DIR / "authorized_keys.json"
KEYS_DIR.mkdir(parents=True, exist_ok=True)
def fingerprint(path: Path):
    with tempfile.TemporaryDirectory() as td:
        env = os.environ.copy(); env["GNUPGHOME"]=td
        subprocess.run(["gpg","--import",str(path)], env=env, capture_output=True)
        proc = subprocess.run(["gpg","--with-colons","--fingerprint"], env=env, capture_output=True, text=True)
        for line in proc.stdout.splitlines():
            if line.startswith("fpr:"):
                return line.split(":")[9]
    return None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--url", required=True); ap.add_argument("--name", required=True); ap.add_argument("--email", default="")
    args=ap.parse_args()
    r = requests.get(args.url, timeout=30); r.raise_for_status()
    dest = KEYS_DIR / Path(args.url).name
    dest.write_bytes(r.content)
    fpr = fingerprint(dest)
    auth = {}
    if AUTHORIZED.exists(): auth = json.loads(AUTHORIZED.read_text(encoding="utf-8"))
    auth[fpr] = {"name":args.name,"email":args.email,"source":args.url,"added_at":datetime.utcnow().isoformat()+"Z"}
    AUTHORIZED.write_text(json.dumps(auth, indent=2), encoding="utf-8")
    print("Added fingerprint", fpr)
if __name__=="__main__": main()