# Security policy

## Supported versions

Security fixes are prepared for the current v2 branch and the latest public release when practical.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository. If it is unavailable, contact the repository owner privately before opening a public issue. Do not include tokens, credential files, or personally identifying paths in a report.

Include the affected version, Windows version, impact, reproduction steps using synthetic credentials, and any suggested mitigation. You can expect an acknowledgement within seven days; remediation timing depends on severity and maintainer availability.

## Security boundaries

The application reads CLI credential files to call the providers' usage endpoints. It does not implement its own OAuth exchange, does not write provider tokens, and does not provide unattended self-update. Provider installation and login actions execute the providers' official commands only after a user action. The project is not code-signed yet; verify release checksums and provenance when those artifacts are published.
