# docker/vllm_pro.Dockerfile
# Imagen base para despliegues vLLM de alto rendimiento (A100/H100)
# Ajusta CUDA/CUDNN/OS según tu infra (las imágenes oficiales NVIDIA son recomendadas).
#
# Notas:
# - Esta imagen instala vllm y dependencias GPU-compatibles.
# - Para reproducibilidad, pinnea versiones exactas (las aquí son orientativas).
# - Para H100/A100 y bf16, necesitas una versión de torch/torchvision compatible con tu driver.
#
FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /workspace

# System packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git curl ca-certificates libsndfile1 pkg-config \
    libglib2.0-0 libsm6 libxext6 libxrender1 unzip wget locales \
    python3 python3-venv python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Set locale
RUN locale-gen en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

# Create virtualenv (optional but tidy)
ENV VENV_PATH=/opt/venv
RUN python3 -m venv $VENV_PATH
ENV PATH="$VENV_PATH/bin:$PATH"

# Upgrade pip / build tools
RUN pip install --upgrade pip setuptools wheel

# Install torch with CUDA support.
# IMPORTANT: Select the correct torch+cu version for your drivers.
# Example: for CUDA 12.1 you may need a nightly or a compatible wheel. Replace according to your infra.
# Uncomment and adjust the appropriate line for your environment.

# NOTE: The below is an example; you MUST verify the correct torch wheel for your GPU and OS.
RUN pip --no-cache-dir install --upgrade "pip"

# Install vLLM and common ML libs. Pin versions in production for reproducibility.
RUN pip --no-cache-dir install \
    "vllm==0.4.0" \
    "transformers==4.35.0" \
    "safetensors" \
    "huggingface-hub" \
    "aiohttp" \
    "uvicorn[standard]" \
    "fastapi" \
    "sentencepiece"

# If you require torch in this container (e.g., for other adapters), install a compatible wheel:
# Example placeholder (adjust to correct wheel for CUDA 12.x):
# RUN pip --no-cache-dir install torch --index-url https://download.pytorch.org/whl/cu121

# Note about bitsandbytes:
# bitsandbytes requires a specific CUDA/driver combination. Install only if you need it.
# RUN pip --no-cache-dir install bitsandbytes==0.39.0

# Create directories for models and logs (to be mounted from host)
RUN mkdir -p /workspace/models /workspace/logs /workspace/data /workspace/scripts

# Copy helper scripts (if present) - you can mount scripts from host instead
COPY ../scripts /workspace/scripts
COPY ../data /workspace/data

# Expose vLLM API port (change if needed)
EXPOSE 8000

# Default entrypoint
CMD ["bash", "-lc", "echo 'vLLM PRO image built. Mount /workspace/models and run /workspace/scripts/start_vllm_server.sh' && bash"]