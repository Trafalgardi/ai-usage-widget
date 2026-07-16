# AI Usage Widget — limit tracker for Windows 11

A lightweight always-on-top widget that shows **usage limits** for
Claude Code and Codex CLI in real time.

![Overview](preview/shot_overview.png)

## Features

### Screens
1. **Overview** — current 5-hour session remaining for both services with reset timer
2. **Claude** — session + weekly (and Opus weekly if available) with reset countdown
3. **Codex** — session + weekly with reset countdown, plan, additional model limits
4. **Settings** — refresh interval, window size, always-on-top mode

### Status Indicators
- **Token status** — colored badge next to service name:
  -  Active — token is valid
  -  Expiring — less than 1 hour remaining
  -  Expired — login required
- **Countdown timer** — shows seconds until next refresh
- **Red bar** — usage ≥ 85%

### System Tray
Minimize to tray and the widget keeps working in the background. Two tray icons with percentages:
- **Orange digits** — Claude Code
- **Green digits** — Codex CLI

Hover over an icon for detailed tooltip. Right-click:
- **Show** — restore window
- **Refresh** — fetch fresh data
- **Exit** — close widget completely

### Quick Login
When a token expires, a **"Login via CLI"** button appears — launches `claude auth login` or `codex login` in a separate window.

---

## Installation

1. **Python 3.10+** required: https://python.org (check *Add to PATH* during install)
2. In the widget folder:
   ```bash
   pip install pywebview pystray Pillow
   ```
3. Run:
   ```bash
   python widget.py
   ```
   Or double-click **start_widget.vbs** to run without a console window.

### Autostart with Windows

`Win+R` → `shell:startup` → copy a **shortcut** to `start_widget.vbs` there.

---

## Screenshots

![Overview](preview/shot_overview.png)
![Claude](preview/shot_claude.png)
![Codex](preview/shot_codex.png)
![Settings](preview/shot_settings.png)
![Tray](preview/shot_tray.png)

### Window Controls
- **Drag** — by the top bar
- **⟳** — refresh data manually
- **◉** — toggle always-on-top
- **⎯** — minimize to tray
- **✕** — close widget

---

## Data Sources

The widget only sends requests to official service APIs. Tokens are read from
the same files used by the CLIs:

| Service | Token | Endpoint |
|---|---|---|
| Claude Code | `~/.claude/.credentials.json` | `api.anthropic.com/api/oauth/usage` |
| Codex CLI | `~/.codex/auth.json` | `chatgpt.com/backend-api/wham/usage` |

You must be logged into each CLI (`/login` in Claude Code, `codex login`).

### About the Endpoints

Both endpoints are the same ones used by the CLIs themselves and tools like CodexBar,
but they are undocumented and may change. If a card stops updating after a CLI update —
report it, and we'll fix the parser (it already accepts multiple field name variants).

---

## Settings

### Via UI
The **Settings** tab lets you change:
- **Refresh interval** — how often to poll the API (15–600 seconds)
- **Window width** — 200–800 px
- **Window height** — 300–1200 px
- **Always on top** — on/off
- **Language** — Русский / English

### Via config.json
```json
{
  "language": "en",
  "refresh_interval_sec": 60,
  "window": {
    "width": 380,
    "height": 600,
    "on_top": true,
    "x": null,
    "y": null
  }
}
```

---

## Troubleshooting

* **HTTP 401/403** — token expired. Click "Login via CLI" or login manually
* **Empty window** — WebView2 Runtime not installed (comes with Windows 11 by default; otherwise: https://developer.microsoft.com/microsoft-edge/webview2/)
* **Red bar** — remaining ≤ 15%, prepare for limit reset
* **Python icon instead of widget** — restart the app, the icon is applied after window creation

---

## Development

### Dependencies
- **pywebview** — WebView2-based window
- **pystray** — system tray icons
- **Pillow** — tray icon generation

### Project Structure
```
usage-widget/
├── widget.py          # Backend: API, parsing, tray
├── ui.html            # Frontend: HTML/CSS/JS interface
├── config.json        # Settings (auto-generated)
├── icon/
│   ├── 512.png        # Source app icon
│   └── app.ico        # Windows icon (auto-generated)
├── preview/           # README screenshots
├── install.bat        # Dependency installer
└── start_widget.vbs   # Console-free launcher
```

### Building EXE
```bash
pip install pyinstaller
python -m PyInstaller --onefile --windowed --name="AI-Usage" --icon="icon/app.ico" --add-data "ui.html;." --add-data "icon/512.png;icon" --add-data "icon/app.ico;icon" --collect-all pywebview --collect-all pystray widget.py
```

### License
MIT
