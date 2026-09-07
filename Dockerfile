# =============================================================================
# HYDRA-UMC-VLA-ENGINE - Container Build: Dockerfile
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0 - see LICENSE
# =============================================================================
# Real, minimal image for the action-tokenization/trajectory-integration
# HTTP API (api.py's own server, stdlib http.server - the base package
# has zero runtime dependencies). Same --addr/--port CLI the real CM5
# systemd unit (systemd/hydra-umc-vla-engine.service) already runs, just
# bound to 0.0.0.0 instead of 127.0.0.1 here - a container's own network
# namespace already isolates it the way the systemd unit's loopback bind
# does on bare metal, and 127.0.0.1 inside a container would be
# unreachable from HYDRA-UMC-COGNITIVE-NODE's own container over the
# compose network. Non-root, matching that same unit's own
# User=hydra-umc-vla-engine. Consumed by HYDRA-UMC-COGNITIVE-NODE's own
# docker-compose.yml as the "vla-engine" service (with /dev/hailo0
# passed through there for real inference).
#
# Deliberately installs the BASE package only, not the optional [hailo]
# extra - hailort is not on PyPI (Hailo Developer Zone / `apt install
# hailo-all`) and hailo_runtime.py's own import is already lazy, so the
# encode/decode/trajectory/status HTTP surface this image serves works
# without it; real Hailo-10 inference is a separate, hardware-specific
# concern this base image does not try to bundle.

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --system --create-home --home-dir /home/hydra hydra
USER hydra

EXPOSE 8098
ENTRYPOINT ["hydra-umc-vla-engine"]
CMD ["serve", "--addr", "0.0.0.0", "--port", "8098"]
