# v2 release checklist and record

This file is a status record, not an unreviewed list of empty boxes. Detailed public artifact evidence is in `POST_RELEASE_NOTES.md`.

## Before tagging

- [x] v2.0.0 diff/version reviewed and tagged.
- [x] Clean Windows tests, production build, EXE smoke, ZIP, and SHA256SUMS completed.
- [x] SBOM and GitHub provenance generated and published.
- [x] Public v2.0.0 EXE/ZIP scanned with Microsoft Defender after download.
- [ ] Authenticode signing remains unavailable; do not claim the executable is signed.

## GitHub repository metadata

- [x] Description and homepage configured.
- [x] Release topics configured.
- [x] Discussions enabled.
- [x] Private vulnerability reporting is enabled.

## Publish

- [x] v2.0.0 branch merged, tag and GitHub Release published.
- [x] EXE, ZIP, SHA256SUMS, SBOM, and provenance published and re-audited.
- [x] Pages screenshots, README links, latest-release redirect, and downloads verified publicly.
- [x] v2.1.0 published from tagged commit `2935460`; public assets, latest redirect, Pages, checksums, packaged smoke, Defender scan, and provenance re-verified.
- [x] v2.0.0 WinGet portable manifest created and passed official `winget validate`.
- [ ] WinGet submission is blocked until local-manifest install/uninstall behavior is tested in an admin-enabled disposable environment; validation alone is not treated as behavioral proof.

## Next release gate

- [x] Final changelog and 2.1.0 version metadata reviewed together.
- [x] All 54 unit tests, compileall, link checks, production Windows build, headless EXE smoke, and hidden WebView lifecycle smoke passed from the release source.
- [x] Exact release EXE/ZIP scanned with Defender and final hashes verified.
- [x] Artifact workflow `32768882064` completed; provenance resolves to tag `v2.1.0` and commit `2935460`; v2.0.0 assets were not replaced.

## Launch

- [ ] Publish a short demo showing `CLI not found → Install → Ready`.
- [ ] Announce the release with the Control Center positioning, trust boundaries, unsigned/signed status, and direct release link.
- [ ] Monitor issues for installer, PATH, WebView2, and usage-endpoint regressions.
