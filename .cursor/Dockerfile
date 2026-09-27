FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    sudo \
    python3 \
    python3-pip \
    python3-venv \
    python3.12-venv \
    git \
    curl \
    ca-certificates \
    ffmpeg \
    tesseract-ocr \
    libgl1 \
    libgles2 \
    libegl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y nodejs \
  && rm -rf /var/lib/apt/lists/* \
  && (id ubuntu >/dev/null 2>&1 || useradd -m -s /bin/bash ubuntu) \
  && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ubuntu \
  && chmod 0440 /etc/sudoers.d/ubuntu

USER ubuntu
WORKDIR /home/ubuntu
