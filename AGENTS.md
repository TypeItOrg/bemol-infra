# Bemol infrastructure

This repository owns staging Compose configuration, Nginx configuration, Certbot hooks, SSH deployment, environment templates and PostgreSQL backups. Application Dockerfiles, local development and image publication belong to their respective repositories.

- Nginx + Certbot are host services configured by `deploy/nginx/` and `deploy/certbot/`. Keep `/api/*` handled by Next.js and `/api/v1` inaccessible from the public edge. Institutional IPv6 rate and concurrency limits use /64 networks; do not replace them with per-address limits.

- Consult [staging operations](docs/STAGING.md). The default branch is `staging`, for the current VPS configuration. Production is not configured; create `main` only when preparing that environment. Staging is the only shared environment configured here; deploy and application rollback use `scripts/deploy-staging.sh` over SSH. Host Nginx and Certbot handle edge routing and TLS. Verify the target host, containers, effective environment, proxy, certificates and health before claiming operational success; provisioning notes and Compose files are not live evidence.
- Read the relevant application's `.github/workflows/` when assessing deployment triggers; documentation about prepared changes may not match the executing branch. Retain environment configuration and CI/image publication. Do not provision, deploy or change deployment policy unless requested.
- Preserve persistent volumes, private environment files and unrelated worktree/index changes. Commit and push only when requested. Do not add or restore infrastructure test suites or acceptance harnesses; application tests belong in the API/UI repositories.
- Follow the user's scope and existing authorization; an audit does not authorize implementation. Complete the requested outcome and authorized verification without stopping after a first draft or repeatedly asking for the same approval. Stop for an unresolved scope, data-loss or access decision, and report blockers or unverified runtime behavior explicitly.

- Keep comments short, simple and on one line; omit obvious comments.
