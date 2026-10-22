# Bemol infrastructure

This repository owns staging Compose configuration, Traefik rules, SSH deployment, environment templates, PostgreSQL backups and local acceptance tooling. Application Dockerfiles, local development and image publication belong to their respective repositories.

- Consult [staging operations](docs/STAGING.md). Branches follow `main` for production and `staging` for the current VPS configuration; production is not provisioned here. Staging is the only shared environment configured here; deploy and application rollback use `scripts/deploy-staging.sh` over SSH. Traefik is a separate Compose project. Verify the target host's containers, effective environment, Traefik configuration and health before claiming operational success; provisioning notes and Compose files are not live evidence.
- Read the relevant application's `.github/workflows/` when assessing deployment triggers; documentation about prepared changes may not match the executing branch. Retain environment configuration and CI/image publication. Do not provision, deploy or change deployment policy unless requested.
- Preserve persistent volumes, private environment files and unrelated worktree/index changes. Commit and push only when requested; do not add or run tests on initiative.
- Follow the user's scope and existing authorization; an audit does not authorize implementation. Complete the requested outcome and authorized verification without stopping after a first draft or repeatedly asking for the same approval. Stop for an unresolved scope, data-loss or access decision, and report blockers or unverified runtime behavior explicitly.

- Keep comments short, simple and on one line; omit obvious comments.
