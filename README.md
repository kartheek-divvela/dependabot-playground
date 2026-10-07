# Dependabot Playground

This repository is a deliberately outdated, multi-ecosystem playground for testing dependency updates. It exercises pip (`module-a`), npm (`module-b`), and Maven (`module-c`, `module-d`, plus the root parent); GitHub Actions are configured in `.github/workflows`.

All dependency and action versions are **DELIBERATELY pinned to old releases** so future dependency tooling has work to do, including intentionally vulnerable versions for alert testing.

## Layout

- `module-a/`: Python package and pip requirements
- `module-b/`: Node.js manifest without a lockfile
- `module-c/`, `module-d/`: Java Maven child modules
- `pom.xml`: Maven aggregator and dependency/plugin management
- `.github/workflows/`: CI and pull-request validation workflows

## Status / Not yet enabled

`.github/dependabot.yml` is intentionally **ABSENT**. Dependabot version-update configuration will be added in a later PR once the CI workflows are in place. No claim is made that Dependabot is currently active in this repository.
