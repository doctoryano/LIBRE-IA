# Forensic Archival & Stewarding — IA LIBRE 2026

Objetivo
- En caso de Emergency Stop durante entrenamiento, el sistema archivará y cifrará los checkpoints
  para análisis forense, sin dejar artefactos accesibles en el host.

Componentes
- scripts/archive_and_encrypt.py: empaqueta una carpeta y la cifra con la clave pública del "steward".
- scripts/train_qlora_sovereign.py: invoca el archivador en caso de EmergencyStop, crea un marcador JSON en `reports/`.
- stewardship public key: colocar `steward_pubkey.asc` en `data/gpg-keys/` (opcional), o configurar `STEWARD_PUBKEY` env var.

Requisitos previos
- gpg (>=2.2) instalado en runner.
- steward public key (ASCII armoured) proporcionada por el Steering Committee.
- scripts/archive_and_encrypt.py debe poder ejecutar gpg (no necesita private keys).

Steward key provisioning
1. Obtain the steward public key file (e.g., steward_pubkey.asc) out-of-band.
2. Place it in the operator host or repo `data/gpg-keys/steward_pubkey.asc` (do not commit private keys).
3. Prefer to provide the path via environment variable in CI:
   STEWARD_PUBKEY=data/gpg-keys/steward_pubkey.asc

CI integration
- Ensure `scripts/archive_and_encrypt.py` is accessible and executable in the runner.
- Set env var `STEWARD_PUBKEY` or `STEWARD_GPG_RECIP` (fingerprint) in the workflow before running training.
- On EmergencyStop the archived encrypted artifact will be saved to `data/forensics/` and the CI artifacts uploader should collect `data/forensics/*.gpg` and `reports/emergency_stop_*.json`.

Operational procedure after EmergencyStop
- The steward obtains the encrypted archive (artifact).
- Steward uses their private key offline to decrypt and analyze the archive.
- The steward publishes findings to the Steering Committee and creates a remediation plan.

Security notes
- Never store steward private key on the runner.
- The archive contains potentially sensitive signals; treat it under strict governance and access control.
- Consider adding HSM or offline storage for steward private key for robust key management.
