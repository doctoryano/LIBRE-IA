```markdown
# Emergency Response Checklist — IA LIBRE 2026 (Stewarding & Auditing)

Propósito
- Pasos claros, ordenados y verificables para responder a una Emergency Stop (detected during training).
- Mantener la cadena de custodia, preservar evidencias cifradas y notificar a las partes responsables.

Roles
- Steward: Custodio de la clave privada GPG para descifrado e investigación forense.
- Operator: Persona que ejecuta el runner / CI and follows the checklist.
- Steering Committee: Governance body that reviews incidents and approves remediation.

IMMEDIATE ACTIONS (Operator)
1. DO NOT attempt to decrypt files on the runner. Keep steward private keys offline.
2. Preserve logs:
   - Do not remove `reports/` and `data/forensics/` directory.
   - If CI runs upload artifacts, ensure `data/forensics/*.gpg` and `reports/emergency_stop_*.json` are attached to the CI artifacts.
3. Copy artifact identifiers (artifact name, CI run id, runner id) to a secure incident ticket (internal issue tracker).
4. Create a human-readable incident note including:
   - CI run id, commit SHA, runner hostname, timestamp, user who triggered the run.
   - Short description of safety trigger (from `reports/emergency_stop_*.json`).

ARCHIVAL (Operator / CI)
1. If not already done by training script, create an encrypted archive:
   - Use `scripts/archive_and_encrypt.py --path <output_dir> --pubkey data/gpg-keys/steward_pubkey.asc`
   - The command prints JSON summary with archive path and sha256.
2. Upload the encrypted .gpg to an immutable artifact storage (CI artifact, S3 with versioning, or other).
3. Confirm that the original checkpoint directory has been fully removed from the runner (training script should have done this). Verify with assertions (ls, du) and record outputs to incident note.

STEWARD ACTIONS (Offline / Trusted Environment)
1. Steward obtains the encrypted archive via secure channel (download artifact).
2. Steward decrypts locally using the steward's private key:
   - Use `scripts/steward_decrypt.sh --in <archive.tar.gz.gpg> --out /secure/location`
   - Decryption must occur on an air-gapped or highly secured environment.
3. Steward inspects artifacts and logs:
   - Evaluate model state, checkpoints, training logs, token batches that triggered the classifier.
   - Build a minimal reproducible test-case for the flagged behavior (if feasible).
4. Steward prepares a forensic report with:
   - findings, recommendations, severity, and remediation steps.

COMMUNICATION (Steering Committee)
1. Steward files a detailed Incident Report into the repository's auditor channel (or private ticket), referencing:
   - PR created earlier (manifest pin), CI run id, artifacts sha256, and steward analysis.
2. Steering Committee convenes to decide:
   - Whether to re-run training (with changes),
   - Whether to blacklist the dataset/model used,
   - Whether to revoke or update policies.
3. Document final decisions in `docs/decisions/incident_<ts>.md` and update governance logs.

FOLLOW-UP (Operator)
1. If remediation requires data changes (remove/modify examples), create a PR with dataset adjustments and require reviews from Steering Committee.
2. Re-run benchmark in an isolated environment after fixes.
3. Archive incident and close the loop in the SOBERANA Issue thread (post_audit_summary will append a comment).

CHECKLIST (Quick)
- [ ] Ensure `data/forensics/*.gpg` present in CI artifacts
- [ ] Ensure `reports/emergency_stop_*.json` present in CI artifacts
- [ ] Confirm output_dir removed from runner
- [ ] Steward has received encrypted archive
- [ ] Forensic report created (private)
- [ ] Steering Committee notified and PR created if action required

Security reminders
- NEVER store steward private keys on any CI/runners.
- Use the least privilege for repo tokens; separate tokens for gist vs releases if policy requires.
- Keep chain-of-custody logs with timestamps and hashes for future audit.
```