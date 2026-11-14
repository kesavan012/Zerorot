"""
env_extractor.py — Environment variable extractor for ZeroRot.

Scans all source files with language-specific regex patterns to find every
environment variable reference. Also reads .env.example for defaults and
inline comments.
"""
import json
import pathlib
import re
from typing import Optional

from .utils import safe_read, infer_type_from_name, infer_description_from_name

_DATA_FILE = pathlib.Path(__file__).parent / "data" / "env_patterns.json"
with open(_DATA_FILE, "r", encoding="utf-8") as _f:
    _PATTERNS_DATA = json.load(_f)

# Map file extensions → language key for pattern selection
_EXT_LANG = {
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".py": "python",
    ".go": "go",
    ".rs": "rust",
    ".java": "java", ".kt": "java",
    ".rb": "ruby",
    ".php": "php",
}


def extract_env_vars(files: list[pathlib.Path], project_root: pathlib.Path) -> list[dict]:
    """
    Scan all source files for environment variable references.

    Returns a list of dicts:
        [{'name': str, 'type': str, 'description': str, 'default': str, 'required': bool}]
    """
    found: dict[str, dict] = {}  # name → metadata

    # ── Pass 1: read .env.example for definitive list + defaults ──────────────
    _read_dotenv_example(project_root, found)

    # ── Pass 2: scan source files ──────────────────────────────────────────────
    for f in files:
        lang = _EXT_LANG.get(f.suffix.lower())
        if not lang:
            continue
        content = safe_read(f)
        if not content:
            continue
        _scan_file(content, lang, found)

    # ── Pass 3: enrich metadata ────────────────────────────────────────────────
    result = []
    for name, meta in sorted(found.items()):
        meta["type"] = meta.get("type") or infer_type_from_name(name, _PATTERNS_DATA)
        meta["description"] = meta.get("description") or infer_description_from_name(name, _PATTERNS_DATA)
        meta["default"] = meta.get("default", "")
        meta["required"] = not meta["default"]
        result.append(meta)

    return result


# ── Private helpers ────────────────────────────────────────────────────────────

def _read_dotenv_example(project_root: pathlib.Path, found: dict) -> None:
    """Parse .env.example / .env.sample for variable names, defaults, comments."""
    candidates = [".env.example", ".env.sample", ".env.template", ".env"]
    for fname in candidates:
        path = project_root / fname
        if not path.exists():
            continue
        content = safe_read(path)
        if not content:
            continue

        pending_comment = ""
        for line in content.splitlines():
            stripped = line.strip()
            # Capture inline or preceding comment as description
            if stripped.startswith("#"):
                pending_comment = stripped.lstrip("#").strip()
                continue
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", stripped)
            if m:
                name = m.group(1)
                default = m.group(2).strip().strip("'\"")
                entry = found.setdefault(name, {"name": name})
                if default:
                    entry.setdefault("default", default)
                if pending_comment:
                    entry.setdefault("description", pending_comment)
                pending_comment = ""
            else:
                pending_comment = ""
        break


def _scan_file(content: str, lang: str, found: dict) -> None:
    """Apply language-specific regex patterns to extract env var names."""
    lang_patterns = _PATTERNS_DATA["patterns"].get(lang, [])

    for pattern_def in lang_patterns:
        regex = pattern_def["regex"]
        group = pattern_def.get("group", 1)
        default_group = pattern_def.get("default_group")

        try:
            for m in re.finditer(regex, content, re.MULTILINE):
                name = m.group(group)
                if not name or not re.match(r"^[A-Z][A-Z0-9_]{0,50}$", name):
                    continue
                # Skip generic / template-like names
                if name in {"X", "VAR", "KEY", "VALUE", "ENV", "NAME"}:
                    continue

                entry = found.setdefault(name, {"name": name})
                # Try to extract default value if the pattern supports it
                if default_group:
                    try:
                        default_val = m.group(default_group)
                        if default_val:
                            entry.setdefault("default", default_val)
                    except IndexError:
                        pass
        except re.error:
            continue

    # Also handle JS/TS default extraction: process.env.X || 'default'
    if lang in ("javascript", "typescript"):
        for m in re.finditer(
            r"process\.env\.([A-Z][A-Z0-9_]*)\s*(?:\|\||\?\?)\s*['\"]([^'\"]+)['\"]",
            content,
        ):
            name, default = m.group(1), m.group(2)
            entry = found.setdefault(name, {"name": name})
            entry.setdefault("default", default)
