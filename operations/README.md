# Operations

Operational commands are separated from deployment declarations.

- `production/`: deployment, backup, restore verification, migration, and health checks.
- `cluster/`: node membership, replica promotion, and failover tooling.
- `development/`: local-only setup and diagnostics.

Run production deployment only through `production/deploy.sh`. It reads the
top-level `docker-compose.prod.yml` and `.env.production` unless explicitly
overridden by `DASHBOARD_COMPOSE_FILE` and `DASHBOARD_ENV_FILE`.
