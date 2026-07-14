import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _extract(pattern: str, relative_path: str) -> str:
    content = (ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(pattern, content)
    assert match, f"version not found in {relative_path}"
    return match.group(1)


def test_release_version_is_consistent():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert expected == _extract(r'version="([^"]+)"', "setup.py")
    assert expected == _extract(r'__version__ = "([^"]+)"', "phone_agent/__init__.py")
    assert expected == _extract(
        r'setApplicationVersion\("([^"]+)"\)',
        "gui_app.py",
    )
