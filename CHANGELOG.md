# Changelog

All notable changes are documented here. The project follows semantic versioning.

## [2.1.1] - 2026-09-02

### Fixed

- Recovered refreshable Claude Code access-token failures through the official CLI path, then retried usage once with freshly read credentials.
- Prevented the hidden-window/no-tray dead state by keeping a permanent application tray icon independent of provider usage data.
- Hardened automatic session recovery with a single-flight guard and credential-state cooldown, and added regression coverage for recovery and tray lifecycle failures.

## [2.1.0] - 2026-08-25

### Added

- Bounded, schema-versioned local usage history with atomic writes, retention, migration, corruption recovery, opt-out, and clear-history controls.
- Conservative burn rate, pace-to-reset, confidence, and projected-exhaustion calculations that require comparable samples and respect reset boundaries.
- Explicitly opt-in local tray alerts with reset-aware suppression, persistent cooldown, and deduplication.
- Preview-first redacted diagnostics for support issues, including app/OS versions and provider status categories without tokens, usernames, raw home paths, auth contents, or raw provider responses.
- Officially validated WinGet v2.0.0 portable manifest and documented submission gate.

### Changed

- Packaged settings now live under `%LOCALAPPDATA%\AI CLI Control Center`; a valid adjacent legacy config is copied once without deleting the source.
- Start with Windows now detects a stale Run entry instead of treating any old command as enabled.
- Updated the supported build/runtime dependency set after isolated production-build and packaged-smoke verification.

### Documentation

- Added the public v2.0.0 artifact/Defender/provenance audit, safe branch maintenance commands, dependency decisions, privacy architecture, and real sanitized v2.1 UI screenshots.

The operational fixes originally considered for a separate v2.0.1 are included in this tested v2.1.0 release candidate, avoiding two back-to-back binaries.

## [2.0.0] - 2026-08-25

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
