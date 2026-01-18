# Imagen base para entrenamiento QLoRA reproducible (trainer)
# NOTA: Ajusta la versión de CUDA / torch wheel según tu infraestructura (drivers).
FROM nvidia/cuda:12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates pkg-config unzip wget jq \
    python3 python3-venv python3-pip git-lfs libsndfile1 && \
    rm -rf /var/lib/apt/lists/*

# Create venv
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# Upgrade pip & setuptools
RUN pip install --upgrade pip setuptools wheel

# Install training libs
# NOTE: For torch choose wheel compatible with your CUDA version. The operator must edit this when needed.
RUN pip install --no-cache-dir \
    transformers==4.35.0 \
    accelerate==0.22.0 \
    peft==0.4.0 \
    safetensors \
    datasets \
    sentencepiece \
    tokenizers \
    bitsandbytes==0.39.0 \
    "git+https://github.com/huggingface/transformers.git@main" || true

# (Optional) Install specific torch wheel externally if necessary:
# Example placeholder (uncomment and edit to match your CUDA):
# RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121

# Install small utilities
RUN pip install --no-cache-dir tqdm accelerate wandb

# Copy repo scripts into image (optional; host mount preferred in prod)
COPY . /workspace

# Default workdir
WORKDIR /workspace

# Entrypoint is empty; we run training scripts explicitly with python inside container
CMD ["bash"]