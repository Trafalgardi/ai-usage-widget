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

## Public v2.1.0 audit — 2026-08-25

Release source and workflows:

- PR [#10](https://github.com/Trafalgardi/ai-usage-widget/pull/10) passed Windows/Linux tests and the production Windows build, then was squash-merged as `2935460d4bbd822840842447f208f14c7f91375c`.
- The push build on `master` (`32768749981`) passed independently before tagging.
- Annotated tag `v2.1.0` resolves to `2935460`; release workflow `32768882064` ran from that tag and completed build, headless smoke, SBOM, provenance, and artifact upload.

Published assets:

| Asset | SHA-256 |
| --- | --- |
| `AI-CLI-Control-Center.exe` | `937d4e32fae88f4da3fb39bebc45468d93b5ac34357e98dcbce4021c5ac94bc0` |
| `AI-CLI-Control-Center-v2.1.0-windows-x64.zip` | `e71e33c09b356aec71bf439d0c2a6083781d33b58f50d73b9213dc3103bd8c45` |
| `AI-CLI-Control-Center.exe.provenance.jsonl` | `748e575efd6664cd1459f2f91aad33ad6cf2e7c465f4671a52a601bc9a5d8432` |
| `sbom.cdx.json` | `aa76a00e548e486f9696304ab683ef2ef3c2d87f8fe0530ae619733ccb329486` |
| `SHA256SUMS.txt` | `0d44fea52b55c69a6e9b2ce8af0016e78a47761490b5936972d5ec4374d8e3c5` |

The public assets were downloaded into a separate temporary directory. GitHub
digests and `SHA256SUMS.txt` matched; the public EXE and ZIP-extracted EXE passed
packaged smoke. Microsoft Defender signature `1.457.318.0` scanned the exact
workflow artifacts with no new detection. `gh attestation verify` identified
the public EXE digest, tag, commit, GitHub-hosted runner, and workflow run above.

[The v2.1.0 release](https://github.com/Trafalgardi/ai-usage-widget/releases/tag/v2.1.0),
the latest-release redirect, direct EXE/checksum links, GitHub Pages, and all
three new v2.1 screenshots returned HTTP 200. The existing v2.0.0 release and
the owner's running copy were not changed or stopped.
