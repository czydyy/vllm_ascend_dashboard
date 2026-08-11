#!/bin/bash
set -euo pipefail

echo "Initializing development dependencies"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js is required" >&2; exit 1; }
command -v uv >/dev/null || { echo "uv is required; install it before running bootstrap" >&2; exit 1; }
command -v pnpm >/dev/null || { echo "pnpm is required; install it before running bootstrap" >&2; exit 1; }

echo "Installing backend dependencies"
(cd backend && uv sync --dev)

echo "Installing frontend dependencies"
(cd frontend && pnpm install)

echo "Initializing the current MySQL schema without creating users"
uv run --directory backend python ../database/bootstrap.py --no-users

cat <<'EOF'

Development initialization completed.
Start the stack with the platform-specific compose helper.
Administrator accounts must be provisioned through the controlled user-management flow;
this script intentionally contains no default credentials.
EOF
