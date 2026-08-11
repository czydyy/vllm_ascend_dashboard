#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required for the local development environment." >&2
  exit 1
}

if [[ ! -f .env.local ]]; then
  cp .env.local.example .env.local
  jwt="$(openssl rand -hex 24)"
  litellm="$(openssl rand -hex 16)"
  sed -i.bak \
    -e "s/replace-with-a-random-local-jwt-secret/$jwt/" \
    -e "s/replace-with-a-random-local-litellm-key/sk-local-$litellm/" \
    -e "s/replace-with-a-local-root-password/local-root-$litellm/" \
    -e "s/replace-with-a-local-database-password/local-db-$litellm/" \
    .env.local
  rm -f .env.local.bak
  echo "Created .env.local with generated local-only secrets."
fi

args=(compose --env-file .env.local -f docker-compose.dev.yml)
if [[ "${1:-}" == "--workers" ]]; then
  args+=(--profile workers)
  shift
fi

if [[ "${1:-}" == "--down" ]]; then
  docker "${args[@]}" down
else
  docker "${args[@]}" up --build -d
  echo "Dashboard: http://localhost:3000"
  echo "API docs:  http://localhost:8000/docs"
fi
