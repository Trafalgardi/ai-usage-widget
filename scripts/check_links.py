"""Fail when release-facing Markdown or landing-page local links are broken."""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
MARKDOWN_FILES = [ROOT / name for name in (
    "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "PRIVACY.md",
    "SECURITY.md", "RELEASE_CHECKLIST.md",
)] + list((ROOT / "docs").glob("*.md"))


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("a", "img"):
            self.values.append(attrs.get("href") or attrs.get("src"))


def _local_target(source, value):
    if not value or value.startswith(("#", "mailto:")):
        return None
    parsed = urlsplit(value.strip("<>"))
    if parsed.scheme or parsed.netloc:
        return None
    return (source.parent / unquote(parsed.path)).resolve()


def main():
    missing = []
    markdown_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    for source in MARKDOWN_FILES:
        if not source.exists():
            continue
        for value in markdown_pattern.findall(source.read_text(encoding="utf-8")):
            target = _local_target(source, value.split(maxsplit=1)[0])
            if target and not target.exists():
                missing.append((source.relative_to(ROOT), value))

    landing = ROOT / "docs" / "index.html"
    parser = _Links()
    parser.feed(landing.read_text(encoding="utf-8"))
    for value in parser.values:
        target = _local_target(landing, value)
        if target and not target.exists():
            missing.append((landing.relative_to(ROOT), value))

    if missing:
        for source, value in missing:
            print(f"Broken local link in {source}: {value}")
        return 1
    print("Release-facing local links OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
