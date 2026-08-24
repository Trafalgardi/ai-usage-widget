# -*- coding: utf-8 -*-
"""Provider installation discovery and normalized CLI health snapshots.

This module intentionally contains no UI code and never reads or mutates OAuth
token values. It is the first layer of the v2 provider-health architecture.
"""

import os
import shutil
import subprocess


_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _norm_path(path):
    if not path:
        return None
    try:
        path = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    except Exception:
        pass
    return os.path.normcase(os.path.normpath(path))


def _add_candidate(items, seen, path, install_method, source):
    if not path:
        return
    expanded = os.path.abspath(os.path.expandvars(os.path.expanduser(path)))
    key = _norm_path(expanded)
    if not key or key in seen:
        return
    if not os.path.isfile(expanded):
        return
    seen.add(key)
    items.append({
        "path": expanded,
        "install_method": install_method,
        "source": source,
    })


def _infer_install_method(provider_id, path):
    p = (_norm_path(path) or "").lower()
    if "\\microsoft\\winget\\links\\" in p:
        return "winget"
    if "\\npm\\" in p or "\\node_modules\\" in p:
        return "npm"
    if provider_id == "claude" and "\\.local\\bin\\claude" in p:
        return "native"
    if provider_id == "codex" and "\\programs\\openai\\codex\\bin\\codex" in p:
        return "standalone"
    return "unknown"


def _run_version(path, args):
    command = [path] + list(args)
    suffix = os.path.splitext(path)[1].lower()
    if os.name == "nt" and suffix in (".cmd", ".bat"):
        command = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=_CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as exc:
        return {
            "works": False,
            "version": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first_line = output.splitlines()[0].strip() if output else None
    return {
        "works": proc.returncode == 0,
        "version": first_line if proc.returncode == 0 else None,
        "error": None if proc.returncode == 0 else (
            first_line or f"exit code {proc.returncode}"
        ),
    }


def _provider_spec(provider_id):
    user_profile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    home = os.path.expanduser("~")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")

    if provider_id == "claude":
        known = [
            (os.path.join(user_profile, ".local", "bin", "claude.exe"), "native", "known_path"),
            (os.path.join(home, ".local", "bin", "claude.exe"), "native", "known_path"),
            (
                os.path.join(local_appdata, "Microsoft", "WinGet", "Links", "claude.exe"),
                "winget",
                "known_path",
            ),
            (os.path.join(appdata, "npm", "claude.cmd"), "npm", "known_path"),
        ]
        return {
            "command": "claude",
            "version_args": ["--version"],
            "known": known,
        }

    if provider_id == "codex":
        codex_install_dir = os.environ.get("CODEX_INSTALL_DIR")
        known = []
        if codex_install_dir:
            known.append((
                os.path.join(codex_install_dir, "codex.exe"),
                "standalone",
                "env_CODEX_INSTALL_DIR",
            ))
        known += [
            (
                os.path.join(local_appdata, "Programs", "OpenAI", "Codex", "bin", "codex.exe"),
                "standalone",
                "known_path",
            ),
            (os.path.join(appdata, "npm", "codex.cmd"), "npm", "known_path"),
        ]
        return {
            "command": "codex",
            "version_args": ["--version"],
            "known": known,
        }

    raise ValueError(f"Unknown provider: {provider_id}")


def discover_cli(provider_id):
    """Return normalized installation health for one provider.

    `path_selected` is the executable resolved through the current process PATH
    when available. `executable_path` is the working executable the widget
    should use for provider commands.
    """
    spec = _provider_spec(provider_id)
    candidates = []
    seen = set()

    path_selected = shutil.which(spec["command"])
    if path_selected:
        _add_candidate(
            candidates,
            seen,
            path_selected,
            _infer_install_method(provider_id, path_selected),
            "PATH",
        )

    for path, method, source in spec["known"]:
        _add_candidate(candidates, seen, path, method, source)

    detected = []
    for candidate in candidates:
        probe = _run_version(candidate["path"], spec["version_args"])
        item = dict(candidate)
        item.update(probe)
        detected.append(item)

    working = [item for item in detected if item["works"]]
    selected = None
    path_key = _norm_path(path_selected)
    if path_key:
        selected = next(
            (item for item in working if _norm_path(item["path"]) == path_key),
            None,
        )
    if selected is None and working:
        selected = working[0]

    if selected:
        state = "installed"
    elif detected:
        state = "broken"
    else:
        state = "missing"

    distinct_working = {_norm_path(item["path"]) for item in working}
    path_conflict = len(distinct_working) > 1

    return {
        "state": state,
        "command": spec["command"],
        "executable_path": selected["path"] if selected else None,
        "version": selected["version"] if selected else None,
        "install_method": selected["install_method"] if selected else None,
        "path_selected": path_selected,
        "path_conflict": path_conflict,
        "detected_copies": detected,
    }


def discover_all():
    return {
        "claude": discover_cli("claude"),
        "codex": discover_cli("codex"),
    }
