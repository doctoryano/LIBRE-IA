#!/usr/bin/env bash
# scripts/ci_setup_runner.sh
# Idempotent installer for Docker + NVIDIA Container Toolkit on Ubuntu 22.04 (self-hosted runner).
# Usage: sudo bash scripts/ci_setup_runner.sh
set -euo pipefail

REQUIRED_DEBIAN_PACKAGES=(apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common)

function echoerr() { echo "$@" 1>&2; }

if [ "$(id -u)" -ne 0 ]; then
  echoerr "This script requires root. Run with sudo."
  exit 1
fi

echo "[ci_setup] Updating apt cache..."
apt-get update -y

echo "[ci_setup] Installing prerequisite packages..."
apt-get install -y --no-install-recommends "${REQUIRED_DEBIAN_PACKAGES[@]}"

# --- Docker CE installation (official repo) ---
if ! command -v docker >/dev/null 2>&1; then
  echo "[ci_setup] Installing Docker (CE)..."
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
  ARCH="$(dpkg --print-architecture)"
  echo \
    "deb [arch=${ARCH} signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io
  echo "[ci_setup] Docker installed."
else
  echo "[ci_setup] Docker already installed. Skipping."
fi

# Ensure docker service is active
systemctl enable --now docker

# Add current non-root user (if any) to docker group for convenience when run manually
if [ -n "${SUDO_USER:-}" ]; then
  echo "[ci_setup] Adding $SUDO_USER to docker group..."
  usermod -aG docker "$SUDO_USER" || true
fi

# --- NVIDIA Container Toolkit installation ---
# Note: NVIDIA drivers (GPU kernel modules) must already be installed for GPUs to be usable.
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "[ci_setup] Detected NVIDIA drivers (nvidia-smi present). Installing NVIDIA Container Toolkit..."
  distribution=$(. /etc/os-release; echo "$ID$VERSION_ID")
  curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/experimental/${distribution}/nvidia-container-toolkit.list \
    -o /etc/apt/sources.list.d/nvidia-container-toolkit.list || true
  apt-get update -y || true
  apt-get install -y --no-install-recommends nvidia-container-toolkit || apt-get install -y --no-install-recommends nvidia-docker2 || true
  # Configure daemon.json to use the nvidia runtime by default (safe change — backup first)
  DAEMON_JSON="/etc/docker/daemon.json"
  if [ -f "$DAEMON_JSON" ]; then
    cp "$DAEMON_JSON" "${DAEMON_JSON}.bak"
  fi
  cat > "$DAEMON_JSON" <<'JSON'
{
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
JSON
  systemctl restart docker
  echo "[ci_setup] NVIDIA Container Toolkit installed and Docker daemon configured."
else
  echo "[ci_setup] WARNING: nvidia-smi not found. NVIDIA drivers not detected. If you plan to use GPUs, install drivers first."
  echo "[ci_setup] You can still use Docker for CPU-only tasks."
fi

# --- Useful additional tools ---
echo "[ci_setup] Installing jq and other useful CLI tools..."
apt-get install -y --no-install-recommends jq vim unzip net-tools iputils-ping || true

# --- Post-install checks ---
echo "[ci_setup] Post-install checks:"
echo " - docker version: $(docker --version 2>/dev/null || echo 'docker not found')"
if command -v nvidia-smi >/dev/null 2>&1; then
  echo " - nvidia-smi:"
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader || true
else
  echo " - nvidia-smi: not present"
fi

cat <<EOF
CI Runner setup complete.

Next recommended manual steps for operator:
1) Re-login to apply docker group membership for your user:
   newgrp docker  # or log out / log in

2) Verify that you can run Docker commands without sudo:
   docker run --rm hello-world

3) If you need GPU access, verify:
   docker run --gpus all --rm nvidia/cuda:12.1.1-runtime-ubuntu22.04 nvidia-smi

4) Build the sandbox image:
   docker build -f docker/sandbox.Dockerfile -t ia-libre/sandbox:latest docker/

5) Build the vLLM PRO image (optional):
   docker build -f docker/vllm_pro.Dockerfile -t ia-libre/vllm:pro .

Security note:
 - Minimize users with access to Docker daemon.
 - Keep drivers and packages updated.
EOF

exit 0