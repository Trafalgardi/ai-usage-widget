# Changelog

All notable changes are documented here. The project follows semantic versioning.

## [2.0.0] - Unreleased

### Added

- Provider Health for Claude Code and Codex CLI with install, sign-in, repair, retry, and PATH-conflict guidance.
- Versioned Python-to-JavaScript contract and normalized action results.
- Safe manual update checks and reversible Start with Windows integration.
- Reproducible PyInstaller build, EXE smoke check, ZIP/checksum generation, SBOM, and provenance workflow.

### Changed

- Positioned the product as a Windows AI CLI Control Center.
- Moved the v2 UI out of runtime JavaScript injection and into the versioned local UI.
- Split provider registry, process execution, health aggregation, UI bridge, update, and Windows integration responsibilities.

### Security

- Redacted token-like values and user-home paths at UI/action boundaries.
- Added privacy, security, contribution, and vulnerability-reporting guidance.

## [1.6.2]

- Last public v1 release before the Provider Health v2 work.
