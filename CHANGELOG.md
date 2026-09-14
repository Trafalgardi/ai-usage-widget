# Changelog

All notable changes are documented here. The project follows semantic versioning.

## [2.3.0] - 2026-09-14

### Added

- Local input/output token accounting for Claude Code and Codex, covering today and the last seven local calendar days, including nested subagents and archived Codex sessions.
- Collapsible provider cards with compact input/output totals; expand to inspect cache reads/writes, models, and standard short-context API cost estimates using the dated rate table.
- Independent Settings switch for local token accounting, with missing-data and partial-coverage states. No conversation content or new token database is persisted.
- Opt-in metadata-only reconciliation script and a design for future cross-machine comparison.

### Fixed

- Classify Codex windows by their reported duration, including weekly-only Pro Lite/x5 plans; do not label a weekly primary window as a five-hour session. The tray uses the available weekly window.
- Account for modern Codex per-response usage records, including responses that never update the UI token counter; deduplicate copied responses by response ID and retain legacy-format support.
- Ignore Claude zeroed auxiliary streaming blocks and avoid marking the current period partial because of invalid historical records outside that period.
- Apply the correct light-theme colors to Claude token and Provider Health cards, while retaining Codex's dark theme.

### Validation

- Reconciled a frozen, metadata-only local sample against an independent per-response calculation: zero differences in input, output and cache totals for both providers and both periods; Decimal cost arithmetic also matched.
- Added regression coverage for duplicate responses, CLI format upgrades, model switches, cache-write durations, timezone/day boundaries and malformed records.
- Costs remain a standard short-context API equivalent, not a subscription bill or subscription-limit percentage. Fast/long-context, regional and tool surcharges are excluded; unknown model rates remain unpriced.

## [2.2.0] - 2026-09-09

### Added

- Tray tooltips show both five-hour and weekly remaining limits with compact reset countdowns.
- Choose the tray indicator's five-hour or weekly limit independently for Claude and Codex through the tray menu; choices persist across restarts.
- English and Russian tray controls, with a dash when the selected limit is unavailable.

### Fixed

- Refresh tray menu translations immediately when the application language changes.

## [2.1.2] - 2026-09-04

### Fixed

- Restored tray icon publication after the v2.1.1 readiness guard replaced pystray's default setup callback.
- Kept the window visible unless the application tray icon has actually been published.

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
