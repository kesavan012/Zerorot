"""
scanner.py — Directory tree walker for ZeroRot.

Recursively walks a project directory, skips junk folders and binary files,
and returns a structured file inventory plus a formatted ASCII tree string.
"""
import pathlib
from typing import Optional

from .utils import SKIP_DIRS, SKIP_FILENAMES, BINARY_EXTENSIONS, is_binary_file, safe_read


# ── Entry points by language ───────────────────────────────────────────────────

ENTRY_POINT_NAMES: set[str] = {
    # JavaScript / TypeScript
    "index.js", "index.ts", "main.js", "main.ts",
    "server.js", "server.ts", "app.js", "app.ts",
    # Python
    "main.py", "app.py", "server.py", "run.py", "manage.py", "wsgi.py", "asgi.py",
    # Go
    "main.go",
    # Rust
    "main.rs", "lib.rs",
    # Java / Kotlin
    "Application.java", "Main.java", "MainActivity.kt", "Application.kt",
    # Ruby
    "application.rb", "config.ru",
    # PHP
    "index.php", "app.php",
    # Flutter / Dart
    "main.dart", "app.dart",
    # Swift
    "AppDelegate.swift", "main.swift",
}

CONFIG_FILE_NAMES: set[str] = {
    ".env.example", ".env.sample", ".env.template",
    "config.py", "settings.py", "config.js", "config.ts",
    "tsconfig.json", "jest.config.js", "jest.config.ts",
    "vite.config.js", "vite.config.ts", "webpack.config.js",
    "docker-compose.yml", "docker-compose.yaml", "Dockerfile",
    "Makefile", ".github",
}

MAX_TREE_DEPTH = 6


def scan_directory(path: str, max_file_size_kb: int = 200) -> dict:
    """
    Walk *path* and collect all readable source files.

    Returns
    -------
    {
        'root'       : pathlib.Path,
        'files'      : list[pathlib.Path],          # all readable source files
        'entry_points': list[pathlib.Path],          # detected entry-point files
        'config_files': list[pathlib.Path],          # detected config files
        'tree_str'   : str,                          # ASCII directory tree
        'dir_summary': dict[str, int],               # folder → file count
    }
    """
    root = pathlib.Path(path).resolve()
    max_bytes = max_file_size_kb * 1024

    all_files: list[pathlib.Path] = []
    entry_points: list[pathlib.Path] = []
    config_files: list[pathlib.Path] = []
    dir_summary: dict[str, int] = {}
    tree_lines: list[str] = [f"{root.name}/"]

    def _walk(current: pathlib.Path, prefix: str, depth: int) -> None:
        if depth > MAX_TREE_DEPTH:
            return
        try:
            raw_entries = sorted(
                current.iterdir(),
                key=lambda x: (x.is_file(), x.name.lower()),
            )
        except PermissionError:
            return

        dirs = [
            e for e in raw_entries
            if e.is_dir()
            and e.name not in SKIP_DIRS
            and not e.name.startswith(".")
            or e.name in {".github", ".env"}
        ]
        dirs = [e for e in dirs if e.is_dir() and e.name not in SKIP_DIRS]

        readable: list[pathlib.Path] = []
        for e in raw_entries:
            if not e.is_file():
                continue
            if e.name in SKIP_FILENAMES:
                continue
            if e.suffix.lower() in BINARY_EXTENSIONS:
                continue
            try:
                if e.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue
            if is_binary_file(e):
                continue
            readable.append(e)
            all_files.append(e)

            if e.name in ENTRY_POINT_NAMES:
                entry_points.append(e)
            if e.name in CONFIG_FILE_NAMES:
                config_files.append(e)

        # Track files per directory
        rel_dir = str(current.relative_to(root))
        if readable:
            dir_summary[rel_dir] = len(readable)

        combined = dirs + readable
        for i, item in enumerate(combined):
            is_last = i == len(combined) - 1
            connector = "└── " if is_last else "├── "
            display = item.name + ("/" if item.is_dir() else "")
            tree_lines.append(f"{prefix}{connector}{display}")
            if item.is_dir():
                extension = "    " if is_last else "│   "
                _walk(item, prefix + extension, depth + 1)

    _walk(root, "", 0)

    return {
        "root": root,
        "files": all_files,
        "entry_points": entry_points,
        "config_files": config_files,
        "tree_str": "\n".join(tree_lines),
        "dir_summary": dir_summary,
    }


def select_core_files(scan_result: dict, max_files: int = 15) -> list[pathlib.Path]:
    """
    Select the most representative source files for analysis.

    Priority:
        1. Detected entry points
        2. Config / env files
        3. Files in api/, routes/, services/, models/ (by line count, descending)
        4. Remaining files by line count
    """
    files: list[pathlib.Path] = scan_result["files"]
    selected: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()

    def _add(f: pathlib.Path) -> None:
        if f not in seen and len(selected) < max_files:
            seen.add(f)
            selected.append(f)

    # Priority 1 & 2
    for f in scan_result["entry_points"]:
        _add(f)
    for f in scan_result["config_files"]:
        _add(f)

    # Priority 3 — important folders
    priority_dirs = {"api", "routes", "controllers", "services", "models",
                     "middleware", "handlers", "core", "workers", "tasks"}

    priority_files = [
        f for f in files
        if any(part in priority_dirs for part in f.parts)
        and f not in seen
    ]

    # Sort by line count (largest first — more logic = more important)
    def _line_count(f: pathlib.Path) -> int:
        try:
            content = safe_read(f)
            return len(content.splitlines()) if content else 0
        except Exception:
            return 0

    priority_files.sort(key=_line_count, reverse=True)
    for f in priority_files:
        _add(f)

    # Priority 4 — everything else by line count
    remaining = [f for f in files if f not in seen]
    remaining.sort(key=_line_count, reverse=True)
    for f in remaining:
        _add(f)

    return selected
