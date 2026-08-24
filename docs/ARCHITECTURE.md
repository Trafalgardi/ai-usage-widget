# v2 architecture

The v2 release keeps the proven WebView/tray and usage-fetch runtime while moving new lifecycle behavior behind explicit module boundaries. This avoids a high-risk rewrite of quota parsing and tray behavior.

## Boundaries

- `application.py`: composition root and packaged-resource smoke mode.
- `provider_registry.py`: supported provider IDs, capabilities, official installer commands, and login arguments.
- `provider_health.py`: Windows CLI discovery, version probes, installation-method inference, and PATH conflict detection.
- `auth_health.py`: read-only, non-secret credential metadata inspection.
- `usage_health.py`: typed failure classification and in-memory last-good usage cache.
- `provider_actions.py` / `session_repair.py`: explicit user-triggered lifecycle operations.
- `process_runner.py`: normalized, time-bounded process execution without shell interpolation.
- `app_storage.py`: atomic local settings persistence.
- `ui_contract.py`: contract version and typed serialization/action results.
- `ui_bridge.py`: the only v2 API exposed to JavaScript.
- `ui.html`: checked-in UI; no runtime JavaScript injection.
- `widget.py`: retained legacy quota parsers and tray/window runtime. New provider lifecycle behavior must not be added here.

## Contract rules

Every snapshot contains `contract_version`. Provider Health has its own `schema_version`. The UI renders only backend-declared actions and does not infer login from human-readable error strings. Action IDs and provider IDs are allowlisted by the registry.

Provider Health separates `cli`, `auth`, and `usage`. Secret credential values are never included. Credential paths are reduced to a home-relative display location, and token-like text is redacted at action/error boundaries.

## Compatibility

`widget_v2.py` remains the supported source and packaged entry point, but delegates to `application.main`. Existing shortcuts therefore continue working. The older `widget.py` entry still launches the legacy bridge; release builds use only `widget_v2.py`.

## Deliberate limits

- Usage endpoints are provider-owned but not documented as stable public APIs.
- Last-good usage is process-local, not persisted across restarts.
- App updates are detected through a manual GitHub Releases check and are never installed automatically.
- Start with Windows uses the current-user Run key and requires no elevation.
- Provider installers execute official remote PowerShell scripts only after an explicit user action and always re-run local discovery to verify the result.
