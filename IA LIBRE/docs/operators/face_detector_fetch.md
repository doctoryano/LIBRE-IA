# Face Detector Download & Verification (Operators)

1) Place manifest
 - Copy `data/models/face_detector/manifest.json.example` to `data/models/face_detector/manifest.json`
 - Fill `proto_sha256` and `model_sha256` with expected checksums (obtain from your source or OOB verification).

2) Run helper
 - From repo root:
   ./scripts/fetch_face_detector.sh --manifest data/models/face_detector/manifest.json --verify

3) Verify results
 - The script prints sha256 for each file and exits non-zero on mismatch (fail-closed).
 - If you don't have expected checksums, run without `--verify` to download and compute the checksums, then add them to the manifest via secure OOB process.

4) Security notes
 - Prefer obtaining expected sha256 from a trusted channel (project website, signed release).
 - After download, do not commit model blobs to the repo; keep them on operator-controlled storage and record manifests/hashes in version control.

5) Test redaction endpoint
 - Build server and run.
 - Use the /api/redact endpoint to validate redaction before enabling multimodal captioning.