# Contributing

AI CLI Control Center prioritizes a reliable Claude Code and Codex CLI experience on Windows. Please discuss large provider additions or stack changes before implementation.

## Development

1. Install Python 3.12 and WebView2.
2. Create a virtual environment and install `requirements-build.txt`.
3. Run `python -m unittest discover -s tests -v`.
4. Run `./scripts/build.ps1 -SkipInstall` from PowerShell for a release-equivalent build.

Tests must mock network, process, installer, and credential access. Never use or commit real auth files. UI, release notes, screenshots, and user-facing documentation should be in English. Preserve the `widget_v2.py` entry point unless a migration is documented.
