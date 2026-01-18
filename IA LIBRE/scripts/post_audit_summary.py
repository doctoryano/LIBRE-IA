#!/usr/bin/env python3
"""
Post an audit summary and attach HTML report.

Behavior:
 - Try to create a Release and upload HTML as an asset (using GITHUB_TOKEN).
 - If release/upload fails, try to create a Gist using GIST_TOKEN (if provided).
 - If GIST_TOKEN not provided or fails, try to create a gist with GITHUB_TOKEN as fallback.
 - Create or comment on an Issue titled "SOBERANA Audit: Latest" with summary + link.

Usage:
  GITHUB_TOKEN=<token> [GIST_TOKEN=<gist_token>] python scripts/post_audit_summary.py --repo owner/repo --report reports/soberana_report.json --html reports/soberana_report.html
"""
from __future__ import annotations
import os, sys, json, argparse, mimetypes, base64
from pathlib import Path
from datetime import datetime
import requests

GITHUB_API = "https://api.github.com"

def load_report(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def summary_md(report: dict) -> str:
    ts = report.get("timestamp") or report.get("timestamp_utc") or datetime.utcnow().isoformat() + "Z"
    total_kwh = report.get("total_kwh", 0.0)
    total_kg_co2 = report.get("total_kg_co2", total_kwh * float(os.getenv("ENERGY_MIX_KG_CO2_KWH", "0.4")))
    summary = report.get("summary", {})
    passed = summary.get("num_passed", sum(1 for t in report.get("tasks", []) if t.get("exec_passed") or t.get("passed")))
    failed = summary.get("num_failed", sum(1 for t in report.get("tasks", []) if not (t.get("exec_passed") or t.get("passed"))))
    model = report.get("model") or report.get("model_path") or "unknown"
    detector = report.get("face_detector", {})
    det_lines = []
    if detector:
        det_lines.append(f"- manifest: `{detector.get('manifest')}`")
        if detector.get("proto", {}).get("sha256"):
            det_lines.append(f"- proto sha256: `{detector['proto']['sha256']}`")
        if detector.get("model", {}).get("sha256"):
            det_lines.append(f"- model sha256: `{detector['model']['sha256']}`")
    det_text = "\n".join(det_lines) if det_lines else "No detector info"
    md = f"""**SOBERANA Audit — summary**

- model: `{model}`
- timestamp: `{ts}`
- total_kwh: `{total_kwh:.6f}` kWh
- total_kg_co2: `{total_kg_co2:.6f}` kgCO2e
- tasks passed/failed: **{passed} / {failed}**

Face detector used:
{det_text}

Full report is available as an artifact in CI or via attached HTML.
"""
    return md

# GitHub helpers
def gh_request(session, method, url, **kwargs):
    r = session.request(method, url, **kwargs)
    return r

def create_release_and_upload(session, repo: str, html_path: Path, tag_prefix: str = "soberana") -> str | None:
    tag = f"{tag_prefix}-{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    # create release
    url = f"{GITHUB_API}/repos/{repo}/releases"
    payload = {"tag_name": tag, "name": f"SOBERANA report {tag}", "body": "Automated SOBERANA run", "prerelease": False, "draft": False}
    r = gh_request(session, "POST", url, json=payload)
    if r.status_code not in (200, 201):
        print("Release creation failed:", r.status_code, r.text)
        return None
    rel = r.json()
    upload_url = rel.get("upload_url", "").split("{")[0]
    # upload asset
    filename = html_path.name
    mime, _ = mimetypes.guess_type(str(html_path))
    with html_path.open("rb") as fh:
        data = fh.read()
    upload_endpoint = f"{upload_url}?name={filename}"
    headers = {"Content-Type": mime or "application/octet-stream"}
    r2 = gh_request(session, "POST", upload_endpoint, headers=headers, data=data)
    if r2.status_code not in (200, 201):
        print("Release asset upload failed:", r2.status_code, r2.text)
        return None
    j = r2.json()
    return j.get("browser_download_url")

def create_gist_with_token(token: str, file_path: Path, public: bool = False) -> str | None:
    s = requests.Session()
    s.headers.update({"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})
    payload = {"public": public, "files": {file_path.name: {"content": file_path.read_text(encoding='utf-8')}}, "description": "SOBERANA HTML report"}
    r = s.post(f"{GITHUB_API}/gists", json=payload)
    if r.status_code not in (200, 201):
        print("Gist creation failed with token:", r.status_code, r.text)
        return None
    return r.json().get("html_url")

def find_issue(session, repo: str, title: str):
    url = f"{GITHUB_API}/repos/{repo}/issues"
    r = gh_request(session, "GET", url, params={"state":"open","per_page":100})
    r.raise_for_status()
    for item in r.json():
        if item.get("title") == title:
            return item
    return None

def create_issue(session, repo: str, title: str, body: str):
    url = f"{GITHUB_API}/repos/{repo}/issues"
    r = gh_request(session, "POST", url, json={"title": title, "body": body})
    r.raise_for_status()
    return r.json()

def post_comment(session, repo: str, issue_number: int, body: str):
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}/comments"
    r = gh_request(session, "POST", url, json={"body": body})
    r.raise_for_status()
    return r.json()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--html", required=False)
    ap.add_argument("--title", default="SOBERANA Audit: Latest")
    args = ap.parse_args()

    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN required in env")
        sys.exit(2)

    GIST_TOKEN = os.getenv("GIST_TOKEN") or os.getenv("GITHUB_GIST_TOKEN")

    report_path = Path(args.report)
    if not report_path.exists():
        print("report not found", report_path); sys.exit(3)
    report = load_report(report_path)
    md = summary_md(report)

    session = requests.Session()
    session.headers.update({"Authorization": f"token {GITHUB_TOKEN}", "Accept":"application/vnd.github.v3+json"})

    asset_url = None
    # Try release + upload
    if args.html:
        html_path = Path(args.html)
        if html_path.exists():
            print("Attempting to create release and upload HTML asset using GITHUB_TOKEN...")
            try:
                asset_url = create_release_and_upload(session, args.repo, html_path)
            except Exception as e:
                print("Release/upload exception:", e)
                asset_url = None
        else:
            print("HTML file not found, skipping release upload")
    # If upload failed, try gist with GIST_TOKEN first
    gist_url = None
    if not asset_url and args.html:
        if GIST_TOKEN:
            print("Attempting to create gist using GIST_TOKEN...")
            gist_url = create_gist_with_token(GIST_TOKEN, Path(args.html), public=False)
            if gist_url:
                print("Created gist with GIST_TOKEN:", gist_url)
        if not gist_url:
            print("Attempting to create gist with GITHUB_TOKEN as fallback...")
            gist_url = create_gist_with_token(GITHUB_TOKEN, Path(args.html), public=False)
            if gist_url:
                print("Created gist with GITHUB_TOKEN:", gist_url)

    # Compose body
    body = md + "\n\n"
    if asset_url:
        body += f"HTML report uploaded as release asset: {asset_url}\n\n"
    elif gist_url:
        body += f"HTML report uploaded as gist: {gist_url}\n\n"
    else:
        body += "HTML report not uploaded (insufficient permissions). See CI artifacts for JSON report.\n\n"

    # Create or update issue
    existing = find_issue(session, args.repo, args.title)
    if existing:
        print("Posting comment to existing issue:", existing.get("html_url"))
        post_comment(session, args.repo, existing["number"], body)
    else:
        print("Creating issue:", args.title)
        create_issue(session, args.repo, args.title, body)

    print("Done.")

if __name__ == "__main__":
    import argparse
    main()