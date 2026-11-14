"""
utils.py — Shared utility helpers for ZeroRot.
"""
import pathlib
import re
from typing import Optional


# ── File-type helpers ──────────────────────────────────────────────────────────

BINARY_EXTENSIONS: set[str] = {
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    # Video / Audio
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav", ".ogg", ".flac",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    # Compiled
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo", ".class",
    ".jar", ".war", ".ear",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Documents
    ".pdf", ".docx", ".xlsx", ".pptx",
    # Databases
    ".db", ".sqlite", ".sqlite3",
    # Lock files (skip entirely)
    ".lock",
}

SKIP_FILENAMES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "Cargo.lock",
    "composer.lock",
    ".DS_Store",
    "Thumbs.db",
    ".gitkeep",
    ".npmignore",
}

SKIP_DIRS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "target", "vendor", "coverage",
    ".idea", ".vscode", ".mypy_cache", ".pytest_cache", ".tox", ".cache",
    "htmlcov", ".eggs", "site-packages", "out", "bin", "obj",
    ".gradle", ".mvn", "tmp", "temp", ".turbo", ".parcel-cache",
    "storybook-static", ".docusaurus", ".serverless",
}


def is_binary_file(path: pathlib.Path) -> bool:
    """Return True if the file is binary or should be skipped."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    if path.name in SKIP_FILENAMES:
        return True
    try:
        with open(path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


def safe_read(path: pathlib.Path, max_bytes: int = 200_000) -> Optional[str]:
    """Read a text file safely, returning None on any error."""
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return None
        # Try UTF-8 first, fall back to chardet, then latin-1
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            pass
        try:
            import chardet
            raw = path.read_bytes()
            detected = chardet.detect(raw)
            enc = detected.get("encoding") or "latin-1"
            return raw.decode(enc, errors="replace")
        except Exception:
            return path.read_text(encoding="latin-1", errors="replace")
    except (OSError, PermissionError):
        return None


# ── Name formatting helpers ────────────────────────────────────────────────────

def slugify(name: str) -> str:
    """Convert a project name to a human-readable title."""
    # Handle scoped packages: @org/name → name
    if "/" in name:
        name = name.split("/")[-1]
    # Replace separators with spaces
    name = re.sub(r"[-_.]", " ", name)
    return name.title()


def infer_type_from_name(var_name: str, patterns_data: dict) -> str:
    """Infer the variable's value type from its name."""
    upper = var_name.upper()
    hints = patterns_data.get("type_hints", {})
    if any(k in upper for k in hints.get("bool_keywords", [])):
        return "boolean"
    if any(k in upper for k in hints.get("int_keywords", [])):
        return "integer"
    if any(k in upper for k in hints.get("url_keywords", [])):
        return "string (URL)"
    if any(k in upper for k in hints.get("secret_keywords", [])):
        return "string (secret)"
    return "string"


def infer_description_from_name(var_name: str, patterns_data: dict) -> str:
    """Produce a human-readable description from the variable name."""
    desc_map = patterns_data.get("description_map", {})
    if var_name in desc_map:
        return desc_map[var_name]
    # Build generic description from name parts
    parts = re.sub(r"([A-Z])", r" \1", var_name).split("_")
    parts = [p.strip().capitalize() for p in parts if p.strip()]
    return " ".join(parts) if parts else var_name.replace("_", " ").capitalize()


# ── Language detection ─────────────────────────────────────────────────────────

LANG_TO_EXTENSIONS: dict[str, list[str]] = {
    "javascript": [".js", ".mjs", ".cjs", ".jsx"],
    "typescript": [".ts", ".tsx"],
    "python":     [".py"],
    "go":         [".go"],
    "rust":       [".rs"],
    "java":       [".java"],
    "kotlin":     [".kt"],
    "ruby":       [".rb"],
    "php":        [".php"],
    "csharp":     [".cs"],
    "cpp":        [".cpp", ".cc", ".cxx", ".h", ".hpp"],
    "c":          [".c", ".h"],
    "shell":      [".sh", ".bash"],
    "dart":       [".dart"],
    "swift":      [".swift"],
}

EXT_TO_LANG: dict[str, str] = {
    ext: lang
    for lang, exts in LANG_TO_EXTENSIONS.items()
    for ext in exts
}


def detect_lang_from_extension(ext: str) -> str:
    return EXT_TO_LANG.get(ext.lower(), "unknown")
