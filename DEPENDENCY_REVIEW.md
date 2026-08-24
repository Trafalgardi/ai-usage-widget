# Dependency review after v2.0.0

Review date: 2026-08-25. Each update was rebased or reproduced against the
then-current `master`, tested alone, and merged only after fresh CI. No security
control was weakened to make a build pass.

| PR | Update | Compatibility and supply-chain review | Verification | Decision |
|---|---|---|---|---|
| [#2](https://github.com/Trafalgardi/ai-usage-widget/pull/2) | `actions/setup-python` 5 → 7 | v7 moves to the Node 24 action runtime and removes an unused pip-install input. Existing `python-version`, cache, and dependency-path inputs remain supported. | CI run `32766429640`: Windows/Linux tests and Windows production build passed. | Merged. |
| [#3](https://github.com/Trafalgardi/ai-usage-widget/pull/3) | `actions/checkout` 4 → 7 | v7 moves to Node 24 and tightens unsafe ref handling for privileged trigger types not used here. Workflows now explicitly disable credential persistence and use read-only contents permission. | CI run `32766864119`: all jobs passed after a normal merge conflict resolution. | Merged. |
| [#4](https://github.com/Trafalgardi/ai-usage-widget/pull/4) | `actions/attest-build-provenance` 2 → 4 | v4 wraps the current GitHub attestation action. Existing `subject-path` and least-privilege `id-token`/`attestations` permissions remain correct. | CI `32767063631` passed; manually dispatched artifact/SBOM/provenance run `32767197400` also passed. | Merged. |
| [#5](https://github.com/Trafalgardi/ai-usage-widget/pull/5) | `actions/upload-artifact` 4 → 7 | v7 changes the action runtime and adds an opt-in direct-archive mode; the default upload semantics and existing inputs are compatible. | Fresh PR production build was green; artifact upload completed. | Merged. |
| [#6](https://github.com/Trafalgardi/ai-usage-widget/pull/6) | PyInstaller 6.15 → 6.22.2 | No used spec/API removal. Resources, icon, Windows version metadata, one-file startup, and packaged imports were checked. | Isolated 54-test-compatible build and headless EXE smoke passed; CI `32767380443` passed. | Merged. |
| [#7](https://github.com/Trafalgardi/ai-usage-widget/pull/7) | setuptools 80.9 → 84 | Build backend and `py-modules` metadata remain supported for Python 3.10–3.13. | Isolated production build and packaged smoke passed; CI `32767589970` passed after a normal merge resolution. | Merged. |
| [#8](https://github.com/Trafalgardi/ai-usage-widget/pull/8) | Pillow 11.3 → 12.3 | Pillow 12 drops Python 3.9 and removed old APIs not used here; the project already requires Python 3.10+. Tray image creation and packaged icon/resources remain compatible. | Isolated build/smoke passed; CI `32767755757` passed. | Merged. |
| [#9](https://github.com/Trafalgardi/ai-usage-widget/pull/9) | pywebview 5.4 → 6.2.1 | Removed legacy dialog constants and DOM APIs are not used. Bridge exposure, callback serialization, minimize-to-tray lifecycle, WebView2 creation, and hidden-window shutdown were reviewed. | Isolated unit/build/headless smoke plus real hidden WebView lifecycle smoke passed; CI `32767889225` passed. | Merged. |

GitHub Actions are kept as official major tags to receive compatible security
fixes, matching the repository's established Dependabot policy. The workflows
limit token permissions and prevent checkout from persisting credentials.
Monthly, one-update-per-PR Dependabot remains useful here because it preserves
the isolated evidence above; grouping these major runtime changes would reduce
diagnostic precision rather than reduce meaningful risk.
