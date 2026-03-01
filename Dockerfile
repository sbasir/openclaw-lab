FROM openclaw
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ripgrep git curl jq python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*
USER node