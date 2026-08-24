# AI Usage Widget v2 — Provider Health Roadmap

## Goal

Evolve the widget from a quota viewer into a Windows control center for AI CLIs. The application should understand the lifecycle of each provider instead of treating every failure as an authentication failure.

## Current implementation status

Implemented on `v2/provider-health`:

- Normalized CLI, auth, usage, and action state for Claude Code and Codex CLI.
- Windows discovery through PATH, `where.exe`, and confirmed installation locations; absolute-path version and action execution.
- Claude access/refresh expiry inspection, scopes and subscription metadata without exposing token values.
- Backend-selected install, login, refresh-session, and retry actions.
- Official Windows native installers for Claude Code and Codex CLI with post-install rediscovery and version validation.
- Explicit Claude refresh-before-login probe through the official CLI. There is no direct refresh-token exchange.
- Typed HTTP/network/format errors and an in-memory last-known-good usage snapshot.
- Transitional provider-health UI integration while the legacy usage/tray runtime remains intact.

Still pending:

- Persistent last-good cache and adaptive refresh/backoff.
- CLI update detection and one-click update UX.
- A dedicated diagnostics view and richer path-conflict repair.
- Removal of the transitional `widget_v2.py` patch after provider modules fully own the runtime.

The provider lifecycle is split into four independent layers:

1. **Installation** — whether the CLI exists, which executable will run, version, install method and duplicate installations.
2. **Authentication** — whether credentials exist, whether the access session is usable/refreshable and whether full login is actually required.
3. **Usage** — whether quota data is available, stale, rate-limited or temporarily unavailable.
4. **Recovery** — the safest action the widget can perform: install, refresh session, login, retry or repair a local conflict.

## Provider health model

Every provider should expose a normalized health snapshot:

```text
ProviderHealth
├─ cli
│  ├─ state
│  ├─ executable_path
│  ├─ version
│  ├─ install_method
│  ├─ detected_copies[]
│  └─ path_conflict
├─ auth
│  ├─ state
│  ├─ access_expires_at
│  ├─ refresh_expires_at
│  └─ credential_source
├─ usage
│  ├─ state
│  ├─ last_success_at
│  ├─ last_error
│  └─ stale
└─ recommended_action
```

The UI must never infer an action from an error string. Actions come from structured state.

## Phase 1 — Provider Health foundation

### 1.1 CLI discovery

- Detect Claude Code and Codex before trying to run login.
- Resolve the executable that the current process would launch.
- Probe known Windows installation paths even when PATH is stale.
- Collect duplicate installations.
- Read `--version` using the absolute executable path.
- Classify the installation method where it can be inferred safely.
- Detect PATH conflicts when the executable selected by PATH differs from another valid installation.

Acceptance criteria:

- Missing CLI is represented as `cli.state = missing`, not as an auth error.
- An installed CLI exposes an absolute executable path.
- Multiple detected copies are visible in diagnostics.
- CLI commands are executed by absolute path after discovery.

### 1.2 Structured auth state

- Remove duplicate token-status implementation from `JsApi`.
- Separate `missing_credentials`, `valid`, `expiring`, `access_expired_refreshable`, `login_required` and `credentials_broken`.
- Claude must inspect both access-token and refresh-token metadata when present.
- `401/403` must not automatically mean `login_required`.

Acceptance criteria:

- Expired Claude access token with a still-valid refresh session does not show full login as the primary action.
- Missing CLI and missing credentials produce different actions.

### 1.3 Structured usage state and last-good snapshot

- Distinguish auth errors, rate limit, network failure, server error and unknown payload.
- Preserve the last successful quota snapshot when the current refresh fails.
- Mark stale data with its age.
- Respect `Retry-After` where available.

Acceptance criteria:

- Temporary API failure never erases previously valid quota information.
- `429` never offers Login.

## Phase 2 — One-click lifecycle actions

### 2.1 Install CLI

Provider-specific install strategies:

- Claude Code: official Windows native installer as primary strategy; WinGet as optional fallback.
- Codex CLI: official Windows installer as primary strategy.

Requirements:

- Explicit user action only.
- Capture installer exit status.
- Re-run discovery after installation.
- Do not trust the process PATH to update in-place; discover known paths again.
- Verify success with the absolute executable and `--version`.

### 2.2 Update CLI

- Detect current version.
- Detect whether an update is available without blocking normal quota refresh.
- Run provider-native update/install flow.
- Detect duplicate/stale installations after update.

### 2.3 Claude session repair

Recovery order:

1. Retry usage once when appropriate.
2. If access session is expired but refresh session is still valid, invoke the official Claude CLI to perform a minimal authenticated probe/refresh.
3. Watch the credential file for a successful rotation.
4. Retry usage.
5. Only if refresh fails or credentials require user interaction, launch full `claude auth login`.

Do not implement Anthropic refresh-token exchange directly in the widget. The official CLI owns rotating refresh credentials and should remain the single writer.

## Phase 3 — UX and diagnostics

Provider card states:

```text
CLI missing            -> Install
Credentials missing    -> Sign in
Access expired         -> Refresh session
Refresh unavailable    -> Sign in
Rate limited           -> Retry later
Network/server failure -> Retry
Duplicate install      -> Fix PATH / diagnostics
Healthy                -> no recovery button
```

Diagnostics view:

- Executable selected by PATH.
- Every discovered CLI copy.
- Version per copy.
- Credential file path and metadata presence (never display token values).
- Last API status and last successful refresh.
- Recommended action with reason code.

## Phase 4 — Adaptive refresh and history

- Activity-aware refresh interval.
- Exponential backoff with jitter for transient failures.
- Local history database for quota snapshots.
- Burn-rate and projected exhaustion.
- Notifications for configurable thresholds and quota resets.

## Release direction

### v2 Provider Health

- CLI discovery and installation.
- Authentication health and recovery.
- Usage health and safe recovery actions.

### v2.x

- CLI update detection and one-click update.
- Persistent last-good cache.
- Adaptive refresh with Retry-After, backoff, and jitter.
- Notifications.

### v3

- Local usage history.
- Burn rate and projected exhaustion.
- Daily and weekly charts.
- Provider plugin architecture.

Future providers to evaluate after the lifecycle contract stabilizes: Gemini CLI, OpenCode, and other AI developer CLIs. They are not part of the current implementation.

## Phase 5 — Provider architecture

Move provider-specific behavior behind a common provider interface/capability descriptor:

```text
Provider
├─ discover_cli()
├─ inspect_auth()
├─ fetch_usage()
├─ install()
├─ update()
├─ recover_auth()
└─ capabilities
```

This is the prerequisite for adding Gemini CLI, OpenCode and future providers without growing provider-specific `if` branches in the UI/backend.

## Implementation order on `v2/provider-health`

1. Add CLI discovery/health module.
2. Integrate discovery into snapshots exposed to the UI.
3. Replace login button inference with `recommended_action`.
4. Add one-click install actions.
5. Add Claude refresh-before-login recovery.
6. Add last-good usage cache and typed API failures.
7. Refactor provider code out of `widget.py` once behavior is covered by the new model.

## Non-goals for the first v2 iteration

- No direct manipulation of OAuth refresh tokens.
- No new providers before the lifecycle model is stable.
- No full UI redesign before the state/action contract is working.
- No Python-to-.NET rewrite as part of the health refactor.
