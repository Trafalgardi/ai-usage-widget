# WinGet manifest preparation

Do not commit a fabricated installer URL or hash. After the v2 GitHub Release is public:

1. Download the final release EXE or ZIP and calculate its SHA-256.
2. Generate a manifest with `wingetcreate new <public-release-url>`.
3. Use the final package identifier chosen by the owner, version, exact public URL, SHA-256, MIT license, Windows minimum version, and silent-install behavior actually supported by the artifact.
4. Run `winget validate --manifest <manifest-directory>` and test installation/uninstallation in a clean Windows VM.
5. Submit only after code signing and update behavior are documented.

The present one-file app is portable and does not yet provide a true uninstall entry. A portable WinGet manifest is preferable unless an installer is added.
