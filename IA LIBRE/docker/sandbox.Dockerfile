# docker/sandbox.Dockerfile
# Lightweight sandbox image for executing generated Python code.
# Built from python:3.10-slim and creates an unprivileged user with uid/gid 9999.
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user 'sandbox' with UID/GID 9999
RUN groupadd -g 9999 sandbox || true && \
    useradd -m -u 9999 -g 9999 -s /usr/sbin/nologin sandbox || true

# Minimal Python environment (no extra packages). Keep image small.
# If you need specific packages for tests, pin and install them here.
# e.g. pip install pytest
RUN python -m pip install --upgrade pip

WORKDIR /work
# ensure /work owned by sandbox user
RUN chown sandbox:sandbox /work

# drop privileges by default (docker run will specify --user 9999)
USER 9999

ENTRYPOINT ["/usr/bin/python", "-u"]