#!/usr/bin/env python3
"""
Advanced dataset cleaner:
 - masks PII (email, IP, JWT, API keys, credit-card heuristics)
 - filters/ redacts banned keywords (data/filters/banned_keywords.txt)
 - optional drop of banned entries (--drop_banned)
 - produces <output>.clean_report.json with stats and banned examples

Usage:
  python scripts/clean_dataset.py --input data/raw/foo.txt --output data/clean/foo.jsonl --drop_banned
"""
from __future__ import annotations
import argparse, json, logging, re, hashlib
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RE_EMAIL = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
RE_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
RE_JWT = re.compile(r"eyJ[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}\.[0-9A-Za-z_\-]{10,}")
RE_API_KEYS = re.compile(r"\b(?:AKIA|ASIA|SK|sk_live_|sk_test_|ghp_[A-Za-z0-9_]{36}|AIza[0-9A-Za-z_\-]{35})[A-Za-z0-9_\-]*\b")
RE_CREDIT_CARD = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

FILTERS_PATH = Path(__file__).resolve().parent.parent / "data" / "filters" / "banned_keywords.txt"
def load_banned():
    kws=[]
    try:
        for ln in FILTERS_PATH.read_text(encoding="utf-8").splitlines():
            ln=ln.strip()
            if not ln or ln.startswith("#"): continue
            kws.append(ln)
    except FileNotFoundError:
        kws=["weapon","bomb","explosive","detonate","rifle","gun"]
    kws = sorted(set(kws), key=lambda s:-len(s))
    pattern = r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b"
    return re.compile(pattern, re.IGNORECASE)

WEAPON_RE = load_banned()
INSTRUCTION_RE = re.compile(r"\b(how to|howto|build|construct|assemble|fabricate|step|instructions)\b", re.IGNORECASE)

def mask_piis(text):
    s = text
    stats = {"emails":0,"ips":0,"jwt":0,"api_keys":0,"credit_cards":0}
    s, n = RE_EMAIL.subn("[EMAIL_REDACTED]", s); stats["emails"] += n
    s, n = RE_IPV4.subn("[IP_REDACTED]", s); stats["ips"] += n
    s, n = RE_JWT.subn("[JWT_REDACTED]", s); stats["jwt"] += n
    s, n = RE_API_KEYS.subn("[API_KEY_REDACTED]", s); stats["api_keys"] += n
    s, n = RE_CREDIT_CARD.subn("[CREDIT_CARD_REDACTED]", s); stats["credit_cards"] += n
    return s, stats

def sha256_of_file(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def process(input_path: Path, output_path: Path, drop_banned=False, max_examples=10):
    stats = {"total":0,"kept":0,"removed_empty":0,"pii":{}, "banned_detected":0}
    banned_examples=[]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with input_path.open("r", encoding="utf-8", errors="ignore") as inf, output_path.open("a", encoding="utf-8") as outf:
        for line in inf:
            stats["total"] += 1
            if not line.strip():
                stats["removed_empty"] += 1
                continue
            text = line.rstrip("\n")
            text_masked, pii_stats = mask_piis(text)
            for k,v in pii_stats.items():
                stats["pii"][k] = stats["pii"].get(k,0) + v
            banned = False
            matches=[]
            if WEAPON_RE.search(text_masked):
                matches.append("weapon_keyword")
            if INSTRUCTION_RE.search(text_masked):
                matches.append("instruction_pattern")
            # heuristic: "how to" near weapon keyword
            if re.search(r"(how to|build|fabricate).{0,120}(" + WEAPON_RE.pattern + r")", text_masked, re.IGNORECASE):
                matches.append("weapon_howto")
            if matches:
                stats["banned_detected"] += 1
                banned = True
                if len(banned_examples) < max_examples:
                    banned_examples.append({"line": stats["total"], "matches": matches, "snippet": text_masked[:400]})
            if banned and drop_banned:
                continue
            # redact weapon keywords instead of removing if not drop
            text_clean = WEAPON_RE.sub("[REDACTED_WEAPON]", text_masked)
            # write as JSONL with text_clean
            outf.write(json.dumps({"text_clean": text_clean}, ensure_ascii=False) + "\n")
            stats["kept"] += 1
    out_hash = sha256_of_file(output_path) if output_path.exists() else None
    report = {"input": str(input_path), "output": str(output_path), "timestamp": datetime.utcnow().isoformat()+"Z", "stats": stats, "output_sha256": out_hash, "banned_examples": banned_examples}
    report_path = output_path.with_suffix(".clean_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", "-i", required=True)
    ap.add_argument("--output", "-o", required=True)
    ap.add_argument("--drop_banned", action="store_true")
    ap.add_argument("--max_examples_report", type=int, default=10)
    args = ap.parse_args()
    inp = Path(args.input)
    out = Path(args.output)
    if not inp.exists():
        print("Input not found:", inp); return
    rep = process(inp, out, drop_banned=args.drop_banned, max_examples=args.max_examples_report)
    print("Report saved:", out.with_suffix(".clean_report.json"))

if __name__ == "__main__":
    main()