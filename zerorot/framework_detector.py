"""
framework_detector.py — Detects the primary framework and full tech stack.

Uses dependency names from the manifest and import patterns from source files
to identify the framework, databases, and auxiliary services in use.
"""
import json
import pathlib
import re
from typing import Optional

from .utils import safe_read

# Load signatures from data file
_DATA_FILE = pathlib.Path(__file__).parent / "data" / "framework_signatures.json"
with open(_DATA_FILE, "r", encoding="utf-8") as _f:
    _SIGS = json.load(_f)

FRAMEWORK_MAP: dict = _SIGS["frameworks"]
DATABASE_MAP: dict = _SIGS["databases"]
SERVICE_MAP: dict  = _SIGS["services"]
IMPORT_PATTERNS: dict = _SIGS["import_patterns"]

LANG_LABELS = {
    "javascript": "Node.js",
    "typescript": "TypeScript / Node.js",
    "python": "Python",
    "go": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "php": "PHP",
    "java": "Java",
    "kotlin": "Kotlin",
    "csharp": "C#",
}


def detect_framework(manifest_data: dict, files: list[pathlib.Path]) -> dict:
    """
    Detect the primary framework and build the full tech stack label list.

    Returns
    -------
    {
        'primary'     : {'label': str, 'type': str} | None,
        'databases'   : list[str],
        'services'    : list[str],
        'tech_stack'  : list[str],   # ordered for display
    }
    """
    all_deps = {
        **manifest_data.get("dependencies", {}),
        **manifest_data.get("dev_dependencies", {}),
    }
    dep_keys_lower = {k.lower() for k in all_deps}

    lang = manifest_data.get("lang", "unknown")

    primary_framework: Optional[dict] = None
    tech_stack: list[str] = []
    detected_dbs: list[str] = []
    detected_services: list[str] = []

    def _add_stack(label: str, container: Optional[list] = None) -> None:
        if label and label not in tech_stack:
            tech_stack.append(label)
        if container is not None and label and label not in container:
            container.append(label)

    # ── Step 1: language label first ──────────────────────────────────────────
    if lang in LANG_LABELS:
        _add_stack(LANG_LABELS[lang])

    # ── Step 2: match frameworks ───────────────────────────────────────────────
    for pkg_pattern, info in FRAMEWORK_MAP.items():
        if _dep_matches(pkg_pattern, dep_keys_lower):
            if primary_framework is None:
                primary_framework = info
            _add_stack(info["label"])

    # ── Step 3: match databases ────────────────────────────────────────────────
    for pkg_pattern, db_label in DATABASE_MAP.items():
        if _dep_matches(pkg_pattern, dep_keys_lower):
            _add_stack(db_label, detected_dbs)

    # ── Step 4: match services ─────────────────────────────────────────────────
    for pkg_pattern, svc_label in SERVICE_MAP.items():
        if _dep_matches(pkg_pattern, dep_keys_lower):
            _add_stack(svc_label, detected_services)

    # ── Step 5: fallback — scan source files for import patterns ──────────────
    if primary_framework is None:
        primary_framework = _scan_imports(files, lang)
        if primary_framework:
            _add_stack(primary_framework["label"])

    return {
        "primary": primary_framework or {"label": LANG_LABELS.get(lang, "Custom"), "type": "unknown"},
        "databases": detected_dbs,
        "services": detected_services,
        "tech_stack": tech_stack,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dep_matches(pattern: str, dep_keys: set[str]) -> bool:
    """Return True if pattern is a substring of (or equal to) any dep key."""
    pattern_lower = pattern.lower()
    return any(pattern_lower in dk or dk == pattern_lower for dk in dep_keys)


def _scan_imports(files: list[pathlib.Path], lang: str) -> Optional[dict]:
    """Scan entry-point-like source files for import statements."""
    ENTRY_NAMES = {
        "main.py", "app.py", "server.py",
        "index.js", "index.ts", "server.js", "server.ts", "app.js", "app.ts",
        "main.go", "main.rs",
    }
    patterns = IMPORT_PATTERNS.get(lang, []) + IMPORT_PATTERNS.get("javascript", [])

    for f in files:
        if f.name not in ENTRY_NAMES:
            continue
        content = safe_read(f)
        if not content:
            continue
        for regex, label in patterns:
            if re.search(regex, content, re.IGNORECASE | re.MULTILINE):
                return {"label": label, "type": "web"}
    return None
