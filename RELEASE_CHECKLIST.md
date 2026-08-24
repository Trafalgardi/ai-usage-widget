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
- [ ] Confirm private vulnerability reporting is enabled.

## Publish

- [x] v2.0.0 branch merged, tag and GitHub Release published.
- [x] EXE, ZIP, SHA256SUMS, SBOM, and provenance published and re-audited.
- [x] Pages screenshots, README links, latest-release redirect, and downloads verified publicly.
- [x] v2.0.0 WinGet portable manifest created and passed official `winget validate`.
- [ ] WinGet submission is blocked until local-manifest install/uninstall behavior is tested in an admin-enabled disposable environment; validation alone is not treated as behavioral proof.

## Next release gate

- [ ] Review final changelog and version metadata together.
- [ ] Run all unit tests, compileall, link checks, production Windows build, headless EXE smoke, and hidden WebView lifecycle smoke from a clean commit.
- [ ] Scan the exact release EXE/ZIP with Defender and verify final hashes.
- [ ] Run the artifact workflow, verify its provenance against the tagged commit, then publish without replacing older assets.

## Launch

- [ ] Publish a short demo showing `CLI not found → Install → Ready`.
- [ ] Announce the release with the Control Center positioning, trust boundaries, unsigned/signed status, and direct release link.
- [ ] Monitor issues for installer, PATH, WebView2, and usage-endpoint regressions.
