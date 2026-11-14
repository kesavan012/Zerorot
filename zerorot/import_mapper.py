"""
import_mapper.py — Build a module dependency graph from import statements.

Parses import/require declarations in source files to understand how the
codebase's internal modules relate to each other. This graph is consumed by
diagram_builder.py to generate the Mermaid architecture flowchart.
"""
import ast
import pathlib
import re
from collections import defaultdict
from typing import Optional

from .utils import safe_read, EXT_TO_LANG


def map_imports(files: list[pathlib.Path], project_root: pathlib.Path) -> dict:
    """
    Build an import graph for the project.

    Returns
    -------
    {
        'adjacency'   : dict[str, list[str]],  # module → [imported modules]
        'layers'      : dict[str, str],         # module → detected layer name
        'entry_points': list[str],              # modules with no inbound edges
    }
    """
    adjacency: dict[str, list[str]] = defaultdict(list)
    all_modules: set[str] = set()

    for f in files:
        lang = EXT_TO_LANG.get(f.suffix.lower())
        if not lang:
            continue
        content = safe_read(f)
        if not content:
            continue

        module_name = _file_to_module(f, project_root)
        all_modules.add(module_name)

        local_imports = []
        if lang == "python":
            local_imports = _extract_python_imports(content, f, project_root)
        elif lang in ("javascript", "typescript"):
            local_imports = _extract_js_imports(content, f, project_root)
        elif lang == "go":
            local_imports = _extract_go_imports(content, project_root)

        for imp in local_imports:
            if imp != module_name and imp not in adjacency[module_name]:
                adjacency[module_name].append(imp)
            all_modules.add(imp)

    # Detect entry points: modules with no inbound edges
    has_inbound: set[str] = set()
    for deps in adjacency.values():
        has_inbound.update(deps)
    entry_points = [m for m in all_modules if m not in has_inbound]

    # Assign layer labels based on folder name patterns
    layers = {m: _detect_layer(m) for m in all_modules}

    return {
        "adjacency": dict(adjacency),
        "layers": layers,
        "entry_points": entry_points,
    }


# ── Layer detection ────────────────────────────────────────────────────────────

LAYER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(routes?|controllers?|handlers?|endpoints?)\b", re.I), "api"),
    (re.compile(r"\b(services?|business|domain|core|use_?cases?)\b", re.I), "service"),
    (re.compile(r"\b(models?|entities?|schemas?|dto)\b", re.I), "model"),
    (re.compile(r"\b(db|database|repos?|repositories)\b", re.I), "data"),
    (re.compile(r"\b(middleware|guards?|interceptors?|filters?)\b", re.I), "middleware"),
    (re.compile(r"\b(workers?|tasks?|jobs?|queues?|consumers?)\b", re.I), "worker"),
    (re.compile(r"\b(utils?|helpers?|lib|shared|common)\b", re.I), "util"),
    (re.compile(r"\b(config|settings?|env)\b", re.I), "config"),
    (re.compile(r"\b(auth|security|jwt|oauth)\b", re.I), "auth"),
]


def _detect_layer(module_name: str) -> str:
    for pattern, layer in LAYER_PATTERNS:
        if pattern.search(module_name):
            return layer
    return "other"


# ── Module naming ──────────────────────────────────────────────────────────────

def _file_to_module(f: pathlib.Path, root: pathlib.Path) -> str:
    try:
        rel = f.relative_to(root)
        parts = list(rel.parts)
        # Drop extension from last part
        parts[-1] = rel.stem
        return "/".join(parts)
    except ValueError:
        return f.stem


# ── Python import parser ───────────────────────────────────────────────────────

def _extract_python_imports(content: str, current_file: pathlib.Path,
                            root: pathlib.Path) -> list[str]:
    local: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _extract_python_imports_regex(content, current_file, root)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level  # number of dots (relative import)
            if level > 0 or (module and not _is_stdlib_or_third_party(module)):
                resolved = _resolve_python_import(module, level, current_file, root)
                if resolved:
                    local.append(resolved)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_stdlib_or_third_party(alias.name):
                    local.append(alias.name.replace(".", "/"))
    return local


def _extract_python_imports_regex(content: str, current_file: pathlib.Path,
                                  root: pathlib.Path) -> list[str]:
    """Fallback regex-based Python import extraction."""
    local: list[str] = []
    for m in re.finditer(
        r"^(?:from\s+(\.+[\w.]*)\s+import|import\s+([\w.]+))", content, re.MULTILINE
    ):
        raw = m.group(1) or m.group(2) or ""
        if raw.startswith("."):
            # relative import — try to resolve
            resolved = _resolve_python_import(raw.lstrip("."), raw.count("."), current_file, root)
            if resolved:
                local.append(resolved)
    return local


def _resolve_python_import(module: str, level: int,
                            current_file: pathlib.Path, root: pathlib.Path) -> Optional[str]:
    if not module:
        return None
    parts = module.split(".")
    if level > 0:
        anchor = current_file.parent
        for _ in range(level - 1):
            anchor = anchor.parent
        try:
            rel = anchor.relative_to(root)
            return str(rel / "/".join(parts))
        except ValueError:
            return None
    return "/".join(parts)


def _is_stdlib_or_third_party(module: str) -> bool:
    """Heuristic: if first segment is a known stdlib module, skip it."""
    import sys
    first = module.split(".")[0]
    return first in sys.stdlib_module_names if hasattr(sys, "stdlib_module_names") else False


# ── JavaScript / TypeScript import parser ─────────────────────────────────────

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+|require\s*\(\s*)['\"](\.[^'"]+)['\"]""",
    re.MULTILINE,
)


def _extract_js_imports(content: str, current_file: pathlib.Path,
                         root: pathlib.Path) -> list[str]:
    local: list[str] = []
    for m in _JS_IMPORT_RE.finditer(content):
        raw = m.group(1)
        try:
            resolved = (current_file.parent / raw).resolve().relative_to(root)
            local.append(str(resolved.with_suffix("")).replace("\\", "/"))
        except (ValueError, OSError):
            continue
    return local


# ── Go import parser ───────────────────────────────────────────────────────────

def _extract_go_imports(content: str, root: pathlib.Path) -> list[str]:
    """Extract internal Go imports (those containing the module path)."""
    module_name = ""
    # Try to read go.mod for module name
    gomod = root / "go.mod"
    if gomod.exists():
        text = safe_read(gomod) or ""
        m = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
        if m:
            module_name = m.group(1)

    local: list[str] = []
    if not module_name:
        return local

    for m in re.finditer(r'"(' + re.escape(module_name) + r'/([^"]+))"', content):
        local.append(m.group(2))
    return local
