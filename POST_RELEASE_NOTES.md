# Post-release verification

## Public v2.0.0 audit — 2026-08-25

Baseline and ancestry:

- `origin/master` and the commit referenced by the annotated `v2.0.0` tag both resolve to `7b17e7a528113eb7301eb37fc11fe7a444d8e26f`.
- A clean branch created directly from that commit passed all 38 release tests, release-link checks, a production PyInstaller build, and packaged headless smoke.
- The existing user checkout and running v2.0.0 process were not modified.

Public artifact verification:

| Asset | SHA-256 | Result |
| --- | --- | --- |
| `AI-CLI-Control-Center.exe` | `59e9204a97304093cbaa0a8377734047ad437d34fdf29b8df43e451c937eabd4` | SHA256SUMS and GitHub digest match; downloaded EXE smoke passed |
| `AI-CLI-Control-Center-v2.0.0-windows-x64.zip` | `d7787586198cd22afb391a33dbcfbc559f5b1c0360b670918a588104ed090890` | SHA256SUMS and GitHub digest match; extracted EXE smoke passed |
| `AI-CLI-Control-Center.exe.provenance.jsonl` | `bf4dd715e61846a7217bfc6603324863774c5e538acb0db22be97bbfecc5f435` | GitHub digest matches |
| `sbom.cdx.json` | `251faa27983e8e6f56e79f96d3ba84acff52aac9a56e88585471208d2fbf4da7` | GitHub digest matches |

`gh attestation verify` succeeded for the public EXE. The verified SLSA statement names commit `7b17e7a`, the `release-artifacts.yml` workflow on `master`, GitHub-hosted runners, and the same EXE digest shown above.

Microsoft Defender was available with real-time protection enabled and signature version `1.457.318.0`. A custom scan of the downloaded release directory, including the EXE and ZIP, completed without a new threat detection. No artifact was uploaded to a third-party scanner.

Public delivery checks:

- [GitHub Pages](https://trafalgardi.github.io/ai-usage-widget/) returned HTTP 200.
- [Latest release](https://github.com/Trafalgardi/ai-usage-widget/releases/latest) redirected to v2.0.0.
- The EXE and SHA256SUMS download URLs returned HTTP 200.
- Every linked Pages image and the README's local release-facing links were present.

No blocker was found in the immutable v2.0.0 assets. Operational improvements are shipped only in later versions; the v2.0.0 tag and assets are not rewritten.
