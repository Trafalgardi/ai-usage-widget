# WinGet manifest preparation

Do not commit a fabricated installer URL or hash. After the v2 GitHub Release is public:

The checked-in `manifests/` tree describes the public v2.0.0 EXE as a WinGet
`portable` package. It intentionally does not claim MSI behavior, an app-owned
uninstaller, or Start menu integration. WinGet owns portable registration,
upgrade, alias, and uninstall behavior.

Validate from the repository root:

```powershell
winget validate --manifest packaging/winget/manifests/t/Trafalgardi/AICLIControlCenter/2.0.0
```

Before submission, re-download the public EXE, verify its GitHub digest and
SHA256SUMS, run the packaged smoke check, test `winget install` and
`winget uninstall` in a disposable Windows user or VM, and then submit this
exact version directory to `microsoft/winget-pkgs`. Do not submit a future
version until its public URL and SHA-256 exist.

The present one-file app is portable and does not provide its own uninstall
entry. A portable WinGet manifest is accurate because WinGet, rather than the
app, owns registration and removal. Code signing is still recommended but must
not be claimed until an Authenticode certificate is available.
