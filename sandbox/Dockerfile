# ProofBox sandbox image. The agent's code runs here and only here.
# Build on the Vultr VM:  docker build -t proofbox-sandbox:latest sandbox/
FROM python:3.12-slim

ARG INSTALL_FOUNDRY=1
ARG SOLC_VERSION=0.8.26

RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs npm curl ca-certificates git coreutils \
 && pip install --no-cache-dir pytest==8.3.4 \
 && rm -rf /var/lib/apt/lists/*

# Foundry + a pinned solc so Solidity proofs compile with no network.
RUN if [ "$INSTALL_FOUNDRY" = "1" ]; then \
      curl -L https://foundry.paradigm.xyz | bash \
   && /root/.foundry/bin/foundryup \
   && cp /root/.foundry/bin/forge /root/.foundry/bin/cast /root/.foundry/bin/anvil /usr/local/bin/ \
   && curl -fsSL -o /usr/local/bin/solc https://github.com/ethereum/solidity/releases/download/v${SOLC_VERSION}/solc-static-linux \
   && chmod +x /usr/local/bin/solc ; \
    fi

# Tools that could help an attacker reach out are removed after build.
RUN apt-get purge -y curl git && apt-get autoremove -y && rm -rf /root/.foundry /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home --shell /bin/sh sandbox
ENV FOUNDRY_SOLC_VERSION=/usr/local/bin/solc \
    FOUNDRY_OFFLINE=true \
    PYTHONPATH=/work \
    NODE_OPTIONS=--max-old-space-size=384
USER 1000:1000
WORKDIR /work
CMD ["sleep", "infinity"]
