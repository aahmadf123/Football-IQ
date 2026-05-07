# syntax=docker/dockerfile:1
# GPU worker image for Football-IQ video processing pipeline.
# Pinned to PyTorch 2.5.1 + CUDA 12.4 on Ubuntu 22.04.

FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime AS base

LABEL maintainer="Toledo Football Analytics"
LABEL org.opencontainers.image.source="https://github.com/aahmadf123/Football-IQ"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# ── System dependencies (FFmpeg with NVDEC/NVENC) ─────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# ── Python dependencies ───────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Worker code ───────────────────────────────────────────────────────────────
COPY . .

# Run as non-root
RUN addgroup --system gpugroup && adduser --system --ingroup gpugroup gpuuser
USER gpuuser

CMD ["python", "-m", "worker"]
