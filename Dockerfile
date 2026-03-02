FROM openclaw
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates tzdata build-essential pkg-config git curl wget jq \
    ripgrep htop tree iproute2 net-tools openssl rsync neovim \
    python3 python3-pip python3-venv \
  && rm -rf /var/lib/apt/lists/*
USER node