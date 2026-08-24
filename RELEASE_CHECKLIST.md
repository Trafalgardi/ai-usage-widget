# v2 release checklist

Implementation can be completed locally; the actions below require repository-owner authority or release credentials.

## Before tagging

- [ ] Review the complete diff and `CHANGELOG.md`; choose the final v2 version/tag.
- [ ] Run `./scripts/build.ps1` on a clean Windows checkout and retain the EXE, ZIP, and `SHA256SUMS.txt`.
- [ ] Run **Prepare release artifacts** and download the SBOM and provenance-bearing artifacts.
- [ ] Scan the release candidate with Microsoft Defender and at least one independent scanner.
- [ ] Code-sign the EXE with an Authenticode certificate if available, then rebuild checksums and smoke-test the signed binary.

## GitHub repository metadata

- [ ] Set the description to: `Windows AI CLI Control Center — install, diagnose, repair, and monitor Claude Code and Codex CLI.`
- [ ] Set the homepage to `https://trafalgardi.github.io/ai-usage-widget/`.
- [ ] Add topics: `windows`, `claude-code`, `codex-cli`, `ai-tools`, `usage-monitor`, `developer-tools`, `pywebview`.
- [ ] Enable Discussions if the maintainer wants a support/community channel.
- [ ] Confirm private vulnerability reporting is enabled.

## Publish

- [ ] Push the reviewed branch and merge through a pull request.
- [ ] Tag the reviewed commit and create a GitHub Release using the v2 changelog.
- [ ] Attach the signed-or-reviewed EXE, ZIP, `SHA256SUMS.txt`, and SBOM; confirm provenance is visible.
- [ ] Update the website and verify every screenshot/link from the public URL.
- [ ] Only after the final public release URL and SHA-256 exist, fill a WinGet manifest from `packaging/winget/README.md`, validate it with `winget validate`, and submit to `microsoft/winget-pkgs`.

## Launch

- [ ] Publish a short demo showing `CLI not found → Install → Ready`.
- [ ] Announce the release with the Control Center positioning, trust boundaries, unsigned/signed status, and direct release link.
- [ ] Monitor issues for installer, PATH, WebView2, and usage-endpoint regressions.
