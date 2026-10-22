#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export BOT_IMAGE_TAG="${1:-latest}"

docker compose pull
docker compose up -d --remove-orphans
docker compose ps
