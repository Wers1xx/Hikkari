#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-up}" in
  up|start)
    docker compose up -d --build
    docker compose logs -f
    ;;
  stop)
    docker compose stop
    ;;
  logs)
    docker compose logs -f
    ;;
  shell)
    docker compose exec hikkari bash
    ;;
  rebuild)
    docker compose build --no-cache
    docker compose up -d
    ;;
  *)
    echo "Usage: $0 {up|stop|logs|shell|rebuild}"
    ;;
esac
