# Privacy

AI CLI Control Center has no project-operated server, account system, analytics, advertising, or telemetry.

## Local data read

- Claude Code credentials: `~/.claude/.credentials.json` or `~/.config/claude/.credentials.json`
- Codex CLI credentials: `$CODEX_HOME/auth.json` or `~/.codex/auth.json`
- Application settings: `%LOCALAPPDATA%\AI CLI Control Center\config.json` for packaged builds, or `config.json` beside the source entry point during development
- Local history: `%LOCALAPPDATA%\AI CLI Control Center\history.json` when history is enabled
- CLI executable paths and version output from local discovery commands

Credential values are used in memory for provider usage requests. Provider Health exposes only non-secret metadata, such as whether a token exists, expiry timestamps, scopes, subscription type, and a home-relative credential location. It does not include access or refresh token values.

History is local and bounded. It stores only a schema version, provider/window keys, UTC capture timestamps, reset timestamps, and normalized remaining percentages. It never stores tokens, raw API responses, account identifiers, usernames, or credential paths. History can be disabled or cleared in Settings. Smart alerts are disabled by default and their cooldown/deduplication state is stored in the same local file.

## Network destinations

- Claude usage: `https://api.anthropic.com/api/oauth/usage` with fallback to `https://claude.ai/api/oauth/usage`
- Codex usage: `https://chatgpt.com/backend-api/wham/usage`
- Manual update check: `https://api.github.com/repos/Trafalgardi/ai-usage-widget/releases/latest`
- User-triggered installers: the official scripts referenced by `https://claude.ai/install.ps1` and `https://chatgpt.com/codex/install.ps1`

Usage requests send the corresponding locally stored credential to that provider. The manual update check sends no provider credential. The app does not send tokens or usage data to this project's maintainer.

## Local changes

Settings are written locally with atomic replacement. On the first packaged launch after upgrading, a valid legacy `config.json` beside the EXE is copied to the new per-user directory; the legacy file is not deleted or rewritten. Corrupt history is moved aside for recovery and a clean bounded store is created.

Enabling **Start with Windows** adds one value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; disabling it removes that value. A stale Run entry is reported as disabled instead of pretending it points to the current executable. The update checker reports availability and opens no installer; updates remain a manual download.

Redacted diagnostics use a strict allowlist: app/OS version, provider discovery and status, CLI version/source category, PATH conflict category, last error code, and timestamps. Full paths, usernames, raw errors, auth contents, and tokens are excluded. The app shows a preview before copying or opening GitHub, and never submits an issue automatically.
