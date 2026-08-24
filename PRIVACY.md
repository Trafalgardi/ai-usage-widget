# Privacy

AI CLI Control Center has no project-operated server, account system, analytics, advertising, or telemetry.

## Local data read

- Claude Code credentials: `~/.claude/.credentials.json` or `~/.config/claude/.credentials.json`
- Codex CLI credentials: `$CODEX_HOME/auth.json` or `~/.codex/auth.json`
- Application settings: `config.json` beside the source entry point or packaged executable
- CLI executable paths and version output from local discovery commands

Credential values are used in memory for provider usage requests. Provider Health exposes only non-secret metadata, such as whether a token exists, expiry timestamps, scopes, subscription type, and a home-relative credential location. It does not include access or refresh token values.

## Network destinations

- Claude usage: `https://api.anthropic.com/api/oauth/usage` with fallback to `https://claude.ai/api/oauth/usage`
- Codex usage: `https://chatgpt.com/backend-api/wham/usage`
- Manual update check: `https://api.github.com/repos/Trafalgardi/ai-usage-widget/releases/latest`
- User-triggered installers: the official scripts referenced by `https://claude.ai/install.ps1` and `https://chatgpt.com/codex/install.ps1`

Usage requests send the corresponding locally stored credential to that provider. The manual update check sends no provider credential. The app does not send tokens or usage data to this project's maintainer.

## Local changes

Settings are written locally. Enabling **Start with Windows** adds one value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; disabling it removes that value. The update checker reports availability and opens no installer; updates remain a manual download.
