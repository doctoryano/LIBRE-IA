# (fragment - integrate into existing script)
# After fetch_face_detector.sh --verify (and after you imported GPG keys if needed)
# Pin manifest by creating a PR (uses GITHUB_TOKEN, no direct commits)
if [ -n "${GITHUB_REPOSITORY:-}" ] && [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "[ci_run] Creating a PR to pin the verified manifest (pin_manifest_tracker)..."
  python3 scripts/pin_manifest_tracker.py --repo "${GITHUB_REPOSITORY}" --manifest "$ROOT_DIR/data/models/face_detector/manifest.json" || { echo "pin_manifest_tracker failed"; exit 1; }
else
  echo "[ci_run] GITHUB_REPOSITORY or GITHUB_TOKEN not set; skipping manifest pinning"
fi

# Later, pass GIST_TOKEN securely to post_audit_summary (set in workflow as secret)
export GIST_TOKEN="${GIST_TOKEN:-}"
python3 scripts/post_audit_summary.py --repo "${GITHUB_REPOSITORY}" --report "$REPORT_DIR/soberana_report.json" --html "$REPORT_DIR/soberana_report.html"