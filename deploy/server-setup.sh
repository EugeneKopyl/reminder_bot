#!/usr/bin/env bash
set -euo pipefail

SWAP_FILE=/swapfile
SWAP_SIZE=2G

ensure_swap() {
  if swapon --show=NAME --noheadings | grep -q .; then
    echo "swap already enabled:"
    swapon --show
    return
  fi
  fallocate -l "$SWAP_SIZE" "$SWAP_FILE"
  chmod 600 "$SWAP_FILE"
  mkswap "$SWAP_FILE"
  swapon "$SWAP_FILE"
  grep -q "^$SWAP_FILE " /etc/fstab || echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
}

tune_swappiness() {
  echo "vm.swappiness=10" > /etc/sysctl.d/99-reminder-bot.conf
  sysctl --system > /dev/null
}

check_docker() {
  docker --version
  docker compose version
}

report_ports() {
  ss -tulpn
  if ss -tln | awk '{print $4}' | grep -qE '(^|:)443$'; then
    echo "port 443 is taken: run the API proxy on another port"
  else
    echo "port 443 is free"
  fi
}

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
ensure_swap
tune_swappiness
check_docker
report_ports
